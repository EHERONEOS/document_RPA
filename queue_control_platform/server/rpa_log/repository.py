"""数据访问层：执行记录 / 日志明细 / 记录文件 / 设备队列维表（设计文档 §4、§5）。

时间约定：对外字段一律 ``yyyy-MM-dd HH:mm:ss`` 字符串（§5.2，服务端格式化），
入库使用 MySQL DATETIME(3/6)。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from .db import db_cursor

_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def parse_datetime(value: str | datetime | None) -> datetime:
    """解析 Agent 上报的时间字符串；兼容空格 / T 分隔与毫秒，失败抛 ValueError。"""
    if value is None:
        return datetime.now()
    if isinstance(value, datetime):
        return value
    text = value.strip()
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"invalid datetime: {value!r}")


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 执行记录（rpa_execution）
# ---------------------------------------------------------------------------

def create_execution(
    *,
    rpa_message_id: str,
    queue_name: str,
    device_name: str,
    job_id: str = "",
    task_id: str = "",
    started_at: str | datetime | None = None,
    customer_code: str = "",
    carrier_code: str = "",
    business_code: str = "",
) -> int:
    """创建一条新的执行记录（每次消费独立成条，不按消息ID去重），顺带 upsert 设备与队列维表。

    2026-09 调整（用户决定）：取消 (rpa_message_id, queue_name) 唯一键——相同消息
    再次消费时插入新记录，各自持有独立的日志与终态；单条记录的 finish 幂等
    （ALREADY_FINISHED 拒绝）仍保留。
    """
    started = parse_datetime(started_at)
    now = datetime.now()  # 统一用服务端应用时钟：MySQL 容器可能是 UTC，NOW() 会差时区
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO rpa_execution
                (rpa_message_id, job_id, queue_name, device_name, task_id,
                 customer_code, carrier_code, business_code, status, started_at,
                 create_time, update_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'RUNNING', %s, %s, %s)
            """,
            (rpa_message_id, job_id, queue_name, device_name, task_id,
             customer_code, carrier_code, business_code, started, now, now),
        )
        execution_id = int(cur.lastrowid)

        # 维表 upsert：无需注册流程（§4.4）
        cur.execute(
            """
            INSERT INTO rpa_device (device_name, last_seen_at, create_time, update_time)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE last_seen_at = VALUES(last_seen_at), update_time = VALUES(update_time)
            """,
            (device_name, now, now, now),
        )
        cur.execute(
            """
            INSERT INTO rpa_queue
                (queue_name, customer_code, carrier_code, business_code, create_time, update_time)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                customer_code = VALUES(customer_code),
                carrier_code  = VALUES(carrier_code),
                business_code = VALUES(business_code),
                update_time   = VALUES(update_time)
            """,
            (queue_name, customer_code, carrier_code, business_code, now, now),
        )
    return execution_id


# ---------------------------------------------------------------------------
# 日志明细（rpa_execution_log）
# ---------------------------------------------------------------------------

def add_logs(execution_id: int, logs: Iterable[dict]) -> int:
    """批量追加日志并累加冗余计数；允许乱序到达（§9.2，展示按 seq DESC）。"""
    rows = [
        (
            execution_id,
            int(item["seq"]),
            str(item.get("level", "INFO")).upper(),
            item["message"],
            item.get("source_file", "") or "",
            int(item.get("source_line", 0) or 0),
            parse_datetime(item.get("log_time")),
        )
        for item in logs
    ]
    if not rows:
        return 0
    now = datetime.now()
    with db_cursor() as cur:
        cur.executemany(
            """
            INSERT INTO rpa_execution_log
                (execution_id, seq, level, message, source_file, source_line, log_time, create_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [row + (now,) for row in rows],
        )
        cur.execute(
            "UPDATE rpa_execution SET log_count = log_count + %s, update_time = %s WHERE id = %s",
            (len(rows), now, execution_id),
        )
    return len(rows)


# ---------------------------------------------------------------------------
# 终态（finish）
# ---------------------------------------------------------------------------

def finish_execution(
    *,
    execution_id: int,
    status: str,
    remark: str = "",
    fail_img_url: str = "",
    record_files: Iterable[dict] = (),
    finished_at: str | datetime | None = None,
    duration_seconds: int | None = None,
) -> dict[str, Any]:
    """写入终态；已终态/不存在的记录拒绝（§9.2 幂等，以首次为准）。

    返回 {"result": FINISHED | ALREADY_FINISHED | NOT_FOUND, ...}。
    """
    finished = parse_datetime(finished_at)
    files = [
        (
            execution_id,
            item.get("type", ""),
            item.get("media_type", "IMAGE"),
            item.get("file_name", ""),
            item.get("url", ""),
            item.get("storage", "OSS"),
            int(item.get("file_size", 0) or 0),
        )
        for item in record_files
    ]
    with db_cursor() as cur:
        cur.execute("SELECT id, status, started_at FROM rpa_execution WHERE id = %s", (execution_id,))
        row = cur.fetchone()
        if row is None:
            return {"result": "NOT_FOUND"}
        if row["status"] != "RUNNING":
            return {"result": "ALREADY_FINISHED", "status": row["status"]}
        if duration_seconds is None:
            duration_seconds = max(0, int((finished - row["started_at"]).total_seconds()))
        cur.execute(
            """
            UPDATE rpa_execution
            SET status = %s, remark = %s, fail_img_url = %s,
                finished_at = %s, duration_seconds = %s, update_time = %s
            WHERE id = %s AND status = 'RUNNING'
            """,
            (status, remark or None, fail_img_url or "", finished, int(duration_seconds), datetime.now(), execution_id),
        )
        if cur.rowcount == 0:  # 并发下被抢先 finish
            return {"result": "ALREADY_FINISHED"}
        cur.executemany(
            """
            INSERT INTO rpa_execution_file
                (execution_id, file_type, media_type, file_name, url, storage, file_size, create_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [file_row + (datetime.now(),) for file_row in files],
        )
    return {"result": "FINISHED", "status": status, "durationSeconds": int(duration_seconds)}


# ---------------------------------------------------------------------------
# 查询（§5.2；M0 先落列表骨架，detail/devices/queues/stats 由 T1.4 补齐）
# ---------------------------------------------------------------------------

def list_executions(
    *,
    rpa_message_id: str | None = None,
    job_id: str | None = None,
    queue_name: str | None = None,
    device_name: str | None = None,
    status: str | None = None,
    begin_time: str | None = None,
    end_time: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    conditions: list[str] = []
    params: list[Any] = []
    if rpa_message_id:
        conditions.append("rpa_message_id LIKE %s")  # 后缀模糊
        params.append(f"%{rpa_message_id}")
    if job_id:
        conditions.append("job_id LIKE %s")
        params.append(f"%{job_id}")
    if queue_name:
        conditions.append("queue_name = %s")  # 精确
        params.append(queue_name)
    if device_name:
        conditions.append("device_name = %s")  # 精确（设备页下钻，§8.3）
        params.append(device_name)
    if status:
        conditions.append("status = %s")  # 精确
        params.append(status)
    if begin_time:
        conditions.append("create_time >= %s")
        params.append(parse_datetime(begin_time))
    if end_time:
        conditions.append("create_time < %s")
        params.append(parse_datetime(end_time))
    where_sql = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    page = max(1, int(page))
    page_size = min(max(1, int(page_size)), 100)
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM rpa_execution" + where_sql, params)
        total = int(cur.fetchone()["total"])
        cur.execute(
            "SELECT * FROM rpa_execution" + where_sql + " ORDER BY id DESC LIMIT %s OFFSET %s",
            [*params, page_size, (page - 1) * page_size],
        )
        rows = [_format_execution_row(r) for r in cur.fetchall()]
    return {"total": total, "page": page, "pageSize": page_size, "list": rows}


def _format_execution_row(row: dict) -> dict:
    return {
        "executionId": int(row["id"]),
        "rpaMessageId": row["rpa_message_id"],
        "jobId": row["job_id"],
        "queueName": row["queue_name"],
        "deviceName": row["device_name"],
        "taskId": row["task_id"],
        "customerCode": row["customer_code"],
        "carrierCode": row["carrier_code"],
        "businessCode": row["business_code"],
        "status": row["status"],
        "remark": row["remark"],
        "failImgUrl": row["fail_img_url"],
        "logCount": int(row["log_count"]),
        "startedAt": format_datetime(row["started_at"]),
        "finishedAt": format_datetime(row["finished_at"]),
        "durationSeconds": None if row["duration_seconds"] is None else int(row["duration_seconds"]),
        "createTime": format_datetime(row["create_time"]),
    }


def get_execution(execution_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM rpa_execution WHERE id = %s", (execution_id,))
        row = cur.fetchone()
        return _format_execution_row(row) if row else None


def list_logs(execution_id: int) -> list[dict]:
    """日志明细：seq DESC 从新到旧（§4.2 / §8.2）。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT seq, level, message, source_file, source_line, log_time
            FROM rpa_execution_log
            WHERE execution_id = %s
            ORDER BY seq DESC, id DESC
            """,
            (execution_id,),
        )
        return [
            {
                "seq": int(row["seq"]),
                "level": row["level"],
                "message": row["message"],
                "sourceFile": row["source_file"],
                "sourceLine": int(row["source_line"]),
                "logTime": format_datetime(row["log_time"]),
            }
            for row in cur.fetchall()
        ]


def list_files(execution_id: int) -> list[dict]:
    """记录文件列表（记录文件弹窗数据源，§4.3）。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, file_type, media_type, file_name, url, storage, file_size, create_time
            FROM rpa_execution_file
            WHERE execution_id = %s
            ORDER BY id
            """,
            (execution_id,),
        )
        return [
            {
                "fileId": int(row["id"]),
                "type": row["file_type"],
                "mediaType": row["media_type"],
                "fileName": row["file_name"],
                "url": row["url"],
                "storage": row["storage"],
                "fileSize": int(row["file_size"]),
                "createTime": format_datetime(row["create_time"]),
            }
            for row in cur.fetchall()
        ]


# ---------------------------------------------------------------------------
# 维表统计（§5.2 / §8.3：今日执行、成功率、平均耗时）
# ---------------------------------------------------------------------------

_ONLINE_WINDOW = timedelta(minutes=5)  # 最近 5 分钟有心跳视为在线


def _success_rate(success: int | None, failed: int | None) -> float | None:
    total = int(success or 0) + int(failed or 0)
    if total <= 0:
        return None
    return round(int(success or 0) / total * 100, 1)  # 百分制，一位小数


def list_device_stats(today_start: datetime) -> list[dict]:
    """设备列表 + 统计：今日执行 / 成功率 / 绑定队列数 / 最近心跳 / 在线状态。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT d.device_name, d.os_info, d.last_seen_at,
                   COUNT(e.id)                            AS today_total,
               SUM(e.status = 'SUCCESS')               AS today_success,
               SUM(e.status IN ('FAILED', 'TIMEOUT'))  AS today_failed,
               COUNT(DISTINCT e.queue_name)            AS queue_count
            FROM rpa_device d
            LEFT JOIN rpa_execution e
                   ON e.device_name = d.device_name AND e.create_time >= %s
            GROUP BY d.device_name, d.os_info, d.last_seen_at
            ORDER BY d.last_seen_at DESC
            """,
            (today_start,),
        )
        now = datetime.now()
        return [
            {
                "deviceName": row["device_name"],
                "osInfo": row["os_info"],
                "boundQueueCount": int(row["queue_count"] or 0),
                "todayCount": int(row["today_total"] or 0),
                "successRate": _success_rate(row["today_success"], row["today_failed"]),
                "lastSeenAt": format_datetime(row["last_seen_at"]),
                "online": bool(row["last_seen_at"]) and now - row["last_seen_at"] <= _ONLINE_WINDOW,
            }
            for row in cur.fetchall()
        ]


def list_queue_stats(today_start: datetime) -> list[dict]:
    """队列列表 + 统计：今日执行 / 成功率 / 平均耗时（终态行）。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT q.queue_name, q.customer_code, q.carrier_code, q.business_code,
                   COUNT(e.id)                           AS today_total,
               SUM(e.status = 'SUCCESS')            AS today_success,
               SUM(e.status IN ('FAILED', 'TIMEOUT')) AS today_failed,
               AVG(CASE WHEN e.status IN ('SUCCESS', 'FAILED', 'TIMEOUT')
                        THEN e.duration_seconds END)   AS avg_duration
            FROM rpa_queue q
            LEFT JOIN rpa_execution e
                   ON e.queue_name = q.queue_name AND e.create_time >= %s
            GROUP BY q.queue_name, q.customer_code, q.carrier_code, q.business_code
            ORDER BY today_total DESC, q.queue_name
            """,
            (today_start,),
        )
        rows = []
        for row in cur.fetchall():
            avg_duration = row["avg_duration"]
            rows.append(
                {
                    "queueName": row["queue_name"],
                    "customerCode": row["customer_code"],
                    "carrierCode": row["carrier_code"],
                    "businessCode": row["business_code"],
                    "todayCount": int(row["today_total"] or 0),
                    "successRate": _success_rate(row["today_success"], row["today_failed"]),
                    "avgDurationSeconds": None if avg_duration is None else int(round(float(avg_duration))),
                }
            )
        return rows


def stats_summary(today_start: datetime) -> dict:
    """首页统计卡：今日总数 / 成功 / 失败（含 TIMEOUT，页面同为红色）/ 运行中。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)                            AS today_total,
               COALESCE(SUM(status = 'SUCCESS'), 0)    AS success_count,
               COALESCE(SUM(status IN ('FAILED', 'TIMEOUT')), 0) AS failed_count,
               COALESCE(SUM(status = 'RUNNING'), 0)    AS running_count
            FROM rpa_execution
            WHERE create_time >= %s
            """,
            (today_start,),
        )
        row = cur.fetchone()
        return {
            "todayTotal": int(row["today_total"] or 0),
            "successCount": int(row["success_count"] or 0),
            "failedCount": int(row["failed_count"] or 0),
            "runningCount": int(row["running_count"] or 0),
        }

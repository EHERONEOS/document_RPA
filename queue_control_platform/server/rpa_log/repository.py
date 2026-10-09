"""数据访问层：执行记录 / 日志明细 / 记录文件（设计文档 §4、§5；2026-10 起设备/队列统计由本模块聚合推导）。

时间约定：对外字段一律 ``yyyy-MM-dd HH:mm:ss`` 字符串（§5.2，服务端格式化），
入库使用 MySQL DATETIME(3/6)。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from .db import db_cursor, db_transaction

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
    """创建一条新的执行记录（每次消费独立成条，不按消息ID去重）。

    2026-09 调整（用户决定）：取消 (rpa_message_id, queue_name) 唯一键——相同消息
    再次消费时插入新记录，各自持有独立的日志与终态；单条记录的 finish 幂等
    （ALREADY_FINISHED 拒绝）仍保留。

    2026-09 调整：相同消息ID重新生成记录时，把其他 RUNNING 记录置为 DEPRECATED，
    保证同一消息同一时刻只有最新一条 RUNNING。

    2026-10 调整：设备/队列维表已删除，统计页改由本表聚合推导
    （见 list_device_stats / list_queue_stats），上报时不再维护维表。
    """
    started = parse_datetime(started_at)
    now = datetime.now()  # 统一用服务端应用时钟：MySQL 容器可能是 UTC，NOW() 会差时区
    with db_transaction() as cur:
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

        # 同一消息重新消费时，保留最新 RUNNING 记录；旧的运行中记录统一废弃。
        deprecated_at = datetime.now()
        cur.execute(
            """
            UPDATE rpa_execution
            SET status = 'DEPRECATED',
                finished_at = %s,
                duration_seconds = GREATEST(0, TIMESTAMPDIFF(SECOND, started_at, %s)),
                update_time = %s
            WHERE rpa_message_id = %s AND id <> %s AND status = 'RUNNING'
            """,
            (deprecated_at, deprecated_at, deprecated_at, rpa_message_id, execution_id),
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


def delete_executions(execution_ids: list[int]) -> dict[str, int]:
    """批量删除执行记录，并在同一事务中级联删除日志明细与记录文件。"""
    ids = list(dict.fromkeys(int(execution_id) for execution_id in execution_ids if int(execution_id) > 0))
    if not ids:
        return {"requested": 0, "deleted": 0, "deletedLogCount": 0, "deletedFileCount": 0}
    placeholders = ", ".join(["%s"] * len(ids))
    with db_transaction() as cur:
        cur.execute(f"SELECT id FROM rpa_execution WHERE id IN ({placeholders}) FOR UPDATE", ids)
        rows = cur.fetchall()
        cur.execute(
            f"SELECT COUNT(*) AS log_count FROM rpa_execution_log WHERE execution_id IN ({placeholders})",
            ids,
        )
        deleted_log_count = int(cur.fetchone()["log_count"])
        cur.execute(
            f"SELECT COUNT(*) AS file_count FROM rpa_execution_file WHERE execution_id IN ({placeholders})",
            ids,
        )
        deleted_file_count = int(cur.fetchone()["file_count"])
        cur.execute(f"DELETE FROM rpa_execution_log WHERE execution_id IN ({placeholders})", ids)
        cur.execute(f"DELETE FROM rpa_execution_file WHERE execution_id IN ({placeholders})", ids)
        cur.execute(f"DELETE FROM rpa_execution WHERE id IN ({placeholders})", ids)
        deleted_count = int(cur.rowcount)
    return {
        "requested": len(ids),
        "deleted": deleted_count,
        "deletedLogCount": deleted_log_count,
        "deletedFileCount": deleted_file_count,
    }


# ---------------------------------------------------------------------------
# 终态（finish）
# ---------------------------------------------------------------------------

def finish_execution(
    *,
    execution_id: int,
    status: str,
    remark: str = "",
    fail_img_url: str = "",
    fail_img_object_name: str = "",
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
            item.get("url", "") or "",
            item.get("object_name", "") or "",
            item.get("remark", "") or "",
            item.get("storage", "OSS") or "OSS",
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
            SET status = %s, remark = %s, fail_img_url = %s, fail_img_object_name = %s,
                finished_at = %s, duration_seconds = %s, update_time = %s
            WHERE id = %s AND status = 'RUNNING'
            """,
            (status, remark or None, fail_img_url or "", fail_img_object_name or "", finished,
             int(duration_seconds), datetime.now(), execution_id),
        )
        if cur.rowcount == 0:  # 并发下被抢先 finish
            return {"result": "ALREADY_FINISHED"}
        if files:
            cur.executemany(
                """
                INSERT INTO rpa_execution_file
                    (execution_id, file_type, media_type, file_name, url, object_name, remark, storage, file_size, create_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        "failImgObjectName": row["fail_img_object_name"] or "",
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
            SELECT id, file_type, media_type, file_name, url, object_name, remark, storage, file_size, create_time
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
                "url": row["url"] or "",
                "objectName": row["object_name"] or "",
                "remark": row["remark"] or "",
                "storage": row["storage"],
                "fileSize": int(row["file_size"]),
                "createTime": format_datetime(row["create_time"]),
            }
            for row in cur.fetchall()
        ]


# ---------------------------------------------------------------------------
# 维表统计（§5.2 / §8.3：今日执行、成功率、平均耗时）
# 2026-10 起 rpa_device / rpa_queue 维表删除，统计直接从 rpa_execution 聚合推导。
# ---------------------------------------------------------------------------

_ONLINE_WINDOW = timedelta(minutes=5)  # 最近 5 分钟有执行活动视为在线


def _success_rate(success: int | None, failed: int | None) -> float | None:
    total = int(success or 0) + int(failed or 0)
    if total <= 0:
        return None
    return round(int(success or 0) / total * 100, 1)  # 百分制，一位小数


def list_device_stats(today_start: datetime) -> list[dict]:
    """设备列表 + 统计：今日执行 / 成功率 / 队列数 / 最近活动 / 在线状态。

    设备清单 = 历史上报过执行记录的 device_name（等价于原 rpa_device 维表的 upsert 结果）；
    lastSeenAt = 最近一次执行记录创建时间（原维表 last_seen_at 同口径）。
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT device_name,
                   MAX(create_time) AS last_seen_at,
                   SUM(create_time >= %s) AS today_total,
                   SUM(create_time >= %s AND status = 'SUCCESS') AS today_success,
                   SUM(create_time >= %s AND status IN ('FAILED', 'TIMEOUT')) AS today_failed,
                   COUNT(DISTINCT CASE WHEN create_time >= %s THEN queue_name END) AS queue_count
            FROM rpa_execution
            GROUP BY device_name
            ORDER BY last_seen_at DESC
            """,
            (today_start, today_start, today_start, today_start),
        )
        now = datetime.now()
        return [
            {
                "deviceName": row["device_name"],
                "osInfo": "",  # 原维表 os_info 从未实际写入，保留字段兼容前端
                "boundQueueCount": int(row["queue_count"] or 0),
                "todayCount": int(row["today_total"] or 0),
                "successRate": _success_rate(row["today_success"], row["today_failed"]),
                "lastSeenAt": format_datetime(row["last_seen_at"]),
                "online": bool(row["last_seen_at"]) and now - row["last_seen_at"] <= _ONLINE_WINDOW,
            }
            for row in cur.fetchall()
        ]


def list_queue_stats(today_start: datetime) -> list[dict]:
    """队列列表 + 统计：今日执行 / 成功率 / 平均耗时（今日终态行）。

    三段业务编码取该队列执行记录的 MAX（编码由队列名确定性解析，同队列恒定）。
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT queue_name,
                   MAX(customer_code) AS customer_code,
                   MAX(carrier_code) AS carrier_code,
                   MAX(business_code) AS business_code,
                   SUM(create_time >= %s) AS today_total,
                   SUM(create_time >= %s AND status = 'SUCCESS') AS today_success,
                   SUM(create_time >= %s AND status IN ('FAILED', 'TIMEOUT')) AS today_failed,
                   AVG(CASE WHEN create_time >= %s AND status IN ('SUCCESS', 'FAILED', 'TIMEOUT')
                            THEN duration_seconds END) AS avg_duration
            FROM rpa_execution
            GROUP BY queue_name
            ORDER BY today_total DESC, queue_name
            """,
            (today_start, today_start, today_start, today_start),
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

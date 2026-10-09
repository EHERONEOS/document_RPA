"""队列控制平台的 MySQL 持久化实现。"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from urllib.parse import unquote, urlparse


def _utcnow() -> datetime:
    """返回不带本地时区偏移的 UTC 时间，便于写入 MySQL DATETIME。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize(value: Any) -> str:
    """将事件中的结构化字段编码为 MySQL JSON 字符串。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _as_json(value: str | None) -> Any:
    """将 MySQL 返回的 JSON 文本还原为 Python 对象。"""
    if not value:
        return []
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


def _as_iso(value: datetime | None) -> str | None:
    """将数据库时间转换为 API 使用的 ISO 字符串。"""
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


class MySQLControlRepository:
    """保存设备、队列分配（含观测状态）、命令和事件流水。"""

    # 保存 MySQL 连接地址，连接在实际查询时按需创建。
    def __init__(self, mysql_url: str):
        self.mysql_url = mysql_url

    # 解析 MySQL URL 并创建一个字典行格式的数据库连接。
    def _connect(self):
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("缺少 PyMySQL，请执行 uv sync 安装依赖") from exc

        parsed = urlparse(self.mysql_url)
        if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname:
            raise RuntimeError("QUEUE_CONTROL_MYSQL_URL 必须是 mysql://user:password@host:port/database")
        database = parsed.path.lstrip("/")
        if not database:
            raise RuntimeError("QUEUE_CONTROL_MYSQL_URL 缺少数据库名称")
        return pymysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    @contextmanager
    # 提供带提交、回滚和关闭保障的数据库事务。
    def _transaction(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # 2026-10 表结构精简：queue_statuses 的观测列并入 queue_assignments，
    # 一行一个队列同时持有"中心意图（desired_state）"与"设备观测值（actual_*）"。
    # JSON 列无法设字面量默认值，观测列全部可空，由应用层保证语义。
    _REPORTED_COLUMNS: tuple[tuple[str, str], ...] = (
        ("actual_state", "ALTER TABLE queue_assignments ADD COLUMN actual_state VARCHAR(32) NOT NULL DEFAULT 'UNREPORTED' AFTER assignment_version"),
        ("process_id", "ALTER TABLE queue_assignments ADD COLUMN process_id BIGINT NULL AFTER actual_state"),
        ("started_at", "ALTER TABLE queue_assignments ADD COLUMN started_at DATETIME(6) NULL AFTER process_id"),
        ("stopped_at", "ALTER TABLE queue_assignments ADD COLUMN stopped_at DATETIME(6) NULL AFTER started_at"),
        ("last_error", "ALTER TABLE queue_assignments ADD COLUMN last_error TEXT NULL AFTER stopped_at"),
        ("restart_reason", "ALTER TABLE queue_assignments ADD COLUMN restart_reason JSON NULL AFTER last_error"),
        ("observed_at", "ALTER TABLE queue_assignments ADD COLUMN observed_at DATETIME(6) NULL AFTER restart_reason"),
    )

    # 创建平台所需全部表和索引，可重复安全执行。
    def initialize_schema(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id VARCHAR(128) PRIMARY KEY,
                display_name VARCHAR(255) NOT NULL,
                token_hash CHAR(64) NOT NULL,
                token VARCHAR(128) NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'OFFLINE',
                last_seen_at DATETIME(6) NULL,
                created_at DATETIME(6) NOT NULL,
                updated_at DATETIME(6) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS queue_assignments (
                queue_name VARCHAR(255) PRIMARY KEY,
                device_id VARCHAR(128) NOT NULL,
                desired_state VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
                assignment_version BIGINT NOT NULL DEFAULT 1,
                actual_state VARCHAR(32) NOT NULL DEFAULT 'UNREPORTED',
                process_id BIGINT NULL,
                started_at DATETIME(6) NULL,
                stopped_at DATETIME(6) NULL,
                last_error TEXT NULL,
                restart_reason JSON NULL,
                observed_at DATETIME(6) NULL,
                created_at DATETIME(6) NOT NULL,
                updated_at DATETIME(6) NOT NULL,
                CONSTRAINT fk_assignment_device FOREIGN KEY (device_id)
                    REFERENCES devices(device_id) ON DELETE CASCADE,
                INDEX idx_assignment_device (device_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS queue_commands (
                command_id CHAR(36) PRIMARY KEY,
                device_id VARCHAR(128) NOT NULL,
                queue_name VARCHAR(255) NULL,
                action VARCHAR(32) NOT NULL,
                force_restart BOOLEAN NOT NULL DEFAULT FALSE,
                state VARCHAR(32) NOT NULL,
                error_message TEXT NOT NULL,
                payload JSON NOT NULL,
                created_at DATETIME(6) NOT NULL,
                acknowledged_at DATETIME(6) NULL,
                CONSTRAINT fk_command_device FOREIGN KEY (device_id)
                    REFERENCES devices(device_id) ON DELETE CASCADE,
                INDEX idx_command_device_created (device_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS queue_events (
                event_id VARCHAR(128) PRIMARY KEY,
                device_id VARCHAR(128) NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                payload JSON NOT NULL,
                received_at DATETIME(6) NOT NULL,
                INDEX idx_event_device_received (device_id, received_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        )
        with self._transaction() as cursor:
            for statement in statements:
                cursor.execute(statement)
            self._ensure_device_token_column(cursor)
            self._merge_legacy_queue_statuses(cursor)

    # 2026-10 新增：设备令牌明文列（用户选择"可随时查看"，替代仅创建时展示一次）。
    # 旧库启动时自动补列；历史设备的明文为空（哈希不可逆），可通过重置令牌补齐。
    _DEVICE_TOKEN_COLUMN: tuple[tuple[str, str], ...] = (
        ("token", "ALTER TABLE devices ADD COLUMN token VARCHAR(128) NULL AFTER token_hash"),
    )

    # 旧库迁移：devices 补明文令牌列（幂等）。
    def _ensure_device_token_column(self, cursor) -> None:
        existing = self._existing_columns(cursor, "devices")
        for column, ddl in self._DEVICE_TOKEN_COLUMN:
            if column.lower() not in existing:
                cursor.execute(ddl)

    # 旧库迁移：存量 queue_assignments 补观测列；queue_statuses 搬数据后删除（幂等）。
    def _merge_legacy_queue_statuses(self, cursor) -> None:
        existing = self._existing_columns(cursor, "queue_assignments")
        for column, ddl in self._REPORTED_COLUMNS:
            if column.lower() not in existing:
                cursor.execute(ddl)
        if not self._table_exists(cursor, "queue_statuses"):
            return
        cursor.execute(
            """
            UPDATE queue_assignments a
            JOIN queue_statuses s
              ON s.device_id = a.device_id AND s.queue_name = a.queue_name
            SET a.actual_state = s.actual_state,
                a.process_id = s.process_id,
                a.started_at = s.started_at,
                a.stopped_at = s.stopped_at,
                a.last_error = s.last_error,
                a.restart_reason = s.restart_reason,
                a.observed_at = s.observed_at
            """
        )
        cursor.execute("DROP TABLE queue_statuses")

    # 查表已存在的列名集合（小写），用于幂等补列。
    @staticmethod
    def _existing_columns(cursor, table: str) -> set[str]:
        cursor.execute(
            """
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table,),
        )
        return {
            str(row.get("COLUMN_NAME") or row.get("column_name") or list(row.values())[0]).lower()
            for row in cursor.fetchall()
        }

    # 判断当前库是否存在指定表。
    @staticmethod
    def _table_exists(cursor, table: str) -> bool:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            LIMIT 1
            """,
            (table,),
        )
        return cursor.fetchone() is not None

    # 创建一个可在页面上管理的设备，并返回仅显示一次的注册令牌。
    def create_device(self, device_id: str, display_name: str) -> dict[str, str]:
        normalized_id = self._normalize_device_id(device_id)
        if not display_name.strip():
            raise ValueError("设备名称不能为空")
        token = secrets.token_urlsafe(32)
        now = _utcnow()
        try:
            with self._transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO devices
                    (device_id, display_name, token_hash, token, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'OFFLINE', %s, %s)
                    """,
                    (normalized_id, display_name.strip(), self._hash_token(token), token, now, now),
                )
        except Exception as exc:
            if "Duplicate entry" in str(exc):
                raise ValueError(f"设备 ID 已存在：{normalized_id}") from exc
            raise
        return {"deviceId": normalized_id, "enrollmentToken": token}

    # 修改设备 ID 与名称：同一事务内显式同步子表 device_id（外键无 ON UPDATE，
    # 且经旧结构迁移的库可能缺失外键），注册令牌保持不变。
    def update_device(self, device_id: str, new_device_id: str, display_name: str) -> dict[str, Any]:
        normalized_old = self._normalize_device_id(device_id)
        normalized_new = self._normalize_device_id(new_device_id)
        normalized_name = display_name.strip()
        if not normalized_name:
            raise ValueError("设备名称不能为空")
        try:
            with self._transaction() as cursor:
                self._require_device(cursor, normalized_old)
                if normalized_new != normalized_old:
                    cursor.execute(
                        "SELECT 1 FROM devices WHERE device_id = %s", (normalized_new,)
                    )
                    if cursor.fetchone() is not None:
                        raise ValueError(f"设备 ID 已存在：{normalized_new}")
                    # 子表在前、主表在后；外键检查临时关闭，事务提交时数据已一致。
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                    for table in ("queue_assignments", "queue_commands", "queue_events"):
                        cursor.execute(
                            f"UPDATE {table} SET device_id = %s WHERE device_id = %s",
                            (normalized_new, normalized_old),
                        )
                    cursor.execute(
                        "UPDATE devices SET device_id = %s WHERE device_id = %s",
                        (normalized_new, normalized_old),
                    )
                cursor.execute(
                    """
                    UPDATE devices SET display_name = %s, updated_at = %s
                    WHERE device_id = %s
                    """,
                    (normalized_name, _utcnow(), normalized_new),
                )
        except Exception as exc:
            if "Duplicate entry" in str(exc):
                raise ValueError(f"设备 ID 已存在：{normalized_new}") from exc
            raise
        return {"deviceId": normalized_new, "displayName": normalized_name}

    # 返回设备明文令牌；明文启用前的历史设备（且未重置过）返回 None。
    def get_device_token(self, device_id: str) -> dict[str, str | None]:
        normalized_id = self._normalize_device_id(device_id)
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT token FROM devices WHERE device_id = %s", (normalized_id,)
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError(f"未注册设备：{normalized_id}")
        return {"deviceId": normalized_id, "enrollmentToken": row["token"] or None}

    # 重置设备令牌：哈希与明文一并更新，旧令牌立即失效。
    def reset_device_token(self, device_id: str) -> dict[str, str]:
        normalized_id = self._normalize_device_id(device_id)
        token = secrets.token_urlsafe(32)
        with self._transaction() as cursor:
            self._require_device(cursor, normalized_id)
            cursor.execute(
                """
                UPDATE devices SET token_hash = %s, token = %s, updated_at = %s
                WHERE device_id = %s
                """,
                (self._hash_token(token), token, _utcnow(), normalized_id),
            )
        return {"deviceId": normalized_id, "enrollmentToken": token}

    # 删除设备及其全部运行数据（绑定、命令、事件流水）；
    # 返回删除前绑定的队列名，供调用方向 Agent 投递停止监听命令。
    # 子表显式删除而非依赖外键级联：经旧结构迁移的库可能缺失 FK 约束。
    def delete_device(self, device_id: str) -> list[str]:
        normalized_id = self._normalize_device_id(device_id)
        with self._transaction() as cursor:
            self._require_device(cursor, normalized_id)
            cursor.execute(
                "SELECT queue_name FROM queue_assignments WHERE device_id = %s ORDER BY queue_name",
                (normalized_id,),
            )
            queue_names = [row["queue_name"] for row in cursor.fetchall()]
            for table in ("queue_assignments", "queue_commands", "queue_events"):
                cursor.execute(
                    f"DELETE FROM {table} WHERE device_id = %s", (normalized_id,)
                )
            cursor.execute("DELETE FROM devices WHERE device_id = %s", (normalized_id,))
        return queue_names

    # 返回设备及其最后心跳，供维护页面展示。
    def list_devices(self) -> list[dict[str, Any]]:
        with self._transaction() as cursor:
            cursor.execute(
                """
                UPDATE devices SET status = 'OFFLINE', updated_at = %s
                WHERE status = 'ONLINE' AND last_seen_at < %s
                """,
                (_utcnow(), _utcnow() - timedelta(seconds=45)),
            )
            cursor.execute(
                """
                SELECT device_id, display_name, status, last_seen_at, created_at
                FROM devices ORDER BY device_id
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "deviceId": row["device_id"],
                "displayName": row["display_name"],
                "status": row["status"],
                "lastSeenAt": _as_iso(row["last_seen_at"]),
                "createdAt": _as_iso(row["created_at"]),
            }
            for row in rows
        ]

    # 返回指定设备负责的队列分配信息。
    def list_device_assignments(self, device_id: str) -> list[dict[str, Any]]:
        normalized_id = self._normalize_device_id(device_id)
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT queue_name, desired_state, assignment_version
                FROM queue_assignments WHERE device_id = %s ORDER BY queue_name
                """,
                (normalized_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "queueName": row["queue_name"],
                "desiredState": row["desired_state"],
                "assignmentVersion": row["assignment_version"],
            }
            for row in rows
        ]

    # 将队列唯一绑定给设备，并递增绑定版本以防旧命令重新生效。
    def assign_queue(self, device_id: str, queue_name: str) -> dict[str, Any]:
        normalized_id = self._normalize_device_id(device_id)
        normalized_queue = self._normalize_queue_name(queue_name)
        now = _utcnow()
        with self._transaction() as cursor:
            self._require_device(cursor, normalized_id)
            cursor.execute(
                "SELECT device_id FROM queue_assignments WHERE queue_name = %s FOR UPDATE",
                (normalized_queue,),
            )
            existing = cursor.fetchone()
            if existing and existing["device_id"] != normalized_id:
                raise ValueError(
                    f"队列 {normalized_queue} 已绑定到设备 {existing['device_id']}"
                )
            if existing:
                cursor.execute(
                    """
                    UPDATE queue_assignments
                    SET desired_state = 'RUNNING', assignment_version = assignment_version + 1,
                        updated_at = %s
                    WHERE queue_name = %s
                    """,
                    (now, normalized_queue),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO queue_assignments
                    (queue_name, device_id, desired_state, assignment_version, created_at, updated_at)
                    VALUES (%s, %s, 'RUNNING', 1, %s, %s)
                    """,
                    (normalized_queue, normalized_id, now, now),
                )
            cursor.execute(
                """
                SELECT queue_name, device_id, desired_state, assignment_version
                FROM queue_assignments WHERE queue_name = %s
                """,
                (normalized_queue,),
            )
            assignment = cursor.fetchone()
        return {
            "queueName": assignment["queue_name"],
            "deviceId": assignment["device_id"],
            "desiredState": assignment["desired_state"],
            "assignmentVersion": assignment["assignment_version"],
        }

    # 解除队列与设备的绑定（观测状态随绑定行一并消失，无需单独清理）。
    def unassign_queue(self, device_id: str, queue_name: str) -> None:
        normalized_id = self._normalize_device_id(device_id)
        normalized_queue = self._normalize_queue_name(queue_name)
        with self._transaction() as cursor:
            cursor.execute(
                """
                DELETE FROM queue_assignments
                WHERE device_id = %s AND queue_name = %s
                """,
                (normalized_id, normalized_queue),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"设备 {normalized_id} 未维护队列 {normalized_queue}")

    # 更新已分配队列的期望状态，供 Agent 重连同步时恢复暂停意图。
    def set_assignment_desired_state(
        self, device_id: str, queue_name: str, desired_state: str
    ) -> None:
        normalized_id = self._normalize_device_id(device_id)
        normalized_queue = self._normalize_queue_name(queue_name)
        normalized_state = desired_state.upper()
        if normalized_state not in {"RUNNING", "PAUSED"}:
            raise ValueError(f"不支持的队列期望状态：{desired_state}")
        with self._transaction() as cursor:
            self._require_assignment(cursor, normalized_id, normalized_queue)
            cursor.execute(
                """
                UPDATE queue_assignments
                SET desired_state = %s, updated_at = %s
                WHERE device_id = %s AND queue_name = %s
                """,
                (normalized_state, _utcnow(), normalized_id, normalized_queue),
            )

    # 创建一个待发送给目标设备的控制命令。
    def create_command(
        self,
        device_id: str,
        queue_name: str | None,
        action: str,
        *,
        force_restart: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_id = self._normalize_device_id(device_id)
        normalized_queue = self._normalize_queue_name(queue_name) if queue_name else None
        allowed_actions = {"assign", "unassign", "pause", "resume", "restart", "restart_all"}
        if action not in allowed_actions:
            raise ValueError(f"不支持的控制操作：{action}")
        if action not in {"restart_all"} and not normalized_queue:
            raise ValueError("该操作必须指定队列")
        now = _utcnow()
        command_id = str(uuid.uuid4())
        command_payload = payload or {}
        with self._transaction() as cursor:
            self._require_device(cursor, normalized_id)
            if normalized_queue and action not in {"assign", "unassign"}:
                self._require_assignment(cursor, normalized_id, normalized_queue)
            cursor.execute(
                """
                INSERT INTO queue_commands
                (command_id, device_id, queue_name, action, force_restart, state, error_message,
                 payload, created_at)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', '', %s, %s)
                """,
                (
                    command_id,
                    normalized_id,
                    normalized_queue,
                    action,
                    force_restart,
                    _serialize(command_payload),
                    now,
                ),
            )
        return {
            "commandId": command_id,
            "deviceId": normalized_id,
            "queueName": normalized_queue,
            "action": action,
            "forceRestart": force_restart,
            "payload": command_payload,
        }

    # 将设备上报的事件去重后写入状态快照和命令结果。
    def record_agent_event(self, event_id: str, event: dict[str, Any]) -> bool:
        device_id = self._normalize_device_id(str(event.get("deviceId") or ""))
        token = str(event.get("token") or "")
        event_type = str(event.get("type") or "")
        if not token or not event_type:
            raise ValueError("设备事件缺少 token 或 type")
        safe_payload = {key: value for key, value in event.items() if key != "token"}
        now = _utcnow()
        with self._transaction() as cursor:
            self._require_device(cursor, device_id, token)
            # 历史设备明文回填：令牌校验通过且明文为空时用上报令牌补齐
            # （哈希不可逆，明文功能启用前创建的设备仅能通过在线 Agent 上报补齐）。
            cursor.execute(
                """
                UPDATE devices SET token = %s
                WHERE device_id = %s AND (token IS NULL OR token = '')
                """,
                (token, device_id),
            )
            cursor.execute(
                """
                INSERT IGNORE INTO queue_events
                (event_id, device_id, event_type, payload, received_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (event_id, device_id, event_type, _serialize(safe_payload), now),
            )
            if cursor.rowcount == 0:
                return False
            cursor.execute(
                """
                UPDATE devices SET status = 'ONLINE', last_seen_at = %s, updated_at = %s
                WHERE device_id = %s
                """,
                (now, now, device_id),
            )
            if event_type in {"status", "heartbeat"}:
                self._update_reported_states(cursor, device_id, event.get("queues") or [], now)
            elif event_type == "command_result":
                self._update_command_result(cursor, device_id, event, now)
        return True

    # 返回维护页面需要的设备、绑定队列和最新运行状态（单表查询，无联表）。
    def dashboard(self) -> dict[str, list[dict[str, Any]]]:
        devices = self.list_devices()
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT device_id, queue_name, desired_state, assignment_version,
                       actual_state, process_id, started_at, stopped_at,
                       last_error, restart_reason, observed_at
                FROM queue_assignments
                ORDER BY device_id, queue_name
                """
            )
            rows = cursor.fetchall()
        queues = [
            {
                "deviceId": row["device_id"],
                "queueName": row["queue_name"],
                "desiredState": row["desired_state"],
                "assignmentVersion": row["assignment_version"],
                "state": row["actual_state"] or "UNREPORTED",
                "pid": row["process_id"],
                "startedAt": _as_iso(row["started_at"]),
                "stoppedAt": _as_iso(row["stopped_at"]),
                "lastError": row["last_error"] or "",
                "restartReason": _as_json(row["restart_reason"]),
                "observedAt": _as_iso(row["observed_at"]),
            }
            for row in rows
        ]
        return {"devices": devices, "queues": queues}

    # 校验设备存在，并在提供令牌时校验其注册凭据。
    def _require_device(self, cursor, device_id: str, token: str | None = None) -> None:
        cursor.execute(
            "SELECT token_hash FROM devices WHERE device_id = %s FOR UPDATE", (device_id,)
        )
        device = cursor.fetchone()
        if device is None:
            raise ValueError(f"未注册设备：{device_id}")
        if token is not None and not secrets.compare_digest(
            device["token_hash"], self._hash_token(token)
        ):
            raise ValueError(f"设备 {device_id} 的注册令牌无效")

    # 校验队列当前确实绑定在命令目标设备上。
    def _require_assignment(self, cursor, device_id: str, queue_name: str) -> None:
        cursor.execute(
            """
            SELECT 1 FROM queue_assignments
            WHERE device_id = %s AND queue_name = %s
            """,
            (device_id, queue_name),
        )
        if cursor.fetchone() is None:
            raise ValueError(f"设备 {device_id} 未维护队列 {queue_name}")

    # 将 Agent 上报的每个队列观测状态写回其绑定行（UPDATE 天然跳过未绑定队列）。
    def _update_reported_states(
        self, cursor, device_id: str, queues: list[dict[str, Any]], observed_at: datetime
    ) -> None:
        reported_queue_names = set()
        for queue in queues:
            queue_name = self._normalize_queue_name(str(queue.get("name") or ""))
            reported_queue_names.add(queue_name)
            # Agent 上报只更新观测列，绝不能反写中心控制意图 desired_state。
            # 否则 resume/pause 后紧随而来的旧心跳会把 desired_state 盖回去，
            # 随后 heartbeat 触发的 sync 又会把设备端打回原状态。
            cursor.execute(
                """
                UPDATE queue_assignments
                SET actual_state = %s, process_id = %s, started_at = %s,
                    stopped_at = %s, last_error = %s, restart_reason = %s,
                    observed_at = %s
                WHERE device_id = %s AND queue_name = %s
                """,
                (
                    str(queue.get("state") or "UNREPORTED"),
                    queue.get("pid"),
                    self._parse_time(queue.get("startedAt")),
                    self._parse_time(queue.get("stoppedAt")),
                    str(queue.get("lastError") or ""),
                    _serialize(queue.get("restartReason") or []),
                    observed_at,
                    device_id,
                    queue_name,
                ),
            )
        self._mark_unreported(cursor, device_id, reported_queue_names, observed_at)

    # 将完整快照中缺失的绑定队列标记为等待 Agent 恢复分配，避免展示过期 PID。
    def _mark_unreported(
        self,
        cursor,
        device_id: str,
        reported_queue_names: set[str],
        observed_at: datetime,
    ) -> None:
        parameters: list[Any] = [observed_at, device_id]
        missing_condition = ""
        if reported_queue_names:
            placeholders = ", ".join(["%s"] * len(reported_queue_names))
            missing_condition = f" AND queue_name NOT IN ({placeholders})"
            parameters.extend(sorted(reported_queue_names))
        cursor.execute(
            f"""
            UPDATE queue_assignments
            SET actual_state = 'UNREPORTED', process_id = NULL, started_at = NULL,
                stopped_at = NULL, last_error = '等待设备同步队列分配',
                restart_reason = JSON_ARRAY(), observed_at = %s
            WHERE device_id = %s{missing_condition}
            """,
            parameters,
        )

    # 将 Agent 对命令的接收或失败结果写入命令记录。
    def _update_command_result(
        self, cursor, device_id: str, event: dict[str, Any], now: datetime
    ) -> None:
        command_id = str(event.get("commandId") or "")
        if not command_id:
            return
        state = "ACCEPTED" if event.get("ok") else "FAILED"
        cursor.execute(
            """
            UPDATE queue_commands
            SET state = %s, error_message = %s, acknowledged_at = %s
            WHERE command_id = %s AND device_id = %s
            """,
            (state, str(event.get("error") or ""), now, command_id, device_id),
        )

    # 规范化页面提交的设备 ID。
    @staticmethod
    def _normalize_device_id(device_id: str) -> str:
        normalized = device_id.strip().upper()
        if not normalized:
            raise ValueError("设备 ID 不能为空")
        if len(normalized) > 128:
            raise ValueError("设备 ID 最长 128 个字符")
        return normalized

    # 规范化页面提交的队列名称。
    @staticmethod
    def _normalize_queue_name(queue_name: str) -> str:
        normalized = queue_name.strip().upper()
        if not normalized:
            raise ValueError("队列名称不能为空")
        if len(normalized) > 255:
            raise ValueError("队列名称最长 255 个字符")
        return normalized

    # 对注册令牌做不可逆摘要后再保存或比对。
    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    # 解析 Agent 事件中的 ISO 时间，格式异常时返回空值。
    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None

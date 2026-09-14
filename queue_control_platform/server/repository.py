"""队列控制平台的 MySQL 持久化实现。"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from urllib.parse import unquote, urlparse

from app.core.task.protocol import (
    TASK_COMMAND_ACTIONS,
    TASK_EVENT_TYPES,
    TaskStatus,
    can_transition,
    normalize_rpa_message_id,
)
from app.core.flow.cache import flow_checksum
from app.core.flow.schema import FlowValidationError, validate_flow_definition

_FLOW_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


def _utcnow() -> datetime:
    """返回不带本地时区偏移的 UTC 时间，便于写入 MySQL DATETIME。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize(value: Any) -> str:
    """将事件中的结构化字段编码为 MySQL JSON 字符串。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _as_json(value: Any) -> Any:
    """将 MySQL 返回的 JSON 文本还原为 Python 对象。"""
    if not value:
        return []
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


def _as_iso(value: datetime | None) -> str | None:
    """将数据库时间转换为 API 使用的 ISO 字符串。"""
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def _column_value(row: dict[str, Any] | None, name: str) -> Any:
    """以不依赖 MySQL 列名大小写的方式读取 information_schema 结果。"""
    if row is None:
        return None
    expected = name.lower()
    for key, value in row.items():
        if key.lower() == expected:
            return value
    return None


class MySQLControlRepository:
    """保存设备、队列分配、命令和最新运行状态。"""

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

    # 创建平台所需全部表和索引，可重复安全执行。
    def initialize_schema(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id VARCHAR(128) PRIMARY KEY,
                display_name VARCHAR(255) NOT NULL,
                token_hash CHAR(64) NOT NULL,
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
                created_at DATETIME(6) NOT NULL,
                updated_at DATETIME(6) NOT NULL,
                CONSTRAINT fk_assignment_device FOREIGN KEY (device_id)
                    REFERENCES devices(device_id) ON DELETE CASCADE,
                INDEX idx_assignment_device (device_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS queue_statuses (
                device_id VARCHAR(128) NOT NULL,
                queue_name VARCHAR(255) NOT NULL,
                actual_state VARCHAR(32) NOT NULL,
                desired_state VARCHAR(32) NOT NULL,
                process_id BIGINT NULL,
                started_at DATETIME(6) NULL,
                stopped_at DATETIME(6) NULL,
                last_error TEXT NOT NULL,
                restart_reason JSON NOT NULL,
                observed_at DATETIME(6) NOT NULL,
                PRIMARY KEY (device_id, queue_name),
                CONSTRAINT fk_status_device FOREIGN KEY (device_id)
                    REFERENCES devices(device_id) ON DELETE CASCADE,
                INDEX idx_status_queue (queue_name)
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
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                task_run_id CHAR(36) PRIMARY KEY,
                rpa_message_id VARCHAR(128) NOT NULL,
                device_id VARCHAR(128) NOT NULL,
                queue_name VARCHAR(255) NOT NULL,
                flow_id VARCHAR(128) NULL,
                flow_version VARCHAR(128) NULL,
                status VARCHAR(32) NOT NULL,
                current_step_id VARCHAR(255) NULL,
                worker_pid BIGINT NULL,
                executor_pid BIGINT NULL,
                started_at DATETIME(6) NOT NULL,
                last_heartbeat_at DATETIME(6) NOT NULL,
                finished_at DATETIME(6) NULL,
                error_message TEXT NOT NULL,
                created_at DATETIME(6) NOT NULL,
                updated_at DATETIME(6) NOT NULL,
                CONSTRAINT fk_task_run_device FOREIGN KEY (device_id)
                    REFERENCES devices(device_id) ON DELETE RESTRICT,
                INDEX idx_task_runs_rpa_message (rpa_message_id),
                INDEX idx_task_runs_device_heartbeat (device_id, last_heartbeat_at),
                INDEX idx_task_runs_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS task_events (
                event_id CHAR(36) PRIMARY KEY,
                task_run_id CHAR(36) NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                step_id VARCHAR(255) NULL,
                payload JSON NOT NULL,
                occurred_at DATETIME(6) NOT NULL,
                received_at DATETIME(6) NOT NULL,
                CONSTRAINT fk_task_event_run FOREIGN KEY (task_run_id)
                    REFERENCES task_runs(task_run_id) ON DELETE CASCADE,
                INDEX idx_task_events_run_received (task_run_id, received_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS task_commands (
                command_id CHAR(36) PRIMARY KEY,
                task_run_id CHAR(36) NOT NULL,
                device_id VARCHAR(128) NOT NULL,
                action VARCHAR(64) NOT NULL,
                idempotency_key VARCHAR(128) NOT NULL,
                state VARCHAR(32) NOT NULL,
                payload JSON NOT NULL,
                created_at DATETIME(6) NOT NULL,
                acknowledged_at DATETIME(6) NULL,
                UNIQUE KEY uq_task_command_idempotency (task_run_id, idempotency_key),
                CONSTRAINT fk_task_command_run FOREIGN KEY (task_run_id)
                    REFERENCES task_runs(task_run_id) ON DELETE CASCADE,
                CONSTRAINT fk_task_command_device FOREIGN KEY (device_id)
                    REFERENCES devices(device_id) ON DELETE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS flow_definitions (
                flow_id VARCHAR(128) PRIMARY KEY,
                display_name VARCHAR(512) NOT NULL,
                description TEXT NOT NULL,
                created_by VARCHAR(128) NOT NULL,
                created_at DATETIME(6) NOT NULL,
                updated_at DATETIME(6) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS flow_versions (
                flow_id VARCHAR(128) NOT NULL,
                flow_version VARCHAR(128) NOT NULL,
                definition JSON NOT NULL,
                checksum CHAR(64) NOT NULL,
                created_by VARCHAR(128) NOT NULL,
                created_at DATETIME(6) NOT NULL,
                PRIMARY KEY (flow_id, flow_version),
                CONSTRAINT fk_flow_version_definition FOREIGN KEY (flow_id)
                    REFERENCES flow_definitions(flow_id) ON DELETE RESTRICT,
                UNIQUE KEY uq_flow_version_checksum (flow_id, checksum)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS flow_bindings (
                binding_id CHAR(36) PRIMARY KEY,
                queue_name VARCHAR(255) NOT NULL,
                flow_id VARCHAR(128) NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_by VARCHAR(128) NOT NULL,
                created_at DATETIME(6) NOT NULL,
                updated_at DATETIME(6) NOT NULL,
                UNIQUE KEY uq_flow_binding_queue (queue_name),
                CONSTRAINT fk_flow_binding_definition FOREIGN KEY (flow_id)
                    REFERENCES flow_definitions(flow_id) ON DELETE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS flow_release_records (
                release_id CHAR(36) PRIMARY KEY,
                flow_id VARCHAR(128) NOT NULL,
                flow_version VARCHAR(128) NOT NULL,
                release_type VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                strategy JSON NOT NULL,
                release_note TEXT NOT NULL,
                released_by VARCHAR(128) NOT NULL,
                released_at DATETIME(6) NOT NULL,
                CONSTRAINT fk_flow_release_version FOREIGN KEY (flow_id, flow_version)
                    REFERENCES flow_versions(flow_id, flow_version) ON DELETE RESTRICT,
                INDEX idx_flow_release_effective (flow_id, status, released_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        )
        with self._transaction() as cursor:
            for statement in statements:
                cursor.execute(statement)
            # 旧库保留该列及其历史数据，但状态上报不再写入源码变更信息。
            cursor.execute(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = 'queue_statuses'
                  AND column_name = 'source_changes'
                """
            )
            legacy_column = cursor.fetchone()
            if str(_column_value(legacy_column, "is_nullable") or "").upper() == "NO":
                cursor.execute(
                    "ALTER TABLE queue_statuses MODIFY COLUMN source_changes JSON NULL"
                )

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
                    (device_id, display_name, token_hash, status, created_at, updated_at)
                    VALUES (%s, %s, %s, 'OFFLINE', %s, %s)
                    """,
                    (normalized_id, display_name.strip(), self._hash_token(token), now, now),
                )
        except Exception as exc:
            if "Duplicate entry" in str(exc):
                raise ValueError(f"设备 ID 已存在：{normalized_id}") from exc
            raise
        return {"deviceId": normalized_id, "enrollmentToken": token}

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

    # 解除队列与设备的绑定，并删除该设备的最新状态快照。
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
            cursor.execute(
                "DELETE FROM queue_statuses WHERE device_id = %s AND queue_name = %s",
                (normalized_id, normalized_queue),
            )

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
        protocol_event_id = str(event.get("eventId") or event_id).strip()
        if not protocol_event_id or len(protocol_event_id) > 128:
            raise ValueError("事件缺少有效 eventId")
        now = _utcnow()
        with self._transaction() as cursor:
            self._require_device(cursor, device_id, token)
            cursor.execute(
                """
                INSERT IGNORE INTO queue_events
                (event_id, device_id, event_type, payload, received_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (protocol_event_id, device_id, event_type, _serialize(safe_payload), now),
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
                self._upsert_statuses(cursor, device_id, event.get("queues") or [], now)
            elif event_type == "command_result":
                self._update_command_result(cursor, device_id, event, now)
            elif event_type in TASK_EVENT_TYPES:
                self._record_task_event(
                    cursor, device_id, event, safe_payload, now, protocol_event_id
                )
        return True

    # 将任务事件写入不可变历史，并原子更新任务的当前运行快照。
    def _record_task_event(
        self,
        cursor,
        device_id: str,
        event: dict[str, Any],
        payload: dict[str, Any],
        now: datetime,
        event_id: str,
    ) -> None:
        task_run_id = str(event.get("taskRunId") or "").strip()
        try:
            task_run_id = str(uuid.UUID(task_run_id))
            rpa_message_id = normalize_rpa_message_id(event.get("rpaMessageId"))
            status = TaskStatus(str(event.get("status") or ""))
        except ValueError as exc:
            raise ValueError(f"任务事件协议无效：{exc}") from exc
        queue_name = self._normalize_queue_name(str(event.get("queueName") or ""))
        event_type = str(event.get("type") or "")
        self._validate_task_event(event_type, status)
        cursor.execute(
            "SELECT status FROM task_runs WHERE task_run_id = %s FOR UPDATE", (task_run_id,)
        )
        existing = cursor.fetchone()
        previous_status = existing["status"] if existing else None
        if not can_transition(previous_status, status):
            raise ValueError(f"任务状态不能从 {previous_status} 转为 {status.value}")
        occurred_at = self._parse_time(event.get("occurredAt")) or now
        step_id = str(event.get("stepId") or "").strip() or None
        worker_pid = event.get("workerPid")
        executor_pid = event.get("executorPid")
        error = str(event.get("error") or "")
        if existing is None:
            cursor.execute(
                """
                INSERT INTO task_runs
                (task_run_id, rpa_message_id, device_id, queue_name, flow_id, flow_version, status,
                 current_step_id, worker_pid, executor_pid, started_at, last_heartbeat_at, finished_at,
                 error_message, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    task_run_id, rpa_message_id, device_id, queue_name,
                    str(event.get("flowId") or "").strip() or None,
                    str(event.get("flowVersion") or "").strip() or None,
                    status.value, step_id, worker_pid, executor_pid, occurred_at, occurred_at,
                    occurred_at if status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.CANCELLED_UNCERTAIN} else None,
                    error, now, now,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE task_runs
                SET status = %s, current_step_id = COALESCE(%s, current_step_id),
                    worker_pid = COALESCE(%s, worker_pid), executor_pid = COALESCE(%s, executor_pid),
                    last_heartbeat_at = %s,
                    finished_at = %s, error_message = %s, updated_at = %s
                WHERE task_run_id = %s
                """,
                (
                    status.value, step_id, worker_pid, executor_pid, occurred_at,
                    occurred_at if status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.CANCELLED_UNCERTAIN} else None,
                    error, now, task_run_id,
                ),
            )
        cursor.execute(
            """
            INSERT INTO task_events
            (event_id, task_run_id, event_type, status, step_id, payload, occurred_at, received_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_id, task_run_id, event_type, status.value, step_id,
                _serialize(payload), occurred_at, now,
            ),
        )

    @staticmethod
    def _validate_task_event(event_type: str, status: TaskStatus) -> None:
        expected = {
            "task_started": {TaskStatus.STARTED},
            "task_heartbeat": {TaskStatus.STARTED, TaskStatus.RUNNING, TaskStatus.PAUSED},
            "task_step_changed": {TaskStatus.RUNNING},
            "task_paused": {TaskStatus.PAUSED},
            "task_cancelled": {TaskStatus.CANCELLED, TaskStatus.CANCELLED_UNCERTAIN},
            "task_finished": {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.CANCELLED_UNCERTAIN},
        }
        if status not in expected[event_type]:
            raise ValueError(f"任务事件 {event_type} 不接受状态 {status.value}")

    # 按任务运行 ID 返回中心页面和后续调试 API 需要的当前快照。
    def get_task_run(self, task_run_id: str) -> dict[str, Any] | None:
        normalized_id = str(uuid.UUID(str(task_run_id)))
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT task_run_id, rpa_message_id, device_id, queue_name, flow_id, flow_version,
                       status, current_step_id, worker_pid, executor_pid, started_at,
                       last_heartbeat_at, finished_at, error_message
                FROM task_runs WHERE task_run_id = %s
                """,
                (normalized_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "taskRunId": row["task_run_id"], "rpaMessageId": row["rpa_message_id"],
            "deviceId": row["device_id"], "queueName": row["queue_name"],
            "flowId": row["flow_id"], "flowVersion": row["flow_version"],
            "status": row["status"], "currentStepId": row["current_step_id"],
            "workerPid": row["worker_pid"], "executorPid": row["executor_pid"],
            "startedAt": _as_iso(row["started_at"]),
            "lastHeartbeatAt": _as_iso(row["last_heartbeat_at"]),
            "finishedAt": _as_iso(row["finished_at"]), "error": row["error_message"],
        }

    # 第一阶段仅建立命令标识与去重；实际分发由任务执行阶段补充。
    def create_task_command(
        self, task_run_id: str, action: str, idempotency_key: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if action not in TASK_COMMAND_ACTIONS:
            raise ValueError(f"不支持的任务命令：{action}")
        normalized_id = str(uuid.UUID(str(task_run_id)))
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise ValueError("任务命令需要不超过 128 字符的 idempotencyKey")
        command_id = str(uuid.uuid4())
        now = _utcnow()
        with self._transaction() as cursor:
            cursor.execute("SELECT device_id FROM task_runs WHERE task_run_id = %s FOR UPDATE", (normalized_id,))
            run = cursor.fetchone()
            if run is None:
                raise ValueError(f"任务不存在：{normalized_id}")
            cursor.execute(
                """
                INSERT INTO task_commands
                (command_id, task_run_id, device_id, action, idempotency_key, state, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', %s, %s)
                ON DUPLICATE KEY UPDATE command_id = command_id
                """,
                (command_id, normalized_id, run["device_id"], action, key, _serialize(payload or {}), now),
            )
            cursor.execute(
                "SELECT command_id, device_id, state FROM task_commands WHERE task_run_id = %s AND idempotency_key = %s",
                (normalized_id, key),
            )
            saved = cursor.fetchone()
        return {"commandId": saved["command_id"], "taskRunId": normalized_id, "deviceId": saved["device_id"], "action": action, "state": saved["state"], "idempotencyKey": key}

    # 创建流程元数据；流程内容只能以不可变版本单独写入。
    def create_flow(
        self, flow_id: str, display_name: str, description: str = "", created_by: str = "system"
    ) -> dict[str, Any]:
        flow_id = self._normalize_flow_identifier(flow_id, "flowId")
        display_name = self._normalize_display_name(display_name)
        now = _utcnow()
        with self._transaction() as cursor:
            cursor.execute("SELECT 1 FROM flow_definitions WHERE flow_id = %s", (flow_id,))
            if cursor.fetchone() is not None:
                raise ValueError(f"流程已存在：{flow_id}")
            cursor.execute(
                """
                INSERT INTO flow_definitions
                (flow_id, display_name, description, created_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (flow_id, display_name, str(description or ""), self._normalize_actor(created_by), now, now),
            )
        return self.get_flow(flow_id) or {}

    # 返回流程及其当前有效发布版本，供流程中心列表使用。
    def list_flows(self) -> list[dict[str, Any]]:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT d.flow_id, d.display_name, d.description, d.created_by, d.created_at, d.updated_at,
                       r.flow_version AS current_version, r.released_at AS last_released_at
                FROM flow_definitions d
                LEFT JOIN flow_release_records r ON r.release_id = (
                    SELECT latest.release_id FROM flow_release_records latest
                    WHERE latest.flow_id = d.flow_id AND latest.status = 'PUBLISHED'
                    ORDER BY latest.released_at DESC, latest.release_id DESC LIMIT 1
                )
                ORDER BY d.updated_at DESC, d.flow_id
                """
            )
            rows = cursor.fetchall()
        return [self._flow_summary(row) for row in rows]

    def get_flow(self, flow_id: str) -> dict[str, Any] | None:
        normalized_id = self._normalize_flow_identifier(flow_id, "flowId")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT d.flow_id, d.display_name, d.description, d.created_by, d.created_at, d.updated_at,
                       r.flow_version AS current_version, r.released_at AS last_released_at
                FROM flow_definitions d
                LEFT JOIN flow_release_records r ON r.release_id = (
                    SELECT latest.release_id FROM flow_release_records latest
                    WHERE latest.flow_id = d.flow_id AND latest.status = 'PUBLISHED'
                    ORDER BY latest.released_at DESC, latest.release_id DESC LIMIT 1
                )
                WHERE d.flow_id = %s
                """,
                (normalized_id,),
            )
            row = cursor.fetchone()
        return self._flow_summary(row) if row else None

    # 对定义执行运行时相同的 Schema 校验后，保存一次且永不修改的版本快照。
    def create_flow_version(
        self, flow_id: str, flow_version: str, definition: dict[str, Any], created_by: str = "system"
    ) -> dict[str, Any]:
        flow_id = self._normalize_flow_identifier(flow_id, "flowId")
        flow_version = self._normalize_flow_identifier(flow_version, "flowVersion")
        try:
            validated = validate_flow_definition(definition)
        except FlowValidationError as exc:
            raise ValueError(f"流程 Schema 校验失败：{exc}") from exc
        if validated["flowId"] != flow_id or validated["flowVersion"] != flow_version:
            raise ValueError("URL 中的 flowId 和 flowVersion 必须与流程定义一致")
        checksum = flow_checksum(validated)
        now = _utcnow()
        with self._transaction() as cursor:
            cursor.execute("SELECT 1 FROM flow_definitions WHERE flow_id = %s FOR UPDATE", (flow_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"流程不存在：{flow_id}")
            cursor.execute(
                "SELECT checksum FROM flow_versions WHERE flow_id = %s AND flow_version = %s",
                (flow_id, flow_version),
            )
            if cursor.fetchone() is not None:
                raise ValueError(f"流程版本不可修改：{flow_id}@{flow_version}")
            cursor.execute(
                """
                INSERT INTO flow_versions
                (flow_id, flow_version, definition, checksum, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (flow_id, flow_version, _serialize(validated), checksum, self._normalize_actor(created_by), now),
            )
            cursor.execute(
                "UPDATE flow_definitions SET updated_at = %s WHERE flow_id = %s", (now, flow_id)
            )
        return self.get_flow_version(flow_id, flow_version) or {}

    def list_flow_versions(self, flow_id: str) -> list[dict[str, Any]]:
        flow_id = self._normalize_flow_identifier(flow_id, "flowId")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT flow_id, flow_version, checksum, created_by, created_at
                FROM flow_versions WHERE flow_id = %s ORDER BY created_at DESC, flow_version DESC
                """,
                (flow_id,),
            )
            rows = cursor.fetchall()
        return [
            {"flowId": row["flow_id"], "flowVersion": row["flow_version"], "checksum": row["checksum"],
             "createdBy": row["created_by"], "createdAt": _as_iso(row["created_at"])}
            for row in rows
        ]

    def get_flow_version(self, flow_id: str, flow_version: str) -> dict[str, Any] | None:
        flow_id = self._normalize_flow_identifier(flow_id, "flowId")
        flow_version = self._normalize_flow_identifier(flow_version, "flowVersion")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT flow_id, flow_version, definition, checksum, created_by, created_at
                FROM flow_versions WHERE flow_id = %s AND flow_version = %s
                """,
                (flow_id, flow_version),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "flowId": row["flow_id"], "flowVersion": row["flow_version"],
            "definition": _as_json(row["definition"]), "checksum": row["checksum"],
            "createdBy": row["created_by"], "createdAt": _as_iso(row["created_at"]),
        }

    # 一个队列只保留一个启用绑定，避免同一任务存在不确定的流程路由。
    def upsert_flow_binding(
        self, queue_name: str, flow_id: str, *, enabled: bool = True, created_by: str = "system"
    ) -> dict[str, Any]:
        queue_name = self._normalize_queue_name(queue_name)
        flow_id = self._normalize_flow_identifier(flow_id, "flowId")
        now = _utcnow()
        with self._transaction() as cursor:
            cursor.execute("SELECT 1 FROM flow_definitions WHERE flow_id = %s", (flow_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"流程不存在：{flow_id}")
            cursor.execute("SELECT binding_id FROM flow_bindings WHERE queue_name = %s FOR UPDATE", (queue_name,))
            existing = cursor.fetchone()
            if existing is None:
                binding_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO flow_bindings
                    (binding_id, queue_name, flow_id, enabled, created_by, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (binding_id, queue_name, flow_id, enabled, self._normalize_actor(created_by), now, now),
                )
            else:
                binding_id = existing["binding_id"]
                cursor.execute(
                    """
                    UPDATE flow_bindings SET flow_id = %s, enabled = %s, updated_at = %s
                    WHERE binding_id = %s
                    """,
                    (flow_id, enabled, now, binding_id),
                )
        return self.get_flow_binding(queue_name) or {}

    def get_flow_binding(self, queue_name: str) -> dict[str, Any] | None:
        queue_name = self._normalize_queue_name(queue_name)
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT binding_id, queue_name, flow_id, enabled, created_by, created_at, updated_at FROM flow_bindings WHERE queue_name = %s",
                (queue_name,),
            )
            row = cursor.fetchone()
        return self._binding_summary(row) if row else None

    def list_flow_bindings(self) -> list[dict[str, Any]]:
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT binding_id, queue_name, flow_id, enabled, created_by, created_at, updated_at FROM flow_bindings ORDER BY queue_name"
            )
            rows = cursor.fetchall()
        return [self._binding_summary(row) for row in rows]

    # 发布只新增审计记录。新的记录在设备解析绑定时优先于旧记录，而非修改旧版本。
    def release_flow_version(
        self,
        flow_id: str,
        flow_version: str,
        strategy: dict[str, Any] | None = None,
        *,
        release_note: str = "",
        released_by: str = "system",
        release_type: str = "PUBLISH",
    ) -> dict[str, Any]:
        flow_id = self._normalize_flow_identifier(flow_id, "flowId")
        flow_version = self._normalize_flow_identifier(flow_version, "flowVersion")
        strategy = self._normalize_release_strategy(strategy or {"mode": "all"})
        now = _utcnow()
        release_id = str(uuid.uuid4())
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT 1 FROM flow_versions WHERE flow_id = %s AND flow_version = %s",
                (flow_id, flow_version),
            )
            if cursor.fetchone() is None:
                raise ValueError(f"流程版本不存在：{flow_id}@{flow_version}")
            cursor.execute(
                """
                INSERT INTO flow_release_records
                (release_id, flow_id, flow_version, release_type, status, strategy, release_note, released_by, released_at)
                VALUES (%s, %s, %s, %s, 'PUBLISHED', %s, %s, %s, %s)
                """,
                (release_id, flow_id, flow_version, release_type, _serialize(strategy), str(release_note or ""), self._normalize_actor(released_by), now),
            )
            cursor.execute("UPDATE flow_definitions SET updated_at = %s WHERE flow_id = %s", (now, flow_id))
        return self.get_release(release_id) or {}

    def rollback_flow(self, flow_id: str, target_version: str, **kwargs: Any) -> dict[str, Any]:
        return self.release_flow_version(
            flow_id, target_version, kwargs.get("strategy"), release_note=kwargs.get("release_note", ""),
            released_by=kwargs.get("released_by", "system"), release_type="ROLLBACK",
        )

    def get_release(self, release_id: str) -> dict[str, Any] | None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT release_id, flow_id, flow_version, release_type, status, strategy,
                       release_note, released_by, released_at
                FROM flow_release_records WHERE release_id = %s
                """,
                (str(release_id),),
            )
            row = cursor.fetchone()
        return self._release_summary(row) if row else None

    def list_flow_releases(self, flow_id: str) -> list[dict[str, Any]]:
        flow_id = self._normalize_flow_identifier(flow_id, "flowId")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT release_id, flow_id, flow_version, release_type, status, strategy,
                       release_note, released_by, released_at
                FROM flow_release_records WHERE flow_id = %s ORDER BY released_at DESC, release_id DESC
                """,
                (flow_id,),
            )
            rows = cursor.fetchall()
        return [self._release_summary(row) for row in rows]

    def compare_flow_versions(self, flow_id: str, left_version: str, right_version: str) -> dict[str, Any]:
        left = self.get_flow_version(flow_id, left_version)
        right = self.get_flow_version(flow_id, right_version)
        if left is None or right is None:
            raise ValueError("用于对比的流程版本不存在")
        left_steps = self._steps_by_id(left["definition"].get("steps", []))
        right_steps = self._steps_by_id(right["definition"].get("steps", []))
        return {
            "flowId": left["flowId"], "leftVersion": left["flowVersion"], "rightVersion": right["flowVersion"],
            "addedStepIds": sorted(set(right_steps) - set(left_steps)),
            "removedStepIds": sorted(set(left_steps) - set(right_steps)),
            "changedStepIds": sorted(step_id for step_id in set(left_steps) & set(right_steps) if left_steps[step_id] != right_steps[step_id]),
            "checksumChanged": left["checksum"] != right["checksum"],
        }

    # 设备重连或发布后下发当前可用的完整绑定快照；版本内容由 Agent 再经 API 拉取。
    def list_device_flow_bindings(self, device_id: str) -> list[dict[str, str]]:
        device_id = self._normalize_device_id(device_id)
        with self._transaction() as cursor:
            self._require_device(cursor, device_id)
            cursor.execute(
                """
                SELECT b.queue_name, b.flow_id
                FROM flow_bindings b
                INNER JOIN queue_assignments a ON a.queue_name = b.queue_name
                WHERE a.device_id = %s AND b.enabled = TRUE
                ORDER BY b.queue_name
                """,
                (device_id,),
            )
            bindings = cursor.fetchall()
            result = []
            for binding in bindings:
                release = self._effective_release(cursor, binding["flow_id"], device_id)
                if release is not None:
                    result.append({
                        "queueName": binding["queue_name"], "flowId": binding["flow_id"],
                        "flowVersion": release["flow_version"], "checksum": release["checksum"],
                    })
        return result

    def list_flow_target_devices(self, flow_id: str) -> list[str]:
        flow_id = self._normalize_flow_identifier(flow_id, "flowId")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT a.device_id FROM queue_assignments a
                INNER JOIN flow_bindings b ON b.queue_name = a.queue_name
                WHERE b.flow_id = %s AND b.enabled = TRUE ORDER BY a.device_id
                """,
                (flow_id,),
            )
            rows = cursor.fetchall()
        return [row["device_id"] for row in rows]

    # Agent 拉取流程定义前必须校验其设备凭据。
    def get_agent_flow_version(
        self, device_id: str, token: str, flow_id: str, flow_version: str
    ) -> dict[str, Any] | None:
        device_id = self._normalize_device_id(device_id)
        with self._transaction() as cursor:
            self._require_device(cursor, device_id, token)
        return self.get_flow_version(flow_id, flow_version)

    # 返回维护页面需要的设备、绑定队列和最新运行状态。
    def dashboard(self) -> dict[str, list[dict[str, Any]]]:
        devices = self.list_devices()
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT a.device_id, a.queue_name, a.desired_state, a.assignment_version,
                       s.actual_state, s.process_id, s.started_at, s.stopped_at,
                       s.last_error, s.restart_reason, s.observed_at
                FROM queue_assignments a
                LEFT JOIN queue_statuses s
                  ON s.device_id = a.device_id AND s.queue_name = a.queue_name
                ORDER BY a.device_id, a.queue_name
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

    @staticmethod
    def _flow_summary(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "flowId": row["flow_id"], "displayName": row["display_name"],
            "description": row["description"], "createdBy": row["created_by"],
            "createdAt": _as_iso(row["created_at"]), "updatedAt": _as_iso(row["updated_at"]),
            "currentVersion": row.get("current_version"), "lastReleasedAt": _as_iso(row.get("last_released_at")),
        }

    @staticmethod
    def _binding_summary(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "bindingId": row["binding_id"], "queueName": row["queue_name"],
            "flowId": row["flow_id"], "enabled": bool(row["enabled"]),
            "createdBy": row["created_by"], "createdAt": _as_iso(row["created_at"]),
            "updatedAt": _as_iso(row["updated_at"]),
        }

    @staticmethod
    def _release_summary(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "releaseId": row["release_id"], "flowId": row["flow_id"],
            "flowVersion": row["flow_version"], "releaseType": row["release_type"],
            "status": row["status"], "strategy": _as_json(row["strategy"]),
            "releaseNote": row["release_note"], "releasedBy": row["released_by"],
            "releasedAt": _as_iso(row["released_at"]),
        }

    def _effective_release(self, cursor, flow_id: str, device_id: str) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT r.flow_version, r.strategy, v.checksum
            FROM flow_release_records r
            INNER JOIN flow_versions v
              ON v.flow_id = r.flow_id AND v.flow_version = r.flow_version
            WHERE r.flow_id = %s AND r.status = 'PUBLISHED'
            ORDER BY r.released_at DESC, r.release_id DESC
            """,
            (flow_id,),
        )
        for release in cursor.fetchall():
            if self._release_applies(_as_json(release["strategy"]), device_id):
                return release
        return None

    @staticmethod
    def _release_applies(strategy: Any, device_id: str) -> bool:
        if not isinstance(strategy, dict):
            return False
        mode = strategy.get("mode")
        if mode == "all":
            return True
        if mode == "devices":
            return device_id in strategy.get("deviceIds", [])
        if mode == "percentage":
            digest = hashlib.sha256(device_id.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % 100
            return bucket < strategy.get("percentage", 0)
        return False

    @staticmethod
    def _steps_by_id(steps: list[Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_id = step.get("stepId")
            if isinstance(step_id, str):
                result[step_id] = step
            for child_key in ("then", "else", "steps"):
                children = step.get(child_key)
                if isinstance(children, list):
                    result.update(MySQLControlRepository._steps_by_id(children))
        return result

    @staticmethod
    def _normalize_flow_identifier(value: str, name: str) -> str:
        normalized = str(value or "").strip()
        if not _FLOW_IDENTIFIER.fullmatch(normalized):
            raise ValueError(f"{name} 必须是以字母开头的标识符")
        return normalized

    @staticmethod
    def _normalize_display_name(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized or len(normalized) > 512:
            raise ValueError("displayName 必须是 1 至 512 个字符的文本")
        return normalized

    @staticmethod
    def _normalize_actor(value: str) -> str:
        normalized = str(value or "system").strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("操作人必须是 1 至 128 个字符")
        return normalized

    def _normalize_release_strategy(self, strategy: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(strategy, dict):
            raise ValueError("发布策略必须是对象")
        mode = str(strategy.get("mode") or "").lower()
        if mode == "all" and set(strategy) == {"mode"}:
            return {"mode": "all"}
        if mode == "devices" and set(strategy) == {"mode", "deviceIds"}:
            device_ids = strategy.get("deviceIds")
            if not isinstance(device_ids, list) or not device_ids:
                raise ValueError("设备灰度必须提供非空 deviceIds")
            return {"mode": "devices", "deviceIds": sorted({self._normalize_device_id(str(item)) for item in device_ids})}
        if mode == "percentage" and set(strategy) == {"mode", "percentage"}:
            percentage = strategy.get("percentage")
            if not isinstance(percentage, int) or isinstance(percentage, bool) or not 1 <= percentage <= 99:
                raise ValueError("百分比灰度必须是 1 至 99 的整数")
            return {"mode": "percentage", "percentage": percentage}
        raise ValueError("发布策略仅支持 all、devices 或 percentage")

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

    # 将 Agent 上报的每个队列状态写入最新状态表。
    def _upsert_statuses(
        self, cursor, device_id: str, queues: list[dict[str, Any]], observed_at: datetime
    ) -> None:
        reported_queue_names = set()
        for queue in queues:
            queue_name = self._normalize_queue_name(str(queue.get("name") or ""))
            reported_queue_names.add(queue_name)
            cursor.execute(
                """
                SELECT 1 FROM queue_assignments
                WHERE device_id = %s AND queue_name = %s
                """,
                (device_id, queue_name),
            )
            if cursor.fetchone() is None:
                continue
            desired_state = str(queue.get("desiredState") or "RUNNING").upper()
            if desired_state in {"RUNNING", "PAUSED"}:
                cursor.execute(
                    """
                    UPDATE queue_assignments SET desired_state = %s, updated_at = %s
                    WHERE device_id = %s AND queue_name = %s
                    """,
                    (desired_state, observed_at, device_id, queue_name),
                )
            cursor.execute(
                """
                INSERT INTO queue_statuses
                (device_id, queue_name, actual_state, desired_state, process_id, started_at,
                 stopped_at, last_error, restart_reason, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    actual_state = VALUES(actual_state), desired_state = VALUES(desired_state),
                    process_id = VALUES(process_id), started_at = VALUES(started_at),
                    stopped_at = VALUES(stopped_at), last_error = VALUES(last_error),
                    restart_reason = VALUES(restart_reason),
                    observed_at = VALUES(observed_at)
                """,
                (
                    device_id,
                    queue_name,
                    str(queue.get("state") or "UNREPORTED"),
                    str(queue.get("desiredState") or "RUNNING"),
                    queue.get("pid"),
                    self._parse_time(queue.get("startedAt")),
                    self._parse_time(queue.get("stoppedAt")),
                    str(queue.get("lastError") or ""),
                    _serialize(queue.get("restartReason") or []),
                    observed_at,
                ),
            )
        self._mark_missing_statuses(
            cursor, device_id, reported_queue_names, observed_at
        )

    # 将完整快照中缺失的旧状态标记为等待 Agent 恢复分配，避免展示过期 PID。
    def _mark_missing_statuses(
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
            missing_condition = f" AND s.queue_name NOT IN ({placeholders})"
            parameters.extend(sorted(reported_queue_names))
        cursor.execute(
            f"""
            UPDATE queue_statuses s
            INNER JOIN queue_assignments a
              ON a.device_id = s.device_id AND a.queue_name = s.queue_name
            SET s.actual_state = 'UNREPORTED', s.process_id = NULL, s.started_at = NULL,
                s.stopped_at = NULL, s.last_error = '等待设备同步队列分配',
                s.restart_reason = JSON_ARRAY(),
                s.observed_at = %s
            WHERE s.device_id = %s{missing_condition}
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

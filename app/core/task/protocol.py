"""任务运行标识、状态流转和控制事件封装。"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

PROTOCOL_VERSION = 1


class TaskStatus(StrEnum):
    """单条 RPA 消息执行时持久化的状态。"""

    PENDING = "PENDING"
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    CANCELLED_UNCERTAIN = "CANCELLED_UNCERTAIN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


TERMINAL_TASK_STATUSES = {
    TaskStatus.CANCELLED,
    TaskStatus.CANCELLED_UNCERTAIN,
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
}

TASK_EVENT_TYPES = {
    "task_started",
    "task_heartbeat",
    "task_step_changed",
    "task_paused",
    "task_cancelled",
    "task_finished",
}

TASK_COMMAND_ACTIONS = {
    "cancel_task",
    "pause_at_step",
    "patch_task_context",
    "resume_task",
}

_ALLOWED_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.STARTED, TaskStatus.CANCELLED},
    TaskStatus.STARTED: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.PAUSED,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELLED_UNCERTAIN,
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
    },
    TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
}


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_task_run_id() -> str:
    return str(uuid.uuid4())


def normalize_task_run_id(value: Any) -> str:
    task_run_id = str(value or "").strip()
    if not task_run_id:
        return new_task_run_id()
    try:
        return str(uuid.UUID(task_run_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError("taskRunId 必须是 UUID") from exc


def normalize_rpa_message_id(value: Any) -> str:
    rpa_message_id = str(value or "").strip()
    if not rpa_message_id:
        raise ValueError("rpaMessageId 不能为空")
    if len(rpa_message_id) > 128:
        raise ValueError("rpaMessageId 最长 128 个字符")
    return rpa_message_id


def can_transition(current: TaskStatus | str | None, target: TaskStatus | str) -> bool:
    if current is None:
        return target == TaskStatus.STARTED
    current_status = TaskStatus(current)
    target_status = TaskStatus(target)
    return target_status == current_status or target_status in _ALLOWED_TRANSITIONS.get(
        current_status, set()
    )


@dataclass(frozen=True)
class TaskRuntimeIdentity:
    task_run_id: str
    rpa_message_id: str
    queue_name: str
    flow_id: str | None = None
    flow_version: str | None = None


def build_task_event(
    identity: TaskRuntimeIdentity,
    event_type: str,
    status: TaskStatus | str,
    *,
    device_id: str,
    worker_pid: int | None = None,
    executor_pid: int | None = None,
    step_id: str | None = None,
    error: str = "",
    event_id: str | None = None,
) -> dict[str, Any]:
    """构建自包含且可安全重试的任务事件载荷。"""
    if event_type not in TASK_EVENT_TYPES:
        raise ValueError(f"不支持的任务事件：{event_type}")
    normalized_status = TaskStatus(status)
    return {
        "eventId": event_id or str(uuid.uuid4()),
        "type": event_type,
        "protocolVersion": PROTOCOL_VERSION,
        "occurredAt": utcnow_iso(),
        "deviceId": device_id.strip().upper(),
        "taskRunId": identity.task_run_id,
        "rpaMessageId": identity.rpa_message_id,
        "queueName": identity.queue_name,
        "flowId": identity.flow_id,
        "flowVersion": identity.flow_version,
        "workerPid": worker_pid if worker_pid is not None else os.getpid(),
        "executorPid": executor_pid,
        "stepId": step_id,
        "status": normalized_status.value,
        "error": error,
    }

"""为已注册队列控制 Agent 尽力上报任务生命周期。"""
from __future__ import annotations

import threading

from app.core.task.protocol import TaskRuntimeIdentity, TaskStatus, build_task_event


class TaskEventReporter:
    """发布任务事件，但不让控制面故障中断 RPA 业务。"""

    def __init__(
        self,
        *,
        device_id: str,
        enrollment_token: str,
        redis_url: str,
        heartbeat_seconds: float = 15,
        publisher=None,
    ):
        self.device_id = device_id
        self.enrollment_token = enrollment_token
        self.redis_url = redis_url
        self.heartbeat_seconds = heartbeat_seconds
        self._publisher = publisher
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._identity: TaskRuntimeIdentity | None = None
        self._status = TaskStatus.PENDING
        self._step_id: str | None = None

    def start(self, identity: TaskRuntimeIdentity) -> None:
        self._identity = identity
        self.report("task_started", TaskStatus.STARTED)
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"task-heartbeat-{identity.task_run_id}",
            daemon=True,
        )
        self._thread.start()

    def step_changed(self, step_id: str) -> None:
        self._step_id = step_id
        self.report("task_step_changed", TaskStatus.RUNNING, step_id=step_id)

    def finish(self, success: bool, error: str = "") -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self.report("task_finished", TaskStatus.SUCCEEDED if success else TaskStatus.FAILED, error=error)

    def report(self, event_type: str, status: TaskStatus, *, step_id: str | None = None, error: str = "") -> None:
        if self._identity is None:
            return
        self._status = status
        try:
            self._get_publisher().publish_event(
                {
                    "token": self.enrollment_token,
                    **build_task_event(
                        self._identity,
                        event_type,
                        status,
                        device_id=self.device_id,
                        step_id=step_id if step_id is not None else self._step_id,
                        error=error,
                    ),
                }
            )
        except Exception:  # noqa: BLE001 - 控制面上报明确采用尽力而为策略。
            return

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self.heartbeat_seconds):
            self.report("task_heartbeat", self._status)

    def _get_publisher(self):
        if self._publisher is None:
            from app.control.queue_client.redis_client import QueueControlRedisClient

            self._publisher = QueueControlRedisClient(self.redis_url)
        return self._publisher


def build_task_event_reporter(settings) -> TaskEventReporter:
    return TaskEventReporter(
        device_id=settings.device_id,
        enrollment_token=settings.enrollment_token,
        redis_url=settings.redis_url,
    )

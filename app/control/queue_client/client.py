"""接收 Redis 控制命令并管理本机队列 Worker 的队列控制客户端。"""
from __future__ import annotations

import atexit
import socket
import threading
from typing import Any

from app.control.queue_client.config import QueueClientSettings
from app.control.queue_client.redis_client import QueueControlRedisClient
from app.control.supervisor import QueueSupervisor


class QueueControlClient:
    """将中心平台命令转为本机 Worker 生命周期操作。"""

    # 创建不落本地状态文件的监管器，并准备 Redis 命令循环。
    def __init__(
        self,
        settings: QueueClientSettings,
        redis_client: QueueControlRedisClient | None = None,
    ):
        self.settings = settings
        self.redis_client = redis_client or QueueControlRedisClient(settings.redis_url)
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self.supervisor = QueueSupervisor(
            [],
            project_root=settings.project_root,
            drain_timeout_seconds=settings.drain_timeout_seconds,
            persist_state=False,
            status_observer=self._publish_status,
        )
        atexit.register(self.stop)

    # 启动本机监管器、发送初始心跳，并进入 Redis 命令消费循环。
    def run_forever(self) -> None:
        self.supervisor.start()
        self._publish_heartbeat()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="queue-control-client-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        try:
            while not self._stop_event.is_set():
                messages = self.redis_client.read_commands(
                    self.settings.device_id, socket.gethostname()
                )
                for message_id, command in messages:
                    self._handle_message(message_id, command)
        finally:
            self.stop()

    # 停止命令循环和本机监管器。
    def stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self.supervisor.stop()

    # 处理一条控制命令，回传结果后再确认 Redis Stream 消息。
    def _handle_message(self, message_id: str, command: dict[str, Any]) -> None:
        command_id = str(command.get("commandId") or "")
        try:
            self._execute_command(command)
            if command_id:
                self._publish_event(
                    {"type": "command_result", "commandId": command_id, "ok": True}
                )
            self.redis_client.acknowledge_command(self.settings.device_id, message_id)
        except Exception as exc:
            if command_id:
                self._publish_event(
                    {
                        "type": "command_result",
                        "commandId": command_id,
                        "ok": False,
                        "error": str(exc),
                    }
                )
            self.redis_client.acknowledge_command(self.settings.device_id, message_id)

    # 将平台定义的操作映射为本机 QueueSupervisor 方法。
    def _execute_command(self, command: dict[str, Any]) -> None:
        action = str(command.get("action") or "")
        queue_name = command.get("queueName")
        if action == "assign":
            self.supervisor.assign(str(queue_name or ""))
        elif action == "sync":
            self._sync_assignments(command.get("assignments") or [])
        elif action == "unassign":
            self.supervisor.unassign(str(queue_name or ""))
        elif action == "pause":
            self.supervisor.pause(str(queue_name or ""))
        elif action == "resume":
            self.supervisor.resume(str(queue_name or ""))
        elif action == "restart":
            self.supervisor.restart(
                str(queue_name or ""), force=bool(command.get("forceRestart", False))
            )
        elif action == "restart_all":
            self.supervisor.restart_all()
        else:
            raise ValueError(f"不支持的设备命令：{action}")

    # 将中心平台下发的完整队列快照恢复为本机监管器的实际运行状态。
    def _sync_assignments(self, assignments: list[dict[str, Any]]) -> None:
        expected = {
            str(item.get("queueName") or "").upper(): str(
                item.get("desiredState") or "RUNNING"
            ).upper()
            for item in assignments
            if str(item.get("queueName") or "").strip()
        }
        current = {item["name"]: item for item in self.supervisor.queue_statuses()}
        for queue_name in sorted(set(current) - set(expected)):
            self.supervisor.unassign(queue_name)
        for queue_name, desired_state in expected.items():
            runtime = current.get(queue_name)
            if runtime is None:
                self.supervisor.assign(queue_name, start=desired_state != "PAUSED")
            elif desired_state == "PAUSED" and runtime["desiredState"] != "PAUSED":
                self.supervisor.pause(queue_name)
            elif desired_state == "RUNNING" and runtime["state"] == "PAUSED":
                self.supervisor.resume(queue_name)

    # 按固定间隔发送心跳，使平台能识别离线设备。
    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(15):
            try:
                self._publish_heartbeat()
            except Exception:
                continue

    # 向中心事件流上报当前设备可达。
    def _publish_heartbeat(self) -> None:
        self._publish_event(
            {
                "type": "heartbeat",
                "hostname": socket.gethostname(),
                "queues": self.supervisor.queue_statuses(),
            }
        )

    # 将监管器的全量队列快照上报到中心事件流。
    def _publish_status(self, queues: list[dict[str, Any]]) -> None:
        self._publish_event({"type": "status", "queues": queues})

    # 补充设备身份并写入 Redis 状态事件流。
    def _publish_event(self, payload: dict[str, Any]) -> None:
        self.redis_client.publish_event(
            {
                "deviceId": self.settings.device_id,
                "token": self.settings.enrollment_token,
                **payload,
            }
        )

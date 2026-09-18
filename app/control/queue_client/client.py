"""接收 Redis 控制命令并管理本机队列 Worker 的队列控制客户端。"""
from __future__ import annotations

import atexit
import socket
import threading
import time
from typing import Any

from app.config.settings import Settings
from app.control.queue_client.config import QueueClientSettings
from app.control.queue_client.redis_client import (
    QueueControlRedisClient,
    is_control_plane_unavailable,
)
from app.control.supervisor import QueueSupervisor
from app.core.logging.logger import info, warn
from app.core.scheduler.account_session import (
    AccountSessionSettings,
    create_account_session_manager,
)

# 控制面 Redis 失联后的重连退避：首次 1 秒，上限 30 秒。
_INITIAL_RECONNECT_SECONDS = 1.0
_MAX_RECONNECT_SECONDS = 30.0
# Redis 通但平台未下发队列时，等待这么久再启用本地兜底。
_SERVER_ASSIGNMENT_WAIT_SECONDS = 15.0


class QueueControlClient:
    """将中心平台命令转为本机 Worker 生命周期操作。"""

    # 创建不落本地状态文件的监管器，并准备 Redis 命令循环。
    def __init__(
        self,
        settings: QueueClientSettings,
        redis_client: QueueControlRedisClient | None = None,
        *,
        supervisor: QueueSupervisor | None = None,
        worker_target=None,
        enable_account_session: bool = True,
    ):
        self.settings = settings
        self.redis_client = redis_client or QueueControlRedisClient(settings.redis_url)
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._account_session_manager = None
        self._account_session_coordinator = None
        self._enable_account_session = enable_account_session
        # 当前是否处于本地兜底态；平台下发 assign/sync 后退出兜底。
        self._fallback_active = False
        self._fallback_miss_count = 0
        self._server_wait_started_at = 0.0
        if supervisor is not None:
            self.supervisor = supervisor
        else:
            supervisor_kwargs = {}
            if worker_target is not None:
                supervisor_kwargs["worker_target"] = worker_target
            self.supervisor = QueueSupervisor(
                [],
                project_root=settings.project_root,
                drain_timeout_seconds=settings.drain_timeout_seconds,
                persist_state=False,
                # 本地模式不向中心平台上报状态，避免无 Redis 时刷错误。
                status_observer=None if settings.uses_local_queues else self._publish_status,
                **supervisor_kwargs,
            )
        atexit.register(self.stop)

    # 启动本机监管器，并按开关进入本地监听或服务端命令循环。
    def run_forever(self) -> None:
        try:
            if self._enable_account_session:
                self._start_account_session_coordinator()
            if self.settings.uses_local_queues:
                self._run_local_mode()
                return
            self._run_server_mode()
        finally:
            self.stop()

    # 停止命令循环和本机监管器。
    def stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self.supervisor.stop()
        if self._account_session_manager is not None:
            try:
                self._account_session_coordinator.close()
            finally:
                self._account_session_manager.shutdown()
                self._account_session_manager = None
                self._account_session_coordinator = None

    def _start_account_session_coordinator(self) -> None:
        if self._account_session_manager is not None:
            return
        manager, coordinator = create_account_session_manager(
            AccountSessionSettings.from_app_settings(Settings.from_env())
        )
        self._account_session_manager = manager
        self._account_session_coordinator = coordinator
        self.supervisor.set_account_session_coordinator(coordinator)

    # 完全按本地 RPA_QUEUES 启动监听，不连接中心控制平台。
    def _run_local_mode(self) -> None:
        info("QUEUE_ASSIGNMENT_SOURCE=local：按 RPA_QUEUES 启动监听，不连接控制平台")
        self._apply_local_queues()
        self.supervisor.start()
        self._stop_event.wait()

    # 将本地环境变量中的队列集合登记到监管器。
    def _apply_local_queues(self) -> None:
        queues = self.settings.fallback_queues
        if not queues:
            raise RuntimeError("QUEUE_ASSIGNMENT_SOURCE=local 时必须配置 RPA_QUEUES")
        for queue_name in queues:
            self.supervisor.assign(queue_name)

    # 走服务端下发：心跳上报、消费 Redis 命令；连不上或等不到下发时启用本地兜底。
    def _run_server_mode(self) -> None:
        self.supervisor.start()
        self._server_wait_started_at = time.monotonic()
        self._safe_publish_heartbeat()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="queue-control-client-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        backoff = _INITIAL_RECONNECT_SECONDS
        while not self._stop_event.is_set():
            if self._poll_command_cycle():
                backoff = _INITIAL_RECONNECT_SECONDS
                continue
            self._stop_event.wait(backoff)
            backoff = min(backoff * 2, _MAX_RECONNECT_SECONDS)

    # 读取并处理一批控制命令；Redis 不可达或平台未下发时启用兜底。
    def _poll_command_cycle(self) -> bool:
        try:
            messages = self.redis_client.read_commands(
                self.settings.device_id, socket.gethostname()
            )
        except Exception as exc:
            if not is_control_plane_unavailable(exc):
                raise
            self._ensure_fallback_queues(exc)
            return False
        for message_id, command in messages:
            self._handle_message(message_id, command)
        # Redis 通不代表平台已下发队列；超时仍无分配时先用本地 RPA_QUEUES。
        self._maybe_fallback_without_assignment()
        return True

    # 首次心跳失败时也走兜底，避免启动即因 Redis 不可达退出。
    def _safe_publish_heartbeat(self) -> None:
        try:
            self._publish_heartbeat()
        except Exception as exc:
            if not is_control_plane_unavailable(exc):
                raise
            self._ensure_fallback_queues(exc)

    # Redis 通但迟迟收不到平台分配时，用本地队列先顶上。
    def _maybe_fallback_without_assignment(self) -> None:
        if self._fallback_active or self.supervisor.queue_statuses():
            return
        elapsed = time.monotonic() - self._server_wait_started_at
        if elapsed < _SERVER_ASSIGNMENT_WAIT_SECONDS:
            return
        self._ensure_fallback_queues("平台未在时限内下发队列")

    # 确保本地 RPA_QUEUES 中的队列正在监听。
    def _ensure_fallback_queues(self, reason: BaseException | str) -> None:
        fallback = self.settings.fallback_queues
        if not fallback:
            self._fallback_miss_count += 1
            if self._fallback_miss_count == 1 or self._fallback_miss_count % 10 == 0:
                warn(f"无法启用本地兜底（{reason}），且未配置 RPA_QUEUES，将继续等待平台下发")
            self._fallback_active = True
            return
        existing = {item["name"]: item for item in self.supervisor.queue_statuses()}
        started: list[str] = []
        for queue_name in fallback:
            runtime = existing.get(queue_name)
            if runtime is None:
                self.supervisor.assign(queue_name)
                started.append(queue_name)
            elif runtime["state"] == "FAILED":
                # assign 不会拉起 FAILED 队列，兜底时主动重启。
                self.supervisor.restart(queue_name)
                started.append(queue_name)
        if started and not self._fallback_active:
            warn(f"启用本地兜底队列（{reason}）：{started}")
        elif started:
            warn(f"补齐本地兜底队列（{reason}）：{started}")
        elif not self._fallback_active:
            warn(f"已有队列继续运行，并保持本地兜底状态（{reason}）")
        self._fallback_active = True

    # 平台真正下发队列后退出兜底态，后续以服务端列表为准。
    def _mark_server_assignment_applied(self) -> None:
        if not self._fallback_active:
            return
        info("已收到平台队列下发，退出本地兜底")
        self._fallback_active = False
        self._fallback_miss_count = 0

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
            self._mark_server_assignment_applied()
        elif action == "sync":
            self._sync_assignments(command.get("assignments") or [])
            self._mark_server_assignment_applied()
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
                "assignmentSource": self.settings.assignment_source,
                "fallbackActive": self._fallback_active,
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

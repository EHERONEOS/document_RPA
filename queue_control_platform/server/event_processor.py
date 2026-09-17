"""将 Redis 中的 Agent 事件可靠落库到 MySQL。"""
from __future__ import annotations

import threading


class EventProcessor:
    """持续消费状态事件流，并更新中心平台数据库。"""

    # 保存事件流和仓储，并初始化用于停止后台线程的信号。
    def __init__(self, repository, bus, consumer_name: str = "platform-web"):
        self.repository = repository
        self.bus = bus
        self.consumer_name = consumer_name
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # 启动一个后台线程持续处理设备状态事件。
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self.run_forever, name="queue-control-event-processor", daemon=True
        )
        self._thread.start()

    # 停止后台事件处理线程。
    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    # 循环读取 Redis Stream，单条成功落库后才确认消息。
    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                self._stop_event.wait(1)

    # 处理当前可读取的一批状态事件，方便单元测试直接调用。
    def run_once(self) -> int:
        processed = 0
        for event_id, event in self.bus.read_events(self.consumer_name):
            try:
                accepted = self.repository.record_agent_event(event_id, event)
            except ValueError:
                # 注册信息无效的事件无法在后续重试中自行恢复，确认后跳过以免阻塞流。
                self.bus.acknowledge_event(event_id)
                continue
            if accepted and event.get("type") == "heartbeat":
                self._reconcile_assignments(
                    str(event.get("deviceId") or ""),
                    event.get("queues") or [],
                )
            self.bus.acknowledge_event(event_id)
            processed += 1
        return processed

    # 仅在本机队列与中心分配不一致时下发 sync，避免每次心跳都淹没真实控制命令。
    def _reconcile_assignments(self, device_id: str, reported_queues: list) -> None:
        assignments = self.repository.list_device_assignments(device_id)
        expected = {
            str(item["queueName"]).upper(): str(item["desiredState"]).upper()
            for item in assignments
        }
        reported = {
            str(item.get("name") or "").upper(): str(
                item.get("desiredState") or ""
            ).upper()
            for item in reported_queues
            if str(item.get("name") or "").strip()
        }
        if expected == reported:
            return
        self.bus.send_command(
            device_id,
            {"action": "sync", "assignments": assignments},
        )

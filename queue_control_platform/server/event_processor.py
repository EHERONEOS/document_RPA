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
                self._send_assignment_snapshot(str(event.get("deviceId") or ""))
            self.bus.acknowledge_event(event_id)
            processed += 1
        return processed

    # 在设备心跳后下发完整分配快照，使重启后的 Agent 自动恢复本机队列。
    def _send_assignment_snapshot(self, device_id: str) -> None:
        assignments = self.repository.list_device_assignments(device_id)
        self.bus.send_command(
            device_id,
            {"action": "sync", "assignments": assignments},
        )

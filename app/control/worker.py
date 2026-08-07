"""单个队列消费者的子进程入口。"""
from __future__ import annotations

import queue
import time
from typing import Any


# 作为独立进程入口，启动并协作式排空一个队列消费者。
def run_queue_worker(queue_name: str, commands, events, account_session_coordinator=None) -> None:
    """运行一个队列，直到收到本地排空命令。"""
    try:
        from app.queue.consumer import create_queue_consumer

        consumer = create_queue_consumer(queue_name, account_session_coordinator)
        consumer.start_consuming_message()
        ready_deadline = time.monotonic() + 30
        while not consumer.wait_until_ready(timeout=0.1):
            if consumer.last_error or time.monotonic() >= ready_deadline:
                break
        if not consumer.wait_until_ready(timeout=0):
            error = consumer.last_error or "30 秒内未建立 RabbitMQ 消费订阅"
            events.put({"type": "failed", "queue": queue_name, "error": error})
            return

        events.put({"type": "ready", "queue": queue_name})
        while True:
            if consumer.last_error:
                events.put(
                    {"type": "failed", "queue": queue_name, "error": consumer.last_error}
                )
                return
            try:
                command: dict[str, Any] = commands.get(timeout=0.25)
            except queue.Empty:
                continue

            if command.get("type") != "drain":
                continue

            events.put({"type": "draining", "queue": queue_name})
            consumer.request_drain()
            timeout = max(float(command.get("timeout", 0)), 0)
            deadline = time.monotonic() + timeout
            timeout_reported = False
            while not consumer.wait_until_drained(timeout=0.25):
                if not timeout_reported and timeout and time.monotonic() >= deadline:
                    timeout_reported = True
                    events.put({"type": "drain_timeout", "queue": queue_name})

            if consumer.last_error:
                events.put(
                    {"type": "failed", "queue": queue_name, "error": consumer.last_error}
                )
            else:
                events.put({"type": "paused", "queue": queue_name})
            return
    except Exception as exc:
        events.put({"type": "failed", "queue": queue_name, "error": str(exc)})

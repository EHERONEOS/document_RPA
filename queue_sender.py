"""从应用包外部向 RabbitMQ 发送 RPA 任务消息。

用法：
    uv run python queue_sender.py

    # 覆盖目标队列，或为每个指定单号分别发送一条消息。
    uv run python queue_sender.py --queue FHT_MSCGW_SI --job-number 96543453643
"""
from __future__ import annotations

import argparse
import atexit
from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from typing import Any

from app.config import bootstrap_environment

bootstrap_environment()

from funboost import (
    BrokerEnum,
    PriorityConsumingControlConfig,
    PublisherParams,
    get_publisher,
)

# 导入该模块会注册项目自定义的 RabbitMQ 发布器和消费者类型。
from app.queue import rabbitmq  # noqa: F401


_publisher_lock = RLock()
_publishers: dict[str, Any] = {}
_exit_handler_registered = False
DEFAULT_MESSAGE_PATH = "./message_list/FHT_MSCGW_SI.json"


def send_queue_message(
    queue_name: str,
    task: dict[str, Any],
    *,
    delay: int = 0,
    passive: bool = True,
) -> bool:
    """向 RabbitMQ 队列发送一条任务消息。

    Worker 消费者要求 funboost 接收 ``task`` 关键字参数，因此发布消息包装为
    ``{"task": task}``。
    """
    normalized_queue_name = _normalize_queue_name(queue_name)
    normalized_task = _normalize_task(task, normalized_queue_name)
    priority_control_config = (
        PriorityConsumingControlConfig(countdown=delay) if delay else None
    )

    with _publisher_lock:
        publisher = _get_publisher(normalized_queue_name, passive=passive)
        publisher.publish(
            msg={"task": normalized_task},
            priority_control_config=priority_control_config,
        )
    return True


def send_queue_messages_for_job_numbers(
    queue_name: str,
    task: dict[str, Any],
    job_numbers: list[str],
    *,
    delay: int = 0,
    passive: bool = True,
) -> None:
    """将指定单号依次写入 blNo、jobNo 后发送到队列。"""
    for job_number in job_numbers:
        message_task = deepcopy(task)
        content = message_task.setdefault("content", {})
        if not isinstance(content, dict):
            raise TypeError("task.content 必须是 dict")
        content["blNo"] = job_number
        content["jobNo"] = job_number
        send_queue_message(
            queue_name,
            message_task,
            delay=delay,
            passive=passive,
        )
        print(f"sent queue={queue_name.strip().upper()} job_no={job_number}")


def close_publishers() -> None:
    """关闭全部缓存的发布器连接。"""
    with _publisher_lock:
        publishers = list(_publishers.values())
        _publishers.clear()

    for publisher in publishers:
        try:
            publisher.close()
        except Exception:
            pass


def _get_publisher(queue_name: str, *, passive: bool):
    global _exit_handler_registered

    cache_key = f"{queue_name}:{int(passive)}"
    publisher = _publishers.get(cache_key)
    if publisher is None:
        publisher = get_publisher(
            PublisherParams(
                queue_name=queue_name,
                logger_prefix=queue_name,
                broker_exclusive_config=_broker_config(passive=passive),
                broker_kind=BrokerEnum.RABBITMQ_AMQPSTORM,
            )
        )
        _publishers[cache_key] = publisher

    if not _exit_handler_registered:
        atexit.register(close_publishers)
        _exit_handler_registered = True
    return publisher


def _broker_config(*, passive: bool) -> dict[str, Any]:
    return {
        "x-max-priority": None,
        "durable": True,
        "passive": passive,
        "x-dead-letter-exchange": "dlx_exchange",
        "x-dead-letter-routing-key": "dlx_routing_key",
    }


def _normalize_queue_name(queue_name: str) -> str:
    normalized = str(queue_name or "").strip().upper()
    if not normalized:
        raise ValueError("queue_name 不能为空")
    return normalized


def _normalize_task(task: dict[str, Any], queue_name: str) -> dict[str, Any]:
    if not isinstance(task, dict):
        raise TypeError("task 必须是 dict")

    normalized_task = dict(task)
    normalized_task["rpaTaskTopic"] = str(
        normalized_task.get("rpaTaskTopic") or queue_name
    ).strip().upper()
    return normalized_task


def _load_task(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("task"), dict):
        return payload["task"]
    if isinstance(payload, dict):
        return payload
    raise TypeError("message JSON 必须是对象，或包含 task 对象")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one RPA task message to RabbitMQ.")
    parser.add_argument(
        "--queue",
        help="目标队列名；默认使用消息中的 rpaTaskTopic",
    )
    parser.add_argument(
        "--message",
        default=DEFAULT_MESSAGE_PATH,
        help=f"任务消息 JSON 文件路径（默认：{DEFAULT_MESSAGE_PATH}）",
    )
    parser.add_argument(
        "--job-number",
        action="append",
        default=[],
        help="覆写消息中的 content.blNo 和 content.jobNo；可重复指定",
    )
    parser.add_argument("--delay", type=int, default=0, help="延迟发送秒数")
    parser.add_argument(
        "--declare",
        action="store_true",
        help="队列不存在时允许声明队列；默认只向已存在队列发送",
    )
    args = parser.parse_args()

    task = _load_task(args.message)
    queue_name = args.queue or task.get("rpaTaskTopic")
    if args.job_number:
        send_queue_messages_for_job_numbers(
            queue_name,
            task,
            args.job_number,
            delay=args.delay,
            passive=not args.declare,
        )
        return

    send_queue_message(
        queue_name,
        task,
        delay=args.delay,
        passive=not args.declare,
    )
    print(f"sent queue={_normalize_queue_name(queue_name)} message={args.message}")


if __name__ == "__main__":
    main()

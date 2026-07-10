from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from app.core.task.errors import QueueNameError


@dataclass
class TaskContext:
    """单条 RPA 消息的运行上下文。"""

    raw_message: dict[str, Any]
    task: dict[str, Any]
    queue_name: str
    rpa_message_id: str
    customer_code: str
    carrier_code: str
    business_code: str
    website_info: dict[str, Any]
    content: dict[str, Any]
    remain_content: dict[str, Any]
    runtime_mode: str = "queue"
    enable_notify: bool = True
    enable_result_publish: bool = True
    enable_record: bool | None = None


def parse_queue_name(queue_name: str) -> tuple[str, str, str]:
    """解析客户_船司_业务格式的队列名。"""
    parts = [part.strip().upper() for part in queue_name.split("_") if part.strip()]
    if len(parts) != 3:
        raise QueueNameError(f"队列名格式错误：{queue_name}")
    return parts[0], parts[1], parts[2]


def copy_content(content: dict[str, Any]) -> dict[str, Any]:
    """深拷贝填单内容，用于追踪未填字段。"""
    return copy.deepcopy(content)

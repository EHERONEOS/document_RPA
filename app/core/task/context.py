import copy
from dataclasses import dataclass

from app.core.task.router import resolve_queue_route


@dataclass
class TaskContext:
    """单条 RPA 消息的运行上下文。"""
    task: dict
    task_id: str | int
    queue_name: str
    rpa_message_id: str
    customer_code: str
    carrier_code: str
    business_code: str
    website_info: dict
    content: dict
    remain_content: dict
    runtime_mode: str = "queue"
    enable_notify: bool = True
    enable_result_publish: bool = True


def parse_queue_name(queue_name):
    """返回完整队列名注册的客户、船司和业务信息。"""
    route = resolve_queue_route(queue_name)
    return route.customer_code, route.carrier_code, route.business_code


def copy_content(content):
    """深拷贝填单内容，用于追踪未填字段。"""
    return copy.deepcopy(content)

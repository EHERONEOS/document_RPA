from app.core.task.context import TaskContext, copy_content, parse_queue_name
from app.core.task.errors import MessageParseError


def _require_dict(value, name):
    if not isinstance(value, dict):
        raise MessageParseError(f"{name} 必须是对象")
    return value


def build_task_context(
    task,
    *,
    runtime_mode="queue",
    enable_notify=True,
    enable_result_publish=True,
    enable_record=None,
):
    """从原始队列 task 消息构建任务上下文。"""
    # task = _require_dict(raw_message, "task")
    queue_name = str(task.get("rpaTaskTopic") or "").strip().upper()
    if not queue_name:
        raise MessageParseError("task.rpaTaskTopic 不能为空")

    customer_code, carrier_code, business_code = parse_queue_name(queue_name)
    website_info = _require_dict(task.get("websiteInfo"), "task.websiteInfo")
    content = _require_dict(task.get("content"), "task.content")
    rpa_message_id = str(task.get("rpaMessageId") or "").strip()
    task_id = task.get("id")
    if not rpa_message_id:
        raise MessageParseError("task.rpaMessageId 不能为空")

    return TaskContext(
        # raw_message=raw_message,
        task=task,
        task_id=task_id,
        queue_name=queue_name,
        rpa_message_id=rpa_message_id,
        customer_code=customer_code,
        carrier_code=carrier_code,
        business_code=business_code,
        website_info=website_info,
        content=content,
        remain_content=copy_content(content),
        runtime_mode=runtime_mode,
        enable_notify=enable_notify,
        enable_result_publish=enable_result_publish,
        enable_record=enable_record,
    )

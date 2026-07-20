from app.core.task.dispatcher import dispatch_context
from app.queue.message import build_task_context
from app.queue.booster import RpaBoosterParams


def handle_message(raw_message):
    """处理单条队列消息。"""
    context = build_task_context(raw_message)
    return dispatch_context(context)


def build_raw_message(message=None, task=None, **kwargs):
    """兼容 funboost 传入整包消息或 task 关键字参数两种形式。"""
    if isinstance(message, dict) and "task" in message:
        return message
    if isinstance(task, dict):
        return {"task": task}
    if kwargs:
        return kwargs
    return message or {}


def start_consumers(queue_names):
    """启动 funboost 消费者。"""
    try:
        from funboost import boost
    except Exception as exc:
        raise RuntimeError(f"funboost 未安装或不可用：{exc}") from exc

    consumers = []
    for queue_name in queue_names:

        @boost(
            RpaBoosterParams(
                queue_name=queue_name,
                logger_prefix=queue_name,
            )
        )
        def consume(message=None, task=None, _queue_name=queue_name, **kwargs):
            raw_message = build_raw_message(message=message, task=task, **kwargs)
            return handle_message(raw_message)

        consumers.append(consume)

    for consume in consumers:
        consume.consume()

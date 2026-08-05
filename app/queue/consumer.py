import json
from datetime import datetime
from pathlib import Path
from time import sleep

from app.core.browser.session_lock import BrowserProfileLock
from app.core.task.dispatcher import dispatch_context
from app.queue.message import build_task_context


def handle_message(task):
    """处理单条队列消息。"""
    context = build_task_context(task)
    # 不同队列可能复用同一个网站信息和 Chromium profile，需串行执行整个任务生命周期。
    with BrowserProfileLock(context):
        return dispatch_context(context)


def save_task_message(task, queue_name):
    """将队列 task 消息保存到本地文件。"""
    if not isinstance(task, dict):
        return

    output_dir = Path("runtime/task_messages") / str(queue_name).lower()
    output_dir.mkdir(parents=True, exist_ok=True)

    message_id = str(task.get("rpaMessageId") or "").strip()
    filename = message_id or datetime.now().strftime("%Y%m%d%H%M%S%f")
    output_path = output_dir / f"{filename}.json"
    output_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")


def create_queue_consumer(queue_name):
    """为单个 RabbitMQ 队列创建可由本地控制台管理的消费者。"""
    try:
        from app.queue.booster import RpaBoosterParams
        from app.queue.pausable_rabbitmq import PausableRabbitmqConsumer
        # 导入该模块会注册项目自定义的 RabbitMQ 发布器。
        from app.queue import rabbitmq  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(f"funboost 未安装或不可用：{exc}") from exc

    def consume(task=None):
        return handle_message(task or {})

    return PausableRabbitmqConsumer(
        RpaBoosterParams(
            queue_name=queue_name,
            logger_prefix=queue_name,
            consuming_function=consume,
        )
    )


def start_consumers(queue_names):
    """兼容在当前进程中启动消费者的旧入口。

    ``app.main`` 现通过 ``QueueSupervisor`` 为每个配置队列分配独立进程；保留
    此函数以兼容既有调用方。
    """
    consumers = [create_queue_consumer(queue_name) for queue_name in queue_names]
    for consumer in consumers:
        consumer.start_consuming_message()

    # 此模式下 Funboost 在后台线程调度 AMQP 循环，保留旧入口的阻塞行为。
    while True:
        sleep(60)

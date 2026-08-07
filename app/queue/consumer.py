import json
import os
from datetime import datetime
from pathlib import Path
from time import sleep

from app.core.browser.session_lock import build_account_session_key, build_browser_profile_name
from app.core.task.dispatcher import dispatch_context
from app.queue.message import build_task_context


_LOCAL_ACCOUNT_COORDINATOR = None


def _get_local_account_coordinator():
    """Provide the legacy in-process consumer entry with the same slot rules."""
    global _LOCAL_ACCOUNT_COORDINATOR
    if _LOCAL_ACCOUNT_COORDINATOR is None:
        from app.config.settings import Settings
        from app.core.scheduler.account_session import AccountSessionCoordinator, AccountSessionSettings

        _LOCAL_ACCOUNT_COORDINATOR = AccountSessionCoordinator(
            AccountSessionSettings.from_app_settings(Settings.from_env())
        )
    return _LOCAL_ACCOUNT_COORDINATOR


def handle_message(task, account_session_coordinator=None):
    """处理单条队列消息。"""
    context = build_task_context(task)
    coordinator = account_session_coordinator or _get_local_account_coordinator()
    account_key = build_account_session_key(context)
    lease = coordinator.acquire_slot(
        account_key,
        build_browser_profile_name(context),
        owner_pid=os.getpid(),
    )
    context.browser_lease = lease
    context.account_session_coordinator = coordinator
    try:
        return dispatch_context(context)
    finally:
        coordinator.release_slot(account_key, lease["lease_id"])


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


def create_queue_consumer(queue_name, account_session_coordinator=None):
    """为单个 RabbitMQ 队列创建可由本地控制台管理的消费者。"""
    try:
        from app.queue.booster import RpaBoosterParams
        from app.queue.pausable_rabbitmq import PausableRabbitmqConsumer
        # 导入该模块会注册项目自定义的 RabbitMQ 发布器。
        from app.queue import rabbitmq  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(f"funboost 未安装或不可用：{exc}") from exc

    def consume(task=None):
        return handle_message(task or {}, account_session_coordinator)

    from app.config.settings import Settings

    settings = Settings.from_env()

    return PausableRabbitmqConsumer(
        RpaBoosterParams(
            queue_name=queue_name,
            logger_prefix=queue_name,
            consuming_function=consume,
            concurrent_num=settings.queue_concurrent_num,
            qps=settings.queue_qps,
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

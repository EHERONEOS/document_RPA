from app.config.queue_config import QueueWorkerConfig
from app.core.logging.logger import log
from app.core.task.dispatcher import dispatch_context
from app.queue.message import build_task_context


def handle_message(raw_message: dict):
    """处理单条队列消息。"""
    context = build_task_context(raw_message)
    return dispatch_context(context)


def _normalize_config(config: QueueWorkerConfig | list[str]) -> QueueWorkerConfig:
    """兼容旧调用方式，将队列名列表转换为配置对象。"""
    if isinstance(config, QueueWorkerConfig):
        return config
    return QueueWorkerConfig(
        queue_names=config,
        rabbitmq_host="",
        rabbitmq_port=0,
        rabbitmq_user="",
        rabbitmq_password="",
    )


def start_consumers(
    config: QueueWorkerConfig | list[str],
    *,
    boost_decorator=None,
    broker_enum=None,
) -> list:
    """启动 funboost 消费者。"""
    worker_config = _normalize_config(config)
    if boost_decorator is None or broker_enum is None:
        try:
            from funboost import BrokerEnum, boost
        except Exception as exc:
            raise RuntimeError(f"funboost 未安装或不可用：{exc}") from exc
        boost_decorator = boost
        broker_enum = BrokerEnum

    log(
        "启动队列消费者 "
        f"RabbitMQ={worker_config.connection_summary()} "
        f"queues={worker_config.queue_names}"
    )
    consumers = []
    for queue_name in worker_config.queue_names:

        @boost_decorator(queue_name, broker_kind=broker_enum.RABBITMQ_AMQPSTORM)
        def consume(message, _queue_name=queue_name):
            return handle_message(message)

        consumers.append(consume)

    for consume in consumers:
        consume.consume()

    return consumers

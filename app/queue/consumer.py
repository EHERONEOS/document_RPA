from app.core.task.dispatcher import dispatch_context
from app.queue.message import build_task_context
from app.queue.rabbitmq import RabbitmqPublisherWithDlx, build_rabbitmq_broker_config


def handle_message(raw_message):
    """处理单条队列消息。"""
    context = build_task_context(raw_message)
    return dispatch_context(context)


def start_consumers(queue_names):
    """启动 funboost 消费者。"""
    try:
        from funboost import BoosterParams, BrokerEnum, boost
    except Exception as exc:
        raise RuntimeError(f"funboost 未安装或不可用：{exc}") from exc

    consumers = []
    for queue_name in queue_names:

        @boost(
            BoosterParams(
                queue_name=queue_name,
                broker_kind=BrokerEnum.RABBITMQ_AMQPSTORM,
                broker_exclusive_config=build_rabbitmq_broker_config(),
                publisher_override_cls=RabbitmqPublisherWithDlx,
            )
        )
        def consume(message, _queue_name=queue_name):
            return handle_message(message)

        consumers.append(consume)

    for consume in consumers:
        consume.consume()

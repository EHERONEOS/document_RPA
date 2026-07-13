from funboost import BrokerEnum, BoosterParams

from app.queue.rabbitmq import RabbitmqPublisherWithDlx, build_rabbitmq_broker_config


class RpaBoosterParams(BoosterParams):
    """项目默认 funboost 消费者参数。"""

    broker_kind: str = BrokerEnum.RABBITMQ_AMQPSTORM
    queue_name: str = ""
    qps: float = 1
    broker_exclusive_config: dict = build_rabbitmq_broker_config()
    is_push_to_dlx_queue_when_retry_max_times: bool = True
    concurrent_num: int = 1
    # max_retry_times: int = 0
    logger_prefix: str = ""
    is_support_remote_kill_task: bool = True
    publisher_override_cls: type = RabbitmqPublisherWithDlx

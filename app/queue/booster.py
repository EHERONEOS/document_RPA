import os

from funboost import BrokerEnum, BoosterParams

from app.config.types import str_to_bool


class RpaBoosterParams(BoosterParams):
    """项目默认 funboost 消费者参数。"""

    # 使用 RabbitMQ 作为消息队列，并指定 funboost 使用 amqpstorm 客户端实现。
    broker_kind: str = BrokerEnum.RABBITMQ_AMQPSTORM
    # 队列名称，默认空字符串，通常由具体消费者覆盖。
    queue_name: str = ""
    # 每秒消费速率限制，默认每秒最多处理 1 个任务。
    qps: float = 1
    # RabbitMQ 专属配置，包括队列持久化、死信交换机、死信路由键等。
    broker_exclusive_config: dict = {
        # RabbitMQ 优先级队列最大优先级，None 表示不启用优先级队列。
        "x-max-priority": None,
        # 队列是否持久化，True 表示 RabbitMQ 重启后队列仍然保留。
        "durable": True,
        # 是否只检查队列是否存在，True 表示队列不存在时直接报错，不主动创建。
        "passive": True,
        # 死信交换机名称，消费失败达到最大重试次数后消息会投递到该交换机。
        "x-dead-letter-exchange": "dlx_exchange",
        # 死信路由键，用于将死信消息路由到指定死信队列。
        "x-dead-letter-routing-key": "dlx_routing_key",
        # "dead_letter_queue": "dlx_queue",
    }
    # 任务重试达到最大次数后，是否推送到死信队列。
    is_push_to_dlx_queue_when_retry_max_times: bool = True
    # 并发消费数量，默认只开 1 个并发 worker。
    concurrent_num: int = 1
    # 最大重试次数，当前注释掉不生效。
    max_retry_times: int = 0
    # 日志前缀，用于区分不同消费者日志。
    logger_prefix: str = ""
    # 是否支持远程杀死正在执行的任务，默认通过环境变量关闭。
    is_support_remote_kill_task: bool = str_to_bool(os.getenv("ENABLE_REMOTE_KILL_TASK", "false"))

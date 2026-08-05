from funboost import BrokerEnum, register_custom_broker
from funboost.consumers.rabbitmq_amqpstorm_consumer import RabbitmqConsumerAmqpStorm
from funboost.publishers.rabbitmq_amqpstorm_publisher import RabbitmqPublisherUsingAmqpStorm


class RabbitmqPublisherWithDlx(RabbitmqPublisherUsingAmqpStorm):
    """声明已有 RabbitMQ 队列时携带死信交换机参数。"""

    def custom_init(self) -> None:
        arguments = {}
        broker_config = self.publisher_params.broker_exclusive_config
        if broker_config.get("x-max-priority"):
            arguments["x-max-priority"] = broker_config["x-max-priority"]
        if broker_config.get("x-dead-letter-exchange"):
            arguments["x-dead-letter-exchange"] = broker_config["x-dead-letter-exchange"]
        if broker_config.get("x-dead-letter-routing-key"):
            arguments["x-dead-letter-routing-key"] = broker_config["x-dead-letter-routing-key"]
        # 现有项目参数使用 ``durable``；兼容已部署配置中的旧键
        # ``queue_durable``。
        self._queue_durable = broker_config.get(
            "queue_durable", broker_config.get("durable", True)
        )
        self.queue_declare_params = {
            "queue": self._queue_name,
            "durable": self._queue_durable,
            "arguments": arguments,
            "auto_delete": False,
            "passive": bool(broker_config.get("passive", False)),
        }


register_custom_broker(
    BrokerEnum.RABBITMQ_AMQPSTORM,
    RabbitmqPublisherWithDlx,
    RabbitmqConsumerAmqpStorm,
)

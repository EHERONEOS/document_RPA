from funboost import BrokerEnum
from funboost.core.broker_kind__exclusive_config_default_define import register_broker_exclusive_config_default
from funboost.publishers.rabbitmq_amqpstorm_publisher import RabbitmqPublisherUsingAmqpStorm

from app.config.rabbitmq import RabbitmqSettings


register_broker_exclusive_config_default(
    BrokerEnum.RABBITMQ_AMQPSTORM,
    {
        "queue_durable": True,
        "passive": False,
        "x-max-priority": None,
        "no_ack": False,
        "x-dead-letter-exchange": None,
        "x-dead-letter-routing-key": None,
    },
)


def build_rabbitmq_broker_config():
    """构建 RabbitMQ 队列声明配置。"""
    return RabbitmqSettings.from_env().to_broker_exclusive_config()


class RabbitmqPublisherWithDlx(RabbitmqPublisherUsingAmqpStorm):
    """声明已有 RabbitMQ 队列时携带死信交换机参数。"""

    def custom_init(self):
        arguments = {}
        broker_config = self.publisher_params.broker_exclusive_config
        if broker_config.get("x-max-priority"):
            arguments["x-max-priority"] = broker_config["x-max-priority"]
        if broker_config.get("x-dead-letter-exchange"):
            arguments["x-dead-letter-exchange"] = broker_config["x-dead-letter-exchange"]
        if broker_config.get("x-dead-letter-routing-key"):
            arguments["x-dead-letter-routing-key"] = broker_config["x-dead-letter-routing-key"]
        self._queue_durable = broker_config["queue_durable"]
        self.queue_declare_params = {
            "queue": self._queue_name,
            "durable": self._queue_durable,
            "arguments": arguments,
            "auto_delete": False,
            "passive": bool(broker_config.get("passive", False)),
        }

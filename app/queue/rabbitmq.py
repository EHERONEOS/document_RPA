import os

from funboost.publishers.rabbitmq_amqpstorm_publisher import RabbitmqPublisherUsingAmqpStorm


def build_rabbitmq_broker_config():
    """构建 RabbitMQ 队列声明配置。"""
    config = {
        "queue_durable": True,
        "x-max-priority": None,
        "no_ack": False,
    }
    dead_letter_exchange = os.getenv("RABBITMQ_DEAD_LETTER_EXCHANGE", "dlx_exchange").strip()
    if dead_letter_exchange:
        config["x-dead-letter-exchange"] = dead_letter_exchange
    dead_letter_routing_key = os.getenv("RABBITMQ_DEAD_LETTER_ROUTING_KEY", "dlx_routing_key").strip()
    if dead_letter_routing_key:
        config["x-dead-letter-routing-key"] = dead_letter_routing_key
    return config


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
        }

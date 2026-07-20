import os
from dataclasses import dataclass
from urllib.parse import quote_plus



@dataclass(frozen=True)
class RabbitmqSettings:
    """RabbitMQ 连接和队列声明配置。"""

    user: str
    password: str
    host: str
    port: int
    virtual_host: str
    # dead_letter_exchange: str
    # dead_letter_routing_key: str
    # queue_durable: bool
    # queue_passive: bool
    # no_ack: bool

    @property
    def url(self):
        return f"amqp://{self.user}:{quote_plus(self.password)}@{self.host}:{self.port}/{self.virtual_host}"

    @classmethod
    def from_env(cls):
        return cls(
            user=os.getenv("RABBITMQ_USER", "guest"),
            password=os.getenv("RABBITMQ_PASSWORD", "guest"),
            host=os.getenv("RABBITMQ_HOST", "192.168.60.106"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            virtual_host=os.getenv("RABBITMQ_VIRTUAL_HOST", "/"),
            # dead_letter_exchange="dlx_exchange",
            # dead_letter_routing_key="dlx_routing_key",
            # queue_durable=True,
            # queue_passive=False,
            # no_ack=False,
        )

    # def to_broker_exclusive_config(self):
    #     config = {
    #         "queue_durable": self.queue_durable,
    #         "passive": self.queue_passive,
    #         # "x-max-priority": 0,
    #         # "no_ack": self.no_ack,
    #     }
    #     if self.dead_letter_exchange:
    #         config["x-dead-letter-exchange"] = self.dead_letter_exchange
    #     if self.dead_letter_routing_key:
    #         config["x-dead-letter-routing-key"] = self.dead_letter_routing_key
    #     return config

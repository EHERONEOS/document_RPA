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

    @property
    def url(self):
        return f"amqp://{self.user}:{quote_plus(self.password)}@{self.host}:{self.port}/{self.virtual_host}"

    @classmethod
    def from_env(cls):
        """从 Nacos shared-datasource 配置读取 RabbitMQ 连接信息。"""
        from app.config.nacos_config import RABBITMQ_CONFIG

        missing = [name.upper() for name, value in RABBITMQ_CONFIG.items() if not value]
        if missing:
            raise RuntimeError(
                "缺少 RabbitMQ 配置："
                + ", ".join(f"RABBITMQ_{name}" for name in missing)
            )
        return cls(
            user=RABBITMQ_CONFIG["user"],
            password=RABBITMQ_CONFIG["password"],
            host=RABBITMQ_CONFIG["host"],
            port=int(RABBITMQ_CONFIG["port"]),
            virtual_host=RABBITMQ_CONFIG["virtual_host"],
        )

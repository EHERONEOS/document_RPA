import os
from dataclasses import dataclass
from urllib.parse import quote_plus

import yaml


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
        """默认从 Nacos 读取 RabbitMQ 配置，可显式切换为本地环境变量。"""
        source = os.getenv("RABBITMQ_CONFIG_SOURCE", "nacos").strip().lower()
        if source == "nacos":
            values = cls._from_nacos({})
        elif source == "env":
            values = {
                "user": os.getenv("RABBITMQ_USER"),
                "password": os.getenv("RABBITMQ_PASSWORD"),
                "host": os.getenv("RABBITMQ_HOST"),
                "port": os.getenv("RABBITMQ_PORT"),
                "virtual_host": os.getenv("RABBITMQ_VIRTUAL_HOST"),
            }
        else:
            raise RuntimeError(
                "RABBITMQ_CONFIG_SOURCE 仅支持 nacos 或 env"
            )

        missing = [name.upper() for name, value in values.items() if not value]
        if missing:
            raise RuntimeError(
                "缺少 RabbitMQ 配置："
                + ", ".join(f"RABBITMQ_{name}" for name in missing)
            )
        return cls(
            user=values["user"],
            password=values["password"],
            host=values["host"],
            port=int(values["port"]),
            virtual_host=values["virtual_host"],
        )

    @staticmethod
    def _from_nacos(values: dict[str, str | None]) -> dict[str, str | None]:
        """从旧版 Nacos YAML 文档补齐缺失的本地配置。"""
        from app.config.nacos_config import (
            DEFAULT_NACOS_GROUP,
            DEFAULT_NACOS_IP,
            DEFAULT_NACOS_NAMESPACE,
        )
        import nacos

        client = nacos.NacosClient(
            server_addresses=os.getenv(
                "NACOS_SERVER_ADDRESSES",
                os.getenv("nacos_ip", DEFAULT_NACOS_IP),
            ),
            namespace=os.getenv(
                "NACOS_NAMESPACE",
                os.getenv("nacos_namespace", DEFAULT_NACOS_NAMESPACE),
            ),
        )
        config = yaml.safe_load(
            client.get_config(
                data_id=os.getenv("NACOS_RABBITMQ_DATA_ID", "rabbitmq.yml"),
                group=os.getenv("NACOS_GROUP", DEFAULT_NACOS_GROUP),
            )
        ) or {}
        environment = config.get(os.getenv("APP_ENV", "test"), {})
        values = values or {
            "user": None,
            "password": None,
            "host": None,
            "port": None,
            "virtual_host": None,
        }
        for name in values:
            values[name] = values[name] or environment.get(name)
        return values

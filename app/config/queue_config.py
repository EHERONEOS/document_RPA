from dataclasses import dataclass


@dataclass(frozen=True)
class QueueWorkerConfig:
    """队列 Worker 启动配置。"""

    queue_names: list[str]
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str

    def connection_summary(self) -> str:
        """返回不包含密码的连接摘要，便于日志排查。"""
        return f"{self.rabbitmq_host}:{self.rabbitmq_port} user={self.rabbitmq_user}"


def parse_queue_names(raw_value: str) -> list[str]:
    """解析需要消费的队列名列表。"""
    return [item.strip().upper() for item in raw_value.split(",") if item.strip()]

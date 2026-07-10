import os
from dataclasses import dataclass

from app.config.queue_config import QueueWorkerConfig, parse_queue_names


def str_to_bool(value: str | None) -> bool:
    """将环境变量字符串转换为布尔值。"""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    """应用运行配置。"""

    app_env: str
    rpa_queues: list[str]
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str
    browser_port_start: int
    browser_port_end: int
    download_dir: str
    browser_user_data_dir: str
    enable_record: bool

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量读取配置。"""
        return cls(
            app_env=os.getenv("APP_ENV", "local"),
            rpa_queues=parse_queue_names(os.getenv("RPA_QUEUES", "FL_WHL_SI")),
            rabbitmq_host=os.getenv("RABBITMQ_HOST", "192.168.60.106"),
            rabbitmq_port=int(os.getenv("RABBITMQ_PORT", "5672")),
            rabbitmq_user=os.getenv("RABBITMQ_USER", "guest"),
            rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "guest"),
            browser_port_start=int(os.getenv("BROWSER_PORT_START", "9000")),
            browser_port_end=int(os.getenv("BROWSER_PORT_END", "9200")),
            download_dir=os.getenv("DOWNLOAD_DIR", "runtime/downloads"),
            browser_user_data_dir=os.getenv("BROWSER_USER_DATA_DIR", "runtime/browser_profiles"),
            enable_record=str_to_bool(os.getenv("ENABLE_RECORD", "false")),
        )

    def to_queue_worker_config(self) -> QueueWorkerConfig:
        """转换为队列 Worker 启动配置。"""
        return QueueWorkerConfig(
            queue_names=self.rpa_queues,
            rabbitmq_host=self.rabbitmq_host,
            rabbitmq_port=self.rabbitmq_port,
            rabbitmq_user=self.rabbitmq_user,
            rabbitmq_password=self.rabbitmq_password,
        )

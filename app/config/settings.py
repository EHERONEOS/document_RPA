import os
from dataclasses import dataclass

from app.config.rabbitmq import RabbitmqSettings
from app.config.queue_config import parse_queue_names
from app.config.types import str_to_bool


@dataclass(frozen=True)
class Settings:
    """应用运行配置。"""

    app_env: str
    rpa_queues: list
    rabbitmq: RabbitmqSettings
    browser_port_start: int
    browser_port_end: int
    download_dir: str
    browser_user_data_dir: str
    enable_record: bool
    enable_browser: bool

    @classmethod
    def from_env(cls):
        """从环境变量读取配置。"""
        return cls(
            app_env=os.getenv("APP_ENV", "local"),
            rpa_queues=parse_queue_names(os.getenv("RPA_QUEUES", "FL_WHL_SI")),
            rabbitmq=RabbitmqSettings.from_env(),
            browser_port_start=int(os.getenv("BROWSER_PORT_START", "9000")),
            browser_port_end=int(os.getenv("BROWSER_PORT_END", "9200")),
            download_dir=os.getenv("DOWNLOAD_DIR", "runtime/downloads"),
            browser_user_data_dir=os.getenv("BROWSER_USER_DATA_DIR", "runtime/browser_profiles"),
            enable_record=str_to_bool(os.getenv("ENABLE_RECORD", "false")),
            enable_browser=str_to_bool(os.getenv("ENABLE_BROWSER", "false")),
        )

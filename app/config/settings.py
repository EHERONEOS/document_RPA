import os
from dataclasses import dataclass

from app.config.queue_config import parse_queue_names


@dataclass(frozen=True)
class Settings:
    """应用运行配置。"""

    rpa_queues: list
    browser_port_start: int
    browser_port_end: int
    download_dir: str
    browser_user_data_dir: str

    @classmethod
    def from_env(cls):
        """从环境变量读取配置。"""
        return cls(
            rpa_queues=parse_queue_names(os.getenv("RPA_QUEUES", "")),
            browser_port_start=int(os.getenv("BROWSER_PORT_START", "9000")),
            browser_port_end=int(os.getenv("BROWSER_PORT_END", "9200")),
            download_dir=os.getenv("DOWNLOAD_DIR", "runtime/downloads"),
            browser_user_data_dir=os.getenv("BROWSER_USER_DATA_DIR", "runtime/browser_profiles"),
        )

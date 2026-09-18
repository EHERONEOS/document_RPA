import os
from dataclasses import dataclass

from app.config.queue_config import parse_queue_assignment_source, parse_queue_names
from app.config.types import str_to_bool
from app.core.scheduler.browser_cleanup import DEFAULT_BROWSER_CLEANUP_TIME, parse_cleanup_hhmm


@dataclass(frozen=True)
class Settings:
    """应用运行配置。"""

    rpa_queues: list
    queue_assignment_source: str
    browser_port_start: int
    browser_port_end: int
    download_dir: str
    browser_user_data_dir: str
    queue_concurrent_num: int
    queue_qps: float
    account_max_concurrent: int
    account_idle_seconds: int
    browser_cleanup_enabled: bool
    browser_cleanup_time: str
    browser_cleanup_hour: int
    browser_cleanup_minute: int
    browser_cleanup_wait_busy_seconds: int

    @classmethod
    def from_env(cls):
        """从环境变量读取配置。"""
        cleanup_time = os.getenv("BROWSER_CLEANUP_TIME", DEFAULT_BROWSER_CLEANUP_TIME)
        cleanup_hour, cleanup_minute = parse_cleanup_hhmm(cleanup_time)
        return cls(
            rpa_queues=parse_queue_names(os.getenv("RPA_QUEUES", "")),
            queue_assignment_source=parse_queue_assignment_source(
                os.getenv("QUEUE_ASSIGNMENT_SOURCE")
            ),
            browser_port_start=int(os.getenv("BROWSER_PORT_START", "10000")),
            browser_port_end=int(os.getenv("BROWSER_PORT_END", "48000")),
            download_dir=os.getenv("DOWNLOAD_DIR", "runtime/downloads"),
            browser_user_data_dir=os.getenv("BROWSER_USER_DATA_DIR", "runtime/browser_profiles"),
            queue_concurrent_num=int(os.getenv("QUEUE_CONCURRENT_NUM", "3")),
            queue_qps=float(os.getenv("QUEUE_QPS", "3")),
            account_max_concurrent=int(os.getenv("ACCOUNT_MAX_CONCURRENT", "3")),
            account_idle_seconds=int(os.getenv("ACCOUNT_IDLE_SECONDS", "60")),
            browser_cleanup_enabled=str_to_bool(
                os.getenv("BROWSER_CLEANUP_ENABLED", "true")
            ),
            browser_cleanup_time=cleanup_time,
            browser_cleanup_hour=cleanup_hour,
            browser_cleanup_minute=cleanup_minute,
            browser_cleanup_wait_busy_seconds=int(
                os.getenv("BROWSER_CLEANUP_WAIT_BUSY_SECONDS", "1800")
            ),
        )

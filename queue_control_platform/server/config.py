"""中心控制平台的运行配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class PlatformSettings:
    """中心 API、MySQL 和 Redis 的连接配置。"""

    mysql_url: str
    redis_url: str
    host: str
    port: int

    @classmethod
    # 从环境变量读取中心控制平台的连接与监听配置。
    def from_environment(cls) -> "PlatformSettings":
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        return cls(
            mysql_url=os.getenv(
                "QUEUE_CONTROL_MYSQL_URL",
                "mysql://queue_control:queue_control@127.0.0.1:3306/queue_control",
            ),
            redis_url=os.getenv("QUEUE_CONTROL_REDIS_URL", "redis://127.0.0.1:6379/0"),
            host=os.getenv("QUEUE_CONTROL_HOST", "127.0.0.1"),
            port=int(os.getenv("QUEUE_CONTROL_PORT", "8766")),
        )

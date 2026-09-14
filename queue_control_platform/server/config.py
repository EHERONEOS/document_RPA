"""中心控制平台的运行配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

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
    def from_environment(cls) -> PlatformSettings:
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        return cls(
            mysql_url=_flow_development_mysql_url(),
            redis_url=os.getenv("QUEUE_CONTROL_REDIS_URL", "redis://127.0.0.1:6379/0"),
            host=os.getenv("QUEUE_CONTROL_HOST", "127.0.0.1"),
            port=int(os.getenv("QUEUE_CONTROL_PORT", "8766")),
        )


def _flow_development_mysql_url() -> str:
    """返回隔离的流程开发库地址，绝不使用旧控制库。"""
    explicit_url = os.getenv("QUEUE_CONTROL_FLOW_MYSQL_URL", "").strip()
    if explicit_url:
        return _require_flow_development_database(explicit_url)

    legacy_url = os.getenv(
        "QUEUE_CONTROL_MYSQL_URL",
        "mysql://queue_control:queue_control@127.0.0.1:3306/queue_control",
    ).strip()
    parsed = urlparse(legacy_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname:
        raise RuntimeError("QUEUE_CONTROL_MYSQL_URL 必须是有效的 MySQL URL")
    return urlunparse(parsed._replace(path="/queue_control_flow_dev"))


def _require_flow_development_database(mysql_url: str) -> str:
    parsed = urlparse(mysql_url)
    if parsed.path.lstrip("/") != "queue_control_flow_dev":
        raise RuntimeError("Queue Control Flow 仅允许连接 queue_control_flow_dev")
    return mysql_url

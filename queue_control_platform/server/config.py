"""中心控制平台的运行配置。

数据库（MySQL）、控制面 Redis 与监听地址一律通过本地 .env / 环境变量
（QUEUE_CONTROL_* 前缀）读取，代码中不出现任何线上地址：

    QUEUE_CONTROL_MYSQL_URL   统一库 rpa_platform 连接串（仅中央机代码直连）
    QUEUE_CONTROL_REDIS_URL   队列命令总线 Redis（中央机与 Agent 共用）
    QUEUE_CONTROL_HOST/PORT   服务监听地址（中央机部署 0.0.0.0，本地开发 127.0.0.1 即可）

本地开发中央机服务时，把 .env 中上述变量直接指向线上地址即可连线上库调试。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（queue_control_platform/server/config.py 向上两级）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_local_env() -> None:
    """加载本地 .env：先当前工作目录（任意子目录启动均生效），再项目根目录补齐缺失项。

    override=False：已导出的真实环境变量优先级始终高于 .env 文件。
    """
    for candidate in (Path.cwd() / ".env", _PROJECT_ROOT / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


@dataclass(frozen=True)
class PlatformSettings:
    """中心 API、MySQL 和 Redis 的连接配置。"""

    mysql_url: str
    redis_url: str
    host: str
    port: int

    @classmethod
    def from_environment(cls) -> "PlatformSettings":
        # 连接配置只从 .env / 环境变量读取；兜底值指向 docker compose 起的
        # 本地统一库 rpa_platform（旧默认库名 queue_control 已废弃，勿再用）。
        _load_local_env()
        return cls(
            mysql_url=os.getenv(
                "QUEUE_CONTROL_MYSQL_URL",
                "mysql://queue_control:queue_control@127.0.0.1:3306/rpa_platform",
            ),
            redis_url=os.getenv("QUEUE_CONTROL_REDIS_URL", "redis://127.0.0.1:6379/0"),
            host=os.getenv("QUEUE_CONTROL_HOST", "127.0.0.1"),
            port=int(os.getenv("QUEUE_CONTROL_PORT", "8766")),
        )

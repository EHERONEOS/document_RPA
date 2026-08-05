"""机器侧队列控制客户端的运行配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QueueClientSettings:
    """客户端注册身份、Redis 通道和本地 Worker 配置。"""

    device_id: str
    enrollment_token: str
    redis_url: str
    drain_timeout_seconds: int
    project_root: Path

    @classmethod
    # 从环境变量构建机器侧客户端配置，并校验设备注册信息。
    def from_environment(cls, project_root: Path | None = None) -> "QueueClientSettings":
        from app.config import bootstrap_environment

        bootstrap_environment()
        device_id = os.getenv("QUEUE_CONTROL_DEVICE_ID", "").strip().upper()
        token = os.getenv("QUEUE_CONTROL_DEVICE_TOKEN", "").strip()
        if not device_id or not token:
            raise RuntimeError(
                "必须设置 QUEUE_CONTROL_DEVICE_ID 和 QUEUE_CONTROL_DEVICE_TOKEN"
            )
        return cls(
            device_id=device_id,
            enrollment_token=token,
            redis_url=os.getenv("QUEUE_CONTROL_REDIS_URL", "redis://127.0.0.1:6379/0"),
            drain_timeout_seconds=int(os.getenv("CONTROL_DRAIN_TIMEOUT_SECONDS", "1800")),
            project_root=project_root or Path(__file__).resolve().parents[3],
        )

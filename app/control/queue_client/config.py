"""机器侧队列控制客户端的运行配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.config.queue_config import (
    QUEUE_ASSIGNMENT_SOURCE_LOCAL,
    parse_queue_assignment_source,
    parse_queue_names,
)


@dataclass(frozen=True)
class QueueClientSettings:
    """客户端注册身份、Redis 通道、队列来源开关和本地 Worker 配置。"""

    device_id: str
    enrollment_token: str
    redis_url: str
    drain_timeout_seconds: int
    project_root: Path
    assignment_source: str
    fallback_queues: list[str]

    @property
    def uses_local_queues(self) -> bool:
        """是否完全按本地 RPA_QUEUES 启动，不连接中心控制平台。"""
        return self.assignment_source == QUEUE_ASSIGNMENT_SOURCE_LOCAL

    @classmethod
    # 从环境变量构建机器侧客户端配置；server 模式仍校验设备注册信息。
    def from_environment(cls, project_root: Path | None = None) -> "QueueClientSettings":
        from app.config import bootstrap_environment

        bootstrap_environment()
        assignment_source = parse_queue_assignment_source(
            os.getenv("QUEUE_ASSIGNMENT_SOURCE")
        )
        device_id = os.getenv("QUEUE_CONTROL_DEVICE_ID", "").strip().upper()
        token = os.getenv("QUEUE_CONTROL_DEVICE_TOKEN", "").strip()
        # 本地模式不依赖中心平台，因此不强制设备身份；server 模式仍必须注册。
        if assignment_source != QUEUE_ASSIGNMENT_SOURCE_LOCAL and (
            not device_id or not token
        ):
            raise RuntimeError(
                "必须设置 QUEUE_CONTROL_DEVICE_ID 和 QUEUE_CONTROL_DEVICE_TOKEN"
            )
        return cls(
            device_id=device_id,
            enrollment_token=token,
            redis_url=os.getenv("QUEUE_CONTROL_REDIS_URL", "redis://127.0.0.1:6379/0"),
            drain_timeout_seconds=int(os.getenv("CONTROL_DRAIN_TIMEOUT_SECONDS", "1800")),
            project_root=project_root or Path(__file__).resolve().parents[3],
            assignment_source=assignment_source,
            fallback_queues=parse_queue_names(os.getenv("RPA_QUEUES", "")),
        )

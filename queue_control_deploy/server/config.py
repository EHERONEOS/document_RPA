"""部署控制服务运行配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from queue_control_deploy.sync.config import SyncSettings


@dataclass(frozen=True)
class DeploySettings:
    """部署 API、制品存储和操作员鉴权配置。

    字段说明：
    - ``sync``：同步数据库配置，包含原库只读 URL 和新库 URL。
    - ``redis_url``：部署专用 Redis 配置，可复用实例但建议独立 DB。
    - ``artifact_root``：制品持久化根目录。
    - ``operator_token``：发布接口 Bearer Token。
    - ``host``/``port``：部署 API 监听地址。
    """

    sync: SyncSettings
    redis_url: str
    artifact_root: Path
    operator_token: str
    public_base_url: str
    host: str
    port: int

    @classmethod
    def from_environment(cls) -> "DeploySettings":
        """从环境变量加载部署服务配置。

        出参：
            返回不可变 ``DeploySettings``。

        核心逻辑:
            1. 复用同步配置中的数据库 URL。
            2. 制品根目录默认放在项目 runtime，生产通过环境覆盖到持久卷。
            3. ``RELEASE_OPERATOR_TOKEN`` 未设置时使用明确的本地开发默认值。
        """
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        return cls(
            sync=SyncSettings.from_environment(),
            redis_url=os.getenv("QUEUE_CONTROL_DEPLOY_REDIS_URL", "redis://127.0.0.1:6379/1"),
            artifact_root=Path(os.getenv("DEPLOY_ARTIFACT_ROOT", "runtime/deploy-releases")).resolve(),
            operator_token=os.getenv("RELEASE_OPERATOR_TOKEN", "local-development-operator-token"),
            public_base_url=os.getenv("QUEUE_CONTROL_DEPLOY_PUBLIC_BASE_URL", "").rstrip("/"),
            host=os.getenv("QUEUE_CONTROL_DEPLOY_HOST", "127.0.0.1"),
            port=int(os.getenv("QUEUE_CONTROL_DEPLOY_PORT", "8767")),
        )

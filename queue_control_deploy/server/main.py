"""部署控制服务启动入口。"""
from __future__ import annotations

import uvicorn

from queue_control_deploy.server.api import create_app
from queue_control_deploy.server.config import DeploySettings


def main() -> None:
    """启动部署控制 API。

    核心逻辑:
        1. 加载环境配置。
        2. 创建 FastAPI 应用。
        3. 默认监听 127.0.0.1:8767，生产可用环境变量覆盖。
    """
    settings = DeploySettings.from_environment()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

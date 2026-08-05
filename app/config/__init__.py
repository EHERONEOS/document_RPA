"""配置辅助函数。

导入本包时不得发起网络请求。队列 Worker 以独立进程启动，若在导入时请求
Nacos，每次重启都会隐式依赖 Nacos。通用环境变量默认只读取本地 ``.env``；
RabbitMQ 配置由其专用配置模块按需读取。
"""
import os
from pathlib import Path

from dotenv import load_dotenv


_BOOTSTRAPPED = False


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def bootstrap_environment() -> None:
    """加载本地配置，并按需加载 Nacos 提供的配置值。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    if _enabled(os.getenv("NACOS_ENABLED")):
        from app.config.nacos_config import load_nacos_environment

        load_nacos_environment()
    _BOOTSTRAPPED = True


bootstrap_environment()

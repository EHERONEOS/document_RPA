"""配置辅助函数。"""
import os
from pathlib import Path

from dotenv import load_dotenv


_BOOTSTRAPPED = False


def _disabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"0", "false", "no", "off"}


def bootstrap_environment() -> None:
    """加载本地配置，并默认加载 Nacos 提供的配置值。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    if not _disabled(os.getenv("NACOS_ENABLED")):
        from app.config.nacos_config import load_nacos_environment

        load_nacos_environment()
    _BOOTSTRAPPED = True


bootstrap_environment()

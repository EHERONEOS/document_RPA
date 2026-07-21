"""Configuration helpers."""
from pathlib import Path

from dotenv import load_dotenv

from app.config.nacos_config import load_nacos_environment


_BOOTSTRAPPED = False


def bootstrap_environment():
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    load_nacos_environment()
    _BOOTSTRAPPED = True


bootstrap_environment()
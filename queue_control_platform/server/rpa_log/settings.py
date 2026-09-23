"""RPA 日志模块配置（原 rpa-log-service settings，并入平台后数据库配置由平台统一提供）。

仅保留日志模块自身的行为配置；MySQL 连接一律走 QUEUE_CONTROL_MYSQL_URL
（统一库），见 db.py。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]  # server/rpa_log/settings.py → 仓库根


@dataclass(frozen=True)
class Settings:
    service_token: str
    files_dir: Path
    running_timeout_hours: float


def get_settings() -> Settings:
    """读取配置（每次返回新实例，成本低；环境变量在测试中可随时覆盖）。"""
    return Settings(
        service_token=os.getenv("RPA_LOG_SERVICE_TOKEN", "local-dev"),
        files_dir=Path(os.getenv("RPA_LOG_FILES_DIR", str(_REPO_ROOT / "files"))),
        running_timeout_hours=float(os.getenv("RPA_LOG_RUNNING_TIMEOUT_HOURS", "6")),
    )

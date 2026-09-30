"""记录文件存储降级链：OSS → Copyparty（局域网文件服务）→ 本地保留。

Agent 只认 ``{url, storage}`` 语义；OSS 失败（或录屏超限）时通过 HTTP PUT
上传到局域网 Copyparty 服务；两端都失败返回 None 并打 WARN，本地文件保留。
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.core.logging.logger import log

VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_LAN_UPLOAD_TIMEOUT_SECONDS = 1800  # Copyparty 无大小限制，大文件放宽到 30min


def infer_media_type(file_path) -> str:
    """按后缀推断 mediaType：视频后缀 → VIDEO，否则 IMAGE。"""
    return "VIDEO" if Path(file_path).suffix.lower() in VIDEO_SUFFIXES else "IMAGE"


class FileStorageClient:
    """Copyparty 局域网文件客户端（OSS 仍走 OssClient，本类只负责兜底链路）。"""

    def upload_lan(self, file_path) -> dict | None:
        """PUT 上传到 Copyparty。

        返回 ``{"url", "fileName", "fileSize"}``；未配置服务地址 / 上传失败
        返回 None（内部已打 WARN，不抛错）。本地文件一律保留。
        """
        file_path = Path(file_path)
        base_url = os.getenv("RPA_COPIYPARTY_URL", "").strip().rstrip("/")
        if not base_url:
            log("未配置 RPA_COPIYPARTY_URL，跳过 Copyparty 上传，本地文件已保留", level="WARN")
            return None

        password = os.getenv("RPA_COPIYPARTY_PASSWORD", "").strip()
        volume = os.getenv("RPA_COPIYPARTY_VOLUME", "inc").strip().strip("/")

        # 按 yyyy/mm 分子目录 + UUID 前缀，避免文件名冲突
        now = datetime.now(timezone.utc)
        subdir = f"{now.strftime('%Y')}/{now.strftime('%m')}"
        file_id = f"{secrets.token_hex(8)}{file_path.suffix}"

        upload_url = f"{base_url}/{volume}/{subdir}/{file_id}"
        params = {"pw": password} if password else {}

        try:
            file_size = file_path.stat().st_size
            with file_path.open("rb") as fileobj:
                response = requests.put(
                    upload_url,
                    data=fileobj,
                    params=params,
                    timeout=_LAN_UPLOAD_TIMEOUT_SECONDS,
                )
            response.raise_for_status()
            return {
                "url": upload_url,
                "fileName": file_path.name,
                "fileSize": file_size,
            }
        except Exception as exc:  # noqa: BLE001 - 降级：绝不向上抛
            log(f"Copyparty 上传失败，本地文件已保留 path={file_path} error={exc}", level="WARN")
            return None

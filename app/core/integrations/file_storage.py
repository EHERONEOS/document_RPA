"""记录文件存储降级链（设计文档 §6.4 / §7 / T2.6）：OSS → 局域网文件服务 → 本地保留。

Agent 只认 ``{url, storage}`` 语义；OSS 失败（或录屏超限）时尝试局域网
``rpa-log-service`` 的 ``POST /api/v1/files/upload``；两端都失败返回 None 并
打 WARN，本地文件按现状保留（人工可取）。
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

from app.core.logging.logger import log

VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_LAN_UPLOAD_TIMEOUT_SECONDS = 300  # 录屏最大 10MB+，内网宽限


def infer_media_type(file_path) -> str:
    """按后缀推断 mediaType：视频后缀 → VIDEO，否则 IMAGE（§6.4）。"""
    return "VIDEO" if Path(file_path).suffix.lower() in VIDEO_SUFFIXES else "IMAGE"


class FileStorageClient:
    """局域网文件服务客户端（OSS 仍走 OssClient，本类只负责兜底链路）。"""

    def upload_lan(self, file_path) -> dict | None:
        """上传到 rpa-log-service /files/upload。

        返回 ``{"url", "fileName", "fileSize"}``；未配置服务地址 / 上传失败返回 None
        （内部已打 WARN，不抛错）。本地文件一律保留。
        """
        file_path = Path(file_path)
        base_url = os.getenv("RPA_LOG_SERVICE_URL", "").strip().rstrip("/")
        if not base_url:
            log("未配置 RPA_LOG_SERVICE_URL，跳过局域网上传，本地文件已保留", level="WARN")
            return None

        headers = {}
        token = os.getenv("RPA_LOG_SERVICE_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with file_path.open("rb") as fileobj:
                response = requests.post(
                    f"{base_url}/api/v1/files/upload",
                    files={"file": (file_path.name, fileobj)},
                    headers=headers,
                    timeout=_LAN_UPLOAD_TIMEOUT_SECONDS,
                )
            response.raise_for_status()
            envelope = response.json()
            if envelope.get("code") != 0:
                raise RuntimeError(f"业务错误：{envelope.get('message')}")
            data = envelope.get("data") or {}
            return {
                "url": data.get("url") or "",
                "fileName": data.get("fileName") or file_path.name,
                "fileSize": int(data.get("fileSize") or 0),
            }
        except Exception as exc:  # noqa: BLE001 - 降级：绝不向上抛
            log(f"局域网上传失败，本地文件已保留 path={file_path} error={exc}", level="WARN")
            return None

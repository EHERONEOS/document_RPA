"""局域网文件服务（设计文档 §5.1 / §7）：multipart 上传 + /files/* 静态只读访问。

- 扩展名白名单；UUID 重命名杜绝路径穿越；单文件 ≤200MB（413）；
- 落盘 ``{files_dir}/{yyyy}/{mm}/{uuid}{ext}``，返回 ``http://{host}/files/...`` 完整地址。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from ..settings import get_settings
from .agent import ok, verify_token

OSS_FILE_URL_ENDPOINT = "https://fec.cgofish.com/v1/file/url"

router = APIRouter(tags=["files"])

# §5.1：mp4/mov/png/jpg/jpeg…（录屏 + 截图 + 常见图片格式）
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 单文件 ≤200MB
_CHUNK = 1024 * 1024


@router.post("/files/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    _: None = Depends(verify_token),
) -> dict:
    original_name = Path(file.filename or "file").name
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"extension {ext!r} not allowed, whitelist: {sorted(ALLOWED_EXTENSIONS)}",
        )

    settings = get_settings()
    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"file size {declared_size} exceeds {MAX_UPLOAD_SIZE}")

    now = datetime.now()
    rel_dir = Path(f"{now:%Y}") / f"{now:%m}"
    target_dir = settings.files_dir / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid.uuid4().hex}{ext}"  # UUID 重命名

    written = 0
    try:
        with target_path.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                written += len(chunk)
                if written > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail=f"file size exceeds {MAX_UPLOAD_SIZE}")
                out.write(chunk)
    except HTTPException:
        target_path.unlink(missing_ok=True)
        raise
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    host = request.headers.get("host") or (request.client.host if request.client else "localhost")
    url = f"http://{host}/files/{rel_dir.as_posix()}/{target_path.name}"
    return ok({"url": url, "storage": "LAN", "fileName": original_name, "fileSize": written})


@router.get("/files/oss-url")
def resolve_oss_url(objectName: str = Query(..., min_length=1, max_length=512)) -> dict:
    """用 OSS objectName 换带签名的临时地址（设计文档 §9）；由服务端代发，避免浏览器跨域。"""
    try:
        response = requests.get(
            OSS_FILE_URL_ENDPOINT,
            params={"objectName": objectName},
            timeout=10,
        )
        response.raise_for_status()
        envelope = response.json()
    except Exception as exc:  # noqa: BLE001 - 上游失败转 502，前端展示换地址失败
        raise HTTPException(status_code=502, detail=f"resolve oss url failed: {exc}") from exc
    url = str((envelope.get("data") or {}).get("url") or "")
    if not url:
        raise HTTPException(status_code=404, detail=f"oss url not found for objectName={objectName}")
    return ok({"url": url, "objectName": objectName})

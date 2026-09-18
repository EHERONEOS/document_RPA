"""发布制品的磁盘存储与哈希校验。"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredArtifact:
    """保存制品落盘结果。

    字段说明：
    - ``file_name``：服务端保存的文件名。
    - ``absolute_path``：完整持久化路径。
    - ``sha256``：文件内容摘要。
    - ``size_bytes``：文件字节数。
    """

    file_name: str
    absolute_path: Path
    sha256: str
    size_bytes: int


class ArtifactStore:
    """将上传制品安全保存到受控根目录。

    核心逻辑:
        - 所有路径在 ``artifact_root`` 内解析，防止路径穿越。
        - 写入先落临时文件，再原子改名，避免半包被下载。
    """

    def __init__(self, root: Path | str):
        """初始化存储根目录。

        入参：
            ``root``：制品根目录，不存在时创建。
        """
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(file_name: str) -> str:
        """清理上传文件名，仅保留基础名称和安全字符。

        入参：
            ``file_name``：客户端文件名。

        出参：
            返回安全文件名。

        异常：
            ``ValueError``：清理后为空时抛出。
        """
        base = os.path.basename(file_name.replace("\\", "/"))
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
        if not safe or safe in {".", ".."}:
            raise ValueError("制品文件名非法")
        return safe

    def _resolve_inside_root(self, relative_path: str) -> Path:
        """解析根目录内路径并校验不越界。

        入参：
            ``relative_path``：相对制品根目录的路径。

        出参：
            返回绝对路径。

        异常：
            ``ValueError``：路径越界时抛出。
        """
        path = (self.root / relative_path).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("制品路径越界")
        return path

    @staticmethod
    def hash_file(path: Path) -> tuple[str, int]:
        """流式计算文件 sha256 和大小。

        入参：
            ``path``：本地文件。

        出参：
            返回 ``(sha256, size_bytes)``。
        """
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    def save_upload(self, data: bytes, original_name: str, release_unit: str) -> StoredArtifact:
        """保存上传制品字节。

        入参：
            ``data``：制品内容。
            ``original_name``：客户端文件名。
            ``release_unit``：发布单元，用于分子目录。

        出参：
            返回 ``StoredArtifact``。

        核心逻辑:
            1. 清理 unit 与文件名。
            2. 先写 ``.tmp``，校验后再原子改名。
        """
        safe_unit = re.sub(r"[^A-Za-z0-9._-]+", "_", release_unit)
        safe_name = self._safe_name(original_name)
        relative = f"{safe_unit}/{safe_name}"
        destination = self._resolve_inside_root(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_bytes(data)
        sha256, size = self.hash_file(temporary)
        temporary.replace(destination)
        return StoredArtifact(safe_name, destination, sha256, size)

    def open_if_exists(self, artifact_path: str) -> Path:
        """校验数据库记录的制品路径并返回可下载文件。

        入参：
            ``artifact_path``：数据库中保存的路径。

        出参：
            返回存在且位于根目录内的 Path。

        异常：
            ``FileNotFoundError``：文件缺失；``ValueError``：路径越界。
        """
        path = Path(artifact_path).resolve()
        if self.root not in path.parents:
            raise ValueError("制品路径越界")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

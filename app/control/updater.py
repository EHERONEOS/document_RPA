"""Agent 更新器的制品校验、安全解压和 staging 准备。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


# 仅允许目标船司业务源码进入 staging，公共/平台路径必须走 platform 发布。
FORBIDDEN_PARTS = {"__MACOSX"}


def sha256_file(path: Path) -> str:
    """流式计算制品 sha256。

    入参：
        ``path``：本地 zip 文件。

    出参：
        返回十六进制摘要。
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    """读取并校验 manifest 基础字段。

    入参：
        ``path``：manifest JSON 文件。

    出参：
        返回 manifest 字典。

    异常：
        ``ValueError``：缺少必需字段时抛出。
    """
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {"releaseUnit", "version", "sha256", "paths", "queues"}
    missing = sorted(required - set(manifest))
    if missing:
        raise ValueError(f"manifest missing fields: {','.join(missing)}")
    if manifest.get("dependencyChanged") and manifest.get("releaseUnit") != "platform":
        raise ValueError("dependency changes require platform release")
    return manifest


def validate_zip(artifact: Path, manifest: dict[str, Any]) -> list[str]:
    """校验 zip 路径穿越和 manifest 路径白名单。

    入参：
        ``artifact``：zip 制品。
        ``manifest``：发布清单。

    出参：
        返回安全成员名列表。

    异常：
        ``ValueError``：sha256、路径越界或非白名单业务路径非法时抛出。
    """
    actual = sha256_file(artifact)
    if actual != manifest["sha256"]:
        raise ValueError(f"sha256 mismatch: expected={manifest['sha256']} actual={actual}")
    patterns = manifest["paths"]
    safe_members: list[str] = []
    with zipfile.ZipFile(artifact) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            normalized = Path(name)
            if normalized.is_absolute() or ".." in normalized.parts or any(part in FORBIDDEN_PARTS for part in normalized.parts):
                raise ValueError(f"zip traversal forbidden: {name}")
            if info.is_dir():
                continue
            # 目录路径如 app/spider/ZIM/xx.py 必须命中白名单；__pycache__ 只用于校验阶段会被过滤。
            if not any(fnmatch(name, pattern) for pattern in patterns):
                raise ValueError(f"zip path outside manifest paths: {name}")
            safe_members.append(name)
    if not safe_members:
        raise ValueError("artifact is empty")
    return safe_members


def validate_artifact(artifact: Path, manifest: dict[str, Any], staging_root: Path) -> Path:
    """校验内存/远程下载的发布制品并准备 staging。

    入参：
        ``artifact``：已下载的 zip。
        ``manifest``：服务端签发的发布清单。
        ``staging_root``：staging 根目录。

    出参：
        返回解压并编译通过的 staging 目录。

    异常：
        ``ValueError``：sha256、manifest、路径白名单或编译检查失败时抛出。

    核心逻辑:
        与本地 self-test 复用同一套 zip 校验、解压和编译流程，避免双协议风险。
    """
    members = validate_zip(artifact, manifest)
    staging = extract_to_staging(artifact, manifest, staging_root)
    exit_code = compile_staging(staging)
    if exit_code != 0:
        raise ValueError(f"staging compile failed: exit={exit_code}")
    return staging

def extract_to_staging(artifact: Path, manifest: dict[str, Any], staging_root: Path) -> Path:
    """将校验通过的 zip 解压到 staging。

    入参：
        ``artifact``：zip 制品。
        ``manifest``：发布清单。
        ``staging_root``：staging 根目录。

    出参：
        返回本次 staging 目录。

    核心逻辑:
        1. 先清空同 release 旧 staging。
        2. 逐文件二次校验 zip 路径。
        3. 过滤 pycache 后安全解压。
    """
    members = validate_zip(artifact, manifest)
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = staging_root / str(manifest.get("releaseId", manifest["version"]))
    staging = staging.resolve()
    if staging_root.resolve() not in staging.parents:
        raise ValueError("staging path traversal")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(artifact) as archive:
        for member in members:
            if "__pycache__/" in f"{member}/":
                continue
            target = (staging / member).resolve()
            if staging not in target.parents:
                raise ValueError(f"extract traversal forbidden: {member}")
            archive.extract(member, staging)
    return staging


def compile_staging(staging: Path) -> int:
    """对 staging 执行 Python 编译检查。

    入参：
        ``staging``：解压目录。

    出参：
        返回子进程退出码。

    核心逻辑:
        使用当前 Python 的 compileall，避免 Agent 环境外部工具差异。
    """
    import subprocess
    import sys

    return subprocess.run([sys.executable, "-m", "compileall", "-q", str(staging)]).returncode


def self_test(artifact: Path, manifest_path: Path, staging_root: Path) -> dict[str, Any]:
    """执行下载后本地校验全流程。

    入参：
        ``artifact``：本地 zip。
        ``manifest_path``：manifest 文件。
        ``staging_root``：staging 根目录。

    出参：
        返回每一步校验结果。

    核心逻辑:
        1. 校验 manifest/hash/zip 路径。
        2. 解压到 staging 并执行编译。
    """
    manifest = load_manifest(manifest_path)
    if sha256_file(artifact) != manifest["sha256"]:
        raise ValueError("sha256 mismatch")
    members = validate_zip(artifact, manifest)
    staging = extract_to_staging(artifact, manifest, staging_root)
    return {
        "sha256": "OK",
        "paths": "OK",
        "zipTraversal": "OK",
        "extract": "OK",
        "staging": str(staging),
        "memberCount": len(members),
        "compileExitCode": compile_staging(staging),
    }


def main() -> int:
    """提供 ``python -m app.control.updater --self-test`` 入口。"""
    parser = argparse.ArgumentParser(description="校验并准备船司脚本更新制品")
    parser.add_argument("--self-test", action="store_true", help="执行本地校验")
    parser.add_argument("--artifact", type=Path, required=True, help="本地 zip 制品")
    parser.add_argument("--manifest", type=Path, required=True, help="manifest JSON")
    parser.add_argument("--staging-root", type=Path, default=Path("runtime/deploy/staging"))
    args = parser.parse_args()
    if not args.self_test:
        parser.error("请使用 --self-test")
    result = self_test(args.artifact, args.manifest, args.staging_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["compileExitCode"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

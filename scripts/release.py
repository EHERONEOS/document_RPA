#!/usr/bin/env python3
"""从两个 Git commit 构建船司脚本发布包并校验路径边界。"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


# 公共和平台路径一旦混入，就不能伪装成单船司发布。
CARRIER_PREFIX = "app/spider/"
SHARED_PREFIXES = ("app/spider/common/",)
PLATFORM_PREFIXES = (
    "app/core/", "app/queue/", "app/control/", "pyproject.toml", "uv.lock", "funboost_config.py",
)
# 当前已知队列归属；后续以 queue_catalog 为最终事实源。
QUEUE_CATALOG: dict[str, list[str]] = {
    "ZIM": ["QTCT_ZIM_SI", "QTCT_ZIM_VGM"],
    "MSCGW": ["FHT_MSCGW_SI"],
}


def run_git(*args: str) -> str:
    """执行 Git 只读命令。

    入参：
        ``args``：Git 参数。

    出参：
        返回 stdout 文本。

    异常：
        ``RuntimeError``：Git 失败时抛出。
    """
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Git command failed")
    return result.stdout


def classify_path(path: str) -> tuple[str, str | None]:
    """将变更路径分类为 carrier、spider-common 或 platform。

    入参：
        ``path``：Git 相对路径。

    出参：
        返回 ``(kind, carrier)``；carrier 只在船司路径时有值。

    核心逻辑:
        1. ``app/spider/common/**`` 是共享代码。
        2. ``app/spider/<NAME>/**`` 是单船司代码。
        3. 其他所有路径保守归类为 platform。
    """
    normalized = path.replace("\\", "/")
    if normalized.startswith(SHARED_PREFIXES):
        return "spider-common", None
    if normalized.startswith(CARRIER_PREFIX):
        parts = normalized.split("/")
        if len(parts) >= 3 and parts[2]:
            return "carrier", parts[2].upper()
    return "platform", None


def classify_changes(paths: list[str]) -> dict[str, Any]:
    """汇总变更路径并判定发布单元。

    入参：
        ``paths``：两个 commit 之间所有变更路径。

    出参：
        返回分类结果，包含 release_unit、carriers、paths。

    异常：
        ``ValueError``：混入公共/平台代码或多个船司时抛出。
    """
    if not paths:
        raise ValueError("release diff is empty")
    kinds: set[str] = set()
    carriers: set[str] = set()
    for path in paths:
        kind, carrier = classify_path(path)
        kinds.add(kind)
        if carrier:
            carriers.add(carrier)
    if kinds == {"carrier"} and len(carriers) == 1:
        carrier = next(iter(carriers))
        return {
            "releaseUnit": f"carrier:{carrier}",
            "carrier": carrier,
            "paths": sorted(paths),
            "allowedSingleCarrier": True,
        }
    if "carrier" in kinds and ({"spider-common", "platform"} & kinds):
        raise ValueError("release contains shared/platform code changes; carrier release is not allowed")
    if "spider-common" in kinds:
        unit = "spider-common" if kinds == {"spider-common"} else "platform"
        return {"releaseUnit": unit, "carrier": None, "paths": sorted(paths), "allowedSingleCarrier": False}
    return {"releaseUnit": "platform", "carrier": None, "paths": sorted(paths), "allowedSingleCarrier": False}


def build_manifest(
    *,
    from_commit: str,
    to_commit: str,
    version: str,
    classification: dict[str, Any],
    artifact: Path,
) -> dict[str, Any]:
    """构造发布 manifest。

    入参：
        ``from_commit``/``to_commit``：Git 区间。
        ``version``：版本号。
        ``classification``：路径分类结果。
        ``artifact``：打包后的 zip 路径。

    出参：
        返回包含哈希、路径和队列的 manifest。
    """
    digest = hashlib.sha256()
    with artifact.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    carrier = classification.get("carrier")
    return {
        "version": version,
        "fromCommit": from_commit,
        "gitCommit": to_commit,
        "releaseUnit": classification["releaseUnit"],
        "paths": [f"app/spider/{carrier}/**"],
        "queues": QUEUE_CATALOG.get(carrier, []),
        "sha256": digest.hexdigest(),
        "dependencyChanged": False,
    }


def validate_zip_paths(artifact: Path, carrier: str) -> None:
    """校验 zip 只包含目标船司路径且没有路径穿越。

    入参：
        ``artifact``：zip 制品。
        ``carrier``：船司名。

    异常：
        ``ValueError``：包路径越界或混入其他业务路径时抛出。
    """
    allowed_prefix = f"app/spider/{carrier}/"
    with zipfile.ZipFile(artifact) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            normalized = Path(name)
            if normalized.is_absolute() or ".." in normalized.parts:
                raise ValueError(f"zip path traversal detected: {name}")
            if info.is_dir():
                continue
            if not name.startswith(allowed_prefix):
                raise ValueError(f"zip contains path outside {allowed_prefix}: {name}")


def build(from_commit: str, to_commit: str, version: str, output: Path, manifest_output: Path) -> dict[str, Any]:
    """执行完整构建。

    入参：
        ``from_commit``/``to_commit``：Git 区间。
        ``version``：版本号。
        ``output``：制品输出路径。
        ``manifest_output``：manifest 输出路径。

    出参：
        返回 manifest 字典。

    核心逻辑:
        1. 使用 git diff 分类，不读取本地未提交文件。
        2. 使用 git archive 只打包目标船司路径。
        3. 校验 zip 路径并生成 manifest。
    """
    diff = run_git("diff", "--name-only", f"{from_commit}..{to_commit}")
    paths = [line.strip() for line in diff.splitlines() if line.strip()]
    classification = classify_changes(paths)
    if not classification["allowedSingleCarrier"]:
        raise ValueError("only single-carrier releases are supported by this tool")
    carrier = classification["carrier"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        subprocess.run(
            ["git", "archive", "--format=zip", to_commit, *classification["paths"]],
            check=True,
            stdout=handle,
        )
    validate_zip_paths(output, carrier)
    manifest = build_manifest(from_commit=from_commit, to_commit=to_commit, version=version, classification=classification, artifact=output)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    """命令行入口；路径越界或公共代码混入时返回非零。"""
    parser = argparse.ArgumentParser(description="构建按船司脚本发布包")
    parser.add_argument("--from", dest="from_commit", required=True, help="旧 commit/tag")
    parser.add_argument("--to", dest="to_commit", required=True, help="新 commit/tag")
    parser.add_argument("--version", required=True, help="发布版本号")
    parser.add_argument("--artifact-output", type=Path, default=Path("runtime/deploy-releases/release.zip"))
    parser.add_argument("--manifest-output", type=Path, default=Path("runtime/deploy-releases/manifest.json"))
    args = parser.parse_args()
    try:
        manifest = build(args.from_commit, args.to_commit, args.version, args.artifact_output, args.manifest_output)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""用于显示待同步代码变更的按队列源码清单。"""
from __future__ import annotations

import hashlib
from pathlib import Path


PROJECT_FILE_NAMES = (
    "funboost_config.py",
    "app/config/__init__.py",
    "app/config/nacos_config.py",
    "app/config/queue_config.py",
    "app/config/rabbitmq.py",
    "app/config/settings.py",
    "app/config/types.py",
    "app/queue/booster.py",
    "app/queue/consumer.py",
    "app/queue/message.py",
    "app/queue/pausable_rabbitmq.py",
    "app/queue/rabbitmq.py",
    "app/__init__.py",
)


# 计算文件内容的 SHA-256 摘要，用于检测源码是否变更。
def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# 将指定目录下的全部 Python 源文件加入依赖清单。
def _add_python_files(files: set[Path], directory: Path) -> None:
    if directory.is_dir():
        files.update(path for path in directory.rglob("*.py") if path.is_file())


# 构建可能影响指定队列执行流程的源码版本清单。
def queue_manifest(queue_name: str, project_root: Path) -> dict[str, str]:
    """返回可能影响指定队列执行流程的文件。

    船司流程模块可能包含多个业务入口，因此任务模块由队列名第三段选择，而非递归
    跟踪流程模块中的全部导入。共享代码仍会加入每个受影响队列的清单。
    """
    parts = [part.strip() for part in queue_name.upper().split("_") if part.strip()]
    customer = parts[0] if len(parts) >= 1 else ""
    carrier = parts[1] if len(parts) >= 2 else ""
    business = parts[2] if len(parts) >= 3 else ""

    files: set[Path] = set()
    for name in PROJECT_FILE_NAMES:
        path = project_root / name
        if path.is_file():
            files.add(path)

    # 核心代码会参与所有 RPA 任务，因此影响全部队列。
    _add_python_files(files, project_root / "app" / "core")

    if carrier:
        carrier_root = project_root / "app" / "spider" / carrier
        router = carrier_root / "router.py"
        if router.is_file():
            files.add(router)
        _add_python_files(files, carrier_root / "common")

        flow = carrier_root / "flows" / f"{customer.lower()}_{carrier.lower()}.py"
        if flow.is_file():
            files.add(flow)

        task = carrier_root / "tasks" / f"{carrier.lower()}_{business.lower()}.py"
        if task.is_file():
            files.add(task)

    return {
        str(path.relative_to(project_root)): file_digest(path)
        for path in sorted(files)
    }


# 对比保存的版本清单，返回已修改或已删除的源码路径。
def manifest_changes(manifest: dict[str, str], project_root: Path) -> list[str]:
    changes = []
    for relative_path, expected_digest in manifest.items():
        path = project_root / relative_path
        if not path.is_file() or file_digest(path) != expected_digest:
            changes.append(relative_path)
    return sorted(changes)

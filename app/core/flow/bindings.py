"""保存流程中心下发的本地队列到流程绑定。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class FlowBindingCache:
    """在流程缓存目录中保存最近有效的绑定快照。"""

    def __init__(self, directory: str | Path = "runtime/flow_cache"):
        self.directory = Path(directory)
        self.path = self.directory / "bindings.json"

    def put(self, bindings: list[dict[str, Any]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen_queues: set[str] = set()
        for binding in bindings:
            if not isinstance(binding, dict):
                raise ValueError("流程绑定必须是对象")
            queue_name = str(binding.get("queueName") or "").strip().upper()
            flow_id = str(binding.get("flowId") or "").strip()
            flow_version = str(binding.get("flowVersion") or "").strip()
            checksum = str(binding.get("checksum") or "").strip().lower()
            if not queue_name or not flow_id or not flow_version or len(checksum) != 64:
                raise ValueError("流程绑定缺少 queueName、flowId、flowVersion 或 checksum")
            if queue_name in seen_queues:
                raise ValueError(f"队列存在重复流程绑定：{queue_name}")
            seen_queues.add(queue_name)
            normalized.append(
                {
                    "queueName": queue_name,
                    "flowId": flow_id,
                    "flowVersion": flow_version,
                    "checksum": checksum,
                }
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                json.dumps({"bindings": normalized}, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return normalized

    def get(self, queue_name: str) -> dict[str, str] | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        bindings = payload.get("bindings") if isinstance(payload, dict) else None
        if not isinstance(bindings, list):
            return None
        normalized_queue = queue_name.strip().upper()
        for binding in bindings:
            if isinstance(binding, dict) and binding.get("queueName") == normalized_queue:
                return {
                    "flowId": str(binding.get("flowId") or ""),
                    "flowVersion": str(binding.get("flowVersion") or ""),
                    "checksum": str(binding.get("checksum") or ""),
                }
        return None

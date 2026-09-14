"""保存在 Agent 文件系统中的已校验最近有效流程定义。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.core.flow.schema import FlowValidationError, validate_flow_definition


class FlowCache:
    """本地不可变流程版本缓存；Redis 只传递同步通知。"""

    def __init__(self, directory: str | Path = "runtime/flow_cache"):
        self.directory = Path(directory)

    def put(self, definition: dict[str, Any], *, checksum: str | None = None) -> dict[str, Any]:
        validated = validate_flow_definition(definition)
        actual_checksum = flow_checksum(validated)
        if checksum and checksum.lower() != actual_checksum:
            raise FlowValidationError("流程版本校验和不匹配")
        path = self._path(validated["flowId"], validated["flowVersion"])
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"checksum": actual_checksum, "definition": validated}
        temporary_path = path.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
            )
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return validated

    def get(self, flow_id: str, flow_version: str) -> dict[str, Any]:
        path = self._path(flow_id, flow_version)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FlowValidationError(f"本地未缓存流程版本：{flow_id}@{flow_version}") from exc
        except json.JSONDecodeError as exc:
            raise FlowValidationError(f"本地流程缓存损坏：{path}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("definition"), dict):
            raise FlowValidationError(f"本地流程缓存格式无效：{path}")
        definition = validate_flow_definition(payload["definition"])
        if definition["flowId"] != flow_id or definition["flowVersion"] != flow_version:
            raise FlowValidationError("本地流程缓存的版本与请求不一致")
        if payload.get("checksum") != flow_checksum(definition):
            raise FlowValidationError("本地流程缓存校验和不匹配")
        return definition

    def _path(self, flow_id: str, flow_version: str) -> Path:
        # 流程标识已在持久化前通过 Schema 校验，只允许安全字符。
        return self.directory / flow_id / f"{flow_version}.json"


def flow_checksum(definition: dict[str, Any]) -> str:
    canonical = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

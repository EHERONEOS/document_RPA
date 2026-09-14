"""从中心拉取已发布流程版本并更新本地缓存。"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.flow.bindings import FlowBindingCache
from app.core.flow.cache import FlowCache, flow_checksum
from app.core.flow.schema import FlowValidationError


class FlowSynchronizer:
    """原子同步一份完整且已校验的流程绑定快照。"""

    def __init__(
        self,
        *,
        api_url: str,
        device_id: str,
        enrollment_token: str,
        cache_directory: str,
    ):
        self.api_url = api_url.rstrip("/")
        self.device_id = device_id
        self.enrollment_token = enrollment_token
        self.flow_cache = FlowCache(cache_directory)
        self.binding_cache = FlowBindingCache(cache_directory)

    def sync(self, command: dict[str, Any]) -> dict[str, Any]:
        bindings = command.get("bindings")
        if not isinstance(bindings, list):
            raise ValueError("flow_sync 命令缺少 bindings")
        fetched: list[dict[str, Any]] = []
        for binding in bindings:
            if not isinstance(binding, dict):
                raise ValueError("flow_sync 命令包含无效绑定")
            flow_id = str(binding.get("flowId") or "").strip()
            flow_version = str(binding.get("flowVersion") or "").strip()
            expected_checksum = str(binding.get("checksum") or "").strip().lower()
            try:
                cached = self.flow_cache.get(flow_id, flow_version)
            except FlowValidationError:
                cached = None
            if cached is None or flow_checksum(cached) != expected_checksum:
                definition = self._fetch_definition(flow_id, flow_version)
                actual_checksum = flow_checksum(definition)
                if actual_checksum != expected_checksum:
                    raise ValueError(f"流程校验和不匹配：{flow_id}@{flow_version}")
                self.flow_cache.put(definition, checksum=expected_checksum)
            fetched.append(binding)
        self.binding_cache.put(fetched)
        return {"syncedBindings": len(fetched)}

    def _fetch_definition(self, flow_id: str, flow_version: str) -> dict[str, Any]:
        if not self.api_url:
            raise RuntimeError("未配置 QUEUE_CONTROL_FLOW_API_URL，无法同步流程")
        if not flow_id or not flow_version:
            raise ValueError("流程同步缺少 flowId 或 flowVersion")
        url = (
            f"{self.api_url}/api/agent/flows/{quote(flow_id, safe='')}/"
            f"{quote(flow_version, safe='')}"
        )
        request = Request(
            url,
            headers={
                "X-Queue-Control-Device": self.device_id,
                "X-Queue-Control-Token": self.enrollment_token,
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"流程中心拒绝同步 {flow_id}@{flow_version}：HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"无法拉取流程 {flow_id}@{flow_version}：{exc}") from exc
        definition = payload.get("definition") if isinstance(payload, dict) else None
        if not isinstance(definition, dict):
            raise RuntimeError(f"流程中心返回了无效定义：{flow_id}@{flow_version}")
        return definition

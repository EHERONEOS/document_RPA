"""MSCGW SI 航线和港口动作。"""
from __future__ import annotations

from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.spider.MSCGW.common.si_field_verify import ROUTER_DETAIL_FIELDS
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


class RoutingActions:
    """封装 SI 航线和港口字段的填写及回读校验。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime

    def fill_router_details(self, _inputs: Mapping[str, Any]) -> None:
        """填写收货地、起运港、卸货港和交货地，并回读校验。"""
        for field_path, selector, name, required in ROUTER_DETAIL_FIELDS:
            value = self.runtime.content.get(field_path)
            if value:
                self.runtime.dom.scroll_to_see(selector, name, required=required)
                self.runtime.si_shadow.input_text(selector, value, name, required=required)
        self.runtime._verify_router_details()

    def register(self, registry: ActionRegistry) -> None:
        """将航线填写动作绑定到显式动作白名单。"""
        registry.register(
            "MSCGW.fill_router_details",
            lambda _context, inputs: self.fill_router_details(inputs),
        )

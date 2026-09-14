"""MSCGW SI 校验动作。"""
from __future__ import annotations

from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


class ValidationActions:
    """封装保存前的字段完成性校验。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime

    def verify_shipping_instruction(self, _inputs: Mapping[str, Any]) -> None:
        """在保存前检查所有预期字段是否已处理。"""
        self.runtime.raise_if_unfilled_fields()

    def register(self, registry: ActionRegistry) -> None:
        """将保存前校验动作绑定到显式动作白名单。"""
        registry.register(
            "MSCGW.verify_shipping_instruction",
            lambda _context, inputs: self.verify_shipping_instruction(inputs),
        )

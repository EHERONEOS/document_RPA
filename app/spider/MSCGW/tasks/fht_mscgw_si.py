"""FHT 客户的 MSCGW Shipping Instruction 生命周期入口。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.flow.runtime import FlowExecutionResult, FlowRuntime
from app.core.task.context import TaskContext
from app.spider.MSCGW.actions import build_mscgw_si_registry
from app.spider.MSCGW.base import MscgwBase
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


_DEFAULT_FLOW_PATH = Path(__file__).resolve().parents[1] / "flows" / "fht_mscgw_si_v1.json"


def _load_default_flow() -> dict[str, Any]:
    """读取未绑定流程中心时使用的本地固定流程版本。"""
    try:
        return json.loads(_DEFAULT_FLOW_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法加载 FHT MSCGW SI 默认流程：{_DEFAULT_FLOW_PATH}") from exc


class FhtMscgwSiTask(MscgwBase):
    """仅承接 FHT 队列的 RPA 生命周期，SI 页面操作由动作库实现。"""

    enable_record = True  # 是否开启录屏
    job_type = "SI"
    defer_login_to_business = True

    def __init__(self, context: TaskContext):
        super().__init__(context)
        self._flow_definition: dict[str, Any] | None = None
        self.flow_result: FlowExecutionResult | None = None
        self.si_shadow = None

    def run_flow(self, definition: dict[str, Any]) -> bool:
        """在既有浏览器、录屏和结果回传生命周期中执行中心发布的流程。"""
        self._flow_definition = definition
        return self.run()

    def execute_business(self) -> None:
        """通过独立 MSCGW SI 运行时执行动作链，不调用 FHT 业务方法。"""
        definition = self._flow_definition or _load_default_flow()
        runtime = MscgwSiRuntime(self)
        registry = build_mscgw_si_registry(runtime)
        self.flow_result = FlowRuntime(registry).run(definition, self.context)


def fht_mscgw_si(context: TaskContext) -> bool:
    """提供给未绑定流程版本的 FHT_MSCGW_SI 静态路由入口。"""
    return FhtMscgwSiTask(context).run()


def fht_mscgw_si_flow(context: TaskContext, definition: dict[str, Any]) -> bool:
    """提供给流程中心绑定的 FHT_MSCGW_SI 声明式入口。"""
    return FhtMscgwSiTask(context).run_flow(definition)

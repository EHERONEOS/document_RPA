"""显式组装 MSCGW 声明式动作白名单的入口。"""
from __future__ import annotations

from app.core.flow.runtime import ActionRegistry
from app.spider.MSCGW.actions.cargo import CargoActions
from app.spider.MSCGW.actions.document import DocumentActions
from app.spider.MSCGW.actions.navigation import NavigationActions
from app.spider.MSCGW.actions.parties import PartyActions
from app.spider.MSCGW.actions.payment import PaymentActions
from app.spider.MSCGW.actions.publishing import PublishingActions
from app.spider.MSCGW.actions.routing import RoutingActions
from app.spider.MSCGW.actions.session import SessionActions
from app.spider.MSCGW.actions.validation import ValidationActions
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


def build_mscgw_si_registry(runtime: MscgwSiRuntime) -> ActionRegistry:
    """从按业务域审核过的能力组装 SI 动作注册表。"""
    registry = ActionRegistry()
    SessionActions(runtime).register(registry)
    NavigationActions(runtime).register(registry)
    DocumentActions(runtime).register(registry)
    PartyActions(runtime).register(registry)
    RoutingActions(runtime).register(registry)
    CargoActions(runtime).register(registry)
    PaymentActions(runtime).register(registry)
    ValidationActions(runtime).register(registry)
    PublishingActions(runtime).register(registry)
    return registry

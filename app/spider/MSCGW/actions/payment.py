"""MSCGW SI 付款动作。"""
from __future__ import annotations

from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.spider.MSCGW import selectors
from app.spider.MSCGW.actions.parties import LocationActions
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


class PaymentActions:
    """封装付款方式、付款地点和备注的填写及校验。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime
        self.locations = LocationActions(runtime)

    def fill_payment(self, _inputs: Mapping[str, Any]) -> None:
        """填写付款方式、异地付款地点和备注，并校验页面回读。"""
        self.runtime.si_shadow.select_radio(
            selectors.PAYMENT_TYPE_RADIO, self.runtime.content.get("paymentType"), name="选择付款方式"
        )
        if self.runtime.content.get("paymentType") == "Payable Elsewhere":
            self.runtime.dom.scroll_to_see(selectors.PAYMENT_LOCATION_INPUT)
            self.locations.select_location(
                selectors.PAYMENT_LOCATION_INPUT,
                self.runtime.content.get("paymentLocation"),
                name="选择异地付款地点",
            )
        if self.runtime.content.get("remarks"):
            self.runtime.dom.scroll_to_see(selectors.PAYMENT_REMARK_INPUT)
            self.runtime.si_shadow.input_text(
                selectors.PAYMENT_REMARK_INPUT, self.runtime.content.get("remarks"), name="填写备注"
            )
        self.runtime._verify_payment_type()

    def register(self, registry: ActionRegistry) -> None:
        """将付款填写动作绑定到显式动作白名单。"""
        registry.register("MSCGW.fill_payment", lambda _context, inputs: self.fill_payment(inputs))

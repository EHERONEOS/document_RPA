"""MSCGW SI 支付方式填写。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


class SiFillPaymentTypeMixin:
    """封装支付方式、Elsewhere Location 与备注。"""

    def _fill_payment_type(self: "FhtMscgwSiTask") -> None:
        payment_type = self.content.get("paymentType")
        self.si_shadow.select_radio(selectors.PAYMENT_TYPE_RADIO, payment_type, name="选择支付方式")
        if payment_type == "Payable Elsewhere":
            self.dom.scroll_to_see(selectors.PAYMENT_LOCATION_INPUT)
            api = selectors.SEARCH_FREE_LOCATION_API if self.splitOrConsolidatedBill else selectors.SEARCH_LOCATION_API
            self.search_location_select(
                selectors.PAYMENT_LOCATION_INPUT,
                self.content.get("paymentLocation"),
                api,
                "GetLocations",
                name="选择Elsewhere Location",
            )
        if self.content.get("remarks"):
            self.dom.scroll_to_see(selectors.PAYMENT_REMARK_INPUT)
            self.si_shadow.input_text(selectors.PAYMENT_REMARK_INPUT, self.content.get("remarks"), name="填写备注")
        self._verify_payment_type()

    def _verify_payment_type(self: "FhtMscgwSiTask") -> None:
        """校验支付方式。"""
        self.verify_page_value(
            selector=selectors.PAYMENT_TYPE_CHECKED,
            field_path="paymentType",
            selector_type="text",
            page=self.si_shadow,
            name="出单类型",
        )
        if self.content.get("paymentType") == "Payable Elsewhere":
            self.verify_page_value(
                selector=selectors.PAYMENT_LOCATION_INPUT,
                field_path="paymentLocation",
                selector_type="value",
                page=self.si_shadow,
                name="选择Elsewhere Location",
            )
        self.verify_page_value(
            selector=selectors.PAYMENT_REMARK_INPUT,
            field_path="remarks",
            selector_type="value",
            page=self.si_shadow,
            name="填写备注",
            skip_if_empty=True,
        )

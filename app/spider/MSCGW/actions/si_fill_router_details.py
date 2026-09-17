"""MSCGW SI 普通单港口信息填写。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask

ROUTER_DETAIL_FIELDS = (
    ("receiptPlace", selectors.RECEIPT_INPUT, "收货地", False),
    ("pol", selectors.POL_INPUT, "起运港", True),
    ("pod", selectors.POD_INPUT, "卸货港", True),
    ("deliveryPlace", selectors.DELIVERY_INPUT, "交货地", False),
)

class SiFillRouterDetailsMixin:
    """封装普通 SI 的收发港及路由字段。"""

    def _fill_router_details(self: "FhtMscgwSiTask") -> None:
        for field_path, selector, name, required in ROUTER_DETAIL_FIELDS:
            value = self.content.get(field_path)
            if value:
                self.dom.scroll_to_see(selector, name, required=required)
                self.si_shadow.input_text(selector, value, name, required=required)
        self._verify_router_details()

    def _verify_router_details(self: "FhtMscgwSiTask") -> None:
        """验证普通单港口字段。"""
        for field_path, selector, name, required in ROUTER_DETAIL_FIELDS:
            self.verify_page_value(
                selector=selector,
                field_path=field_path,
                selector_type="value",
                page=self.si_shadow,
                name=name,
                skip_if_empty=not required,
            )

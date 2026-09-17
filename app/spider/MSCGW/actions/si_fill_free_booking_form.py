"""MSCGW SI 拆并单订舱信息填写。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


class SiFillFreeBookingFormMixin:
    """封装拆并单的订舱信息表单。"""

    def _fill_free_booking_form(self: "FhtMscgwSiTask") -> None:
        self.si_shadow.input_text(
            selectors.FREE_BOOKING_NUMBER,
            self.content.get("carrierBookingNumber"),
            name="输入订舱号",
        )
        self.si_shadow.select_by_word(
            selectors.FREE_AGENCY,
            self.content.get("mscAgency"),
            selectors.FREE_AGENCY_OPTIONS,
            clear_locator=selectors.FREE_AGENCY_CLEAR,
            name="选择MSC代理",
        )
        self.si_shadow.input_text(selectors.FREE_VESSEL, self.content.get("vessel"), name="输入船名")
        self.si_shadow.input_text(selectors.FREE_VOYAGE, self.content.get("voyage"), name="输入航次")
        self.verify_free_booking_form()

    def verify_free_booking_form(self: "FhtMscgwSiTask") -> None:
        """验证拆并单订舱信息。"""
        required_fields = (
            ("carrierBookingNumber", selectors.FREE_BOOKING_NUMBER, "订舱号", self.si_shadow),
            ("mscAgency", selectors.FREE_AGENCY, "MSC代理", self.si_shadow),
            ("vessel", selectors.FREE_VESSEL, "船名", self.si_shadow),
            ("voyage", selectors.FREE_VOYAGE, "航次", self.si_shadow),
        )
        for field_path, selector, name, page in required_fields:
            self.verify_page_value(
                selector=selector,
                field_path=field_path,
                selector_type="value",
                page=page,
                name=name,
            )

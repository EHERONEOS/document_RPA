"""MSCGW SI 普通单港口信息填写。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.task.errors import FormValidationError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.tasks.fz_snlwy_si import FzSnlwySiTask

ROUTER_DETAIL_FIELDS = (
    ("receiptPlace", selectors.RECEIPT_TEXT, selectors.RECEIPT_EDIT, "接货地"),
    ("pol", selectors.POL_TEXT, selectors.POL_EDIT, "装货港"),
    ("pod", selectors.POD_TEXT, selectors.POD_EDIT, "卸货港"),
    ("deliveryPlace", selectors.DELIVERY_TEXT, selectors.DELIVERY_EDIT, "目的地"),
)


def _compact_text(value) -> str:
    """去掉页面把签发类型拆成多段后产生的空白。"""
    return "".join(str(value or "").split())


class SiFillPortInfoMixin:
    """填写SI 收发通港口信息。"""

    def _fill_port_info(self: "FzSnlwySiTask") -> None:
        for field_path, text_sel, edit_sel, name in ROUTER_DETAIL_FIELDS:
            value = self.content.get(field_path)
            port_text = self.dom.get_text(text_sel, name=name)
            if port_text == value:
                continue
            self.dom.click(edit_sel, name=f"编辑{name}")
            self.dom.select_by_word(selectors.PORT_SELECT, value, selectors.PORT_OPTIONS, name="选择港口")
            self.dom.click(selectors.PORT_SUBMIT, name="确认港口")

        release_mode = self.content.get("releaseMode")
        model_text = self.dom.get_text(selectors.RELEASE_MODE_TEXT, name="申请签发类型")
        if _compact_text(release_mode) not in _compact_text(model_text):
            self.dom.select_by_word(
                selectors.RELEASE_MODE_SELECT,
                release_mode,
                selectors.RELEASE_MODE_OPTIONS,
                name="选择申请签发类型",
                ignore_space=True,
            )
        if self.content.get("hblNo"):
            self.dom.input_text(selectors.HBL_NO, self.content.get("hblNo"), name="填写House B/L No.")
        
        self._verify_port_info()

    def _verify_port_info(self: "FzSnlwySiTask") -> None:
        """验证普通单港口字段。"""
        for field_path, selector,edit_sel, name in ROUTER_DETAIL_FIELDS:
            self.verify_page_value(
                selector=selector,
                field_path=field_path,
                selector_type="text",
                name=name
            )
        release_mode = self.content.get("releaseMode")
        release_mode_text = self.dom.get_text(selectors.RELEASE_MODE_TEXT, name="申请签发类型")
        if _compact_text(release_mode) not in _compact_text(release_mode_text):
            raise FormValidationError(
                f"申请签发类型校验失败，实际值：{release_mode_text}，期望值：{release_mode}"
            )
        self.mark_field_done("releaseMode")
        self.verify_page_value(
            selector=selectors.HBL_NO,
            field_path="hblNo",
            selector_type="value",
            name="House B/L No.",
            skip_if_empty=True
        )

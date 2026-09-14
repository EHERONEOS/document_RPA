"""MSCGW SI 页面导航动作。"""
from __future__ import annotations

import time
from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.core.task.errors import BusinessError
from app.spider.MSCGW import selectors
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


class NavigationActions:
    """封装进入 MSCGW 装运指令页面所需的导航步骤。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime

    def open_shipping_instruction(self, _inputs: Mapping[str, Any]) -> dict[str, str]:
        """按是否空白提单进入装运指令页面并初始化 Shadow DOM。"""
        if self.runtime.blank_bill:
            self._goto_create_shipping_instruction()
        else:
            self._goto_shipping_instructions(self.runtime.content["bookingNo"])
        shadow = self.runtime.dom.get_shadow_root(selectors.SI_SHADOW)
        if shadow is None:
            raise BusinessError("未获取到 MSCGW SI 页面 Shadow DOM")
        self.runtime.si_shadow = shadow
        return {"url": str(getattr(self.runtime.page, "url", "") or "")}

    def _goto_shipping_instructions(self, booking_number: str) -> None:
        last_error: BusinessError | None = None
        for _ in range(3):
            try:
                self.runtime.http.wait_api_finished(
                    selectors.DASHBOARD_GRAPHQL_API,
                    trigger=lambda: self.runtime.page.get(selectors.EBOOKINGS_URL),
                )
                break
            except Exception:
                last_error = BusinessError("订舱列表查询失败")
        else:
            raise last_error or BusinessError("订舱列表查询失败")
        self.runtime.dom.input_text(selectors.BOOKING_SEARCH_INPUT, booking_number, "订舱搜索框", timeout=10)
        self.runtime.dom.click(selectors.SEARCH_BUTTON, "搜索按钮")
        page_booking_number = self.runtime.dom.get_text(
            selectors.BOOKING_FIRST_NUMBER, "第一条订舱号", required=False
        )
        if not page_booking_number:
            raise BusinessError("未找到订舱号，可能是订舱号不存在")
        if page_booking_number != booking_number:
            raise BusinessError(f"订舱号不匹配，页面值为 {page_booking_number}，消息值为 {booking_number}")
        page_status = self.runtime.dom.get_text(selectors.BOOKING_FIRST_STATUS, "第一条订舱状态", required=False)
        if page_status != "Confirmed":
            raise BusinessError(f"订舱号 {booking_number} 状态不是 Confirmed，页面值为 {page_status}")
        self.runtime.dom.click(selectors.BOOKING_FIRST_BUTTON, "跳转填单页面")
        self._wait_for_shipping_instructions()

    def _goto_create_shipping_instruction(self) -> None:
        self.runtime.page.get(selectors.CREATE_SHIPPING_INSTRUCTIONS_URL)
        self.runtime.page._wait_loaded()
        self.runtime.dom.input_text(selectors.CREATE_BOOKING_INPUT, self.runtime.content["bookingNo"], "订舱号")
        self.runtime.http.wait_api_finished(
            selectors.CHECK_BOOKING_API,
            trigger=lambda: self.runtime.dom.click(selectors.CREATE_CHECK_BOOKING_BTN),
        )
        create_button = self.runtime.dom._find(selectors.CREATE_BOOKING_BTN, required=False, name="创建提单")
        if create_button:
            create_button.click()
            self._wait_for_shipping_instructions()
            return
        reset_button = self.runtime.dom._find(selectors.RESET_CREATE_BOOKING_BTN, required=False, name="重置创建")
        if reset_button and reset_button.states.is_clickable:
            reset_button.click()
            time.sleep(1)
            self.runtime.dom.click(selectors.RESET_CREATE_SUBMIT, name="确认重置创建")
            self.runtime.dom.click(selectors.RESET_CREATE_CANCEL, name="关闭重置弹窗", required=False)
            self._wait_for_shipping_instructions()
            return
        if self.runtime.dom._find(selectors.CHECK_NO_BOOKING, required=False):
            raise BusinessError(f"订舱号 {self.runtime.content.get('bookingNo')} 不存在")
        errors = self.runtime.dom._find_eles(selectors.CHECK_ERROR_LI, required=False) or []
        messages = [
            (getattr(element, "text", "") or "").strip()
            for element in errors
            if (getattr(element, "text", "") or "").strip()
        ]
        raise BusinessError(f"订舱号 {self.runtime.content.get('bookingNo')} 已创建，错误信息为 {messages}")

    def _wait_for_shipping_instructions(self) -> None:
        for _ in range(30):
            if selectors.SHIPPING_INSTRUCTIONS_URL in str(getattr(self.runtime.page, "url", "") or ""):
                self.runtime.dom._find("css:#documents", timeout=20)
                return
            time.sleep(1)
        raise BusinessError("MSC 未在 30 秒内跳转至填单页面")

    def register(self, registry: ActionRegistry) -> None:
        """将打开 SI 页面的动作绑定到显式动作白名单。"""
        registry.register(
            "MSCGW.open_shipping_instruction",
            lambda _context, inputs: self.open_shipping_instruction(inputs),
        )

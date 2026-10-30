"""MSCGW SI 页面导航与地点搜索。"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from app.core.task.errors import BusinessError, ElementOperationError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.tasks.fz_snlwy_si import FzSnlwySiTask


class SiNavigationMixin:
    """封装 SI 各类填单页面的导航及地点选择。"""


    def _goto_booking_page(self: "FzSnlwySiTask") -> None:
        """跳转至订舱页面。

        页面加载时会先查订舱列表，这段时间查询按钮不可点。
        必须先等初始化接口结束，再等按钮恢复，然后才填订舱号并搜索。
        """
        self.confirm_submit()
        bookingNo = self.content["bookingNo"]
        self.http.wait_api_finished(
            selectors.BOOKING_LIST_API,
            trigger=lambda: self.page.get(selectors.BOOKING_URL),
            name="订舱列表初始化",
            timeout=60,
        )
        self._wait_booking_search_ready()
        self.dom.input_text(selectors.BOOKING_SEARCH_INPUT, bookingNo, "搜索框", timeout=30)
        self._wait_booking_search_ready()
        self.http.wait_api_finished(
            selectors.BOOKING_LIST_API,
            trigger=lambda: self.dom.click(selectors.SEARCH_BUTTON, "搜索按钮"),
            name="订舱查询",
            timeout=60,
        )

        booking_row = self.dom.get_text(
            selectors.BOOKING_ROW, "订舱列表行", required=False
        )
        if not booking_row:
            raise BusinessError(f"查不到订舱号{bookingNo}")
        page_booking_no = self.dom.get_text(
            selectors.BOOKING_ROW_NO, "查询订舱号", required=False
        )
        if page_booking_no != bookingNo:
            raise BusinessError(f"查不到订舱号{bookingNo}")
        open_bl_no_btn = self.dom._find(selectors.OPEN_BL_NO_BTN, "生成提单按钮", timeout=1,required=False)
        if not open_bl_no_btn:
            raise BusinessError(f"该订舱号{bookingNo}无法生成提单")
        res = self.http.wait_api_finished(
            selectors.BOOKING_CHECK_API,
            trigger=lambda: self.dom.click(selectors.OPEN_BL_NO_BTN, "生成提单按钮"),
            name="生成提单"
        )
        if res.get("response", {}).get("code") != 0:
            raise BusinessError(f"生成提单校验失败;官网提示信息:{res.get('response', {}).get('msg')}")
        time.sleep(3)
        url = str(getattr(self.page, "url", "") or "")
        if not selectors.CREATE_BL_URL in url:
            raise BusinessError(f"跳转至生成提单页面失败")


    def _wait_booking_search_ready(self: "FzSnlwySiTask", timeout: int = 60) -> None:
        """等初始化列表查询结束，搜索按钮恢复可点击。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            button = self.dom._find(
                selectors.SEARCH_BUTTON, "搜索按钮", required=False, timeout=1
            )
            class_name = (button.attr("class") or "") if button else ""
            disabled = "is-disabled" in class_name.split() or "disabled" in class_name.split()
            if button and button.states.is_clickable and not disabled:
                return
            time.sleep(0.3)
        raise ElementOperationError("订舱列表仍在初始化，搜索按钮不可点击")

    def confirm_submit(self: "FzSnlwySiTask") -> None:
        """确认提交。"""
        self.dom.click(selectors.DIALOG_CANCEL_BTN, "弹窗取消按钮",required=False,timeout=1)

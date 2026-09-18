"""MSCGW SI 页面导航与地点搜索。"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from app.core.task.errors import BusinessError, ElementNotFoundError
from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


class SiNavigationMixin:
    """封装 SI 各类填单页面的导航及地点选择。"""


    def _goto_navigation(self: "FhtMscgwSiTask") -> None:
        """跳转至导航页面。"""
        if self.blankBill: #空白单
            self._goto_create_shippinginstruction()
        elif self.splitOrConsolidatedBill: #拆并单
            self._goto_free_form_esi()
        else:
            self._goto_shippinginstructions(self.content["bookingNo"])

    def _goto_shippinginstructions(self: "FhtMscgwSiTask", bookingNo: str) -> None:
        """跳转至 Shipping Instructions 填单页面。"""
        last_error = None
        for _ in range(3):
            try:
                self.http.wait_api_finished(
                    selectors.DASHBOARD_GRAPHQL_API,
                    trigger=lambda: self.page.get(selectors.EBOOKINGS_URL),
                    name="查询booking列表接口"
                )
                break
            except Exception as exc:
                last_error = exc
        else:
            raise BusinessError("booking列表查询失败") from last_error

        self.dom.input_text(selectors.BOOKING_SEARCH_INPUT, bookingNo, "搜索框", timeout=10)
        self.dom.click(selectors.SEARCH_BUTTON, "搜索按钮")
        page_booking_no = self.dom.get_text(
            selectors.BOOKING_FIRST_NUMBER, "第一条Booking Number", required=False
        )
        if not page_booking_no:
            raise BusinessError("未找到到Booking Number，可能是因为Booking Number不存在")
        if page_booking_no != bookingNo:
            raise BusinessError(f"Booking Number不匹配,页面值为{page_booking_no},消息值为{bookingNo}")
        page_status = self.dom.get_text(
            selectors.BOOKING_FIRST_STATUS, "第一条Booking Status", required=False
        )
        if page_status != "Confirmed":
            raise BusinessError(f"{bookingNo} 状态不是Confirmed,页面值为{page_status}")
        self.dom.click(selectors.BOOKING_FIRST_BUTTON, "跳转填单页面")
        self._wait_for_shippinginstructions()

    def _goto_create_shippinginstruction(self: "FhtMscgwSiTask") -> None:
        """跳转至空白提单页面。"""
        self.page.get(selectors.CREATE_SHIPPING_INSTRUCTIONS_URL)
        self.page._wait_loaded()
        self.dom.input_text(selectors.CREATE_BOOKING_INPUT, self.content["bookingNo"], "Booking Number")
        self.http.wait_api_finished(
            selectors.CHECK_BOOKING_API,
            trigger=lambda: self.dom.click(selectors.CREATE_CHECK_BOOKING_BTN),
            name="校验booking接口"
        )
        create_btn = self.dom._find(selectors.CREATE_BOOKING_BTN, required=False, name="创建提单")
        if create_btn:
            create_btn.click()
            self._wait_for_shippinginstructions()
            return
        reset_create_btn = self.dom._find(selectors.RESET_CREATE_BOOKING_BTN, required=False, name="重置创建")
        if reset_create_btn and reset_create_btn.states.is_clickable:
            reset_create_btn.click()
            time.sleep(1)
            self.dom.click(selectors.RESET_CREATE_SUBMIT, name="确认重置创建")
            self.dom.click(selectors.RESET_CREATE_CANCEL, name="取消弹窗", required=False)
            self._wait_for_shippinginstructions()
            return

        no_booking = self.dom._find(selectors.CHECK_NO_BOOKING, required=False)
        if no_booking:
            raise BusinessError(f"单号{self.content.get('bookingNo')} 不存在")
        error_doms = self.dom._find_eles(selectors.CHECK_ERROR_LI, required=False) or []
        error_msgs = [
            (getattr(dom, "text", "") or "").strip()
            for dom in error_doms
            if (getattr(dom, "text", "") or "").strip()
        ]
        if error_msgs:
            raise BusinessError(f"单号{self.content.get('bookingNo')}已创建,错误信息为{error_msgs}")
        else:
            raise BusinessError(f"创建空白单页面异常")

    def _goto_free_form_esi(self: "FhtMscgwSiTask") -> None:
        """跳转至拆单/并单页面。"""
        self.page.get(selectors.FREE_FORM_ESI_URL)
        for _ in range(60):
            url = str(getattr(self.page, "url", "") or "")
            if selectors.FREE_FORM_ESI_URL in url:
                self.dom._find("css:#documents", timeout=20, name="等待填单页面加载")
                return
            time.sleep(1)
        raise BusinessError("MSC 未在 60 秒内跳转至 填单页面")

    def _wait_for_shippinginstructions(self: "FhtMscgwSiTask") -> None:
        """等待跳转到 Shipping Instructions。"""
        for _ in range(60):
            url = str(getattr(self.page, "url", "") or "")
            if selectors.SHIPPING_INSTRUCTIONS_URL in url:
                self.dom._find("css:#documents", timeout=20, name="等待填单页面加载")
                return
            time.sleep(1)
        raise BusinessError("MSC 未在 60 秒内跳转至 填单页面")

    def search_location_select(
        self: "FhtMscgwSiTask",
        location: str,
        value: str,
        url: str,
        operationName: str,
        name: str = "选择loaction",
    ) -> None:
        """搜索并选择地点。"""
        target_text = str(value).strip()
        if not target_text:
            raise ElementNotFoundError(f"{name}目标值为空")

        normalize = lambda text: re.sub(r"\s+", " ", str(text or "")).strip().casefold()
        words = re.findall(r"[^\W_]+", target_text, flags=re.UNICODE)
        if not words:
            raise ElementNotFoundError(f"{name}目标值不包含可搜索单词：{target_text}")

        element = self.si_shadow._find(location, name)
        expected_value = str(value)
        if str(element.value or "") == expected_value:
            return True
        element.click()

        search_keywords = []
        for index in range(1, len(words) + 1):
            search_keyword = " ".join(words[:index])
            search_keywords.append(search_keyword)
            self.logger.info(f"搜索并选择{name}，搜索关键词：{search_keyword}")
            self.http.wait_api_finished(
                url=url,
                method=("POST",),
                trigger=lambda keyword=search_keyword: element.input(keyword, clear=True),
                request_params={"operationName": operationName},
                timeout=20,
                required=False,
            )
            for option in self.si_shadow._find_eles(selectors.DIALOG_LOCATION_OPTION, required=False):
                if normalize(option.text) != normalize(target_text):
                    continue
                option.click()
                self.page.run_js("arguments[0].blur();", element)
                self.logger.info(f"选择{name}")
                return True

        raise ElementNotFoundError(
            f"{name}选项不存在：{target_text}；已尝试搜索：{'；'.join(search_keywords)}"
        )

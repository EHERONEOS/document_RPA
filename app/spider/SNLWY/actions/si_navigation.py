"""SNLWY SI 页面导航与地点搜索。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.core.task.errors import BusinessError, ElementOperationError, LoginError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.tasks.snlwy_si import SnlwySiTask


class SiNavigationMixin:
    """封装 SI 各类填单页面的导航及地点选择。"""

    def _booking_search_query(self: "SnlwySiTask") -> tuple[str, str]:
        """提单号优先，提单号为空时使用订舱号。"""
        bl_no = self.content.get("blNo")
        if bl_no is not None and not isinstance(bl_no, str):
            raise BusinessError("下发 blNo 必须是字符串")
        if bl_no and bl_no.strip():
            return "提单号", bl_no.strip()

        booking_no = self.content.get("bookingNo")
        if not isinstance(booking_no, str) or not booking_no.strip():
            raise BusinessError("提单号为空时，下发 bookingNo 必须是非空字符串")
        return "订舱号", booking_no.strip()

    def _goto_booking_page(self: "SnlwySiTask") -> None:
        """跳转至订舱页面。

        页面加载时会先查订舱列表，这段时间查询按钮不可点。
        必须先等初始化接口结束、按钮恢复，再切换查询类型并填号搜索。
        """
        search_type, search_no = self._booking_search_query()
        self._dismiss_optional_dialog()
        self._ensure_booking_initialized()
        self._wait_booking_search_ready()
        self.dom.select_by_word(
            selectors.BOOKING_SEARCH_TYPE,
            search_type,
            selectors.ELEMENT_SELECT_OPTIONS,
            name="订舱查询类型",
        )
        self.dom.input_text(
            selectors.BOOKING_SEARCH_INPUT.format(search_type=search_type),
            search_no,
            "搜索框",
            timeout=30,
        )
        self._wait_booking_search_ready()
        search_result = self.http.wait_api_finished(
            selectors.BOOKING_LIST_API,
            trigger=lambda: self.dom.click(selectors.SEARCH_BUTTON, "搜索按钮"),
            name="订舱查询",
            timeout=60,
        )
        self._check_booking_session(search_result)

        booking_row = self.dom.get_text(
            selectors.BOOKING_ROW, "订舱列表行", required=False
        )
        if not booking_row:
            raise BusinessError(f"查不到{search_type}{search_no}")
        if search_type == "提单号":
            # 结果列表会用省略号展示长号码，get_text 读取的是 DOM 中的原文。
            matches = search_no in booking_row.split()
        else:
            matches = self.dom.get_text(
                selectors.BOOKING_ROW_NO, "查询订舱号", required=False
            ).strip() == search_no
        if not matches:
            raise BusinessError(f"查不到{search_type}{search_no}")
        open_bl_no_btn = self._find_create_bl_button()
        res = self.http.wait_api_finished(
            selectors.BOOKING_CHECK_API,
            trigger=lambda: open_bl_no_btn.click(),
            name="生成提单"
        )
        if res.get("response", {}).get("code") != 0:
            raise BusinessError(f"生成提单校验失败;官网提示信息:{res.get('response', {}).get('msg')}")
        time.sleep(3)
        url = str(getattr(self.page, "url", "") or "")
        if not selectors.CREATE_BL_URL in url:
            raise BusinessError(f"跳转至生成提单页面失败")


    def _ensure_booking_initialized(self: "SnlwySiTask") -> None:
        """复用登录校验的初始化；离开过订舱页或重复调用时重新加载。"""
        initialized = getattr(self, "_booking_initialized", False)
        self._booking_initialized = False
        on_booking_page = (
            self._hash_path(self._page_url()) == self._hash_path(selectors.BOOKING_URL)
        )
        if initialized and on_booking_page:
            self._check_booking_session()
            return

        # 同一路由 get() 可能不发初始化请求，此时必须刷新再监听。
        result = self.http.wait_api_finished(
            selectors.BOOKING_LIST_API,
            trigger=(self.page.refresh if on_booking_page
                     else lambda: self.page.get(selectors.BOOKING_URL)),
            name="订舱列表初始化",
            timeout=60,
        )
        self._check_booking_session(result)

    def _find_create_bl_button(self: "SnlwySiTask", timeout: float = 5):
        """先找行内可用按钮，再悬浮更多并等待响应式菜单（可能挂在 body）。"""
        def available(elements):
            return next(
                (element for element in elements
                 if element.states.is_displayed and element.states.is_enabled
                 and element.states.is_clickable),
                None,
            )

        button = available(self.dom._find_eles(
            selectors.OPEN_BL_NO_BTN, "生成提单按钮", required=False, timeout=1
        ))
        if button:
            return button

        more = available(self.dom._find_eles(
            selectors.BOOKING_MORE_BTN, "订舱更多按钮", required=False, timeout=1
        ))
        menu_opened = False
        if more:
            visible_popup_ids = {
                popup.attr("id") for popup in self.dom._find_eles(
                    selectors.BOOKING_ACTION_POPUPS, "订舱操作菜单", required=False, timeout=0
                ) if popup.states.is_displayed and popup.attr("id")
            }
            more.hover()
            deadline = time.monotonic() + timeout
            while True:
                # Element Plus 可能在首次悬浮时才创建浮层并设置关联 ID。
                popup_ids = set((
                    (more.attr("aria-controls") or "") + " "
                    + (more.attr("aria-describedby") or "")
                ).split())
                button = available(self.dom._find_eles(
                    selectors.OPEN_BL_NO_BTN, "生成提单按钮", required=False, timeout=0
                ))
                if button:
                    return button
                for popup in self.dom._find_eles(
                    selectors.BOOKING_ACTION_POPUPS, "订舱操作菜单", required=False, timeout=0
                ):
                    if not popup.states.is_displayed:
                        continue
                    if popup_ids and popup.attr("id") not in popup_ids:
                        continue
                    if not popup_ids and popup.attr("id") in visible_popup_ids:
                        continue
                    menu_opened = True
                    button = available(popup.eles(selectors.POPUP_CREATE_BL_BTN, timeout=0))
                    if button:
                        return button
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
        search_type, search_no = self._booking_search_query()
        if not more:
            raise ElementOperationError(
                f"{search_type}{search_no}未找到可悬浮的更多按钮，无法检查生成提单操作"
            )
        if not menu_opened:
            raise ElementOperationError(
                f"{search_type}{search_no}的更多菜单未成功展开，无法检查生成提单操作"
            )
        raise BusinessError(f"该{search_type}{search_no}无法生成提单")

    def _check_booking_session(self: "SnlwySiTask", result=None) -> None:
        """登录校验后也可能失效；区分登录跳转与列表加载慢。"""
        body = result.get("response") if isinstance(result, dict) else None
        code = body.get("code") if isinstance(body, dict) else None
        if (
            code in (401, "401")
            or self._is_login_url(self._page_url())
            or self._has_login_button()
        ):
            raise LoginError("SNLWY 登录会话已失效，无法继续查询订舱")

    def _wait_booking_search_ready(self: "SnlwySiTask", timeout: int = 60) -> None:
        """等初始化列表查询结束，搜索按钮恢复可点击。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._check_booking_session()
            button = self.dom._find(
                selectors.SEARCH_BUTTON, "搜索按钮", required=False, timeout=1
            )
            class_name = (button.attr("class") or "") if button else ""
            disabled = "is-disabled" in class_name.split() or "disabled" in class_name.split()
            if button and button.states.is_clickable and not disabled:
                return
            time.sleep(0.3)
        raise ElementOperationError("订舱列表仍在初始化，搜索按钮不可点击")

    def _dismiss_optional_dialog(self: "SnlwySiTask") -> None:
        """关闭可能遗留的提示弹窗，避免遮挡订舱查询。"""
        self.dom.click(selectors.DIALOG_CANCEL_BTN, "弹窗取消按钮",required=False,timeout=1)

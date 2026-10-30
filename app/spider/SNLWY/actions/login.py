"""MSC myMSC 登录流程。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.core.task.errors import BusinessError, LoginError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.base import SnlwyBase


class LoginMixin:
    """复用 myMSC 会话，并在失效时通过 Azure AD B2C 登录。"""

    login_wait_seconds = 10
    session_expire_hours = 12
    # 会话失效时首页会先渲染，等接口 401 后才跳登录页。这段时间不能判成已登录。
    login_redirect_grace_seconds = 8
    login_state_poll_seconds = 0.3


    def login(self: "SnlwyBase") -> None:
        """优先复用 Cookie，必要时只由一个任务提交账号凭据。"""
        # return
        self._open_home_page()
        if self._wait_until_login_settled():
            self.save_session_storage(self.session_redis_key, expire_hours=self.session_expire_hours)
            self.logger.info("SNLWY 已登录")
            return


        self.set_page_session_storage(self.session_redis_key)
        time.sleep(1)
        self.page.refresh()
        if self._wait_until_login_settled():
            self.save_session_storage(self.session_redis_key, expire_hours=self.session_expire_hours)
            self.logger.info("获取redis sessionStorage 登录成功")
            return

        while not self.claim_credential_login():
            self.set_page_session_storage(self.session_redis_key)
            time.sleep(1)
            self.page.refresh()
            if self._wait_until_login_settled():
                self.logger.info("SNLWY 已复用其他任务刷新后的 sessionStorage")
                return
        
        self._auto_login()
        self.save_session_storage(self.session_redis_key, expire_hours=self.session_expire_hours)


    def _open_home_page(self: "SnlwyBase") -> None:
        """打开 SNLWY 首页。"""
        self.page.get(selectors.INDEX_URL, show_errmsg=True)
        


    def _auto_login(self: "SnlwyBase") -> None:
        """优先使用登录服务 Cookie，失败时回退至浏览器自动化登录。"""
        url = str(getattr(self.page, "url", "") or "")
        if not url.startswith(selectors.LOGIN_URL):
            self.page.get(selectors.LOGIN_URL, show_errmsg=True)
            self.page.wait.doc_loaded()
        account = str(self.website_info.get("websiteAccount") or "").strip()
        password = str(self.website_info.get("websitePassword") or "").strip()
        if not account or not password:
            raise LoginError("SNLWY 登录缺少网站账号或密码")

        try:
            self.dom.input_text(selectors.LOGIN_USERNAME, account, "输入账号")
            self.dom.input_text(selectors.LOGIN_PASSWORD, password, "输入密码")
            self.dom.click(selectors.LOGIN_SUBMIT, "点击登录按钮")
            self._wait_for_login_success()
            return
        except Exception as exc:
            self.logger.warn(f"SNLWY 登录服务失败，回退浏览器自动化登录：{exc}")


 


    def _wait_for_login_success(self: "SnlwyBase") -> None:
        """等待 SNLWY 登录成功。"""
        if self._wait_until_login_settled(waiting_for_success=True):
            return
        raise LoginError("SNLWY 登录失败或需要人工完成 MFA/安全验证")


    def _page_url(self: "SnlwyBase") -> str:
        """读取地址。hash 路由以 location.href 为准，避免 CDP 地址还停在首页。"""
        try:
            href = self.page.run_js("return window.location.href")
        except Exception:
            href = None
        if href:
            return str(href)
        return str(getattr(self.page, "url", "") or "")


    @staticmethod
    def _hash_path(url: str) -> str:
        text = str(url or "").strip()
        if "#" in text:
            text = text.split("#", 1)[1]
        text = text.split("?", 1)[0].rstrip("/")
        return text if text.startswith("/") else ""


    def _is_login_url(self: "SnlwyBase", url: str) -> bool:
        return self._hash_path(url) == "/login" or url.startswith(selectors.LOGIN_URL)


    def _is_home_url(self: "SnlwyBase", url: str) -> bool:
        path = self._hash_path(url)
        return path == "/search-service/quick-search" or url.startswith(selectors.INDEX_URL)


    def _has_login_button(self: "SnlwyBase") -> bool:
        return bool(self.dom._find(
            selectors.LOGIN_TAG_DOM, name="登录标识", timeout=0.2, required=False
        ))


    def _home_shell_ready(self: "SnlwyBase") -> bool:
        return bool(self.dom._find(
            "c:.locale-box", "等待语言选择器加载", timeout=0.5, required=False
        ))


    def _access_token_state(self: "SnlwyBase") -> bool | None:
        """读取首页用来维持登录的 ACCESS_TOKEN。读不到时返回 None，不参与判断。"""
        try:
            token = self.page.run_js(
                "return window.sessionStorage.getItem('ACCESS_TOKEN') || ''"
            )
        except Exception:
            return None
        text = str(token or "").strip().strip('"')
        if not text or text in {"null", "undefined"}:
            return False
        return True


    def _wait_until_login_settled(
        self: "SnlwyBase", *, waiting_for_success: bool = False
    ) -> bool:
        """等登录态稳定后再判断是否已登录。

        登录失效时，站点会先打开首页，等接口返回 401 后才跳到登录页。
        跳转完成前地址仍是首页，暂时看不到登录按钮也不能当成已登录。
        """
        deadline = time.monotonic() + self.login_wait_seconds
        ready_since = None
        while time.monotonic() < deadline:
            url = self._page_url()
            if self._is_login_url(url):
                if waiting_for_success:
                    ready_since = None
                    time.sleep(self.login_state_poll_seconds)
                    continue
                return False
            if self._has_login_button():
                if waiting_for_success:
                    ready_since = None
                    time.sleep(self.login_state_poll_seconds)
                    continue
                return False

            token_state = self._access_token_state()
            if token_state is False and self._is_home_url(url):
                ready_since = None
                if not waiting_for_success:
                    self.logger.info("SNLWY 未检测到有效登录令牌，页面还在首页时不判定为已登录")
                    return False
                time.sleep(self.login_state_poll_seconds)
                continue

            if token_state is not False and self._home_shell_ready():
                now = time.monotonic()
                if ready_since is None:
                    ready_since = now
                elif now - ready_since >= self.login_redirect_grace_seconds:
                    if (
                        self._is_login_url(self._page_url())
                        or self._has_login_button()
                        or self._access_token_state() is False
                    ):
                        return False
                    return True
            else:
                ready_since = None
            time.sleep(self.login_state_poll_seconds)
        return False


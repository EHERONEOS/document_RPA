"""MSC myMSC 登录流程。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.core.task.errors import LoginError
from app.spider.MSCGW import selectors
from app.spider.MSCGW.selectors import LOGIN_URL, INDEX_URL, AUTH_URL

if TYPE_CHECKING:
    from app.spider.MSCGW.base import MscgwBase


class LoginMixin:
    """复用 myMSC 会话，并在失效时通过 Azure AD B2C 登录。"""

    login_wait_seconds = 30

    def login(self: "MscgwBase") -> None:
        """优先复用 Cookie，必要时只由一个任务提交账号凭据。"""
        # self._open_login_page()
        # self.util_redis.delete(self.cookies_redis_key)
        self._open_home_page()
        if self._is_logged_in():
            self.save_cookies(self.cookies_redis_key)
            self.logger.info("MSC 已登录")
            return


        self.set_page_cookies(self.cookies_redis_key)
        self._open_home_page()
        if self._is_logged_in():
            self.save_cookies(self.cookies_redis_key)
            self.logger.info("获取redis cookie 登录成功")
            return

        while not self.claim_credential_login():
            self.set_page_cookies(self.cookies_redis_key)
            self._open_home_page()
            if self._is_logged_in():
                self.logger.info("MSC 已复用其他任务刷新后的 Cookie")
                return
        
        self._login_with_credentials()
        self.save_cookies(self.cookies_redis_key)


    def _open_home_page(self: "MscgwBase") -> None:
        """打开 myMSC 首页。"""
        self.page.get(self.index_url, show_errmsg=True)
        self.page.wait.doc_loaded()
        self.dom.click(
            selectors.COOKIE_ACCEPT_BUTTON,
            "MSC Cookie 同意按钮",
            timeout=1,
            required=False,
        )



    def _login_with_credentials(self: "MscgwBase") -> None:
        """优先使用登录服务 Cookie，失败时回退至浏览器自动化登录。"""
        account = str(self.website_info.get("websiteAccount") or "").strip()
        password = str(self.website_info.get("websitePassword") or "")
        if not account or not password:
            raise LoginError("MSC 登录缺少网站账号或密码")

        try:
            self._login_with_service_cookies(account, password)
            return
        except Exception as exc:
            self.logger.warn(f"MSC 登录服务失败，回退浏览器自动化登录：{exc}")

        self._login_with_browser(account, password)

    def _login_with_service_cookies(self: "MscgwBase", account: str, password: str) -> None:
        """调用本地登录服务获取 Cookie，并将其写入浏览器会话。"""
        response = self.http.request(
            "POST",
            selectors.LOGIN_API_URL,
            json={
                "websiteAccount": account,
                "websitePassword": password,
            },
            timeout=self.login_wait_seconds,
        )
        try:
            result: dict[str, Any] = response.json()
        except ValueError as exc:
            raise LoginError("MSC 登录服务返回了无效的 JSON 响应") from exc
        if not isinstance(result, dict):
            raise LoginError("MSC 登录服务返回了无效的 JSON 响应")

        if result.get("code") != 200:
            message = str(result.get("message") or "未知错误")
            raise LoginError(f"MSC 登录服务调用失败：{message}")

        cookies = result.get("data")
        if not isinstance(cookies, dict) or not cookies:
            raise LoginError("MSC 登录服务未返回有效 Cookie")

        self.page.set.cookies(cookies)
        self._open_home_page()
        if not self._is_logged_in():
            raise LoginError("MSC Cookie 登录失败")

    def _login_with_browser(self: "MscgwBase", account: str, password: str) -> None:
        """执行原有 Azure AD B2C 自动化登录流程。"""
        if self._is_auth_in():
            self._submit_login(account, password)
        else:
            self._submit_auth(account, password)

    def _submit_auth(self: "MscgwBase", account: str, password: str) -> None:
        """提交 Azure AD B2C 授权。"""
        self.dom.input_text(selectors.LOGIN_USERNAME, account, "MSC 登录邮箱", timeout=10)
        time.sleep(1)
        self.dom.click(selectors.LOGIN_NEXT, "MSC 登录下一步", timeout=10)
        if self._wait_for_password_page_or_success():
            return
        self._submit_login(account, password)

    def _submit_login(self: "MscgwBase", account: str, password: str) -> None:
        """提交 Azure AD B2C 登录。"""
        # userdom = self.dom._find(selectors.IDENTITY_USERNAME)
        time.sleep(2)
        self.dom.input_text(selectors.IDENTITY_USERNAME, account, "MSC 登录邮箱", timeout=10)

        self.dom.input_text(
            selectors.IDENTITY_PASSWORD,
            password,
            "MSC 登录密码",
            timeout=10,
        )
        self.dom.click(selectors.IDENTITY_SUBMIT, "MSC 登录提交按钮", timeout=10)
        self._wait_for_login_success()


    def _wait_for_password_page_or_success(self: "MscgwBase") -> bool:
        """等待邮箱页在 30 秒内跳转至 Azure AD B2C 授权地址。"""
        for _ in range(self.login_wait_seconds):
            if self._is_auth_in():
                self.page.wait.doc_loaded()
                return False
            if self._is_logged_in():
                self.page.wait.doc_loaded()
                return True
            self._raise_if_identity_error()
            time.sleep(1)
        raise LoginError("MSC 未在 30 秒内跳转至 Azure AD B2C 授权页面")

    def _wait_for_login_success(self: "MscgwBase") -> None:
        """等待 Azure AD B2C 返回 myMSC；超时通常代表 MFA 或验证未完成。"""
        for _ in range(self.login_wait_seconds):
            if self._is_logged_in():
                return
            self._raise_if_identity_error()
            time.sleep(1)
        raise LoginError("MSC 登录失败或需要人工完成 MFA/安全验证")

    def _is_auth_in(self: "MscgwBase") -> bool:
        """判断是否已登录。"""
        url = str(getattr(self.page, "url", "") or "")
        return url.startswith(AUTH_URL)

    def _is_logged_in(self: "MscgwBase") -> bool:
        """判断是否已登录。"""
        url = str(getattr(self.page, "url", "") or "")
        return url.startswith(INDEX_URL)

    def _raise_if_identity_error(self: "MscgwBase") -> None:
        """将 Azure AD B2C 的可见错误转换为统一登录异常。"""
        for error_element in self.page.eles(selectors.IDENTITY_ERROR_MESSAGES, timeout=0.2):
            error_message = str(getattr(error_element, "text", "") or "").strip()
            if error_message:
                raise LoginError(f"MSC 登录失败：{error_message}")

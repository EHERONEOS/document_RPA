"""MSC myMSC 登录流程。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.core.task.errors import LoginError
from app.spider.MSC import selectors
from app.spider.MSC.selectors import LOGIN_URL, INDEX_URL, AUTH_URL

if TYPE_CHECKING:
    from app.spider.MSC.base import MscBase


class LoginMixin:
    """复用 myMSC 会话，并在失效时通过 Azure AD B2C 登录。"""

    login_wait_seconds = 30

    def login(self: "MscBase") -> None:
        """优先复用 Cookie，必要时只由一个任务提交账号凭据。"""
        # self._open_login_page()
        return
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


    def _open_home_page(self: "MscBase") -> None:
        """打开 myMSC 首页。"""
        self.page.get(self.index_url, show_errmsg=True)
        self.page.wait.doc_loaded()
        self.dom.click_if_clickable(
            selectors.COOKIE_ACCEPT_BUTTON,
            "MSC Cookie 同意按钮",
            timeout=1,
        )



    def _login_with_credentials(self: "MscBase") -> None:
        """完成 myMSC 邮箱页和 Azure AD B2C 密码页的两段式登录。"""

        
        account = str(self.website_info.get("websiteAccount") or "").strip()
        password = str(self.website_info.get("websitePassword") or "")
        if not account or not password:
            raise LoginError("MSC 登录缺少网站账号或密码")


        if self._is_auth_in():
            self._submit_login(account, password)
        else:
            self._submit_auth(account, password)
        

        

        


    def _submit_auth(self: "MscBase", account: str, password: str) -> None:
        """提交 Azure AD B2C 授权。"""
        self.dom.input_text(selectors.LOGIN_USERNAME, account, "MSC 登录邮箱", timeout=10)
        self.dom.click(selectors.LOGIN_NEXT, "MSC 登录下一步", timeout=10)
        if self._wait_for_password_page_or_success():
            return
        self._submit_login(account, password)

    def _submit_login(self: "MscBase", account: str, password: str) -> None:
        """提交 Azure AD B2C 登录。"""
        # userdom = self.dom._find(selectors.IDENTITY_USERNAME)

        self.dom.input_text(selectors.IDENTITY_USERNAME, account, "MSC 登录邮箱", timeout=10)

        self.dom.input_text(
            selectors.IDENTITY_PASSWORD,
            password,
            "MSC 登录密码",
            timeout=10,
        )
        self.dom.click(selectors.IDENTITY_SUBMIT, "MSC 登录提交按钮", timeout=10)
        self._wait_for_login_success()


    def _wait_for_password_page_or_success(self: "MscBase") -> bool:
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

    def _wait_for_login_success(self: "MscBase") -> None:
        """等待 Azure AD B2C 返回 myMSC；超时通常代表 MFA 或验证未完成。"""
        for _ in range(self.login_wait_seconds):
            if self._is_logged_in():
                return
            self._raise_if_identity_error()
            time.sleep(1)
        raise LoginError("MSC 登录失败或需要人工完成 MFA/安全验证")

    def _is_auth_in(self: "MscBase") -> bool:
        """判断是否已登录。"""
        url = str(getattr(self.page, "url", "") or "")
        return url.startswith(AUTH_URL)

    def _is_logged_in(self: "MscBase") -> bool:
        """判断是否已登录。"""
        url = str(getattr(self.page, "url", "") or "")
        return url.startswith(INDEX_URL)

    def _raise_if_identity_error(self: "MscBase") -> None:
        """将 Azure AD B2C 的可见错误转换为统一登录异常。"""
        for error_element in self.page.eles(selectors.IDENTITY_ERROR_MESSAGES, timeout=0.2):
            error_message = str(getattr(error_element, "text", "") or "").strip()
            if error_message:
                raise LoginError(f"MSC 登录失败：{error_message}")

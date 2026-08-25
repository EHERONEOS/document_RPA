"""EMC 的 DrissionPage 登录流程。"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from DrissionPage.common import Keys

from app.core.integrations.captcha import get_verify_code
from app.core.integrations.email_otp import read_latest_otp
from app.core.task.errors import LoginError
from app.spider.EMC import selectors

if TYPE_CHECKING:
    from app.spider.EMC.base import EmcBase


class LoginMixin:
    """复用 EMC Cookie，并在失效时执行图形验证码和可选邮件 OTP 登录。"""

    email_otp_roles = frozenset({"FULI", "KAIYANG"})
    captcha_type_id = 7
    captcha_max_attempts = 5
    login_max_attempts = 3

    def login(self: "EmcBase") -> None:
        self._open_si_page()
        if self._is_logged_in(timeout=10):
            self.save_cookies(self.cookies_redis_key)
            self.logger.info("EMC 已登录")
            return

        self.set_page_cookies(self.cookies_redis_key)
        self._open_si_page()
        if self._is_logged_in(timeout=10):
            self.logger.info("EMC 已复用 Redis Cookie")
            return

        while not self.claim_credential_login():
            self.set_page_cookies(self.cookies_redis_key)
            self._open_si_page()
            if self._is_logged_in(timeout=10):
                self.logger.info("EMC 已复用其他任务刷新后的 Cookie")
                return

        self._login_with_credentials()
        self.save_cookies(self.cookies_redis_key)

    def _open_si_page(self: "EmcBase") -> None:
        self.page.get(self.si_url, show_errmsg=True)
        self.page.wait.doc_loaded()
        time.sleep(1)

    def _is_logged_in(self: "EmcBase", timeout=1) -> bool:
        """等待 EMC 顶部登录标识，兼容 BrowserManager 的非阻塞加载模式。"""
        return bool(self.page.eles(selectors.LOGIN_USER_INFO, timeout=timeout))

    def _login_with_credentials(self: "EmcBase") -> None:
        account = str(self.website_info.get("websiteAccount") or "")
        password = str(self.website_info.get("websitePassword") or "")
        if not account or not password:
            raise LoginError("EMC 登录缺少网站账号或密码")

        for attempt in range(1, self.login_max_attempts + 1):
            self.page.get(self.login_url, show_errmsg=True)
            self.page.wait.doc_loaded()
            captcha = self._read_captcha()
            login_input = self.dom._find(selectors.LOGIN_ACCOUNT, "EMC 登录账号", timeout=5)
            login_input.input([account, Keys.TAB, password, Keys.TAB, captcha], clear=True)
            self.dom.click(selectors.LOGIN_SUBMIT, "EMC 登录按钮", timeout=5)

            alert_text = self.dom.handle_alert(timeout=1)
            if alert_text:
                raise LoginError(f"EMC 登录提示：{alert_text}")
            page_html = self.page.html or ""
            if "连续错误 5 次帐户将被锁定" in page_html:
                raise LoginError("EMC 登录账号即将锁定")
            if "Login verification code is not correct" in page_html:
                continue

            self._complete_email_otp_if_required()
            if self._wait_for_login_success():
                return
            self.logger.warn(f"EMC 第 {attempt} 次登录未成功")

        raise LoginError("EMC 登录失败")

    def _read_captcha(self: "EmcBase") -> str:
        for _ in range(self.captcha_max_attempts):
            captcha_element = self.dom._find(selectors.LOGIN_CAPTCHA_IMAGE, "EMC 图形验证码", timeout=10)
            image_path = self.screenshot.element_shot(captcha_element, self.job_no, "emc_login", error=False)
            captcha = str(get_verify_code(image_path, typeid=self.captcha_type_id) or "").strip()
            if len(captcha) == 4:
                return captcha
            self.dom.click(selectors.LOGIN_CAPTCHA_IMAGE, "刷新 EMC 图形验证码", timeout=3)
        raise LoginError("EMC 图形验证码识别失败")

    def _complete_email_otp_if_required(self: "EmcBase") -> None:
        role = str(self.context.customer_role or "").upper()
        has_otp_page = bool(self.page.eles(selectors.otp_input(1), timeout=1))
        if not has_otp_page:
            return
        if role not in self.email_otp_roles:
            raise LoginError(f"EMC 账号要求邮件 OTP，但客户角色 {role or '空'} 未配置")

        code = read_latest_otp(
            os.getenv("EMC_OTP_IMAP_HOST", "").strip(),
            str(self.website_info.get("emailAccount") or ""),
            str(self.website_info.get("emailPassword") or ""),
            subject_marker="Verification code",
        )
        if len(code) != 6:
            raise LoginError("EMC 邮件 OTP 格式错误")
        for index, value in enumerate(code, start=1):
            self.dom.input_text(selectors.otp_input(index), value, f"EMC 邮件 OTP 第 {index} 位", timeout=3)
        self.dom.click(selectors.OTP_CONTINUE, "EMC 邮件 OTP 继续按钮", timeout=5)

    def _wait_for_login_success(self: "EmcBase") -> bool:
        for _ in range(20):
            if self._is_logged_in():
                return True
            time.sleep(1)
        return False

"""HPL 登录流程。"""

import time
from typing import TYPE_CHECKING

from app.core.task.errors import LoginError
from app.spider.HPL import selectors

if TYPE_CHECKING:
    from app.spider.HPL.base import HplBase


class LoginMixin:
    """HPL 会话复用、账号登录和安全验证处理。

    依赖调用方提供 ``page``、``dom``、``logger``、``website_info``、
    ``cookies_redis_key``、``si_url`` 及任务基类的 Cookie 和登录锁方法。
    """

    def login(self: "HplBase") -> None:
        """优先复用本地和 Redis 会话，失效时由单个任务提交账号密码。"""
        self._open_si_page()
        if self._is_logged_in():
            self.save_cookies(self.cookies_redis_key)
            self.logger.info("HPL 已登录")
            return

        self.set_page_cookies(self.cookies_redis_key)
        self._open_si_page()
        if self._is_logged_in():
            self.logger.info("HPL 已复用 Redis Cookie")
            return

        while not self.claim_credential_login():
            self.set_page_cookies(self.cookies_redis_key)
            self._open_si_page()
            if self._is_logged_in():
                self.logger.info("HPL 已复用其他任务刷新后的 Cookie")
                return

        self._submit_credentials()
        self._wait_for_login_success()
        self.save_cookies(self.cookies_redis_key)

    def _open_si_page(self: "HplBase") -> None:
        """打开 SI 首页，处理 Cloudflare，并尽力关闭 Cookie 提示。"""
        self.page.get(self.si_url, show_errmsg=True)
        self.page.wait.doc_loaded()
        time.sleep(2)
        self._handle_cloudflare_challenge()
        self.dom.click_if_clickable(selectors.COOKIE_ACCEPT_BUTTON, "Cookie 同意按钮", timeout=1)

    def _is_logged_in(self: "HplBase") -> bool:
        """通过登录表单是否存在判断当前 HPL 会话状态。"""
        return not bool(self.page.eles(selectors.LOGIN_FORM, timeout=2))

    def _submit_credentials(self: "HplBase") -> None:
        """向 HPL 登录页填写账号密码并提交。"""
        account = self.website_info.get("websiteAccount")
        password = self.website_info.get("websitePassword")
        if not account or not password:
            raise LoginError("HPL 登录缺少网站账号或密码")
        self.dom.input_text(selectors.LOGIN_USERNAME, str(account), "HPL 登录账号", timeout=5)
        self.dom.input_text(selectors.LOGIN_PASSWORD, str(password), "HPL 登录密码", timeout=5)
        self.dom.click(selectors.LOGIN_SUBMIT, "HPL 登录按钮", timeout=5)

    def _wait_for_login_success(self: "HplBase") -> None:
        """等待登录完成，验证码或页面异常会转换为标准登录失败。"""
        self.page.wait.doc_loaded()
        for _ in range(12):
            self._click_shadow_consent()
            self.dom.click_if_clickable(selectors.COOKIE_ACCEPT_BUTTON, "Cookie 同意按钮", timeout=1)
            if self._is_logged_in():
                return
            time.sleep(1)
        raise LoginError("HPL 登录失败或需要人工完成验证码")

    def _handle_cloudflare_challenge(self: "HplBase") -> None:
        """出现 Cloudflare 时点击校验；若仍停在验证页则抛出登录失败。"""
        if not self._is_cloudflare_challenge_present():
            return

        self._click_shadow_consent()
        for _ in range(10):
            if self._is_cloudflare_click_completed():
                return
            time.sleep(0.5)
        raise LoginError("HPL Cloudflare验证失败")

    def _is_cloudflare_challenge_present(self: "HplBase") -> bool:
        """判断当前是否出现 Cloudflare 验证页。"""
        title = (self.page.title or "").strip()
        if "请稍候" in title:
            return True
        if self.page.ele("css:input[name='cf-turnstile-response']", timeout=0.5):
            return True
        main_content = self.page.ele("css:.main-content", timeout=0.5)
        if not main_content:
            return False
        text = (main_content.text or "").strip()
        return "确认您是真人" in text or "请验证您是真人" in text or "验证成功" in text

    def _is_cloudflare_click_completed(self: "HplBase") -> bool:
        """判断 Cloudflare 点击是否已完成。"""
        title = (self.page.title or "").strip()
        main_content = self.page.ele("css:.main-content", timeout=0.5)
        text = ((main_content.text if main_content else "") or "").strip()

        # 已显示验证成功，或页面已离开 Cloudflare 中间页。
        if "验证成功" in text:
            return True
        if "请稍候" not in title and not self.page.ele(
            "css:input[name='cf-turnstile-response']",
            timeout=0.5,
        ):
            return True
        return False

    def _click_shadow_consent(self: "HplBase") -> None:
        """尽力点击 HPL Cloudflare Turnstile 嵌套 Shadow DOM 中的真人校验复选框。"""
        try:
            # Turnstile 会异步挂载 shadow/iframe，短重试避免 host.sr 尚未就绪。
            for _ in range(5):
                host = self._find_turnstile_host()
                if not host:
                    time.sleep(0.4)
                    continue

                host_sr = getattr(host, "sr", None)
                if host_sr is None:
                    time.sleep(0.4)
                    continue

                frame = host_sr.get_frame(1)
                if not frame:
                    time.sleep(0.4)
                    continue

                body = frame.ele("xpath://body", timeout=2)
                body_sr = getattr(body, "sr", None) if body else None
                if body_sr is None:
                    time.sleep(0.4)
                    continue

                checkbox = body_sr.ele(
                    'xpath://input[@type="checkbox" and contains(@aria-label, "真人")]',
                    timeout=2,
                )
                if not checkbox:
                    checkbox = body_sr.ele('xpath://input[@type="checkbox"]', timeout=1)
                if checkbox:
                    checkbox.click()
                    return
                time.sleep(0.4)
        except Exception:
            return

    def _find_turnstile_host(self: "HplBase"):
        """定位承载 Turnstile shadow iframe 的宿主节点。"""
        token = self.page.ele("css:input[name='cf-turnstile-response']", timeout=1)
        if token:
            parent = token.parent()
            if parent is not None:
                return parent

        main_content = self.page.ele("css:.main-content", timeout=1)
        if not main_content:
            return None
        return main_content.ele("xpath:./div/div/div", timeout=1)

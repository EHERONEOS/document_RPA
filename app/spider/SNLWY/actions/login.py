"""SNLWY 会话复用与浏览器登录。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.core.task.errors import LoginError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.base import SnlwyBase


class LoginMixin:
    """优先复用 sessionStorage，会话失效时通过官网表单登录。"""

    login_wait_seconds = 30
    session_expire_hours = 12
    # 会话失效时首页会先渲染，等接口 401 后才跳登录页。这段时间不能判成已登录。
    login_redirect_grace_seconds = 8
    login_state_poll_seconds = 0.3


    def login(self: "SnlwyBase") -> None:
        """优先复用会话，必要时只由一个任务提交账号凭据。"""
        self._open_home_page()
        if self._wait_until_login_settled():
            self.save_session_storage(self.session_redis_key, expire_hours=self.session_expire_hours)
            self.logger.info("SNLWY 已登录")
            return


        self.set_page_session_storage(self.session_redis_key)
        self._open_home_page(refresh=True)
        if self._wait_until_login_settled():
            self.save_session_storage(self.session_redis_key, expire_hours=self.session_expire_hours)
            self.logger.info("获取redis sessionStorage 登录成功")
            return

        while not self.claim_credential_login():
            self.set_page_session_storage(self.session_redis_key)
            self._open_home_page(refresh=True)
            if self._wait_until_login_settled():
                self.logger.info("SNLWY 已复用其他任务刷新后的 sessionStorage")
                return
        
        self._auto_login()
        self.save_session_storage(self.session_redis_key, expire_hours=self.session_expire_hours)


    def _open_home_page(self: "SnlwyBase", *, refresh: bool = False) -> None:
        """统一从首页加载并校验登录态，doc_loaded 不代表 Vue 接口已完成。"""
        self.page.get(selectors.INDEX_URL, show_errmsg=True)
        if refresh:
            # hash 跳转不会重新初始化 Vue，恢复缓存后需刷新以读取新的会话。
            self.page.refresh()
        self.page.wait.doc_loaded()


    def _auto_login(self: "SnlwyBase") -> None:
        """通过官网账号密码表单登录，失败时立即终止任务。"""
        if not self._is_login_url(self._page_url()):
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
            # 当前没有其他登录回退路径，失败必须上抛，不能继续填写业务页面。
            raise LoginError(f"SNLWY 浏览器登录失败：{exc}") from exc


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
        parsed = urlparse(str(url or "").strip())
        text = (parsed.fragment or parsed.path).split("?", 1)[0].rstrip("/")
        return text if text.startswith("/") else ""


    def _is_login_url(self: "SnlwyBase", url: str) -> bool:
        return self._hash_path(url).endswith("/login")


    def _is_home_url(self: "SnlwyBase", url: str) -> bool:
        return self._hash_path(url).endswith("/quick-search")


    def _has_login_button(self: "SnlwyBase") -> bool:
        return bool(self.dom._find(
            selectors.LOGIN_TAG_DOM, name="登录标识", timeout=0.2, required=False
        ))


    def _home_shell_ready(self: "SnlwyBase") -> bool:
        if not self.dom._find(
            "c:.locale-box", "等待语言选择器加载", timeout=0.5, required=False
        ):
            return False
        # 页头可能先于接口数据渲染；可见骨架屏或 loading 遮罩存在时继续等待。
        try:
            return self.page.run_js("""
                return !Array.from(document.querySelectorAll(
                    '.el-skeleton, .el-loading-mask'
                )).some(el => el.getClientRects().length > 0 &&
                    getComputedStyle(el).visibility !== 'hidden');
            """) is True
        except Exception:
            # 路由切换时 JS 上下文可能暂不可用，本轮不能判定成功。
            return False


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

            if (
                self._is_home_url(url)
                and token_state is not False
                and self._home_shell_ready()
            ):
                now = time.monotonic()
                if ready_since is None:
                    ready_since = now
                elif now - ready_since >= self.login_redirect_grace_seconds:
                    if (
                        not self._is_home_url(self._page_url())
                        or self._has_login_button()
                        or self._access_token_state() is False
                        or not self._home_shell_ready()
                    ):
                        ready_since = None
                        time.sleep(self.login_state_poll_seconds)
                        continue
                    return True
            else:
                ready_since = None
            time.sleep(self.login_state_poll_seconds)
        return False


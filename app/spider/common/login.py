import time

from app.core.integrations.captcha import get_ym_hcaptcha_code
from app.core.task.errors import BusinessError, LoginError
from app.spider.ZIM import selectors


class LoginMixin:
    """船司登录公共逻辑。

    依赖调用方（CarrierBase）提供的实例成员：
    - self.page / self.dom
    - self.logger
    - self.website_info
    - self.cookies_redis_key
    - self.login_url / self.index_url / self.siteKey
    - self.is_login() / self.claim_credential_login()
    - self.set_page_cookies() / self.save_cookies()
    """

    def login(self):
        """执行 ZIM 登录。"""
        self.page.get(self.index_url, show_errmsg=True)
        # self.sys_exception_refresh()
        time.sleep(2)
        if self.is_login():
            self.logger.info("已登录")
            return

        self.set_page_cookies(self.cookies_redis_key)
        self.page.get(self.index_url, show_errmsg=True)
        time.sleep(2)
        if self.is_login():
            self.logger.info("已登录")
            return

        while not self.claim_credential_login():
            # 当前浏览器首次读取 Redis 后，可能已有其他任务刷新了该账号的登录状态。
            # 决定是否再次提交登录信息前，先重新加载最新的 Cookie。
            self.set_page_cookies(self.cookies_redis_key)
            self.page.get(self.index_url, show_errmsg=True)
            time.sleep(2)
            if self.is_login():
                self.logger.info("已复用其他任务刷新后的登录信息")
                return
        self.logger.info("登录信息失效,开始登录")
        self.logger.info("开始获取验证码")

        recapture_token = get_ym_hcaptcha_code(self.siteKey, self.login_url)
        self.page.change_mode(mode="s", copy_cookies=True)
        payload = {
            "UserName": self.website_info.get("websiteAccount"),
            "Password": self.website_info.get("websitePassword"),
            "OfficeCode": "",
            "recaptureToken": recapture_token,
        }
        res = self.page.post(
            self.login_url,
            data=payload,
            allow_redirects=False,
            verify=False,
            timeout=30,
        )
        if not res or res.status_code != 200 or res.text != "success":
            raise LoginError("Session登录提交失败")
        self.page.change_mode(mode="d", copy_cookies=True)
        self.page.get(self.index_url, show_errmsg=True)
        time.sleep(3)
        if not self.is_login():
            raise LoginError("登录失败")

    def sys_exception_refresh(self):
        """系统异常刷新页面"""
        for _ in range(3):
            sys_exception_p = self.dom._find(*selectors.SYS_EXCEPTION_P, required=False)
            if not sys_exception_p:
                return
            self.logger.error("系统异常刷新页面")
            self.page.refresh(ignore_cache=True)
            time.sleep(4)
        raise BusinessError("系统异常，刷新3次后仍未恢复")

    def is_login(self):
        """判断是否登录"""
        if self.login_url not in self.page.url:
            self.save_cookies(self.cookies_redis_key)
            return True
        return False

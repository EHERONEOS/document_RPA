import os
import time
from urllib.parse import urlsplit

from app.core.integrations.captcha import get_ym_hcaptcha_code
from app.core.task.base_task import BaseRpaTask
from app.core.task.errors import BrowserStartError, BusinessError, LoginError
from app.spider.ZIM.common import selectors
from app.core.page.dom import DomHelper


LOGIN_URL = "https://cis.zim-logistics.com.cn/Account/Login"
# recapture_token= "P1_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.haJwZACjZXhwzmpfMiancGFzc2tlecUFwC6kkhQQBKuOce8krO7O4ZbPWkfLHcESC2PxgIqarBE6bm54oA7O7YYo6HxspxIS1ivMQwWHq32Df8R_JKu_mXp7pvWLnN9L76VOjXusuK33_JMTk6hhvq4XPItv4wROVj5wMYGKsHEgRX1dD1a_2xV-fYgDf0eA8HDNLk-Fg-45oi90YKS7CtsO6HqmEm6OhVV75SV0vG3_ul1PF-zyHUa8rf6XySbq5Sqv0Tsa-v5jmmulY60OdXxzU2KG5NmSQTjzM100_WJz6QFyxN3z3QM5rBxOgZJiHkdl-jNa99JH21NXJ_WRqjZWT9K_I4--Cf0cyzgXLbQLF3vLnfLfOV88nUGhW8mHIfx4zlMlIVshRVCbbnySEMb4_Qgtoa-g5cbBQtXzSIVCV4_3u08Y6-2AqIcKz--ioNwnVfUqwf3AdchNQN8IGNxSc3pkEhAH81VMGMy8qjEqJ1hqB-RXDPznD2mkJU08MlxXcfN3KD44w5KsDoLFDHj1UzTsTzj5LeGsQh1bRIaTU1nJhEWhXXgGZz88oMiFbDDwTwg6kKEh7ADZ0IpLmzJyEtKZ5PGwm0voEOy0r2wGK42HCdE3Cz_qQb7cD5wgDVEYKYWF_yhQ14H8kprqfV8VqDizUswWedxvlKnpTaE1E4MOVqbEo1mxPhICKSofJ_cdBtuwn-BLIPOq5A8VvonFo0_l5fLSm50KwnUQrHXSGT09dKBfdJ6qRcB-OfJWQhsKn6jjC3MWz-JEWtwkN9JtPyf4NdNAQe1XLVQkRQj8qtgLTtttfU3NlEJNFRefb-5v2DQ-StyuDX7EtkWrPsy4md1is_JsnWIfpvC6Qf4sEo0HdiRzZJvcP_BBL69Lr5oXBTc3qAR8P9zpbzC-KtLv_5THrc6RAYbqNRv2N6hKeYWfbU2q-U0N5GMB7n4O8A7RRgHZdlS9Jq6rsSyeCDOXX8GGGWbfFWryRaVIk3orOfGxK4Re5tPMAij6SG2JDbXwFDa3yXOjSiYAnQQ6IUo2ZtZ3I06xdMRCfBJSlr0zN29As6qQ4gvlIGB6Bx4ZMiqTMc5J6jQlr7YIYmwBBRIN6zRpdY3aDAuwF6zp_qPk-_LJleHLj5KUc8cL75xZzlJYDXyzNfqLp-YKnmaIDKFxAeGY20-K1T_uUCgRtyvm80IeDBngmC1pSlE2nQW1-YOY--rf5FsimWj7aojKUF_dPqTKSUz7X72z20htxpUnDi6jI0zB0JtfkIwRG9DIzMnGchacSZlsFlZNHGDsJ74PYwIPRU1MCixt4Qo5RMKUwoRBdaTjrblGCqZRzTsbydWtpJG6qAoe_rqyqI92la0sUyzYQAtBcGOH5zxR4g8cFd3wNbNyoK-F9M-0cFAWSsNfVy6YMYzbKzXJmBvymCpqdv5jUgPHhCnxurL-5lqRKRGuGA-F7nSp9q_bygIT2XukNje1U3E8d9kTljxiVAzELEUBqzbpGmtXgWov8s9yOeMVe8nzuIgzEzi_yYFiU6Iy-Q0uZT2JHZVOwfQCIZmc1sQCuA9OoJFp3QDx21SMxIIkLVW9vWb21SEupFZY35J1YzlBHSnaHTeXDQ5cu4bK-rI2_Sn7pjjN3JQb1JEY6YCVm9HlH_btl0B3g8E2IrdpdLQbGlbiei_9BVhtwBnlkHTXd0Hzk6aC0Tjks4-ghhv8769jql85khlcVbPCx4J3_vTB8jg34d61LOujLgF8cVE1a5cBNtksPNOTW8modUU7BN7WsiawlN9l0RZiJ49pqd4EtL-5-sxUYA5xRi6d5AExy2m--QZUvTClkUB5p59U58a5o92Ji0VwxU0oIzVn1RVAszvVr2cFqPh8iZanYmO3axXech8xq9n7MdyoQ19md_LON4owk3qkVX25lGZkt4nzqUpmTKGuVtGTj_r-5hJlfp5_ffkjPkaIyyTMu7PUtUk5JW7I3iPlZrrWVylhJgqBnb-momtyqDIzYzI0Y2M3qHNoYXJkX2lkzg07ZCk.HA7UyK9q75AM1cut6z5RgXQ-q1l_jvZgv2XAs07RFn4"
class ZimBaseTask(BaseRpaTask):
    """ZIM 船司公共能力。"""
    carrier_code = "ZIM"
    login_url = LOGIN_URL
    index_url = "https://cis.zim-logistics.com.cn/"
    siteKey = "87004f4a-40ba-4b16-ad22-a8d034b6c6b8"  # 站点可以用于验证码解析使用

    def _ensure_browser_ready(self):
        """ZIM 登录依赖真实浏览器页面和 Session 能力。"""
        required_methods = ("get", "post", "change_mode", "run_js")
        missing_methods = [method for method in required_methods if not hasattr(self.page, method)]
        if missing_methods:
            raise BrowserStartError(
                f"ZIM 登录依赖真实浏览器页面，当前 page={self.page.__class__.__name__}，"
                f"缺少方法: {', '.join(missing_methods)}。请先开启 ENABLE_BROWSER=true"
            )

    def _get_login_headers(self):
        origin = f"{urlsplit(self.login_url).scheme}://{urlsplit(self.login_url).netloc}"
        browser_headers = self.page.run_js(
            """
            return {
                userAgent: navigator.userAgent,
                language: navigator.language,
                platform: navigator.userAgentData && navigator.userAgentData.platform,
                brands: navigator.userAgentData && navigator.userAgentData.brands,
                mobile: navigator.userAgentData && navigator.userAgentData.mobile,
            };
            """
        ) or {}
        headers = {
            "User-Agent": browser_headers.get("userAgent"),
            "Accept": "text/plain, */*; q=0.01",
            "Accept-Language": browser_headers.get("language"),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": origin,
            "Referer": self.login_url,
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        if browser_headers.get("platform"):
            headers["sec-ch-ua-platform"] = f'"{browser_headers["platform"]}"'
        if browser_headers.get("brands"):
            headers["sec-ch-ua"] = ", ".join(
                f'"{brand["brand"]}";v="{brand["version"]}"'
                for brand in browser_headers["brands"]
            )
        if browser_headers.get("mobile") is not None:
            headers["sec-ch-ua-mobile"] = "?1" if browser_headers["mobile"] else "?0"
        return {key: value for key, value in headers.items() if value}

    def login(self):
        """执行 ZIM 登录。"""
        self._ensure_browser_ready()
        website_info = self.context.website_info
        self.logger.info("执行 ZIM 登录入口")
        self.page.get(self.index_url ,show_errmsg=True)
        raise LoginError("登录失败")
        self.sys_exception_refresh()
        time.sleep(3)
        if self.is_login():
            self.logger.info("已登录")
            return
        self.logger.info("登录信息失效,开始登录")
        self.logger.info("开始获取验证码")
        recapture_token = get_ym_hcaptcha_code(self.siteKey,self.login_url)
        self.logger.info(f"验证码获取成功")
        login_headers = self._get_login_headers()
        self.page.change_mode(mode="s",copy_cookies=True)
        payload = {
            # "UserName": website_info.get("websiteAccount"),
            # "Password": website_info.get("websitePassword"),
            "UserName": "qiantang",
            "Password": "Qt*123456",
            "OfficeCode": "",
            "recaptureToken": recapture_token,
        }
        res = self.page.post(
            self.login_url,
            headers=login_headers,
            data=payload,
            allow_redirects=False,
            verify=False,
            timeout=30
        )
        if not res or res.status_code != 200 or res.text != "success":
            raise LoginError("Session登录提交失败")
        self.page.change_mode(mode="d",copy_cookies=True)
        self.page.get(self.index_url,show_errmsg=True)
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
            self.page.refresh()
            time.sleep(4)
        raise BusinessError("系统异常，刷新3次后仍未恢复")

    def is_login(self):
        """判断是否登录"""
        return self.login_url not in self.page.url

    def query_booking(self,blNo:str):
        """查询订舱单据"""
        # 点击订舱导航菜单并等待订舱列表接口完成
        self.http.wait_api_finished(
            selectors.BOOKING_GET_LIST_API,
            trigger=lambda: self.dom.click(*selectors.DC_MENU)
        )
        iframe_dom: DomHelper = self.dom.in_frame(*selectors.DC_LIST_FRAME)
        iframe_dom.input_text(
            selectors.SEARCH_BOOK_NO[0],
            blNo,
            name=selectors.SEARCH_BOOK_NO[1],
        )
        # 点击搜索按钮并等待订舱列表接口完成
        res = self.http.wait_api_finished(
            selectors.BOOKING_GET_LIST_API,
            trigger=lambda: iframe_dom.click(*selectors.SEARCH_BTN)
        )
        if not res or res.get("total") !=1:
            raise BusinessError("查询订舱单据失败")
        bo_row = res.get("datas",{})[0]
        if not bo_row or bo_row.get("gdNo") != blNo:
            raise BusinessError("订舱列表接口返回数据异常")
        return bo_row

import os
import time
from urllib.parse import urlsplit

from app.core.task.base_task import BaseRpaTask
from app.core.task.errors import BrowserStartError, BusinessError, LoginError
from app.spider.ZIM.common import selectors
from app.core.page.dom import DomHelper


LOGIN_URL = "https://cis.zim-logistics.com.cn/Account/Login"
recapture_token="P1_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.haJwZACjZXhwzmpZ0LuncGFzc2tlecUFa51ocVMfgrB_aYev5u2XSnHNzShNAGgmL0Ay_L9pm0c9XPTL_TRTCHvv1H44oSZPWVXg771PpmvlJwLJh7YGVSf62M33gi9uetx8fgWRb_SUXlIgkNrPhi10-pCuctyfvrAL8tboSk3L1I7JIs78yMsqiP1JrtcW_EWEvmVwHtZaxNhb5ac96Z0i1k6bRgsAZCg2s7KVNfH_XgYwDLX7Po0qcMibC5hoO8dk37eqBXo9a7zdKiorikt5gDNva-6rcRTt3-bwRfOwLcrFQVrOGzGE3pkB7bfB0jXwFBJk3xI5kPXhGiAzU-UCoOEHjleEavrP812ta3HkFzd5O2qhyraVCOvZ4r3dZQYpzhj-NtTrm_ylq7DSPGt5hU-l1Os55oWrlWrOwil0deO7fvU9VFRVC7-CXYbvdoerilmTGJQ6aZPoOEohow1PlBWpAUYET86UlRpUHtwfkYhPdf3HtPLjPAZB4dpgBm2lTSIdouczGFK48aOtjGpTohScVe1AGeiVNDDEg2q94ODGfhbEeI7o_TIU1Syga6KarG2lyyNyJeFhzyx5eE9CrF_nITd_F4I-oc8rlQCXr_vpUjVgBMLBJNdDN2devI7Q3Ge20y9_q_btm8Co2wnwAbcDbOUVmGJSKvY46QPV7KbLK7BfhViim1vIe5xgRUTRnncXqiz9tQ0MPOBSgJa5laKdVO_fH4MoGOuNsmRk-cL4pzTg6qUrV1SjrABk4Cu2hxSq_eR4YEd4yyoBoJSAetuI57NIBNdJEZooDTjuAqIU10gJWOPOWZR9Tzsv8ZWvSRYzOEbPUXwxd6xRk_ZnIl8ZXI7yWJXYE4J2Lg79LFu0BQ2Y9-6FGeSCxwQ8od8xRvarNseG8Cb6c6MjPmJ_xjn9HRlUkWw_pbWRRwsBikouv-GoynyivxW3PcwfNaaPNic1V6FSjUnhRUJdOLg7_VwaXMgwja8-WpF2qpowLfNfxXwUAiz8wweGzp4IoA7IMqx_27jJ1pKn43ZL64efj8muUQk8aqoLVMxLWIAkrg8u_8DGe8BUDpwTU4vfrsvzpUVkpyiVTSrIlP9ukiyJjgiuZXS2fdH9H_HwgfNg7ZNNWwl4Gp2zJQigs6Aw1PtNb5bzUsgXoWRGaLaNj7e9MXslPzvbBOcqi_hfglKMJsSpIDQDUZch5vVZIe4fpO8YCW-2ljdLPQWwRtborm_kiair1Nm8IvuPTC399ZzyihQFNB4S5wQEdJEnpTczSwc1iEkffUIyEZfa4dnKBPMgsc_F_ZQXGmEanRIkbTLbMuX2EvKxjnEjn9kz_cGqCdTy-lYWHokI5W8ltQBGd_SPV60BL46h-3zLOZwIeddGdS-c7m7IFY9DXq2SAyUuf8k1btFdQ4_5OUFHl6ukaDhQY9fIeJtHZXFKHfJDnQ9cj2xOQDGq004wtfP3gvnQPDx0akuaJzLOOGnvWB6hIm9XLlhMX5brOnMzhnvX0NoQTJ3-3xo6gfwX4b7JEn5x-jSqPVz6FfXTUiW1fB49MdhndjreqQhZQGYqWu0BmsFmDzPeNuprSp9CRDTav12kpbywOa_qCVeU0Fh4ova9GSUtLsZJXPNV7TUnpOvAGEbGlGeTJufdVXTfIY_4N036Ty8ZW6qwxIGF4pXBLWwE41P0jb3xjzyltoSRXi9MxYMtwuKVp7FQFkKEezQCvjQNfJ3DA1keFDsB4Re4Klek6GlrelrZFxdL2J03W0BPx81lD438ryh_9yLBOhV_lIxbDHnsepAF3_ipWLHY_96BC5go_Iqq3bYrdJQvM1hGFNE_ItFufit3GbDrvI8Tz7aHET20JiOhTm3xSUsC7sE7IzHv4--ia3KoMjk4YWU3YTaoc2hhcmRfaWTODTtkKQ.X595ZT4JfgrqlwlVBNi5Rdj6tc8Yd-eIid1VWaITh3U"
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
        self.page.get(self.index_url)
        time.sleep(3)
        if self.is_login():
            self.logger.info("已登录")
            return
        self.logger.info("登录信息失效,开始登录")
        login_headers = self._get_login_headers()
        self.page.change_mode(mode="s",copy_cookies=True)
        payload = {
            "UserName": website_info.get("websiteAccount"),
            "Password": website_info.get("websitePassword"),
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
        self.page.get(self.index_url)
        time.sleep(3)
        if not self.is_login():
            raise LoginError("登录失败")




    def is_login(self):
        """判断是否登录"""
        return self.login_url not in self.page.url

    def query_booking(self,booking_no):
        """查询订舱单据"""
        # 点击订舱导航菜单并等待订舱列表接口完成
        self.http.wait_api_finished(
            selectors.BOOKING_GET_LIST_API,
            trigger=lambda: self.dom.click(selectors.DC_MENU)
        )
        iframe_dom: DomHelper = self.dom.in_frame(selectors.DC_LIST_FRAME) 
        iframe_dom.input_text(selectors.SEARCH_BOOK_NO, booking_no)
        # 点击搜索按钮并等待订舱列表接口完成
        res = self.http.wait_api_finished(
            selectors.BOOKING_GET_LIST_API,
            trigger=lambda: iframe_dom.click(selectors.SEARCH_BTN)
        )
        if not res or res.get("total") !=1:
            raise BusinessError("查询订舱单据失败")
        bo_row = res.get("datas",{})[0]
        if not bo_row or bo_row.get("gdNo") != booking_no:
            raise BusinessError("订舱列表接口返回数据异常")
        return bo_row

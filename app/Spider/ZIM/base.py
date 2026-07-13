import time

from app.core.task.base_task import BaseRpaTask
from app.core.task.errors import BrowserStartError, BusinessError, LoginError
from app.Spider.ZIM import selectors
from app.core.page.dom import DomHelper


LOGIN_URL = "https://cis.zim-logistics.com.cn/Account/Login"
HEADERS_GET = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": LOGIN_URL,
}
HEADERS_POST = {
    "User-Agent": HEADERS_GET["User-Agent"],
    "Accept": "text/plain, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://cis.zim-logistics.com.cn",
    "Referer": LOGIN_URL,
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua-platform": "\"macOS\"",
    "sec-ch-ua": "\"Chromium\";v=\"148\", \"Google Chrome\";v=\"148\", \"Not/A)Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}
recapture_token = "P1_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.haJwZACjZXhwzmpUVAKncGFzc2tlecUFloADoVFDK9hUA-61YbbjPW3QkiupJFwxpb3IgQadiuKwP_zZI6-7ee_I1rkznLJlkHlyUCUDyRHQNR73YLo9sqR_U2EQrjffxDSA2qFu8XLu2eBL6gxu3Bh_yaNpRy9Xt9hzTRkQ2WIlcj58j8srfmIGfTPWRxE4SkqVn7DgLz5aJ10cyUsZviZbgemiGUeBIoi2bG9VT86EWKt3stGhVHkWQLRUvNch6zsbxU6Arh2ttiwhw5bRS6hxJal_TJJI5kF5eCMSd47-WIjKbKqiPZuhiC-wzz1iVwFVCuGYDKvMUqjeNW94Mqx9tlSWY6HfqdbGUwofp7atdfey7Fe6vG-_LIh1LQcaM_2O2fF4WrN-mV0iTY0c2yS7ApHAODxPGbaeg3ly7xXF-TW2rnjcRga4BJb4hkxh30zF9oSa0amCexSYIsrm7AJ_xFXZG6Tengiuy6VpVjbYuajHaoPIJjMvDWfTS5Ac8GILd_8Zg7Hmw9VHG2y51xd-VmbXrG7tqUBKVLNWEh_mAoqjLOBT9bqSgXqKjEwQ6jgRR1OLGkWgm25vVYI_FYiaRrMcPGxqP7pAfqvJ6DFEWw69pjkCx1xftRaC4OSchZiaxR2FHhdgqsPrqCP8tB0v5Bqa7J_x_FQKhf0PqST2uZaJwdcEbu0HNmsX4-R5ouEJG-b4MTqb2q8J544BRmTOlK0IZ2CwsVx3a0m9bUjsVyNH2qvlkrN8NX2NF-t85quAIhaW9F5GCtS1ErTxH4-0tKI4MVHHPWiziom2-4s1YJBELJepgbbPhs3BA7CqE9NgqTbxbzEr-wBs07_6DMzZkqUeXmdzhZx5wvQC8aX2y0fhRKZiRhhe6-ILic-I13mVhWjGuFEzeFF9_urWFmASxAHyRTK6zUvWG1Ie35ZrLM_IrN-P71Q-7RDJ4icjM9ltyxeNhzoNu5TA_pglISCVZNJL2nPjjn63dsevUQCSh9klcLRfi_bMmz2zy_uVY3uZOEvVR0qwUoY0gF7zE6Oi_1hHGdhqEmcixSBQLw7OivTRQSNVMbsDooP1nfzguOsg7yq8ZDMeUpJc10h4A3fMG2XvcEcKXgR-eRTRnaya3-bHaShd5OYky6VfDcOb16cMNBptCEOcSIScLS7MIoAY-KL1g61k9jV4z536-oj8cQ6F8QlaakxdSEMAK_nkKSXDdbXzeouPxXcA4iPVpfV_I8-fI5T-4QofINii3llh_m5QFkuDvVbFGnHTAKuAHp1pNaJjY1lQ55QF6YpIa9KT9KAaVtoW5N0M1aXbDwwrspDa_xK34cDgMABinhRtGdtN1XNj4W2XLWAe__ADUqRtLl4HsDvyASE0C5e6GJnvOFDw5c-_h-yk1vtcq53ObabxoZqIRNMvTnmgAyZhVnSNStqLYL9YHASj2gaNmpm5AV_DVKwnXUhNkCyytyyLQAF__eupz_NWWzVmlZ73K-UFHG3OtTX77sC1_Wd6PyVVEgpmbi1FVE-I5ediF8zncMMEtXsghBInglYjs5iBl1Z0kuYEqCSlnHLEGO62T8r5MYiKghhhib_I39RLTwTFKFNzSevZaU9li8WvKVO8OCazRlR0rGu4gIxWuX9IIlFJYlvIZC26f5J1NTnzOEb63FfvKFWGNQwW8NQ1831z1cid9qhOwCyeU160a0-rNDa_10jQFkGShm2V2bTkF_dK1afGOvjYKI9hv8YRW_VdiZtDQQKu2UAvXS3lQcQeW5-wjFHTZbKsFgLRILWIwx7HDyoFnn_Htq9f2FpUOkH0lP0c5ufsg4lcB92xishbLqxsP762tveT0J_3nOwVNZzmMV3uvpp2acFCmaDJbmOAsLzeDq9rhq6Vt0M5NAjZeXUnUc92rCJwbn4xaiPvXGkLqsbfp-y1kDYJziobgwAUomtyqDMwYzIyYjNiqHNoYXJkX2lkzg07ZCk.1u_k7FOKdDq3YuV6OeH23pnx-Le8_OKSX5Vvy-mnra4"

class ZimBaseTask(BaseRpaTask):
    """ZIM 船司公共能力。"""
    carrier_code = "ZIM"
    login_url = LOGIN_URL
    index_url = "https://cis.zim-logistics.com.cn/"
    siteKey = "87004f4a-40ba-4b16-ad22-a8d034b6c6b8"  # 站点可以用于验证码解析使用

    def _ensure_browser_ready(self):
        """ZIM 登录依赖真实浏览器页面和 Session 能力。"""
        required_methods = ("get", "post", "change_mode")
        missing_methods = [method for method in required_methods if not hasattr(self.page, method)]
        if missing_methods:
            raise BrowserStartError(
                f"ZIM 登录依赖真实浏览器页面，当前 page={self.page.__class__.__name__}，"
                f"缺少方法: {', '.join(missing_methods)}。请先开启 ENABLE_BROWSER=true"
            )

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
        self.page.change_mode(mode="s",copy_cookies=True)
        payload = {
            "UserName": website_info.get("websiteAccount"),
            "Password": website_info.get("websitePassword"),
            "OfficeCode": "",
            "recaptureToken": recapture_token,
        }
        res = self.page.post(
            self.login_url, 
            headers=HEADERS_POST, 
            data=payload,
            allow_redirects=False,
            verify=False,
            timeout=30
        )
        if not res or res.status_code != 200 or res.text != "success":
            raise LoginError("Session 模式登录提交失败")
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

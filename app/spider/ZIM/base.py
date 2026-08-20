import os
import time
from urllib.parse import urlsplit

from app.core.integrations.captcha import get_ym_hcaptcha_code
from app.core.task.base_task import BaseRpaTask
from app.core.task.context import TaskContext
from app.core.task.errors import BrowserStartError, BusinessError, LoginError
from app.spider.ZIM import selectors
from app.core.page.dom import DomHelper
from app.utils.util_format import format_post_data



class CarrierBase(BaseRpaTask):
    """船司基础类。"""
    carrier_code = "ZIM" # 船司编码
    login_url = "https://cis.zim-logistics.com.cn/Account/Login" # 登录地址
    index_url = "https://cis.zim-logistics.com.cn/" # 首页地址
    siteKey = "87004f4a-40ba-4b16-ad22-a8d034b6c6b8"  # 站点可以用于验证码解析使用

    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.cookies_redis_key = f"cookies:{self.carrier_code}_{self.website_info.get('websiteAccount')}"
        pass
        

    def login(self):
        """执行 ZIM 登录。"""
        self.page.get(self.index_url ,show_errmsg=True) 
        # self.sys_exception_refresh()
        time.sleep(2)
        if self.is_login():
            self.logger.info("已登录")
            return
            
        self.set_page_cookies(self.cookies_redis_key)
        self.page.get(self.index_url ,show_errmsg=True)
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


        recapture_token = get_ym_hcaptcha_code(self.siteKey,self.login_url)
        self.page.change_mode(mode="s",copy_cookies=True)
        payload = {
            "UserName": self.website_info.get("websiteAccount"),
            "Password": self.website_info.get("websitePassword"),
            # "UserName": "qiantang",
            # "Password": "Qt*123456",
            "OfficeCode": "",
            "recaptureToken": recapture_token,
        }
        res = self.page.post(
            self.login_url,
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
        pass

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
        response = res.get("response",{})
        if not response or response.get("total") !=1:
            raise BusinessError("查询订舱单据失败")
        bo_row = response.get("datas",{})[0]
        if not bo_row or bo_row.get("gdNo") != blNo:
            raise BusinessError("订舱列表接口返回数据异常")
        return bo_row
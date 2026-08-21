from app.core.task.base_task import BaseRpaTask
from app.core.task.context import TaskContext
from app.spider.common.login import LoginMixin
from app.spider.common.booking import query_booking as _query_booking


class CarrierBase(LoginMixin, BaseRpaTask):
    """船司基础类。"""
    carrier_code = "ZIM" # 船司编码
    login_url = "https://cis.zim-logistics.com.cn/Account/Login" # 登录地址
    index_url = "https://cis.zim-logistics.com.cn/" # 首页地址
    siteKey = "87004f4a-40ba-4b16-ad22-a8d034b6c6b8"  # 站点可以用于验证码解析使用

    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.cookies_redis_key = f"cookies:{self.carrier_code}_{self.website_info.get('websiteAccount')}"
        pass

    def query_booking(self, blNo: str):
        """查询订舱单据（薄壳，转发到公共方法）。"""
        return _query_booking(self, blNo)

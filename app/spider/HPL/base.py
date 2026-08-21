"""HPL 船司共享登录能力。"""

import random

from app.core.task.base_task import BaseRpaTask
from app.core.task.errors import BusinessError
from app.spider.HPL import selectors
from app.spider.HPL.common.login import LoginMixin


class HplBase(LoginMixin, BaseRpaTask):
    """HPL 船司任务的基础配置和代理能力。"""

    carrier_code = "HPL"
    si_url = selectors.SI_URL
    use_proxy = True

    def __init__(self, context, **kwargs):
        """初始化 HPL 账号级 Cookie 缓存键。"""
        super().__init__(context, **kwargs)
        account_identity = self.website_info.get("id") or self.website_info.get("websiteAccount")
        self.cookies_redis_key = f"cookies:{self.carrier_code}_{account_identity or 'default'}"



    def getProxyData(self):
        """从 Redis 获取代理数据。"""
        nation = random.choice(['HK', 'JP', 'TW', 'SG'])
        redis_key = f"byg240:{nation}:*"
        proxyList = self.redis_client.keys(redis_key)
        if not proxyList:
            return []
        proxy_key = random.choice(proxyList)
        proxyData = self.redis_client.get(proxy_key)
        return [proxyData] if proxyData else []

    def get_browser_proxy(self):
        """返回 HPL 本次浏览器启动使用的首个代理。"""
        proxy_data = self.getProxyData()
        if not proxy_data or not proxy_data[0]:
            raise BusinessError("HPL 未获取到可用代理")
        proxy = proxy_data[0]
        return proxy.decode() if isinstance(proxy, bytes) else str(proxy)

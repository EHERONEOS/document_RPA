"""EMC 船司基础配置。"""

from __future__ import annotations

import random

from app.core.task.base_task import BaseRpaTask
from app.core.task.context import TaskContext
from app.core.task.errors import BusinessError
from app.spider.EMC.common.login import LoginMixin
from app.spider.EMC import selectors


class EmcBase(LoginMixin, BaseRpaTask):
    """EMC 任务共享代理、Cookie 与登录配置。"""

    carrier_code = "EMC"
    use_proxy = True
    si_url = selectors.SI_URL
    login_url = selectors.LOGIN_URL

    def __init__(self, context: TaskContext, **kwargs):
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
        """返回 EMC 本次浏览器启动使用的首个代理。"""
        proxy_data = self.getProxyData()
        if not proxy_data or not proxy_data[0]:
            raise BusinessError("EMC 未获取到可用代理")
        proxy = proxy_data[0]
        return proxy.decode() if isinstance(proxy, bytes) else str(proxy)

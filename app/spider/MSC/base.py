"""MSC 船司共享配置。"""

from app.core.task.base_task import BaseRpaTask
from app.core.task.context import TaskContext
from app.spider.MSC import selectors
from app.spider.MSC.common.login import LoginMixin
from app.spider.common.field_verify import FieldVerificationMixin


class MscBase(FieldVerificationMixin, LoginMixin, BaseRpaTask):
    """复用 MSC 账号的 Cookie 和登录流程。"""

    carrier_code = "MSC"
    login_url = selectors.LOGIN_URL
    index_url = selectors.INDEX_URL

    def __init__(self, context: TaskContext, **kwargs):
        super().__init__(context, **kwargs)
        account_identity = self.website_info.get("id") or self.website_info.get("websiteAccount")
        self.cookies_redis_key = f"cookies:{self.carrier_code}_{account_identity or 'default'}"

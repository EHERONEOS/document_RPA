"""MSCGW 船司共享配置。"""

from app.core.task.base_task import BaseRpaTask
from app.core.task.context import TaskContext
from app.spider.SNLWY import selectors
from app.spider.SNLWY.actions.login import LoginMixin
from app.spider.common.field_verify import FieldVerificationMixin


class SnlwyBase(FieldVerificationMixin, LoginMixin, BaseRpaTask):
    """复用 SNLWY 账号的 Cookie 和登录流程。"""

    carrier_code = "SNLWY"
    login_url = selectors.LOGIN_URL
    index_url = selectors.INDEX_URL

    def __init__(self, context: TaskContext, **kwargs):
        super().__init__(context, **kwargs)
        account_identity = self.website_info.get("websiteAccount")
        self.session_redis_key = f"session:snlwy_{account_identity or 'default'}"

    def _is_checkbox_checked(self, selector: str, label: str) -> bool:
        """读取 Element Plus 复选框选中态，选中时 label class 含 is-checked。"""
        element = self.dom._find(selector, label)
        return "is-checked" in (element.attr("class") or "")

    def _set_checkbox_if_needed(self, selector: str, label: str, expected: bool) -> None:
        """复选框选中状态与预期不一致时点击切换。"""
        if self._is_checkbox_checked(selector, label) != expected:
            self.dom.click(selector, label)

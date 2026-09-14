"""MSCGW SI 动作链共享的页面、会话与校验运行时。"""
from __future__ import annotations

from typing import Any, Protocol

from DrissionPage._pages.chromium_base import ChromiumBase
from app.core.logging.logger import Logger
from app.core.page.dom import DomHelper
from app.core.page.http import HttpHelper
from app.core.task.context import TaskContext
from app.spider.MSCGW.common.login import LoginMixin
from app.spider.MSCGW.common.si_field_verify import MscgwSiFieldVerificationMixin
from app.spider.common.field_verify import FieldVerificationMixin


class MscgwSiLifecycle(Protocol):
    """动作运行时从 RPA 生命周期入口读取的最小能力集合。"""

    context: TaskContext
    page: ChromiumBase
    dom: DomHelper
    http: HttpHelper
    logger: Logger
    website_info: dict[str, Any]
    cookies_redis_key: str
    ignored_unfilled_fields: list[str]
    index_url: str
    attachments: list[Any]
    si_shadow: DomHelper | None

    def save_cookies(self, key: str) -> None: ...

    def set_page_cookies(self, key: str) -> None: ...

    def claim_credential_login(self) -> bool: ...

    def _notify_login_finished(self, success: bool) -> None: ...


class MscgwSiRuntime(MscgwSiFieldVerificationMixin, FieldVerificationMixin, LoginMixin):
    """向动作链提供任务生命周期以外的 MSCGW SI 运行状态。"""

    def __init__(self, lifecycle: MscgwSiLifecycle) -> None:
        self._lifecycle = lifecycle
        self.context: TaskContext = lifecycle.context
        self.content: dict[str, Any] = self.context.content if self.context.content is not None else {}
        self.remain_content: dict[str, Any] = (
            self.context.remain_content if self.context.remain_content is not None else {}
        )
        self.page: ChromiumBase = lifecycle.page
        self.dom: DomHelper = lifecycle.dom
        self.http: HttpHelper = lifecycle.http
        self.logger: Logger = lifecycle.logger
        self.website_info: dict[str, Any] = lifecycle.website_info
        self.cookies_redis_key: str = lifecycle.cookies_redis_key
        self.ignored_unfilled_fields: list[str] = lifecycle.ignored_unfilled_fields
        self.index_url: str = lifecycle.index_url
        self.blank_bill: bool = bool(self.content.get("blankBill", False))
        self._si_shadow: DomHelper | None = lifecycle.si_shadow

    @property
    def si_shadow(self) -> DomHelper:
        """返回已在导航动作中初始化的 SI Shadow DOM 操作对象。"""
        if self._si_shadow is None:
            raise RuntimeError("MSCGW SI Shadow DOM 尚未初始化，请先执行打开提单指令动作")
        return self._si_shadow

    @si_shadow.setter
    def si_shadow(self, value: DomHelper | None) -> None:
        self._si_shadow = value
        # 同步给生命周期对象，保持保存后刷新 Shadow DOM 的状态一致。
        self._lifecycle.si_shadow = value

    @property
    def attachments(self) -> list[Any]:
        return self._lifecycle.attachments

    def save_cookies(self, key: str) -> None:
        self._lifecycle.save_cookies(key)

    def set_page_cookies(self, key: str) -> None:
        self._lifecycle.set_page_cookies(key)

    def claim_credential_login(self) -> bool:
        return self._lifecycle.claim_credential_login()

    def notify_login_finished(self, success: bool) -> None:
        self._lifecycle._notify_login_finished(success)

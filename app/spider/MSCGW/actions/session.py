"""MSCGW 会话生命周期动作。"""
from __future__ import annotations

from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


class SessionActions:
    """封装 MSCGW 登录及其任务生命周期通知。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime

    def login(self, _inputs: Mapping[str, Any]) -> dict[str, bool]:
        """执行 MSCGW 登录链，并同步登录生命周期通知。"""
        success = False
        try:
            self.runtime.login()
            success = True
            return {"loggedIn": True}
        finally:
            self.runtime.notify_login_finished(success)

    def register(self, registry: ActionRegistry) -> None:
        """将登录动作绑定到显式动作白名单。"""
        registry.register("MSCGW.login", lambda _context, inputs: self.login(inputs))

"""MSCGW SI 保存或获取外部可见产物的动作。"""
from __future__ import annotations

import time
from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.core.task.errors import BusinessError
from app.spider.MSCGW import selectors
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


class PublishingActions:
    """封装保存装运指令和下载预览文件的副作用动作。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime

    def save_shipping_instruction(self, _inputs: Mapping[str, Any]) -> None:
        """保存装运指令，确认成功后刷新 Shadow DOM。"""
        self.runtime.si_shadow.click(selectors.SAVE_BOOKING_BTN, name="保存按钮")
        success = self.runtime.si_shadow._find(
            selectors.SAVE_SUCCESS_MSG, name="保存成功消息", timeout=10, required=False
        )
        if not success:
            raise BusinessError("截单保存失败")
        self.runtime.si_shadow.click(selectors.SAVE_SUCCESS_OK, name="保存成功确认按钮")
        self.runtime.page.wait.doc_loaded()
        shadow = self.runtime.dom.get_shadow_root(selectors.SI_SHADOW, timeout=20)
        if shadow is None:
            raise BusinessError("保存成功后未获取到 MSCGW SI 页面 Shadow DOM")
        self.runtime.si_shadow = shadow

    def download_preview(self, _inputs: Mapping[str, Any]) -> None:
        """等待预览可用后下载文件并登记到当前任务附件。"""
        for _ in range(30):
            button = self.runtime.si_shadow._find(selectors.PREVIEW_BTN, name="预览按钮", timeout=1, required=False)
            if button and button.states.is_enabled:
                button.click()
                break
            time.sleep(1)
        else:
            raise BusinessError("页面刷新后预览按钮未可用")
        for _ in range(30):
            button = self.runtime.si_shadow._find(
                selectors.DOWNLOAD_PREVIEW_BTN, name="下载预览按钮", timeout=1, required=False
            )
            if button and button.states.is_enabled:
                self.runtime.attachments.append(self.runtime.dom.click_to_download(button, name="下载预览按钮"))
                break
            time.sleep(1)
        else:
            raise BusinessError("预览下载按钮未可用")
        self.runtime.si_shadow.click(selectors.DOWNLOAD_CLOSE_BTN, name="关闭下载预览按钮")

    def register(self, registry: ActionRegistry) -> None:
        """将保存和预览下载动作绑定到显式动作白名单。"""
        registry.register(
            "MSCGW.save_shipping_instruction",
            lambda _context, inputs: self.save_shipping_instruction(inputs),
        )
        registry.register("MSCGW.download_preview", lambda _context, inputs: self.download_preview(inputs))

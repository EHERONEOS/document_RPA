"""MSCGW SI 保存、预览下载与提交。"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import TYPE_CHECKING

from app.core.task.errors import BusinessError
from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


class SiSaveSubmitMixin:
    """封装 SI 保存、预览下载和直接提交。"""

    def _build_draft_file_stem(self: "FhtMscgwSiTask") -> str:
        safe_queue_name = re.sub(r"[^A-Za-z0-9_-]+", "_", self.context.queue_name).strip("_") or "task"
        safe_job_no = re.sub(r"[^A-Za-z0-9_-]+", "_", str(self.job_no)).strip("_") or "unknown"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{safe_queue_name}_{safe_job_no}_{timestamp}"

    def save_submit(self: "FhtMscgwSiTask") -> None:
        if self.splitOrConsolidatedBill:
            return

        self.si_shadow.click(selectors.SAVE_BOOKING_BTN, name="保存按钮")
        is_save_success = self.si_shadow._find(
            selectors.SAVE_SUCCESS_MSG, name="保存成功消息", timeout=10, required=False
        )
        if not is_save_success:
            raise BusinessError("截单保存失败")
        self.si_shadow.click(selectors.SAVE_SUCCESS_OK, name="保存成功确认按钮")
        self.page.wait.doc_loaded()
        self.si_shadow = self.dom.get_shadow_root(selectors.SI_SHADOW, timeout=20)
        for _ in range(30):
            preview_btn = self.si_shadow._find(selectors.PREVIEW_BTN, name="预览按钮", timeout=1, required=False)
            if preview_btn and preview_btn.states.is_enabled:
                preview_btn.click()
                break
            time.sleep(1)
        else:
            raise BusinessError("页面刷新后预览按钮未可用")
        for _ in range(30):
            download_preview_btn = self.si_shadow._find(
                selectors.DOWNLOAD_PREVIEW_BTN, name="下载预览按钮", timeout=1, required=False
            )
            if download_preview_btn and download_preview_btn.states.is_enabled:
                file_path = self.dom.click_to_download(
                    download_preview_btn,
                    rename=self._build_draft_file_stem(),
                    name="下载预览按钮",
                )
                self.attachments.append(file_path)
                break
            time.sleep(1)
        self.si_shadow.click(selectors.DOWNLOAD_CLOSE_BTN, name="关闭下载预览按钮")
        if self.context.rpa_operate == "SUBMIT_DIRECT":
            self.si_shadow.click(selectors.SUBMIT_BTN, name="提交按钮")
            is_submit_success = self.si_shadow._find(
                selectors.SUBMIT_SUCCESS_MSG, name="提交成功消息", timeout=30, required=False
            )
            if not is_submit_success:
                raise BusinessError("截单提交失败")

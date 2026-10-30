"""MSCGW SI 保存、预览下载与提交。"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.core.task.errors import BusinessError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.tasks.fz_snlwy_si import FzSnlwySiTask


class SiSaveSubmitMixin:
    """封装 SI 保存、预览下载和直接提交。"""

    def _build_draft_file_stem(self: "FzSnlwySiTask") -> str:
        safe_queue_name = re.sub(r"[^A-Za-z0-9_-]+", "_", self.context.queue_name).strip("_") or "task"
        safe_job_no = re.sub(r"[^A-Za-z0-9_-]+", "_", str(self.job_no)).strip("_") or "unknown"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{safe_queue_name}_{safe_job_no}_{timestamp}"

    def save_submit(self: "FzSnlwySiTask") -> None:
        """保存并提交。"""
        self.dom.click(selectors.SAVE_BUTTON, name="存草稿按钮")
        self.page.wait.doc_loaded()
        self.download_draft()
        self.page.wait.doc_loaded()
        if self.context.rpa_operate == "SUBMIT_DIRECT":
            self.dom.click(selectors.SUBMIT_BUTTON, name="提交按钮")
            self.page.wait.doc_loaded()


    def download_draft(self: "FzSnlwySiTask") -> None:
        """下载草稿件。"""
        download_preview_btn = self.dom._find(
            selectors.ATTACH_BUTTON, name="查看预览按钮", timeout=1, required=False
        )
        file_path = self.dom.click_to_download(
            download_preview_btn,
            rename=self._build_draft_file_stem(),
            name="下载草稿件",
        )
        self.attachments.append(file_path)
        pass


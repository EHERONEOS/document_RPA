"""SNLWY SI 保存、预览下载与提交。"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import TYPE_CHECKING

from DrissionPage.errors import BaseError

from app.core.task.errors import ElementOperationError
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
        # 保存通过异步接口完成，doc_loaded() 不会等待遮罩及表单重新渲染。
        self.download_draft(after_save=True)
        if self.context.rpa_operate == "SUBMIT_DIRECT":
            self.dom.click(selectors.SUBMIT_BUTTON, name="提交按钮")
            self.page.wait.doc_loaded()


    def _wait_draft_ready(
        self: "FzSnlwySiTask", *, after_save: bool = False, timeout: float = 60
    ):
        """记住短暂的保存成功提示，等刷新结束后返回当前页面的预览按钮。"""
        deadline = time.monotonic() + timeout
        save_succeeded = not after_save
        ready_since = None
        reason = "未检测到保存成功提示" if after_save else "预览件按钮未就绪"
        while time.monotonic() < deadline:
            try:
                status = self.page.run_js("""
                    const visible = el => el.getClientRects().length > 0 &&
                        getComputedStyle(el).visibility !== 'hidden';
                    const messages = selector => Array.from(
                        document.querySelectorAll(selector)
                    ).filter(visible).map(el => el.innerText || '').join('；');
                    return {
                        loading: Array.from(document.querySelectorAll(
                            '.el-skeleton, .el-loading-mask'
                        )).some(visible),
                        success: /操作成功|保存成功|存为草稿成功/.test(
                            messages('.el-message--success')
                        ),
                        error: messages('.el-message--error')
                    };
                """)
                if status['error']:
                    raise ElementOperationError(f"官网提示：{status['error']}")
                save_succeeded = save_succeeded or status['success'] is True
                if not save_succeeded:
                    reason = "未检测到保存成功提示"
                elif status['loading']:
                    reason = "加载遮罩或骨架屏未消失"
                else:
                    # 刷新可能替换旧 DOM；每轮重新定位，滚动后再判断是否被遮挡。
                    button = self.dom._find(
                        selectors.ATTACH_BUTTON, name="查看预览按钮",
                        timeout=0, required=False,
                    )
                    if button:
                        button.scroll.to_see()
                    if button and button.states.is_clickable and not button.states.is_covered:
                        if ready_since is None:
                            ready_since = time.monotonic()
                        # 避免保存成功与下一轮表单加载之间的短暂空隙。
                        if time.monotonic() - ready_since >= 1:
                            return button
                        time.sleep(0.2)
                        continue
                    reason = "预览件按钮不存在、不可点击或被遮挡"
            except BaseError:
                # 路由切换期间可能丢失 JS 上下文或元素，本轮不判定就绪。
                reason = "页面切换中，暂时无法读取页面或预览件按钮"
            ready_since = None
            time.sleep(0.2)
        stage = "保存后页面未就绪" if after_save else "预览件页面未就绪"
        raise ElementOperationError(f"{stage}：等待={timeout}s；{reason}")

    def download_draft(self: "FzSnlwySiTask", *, after_save: bool = False) -> None:
        """下载草稿件。"""
        download_preview_btn = self._wait_draft_ready(after_save=after_save)
        file_path = self.dom.click_to_download(
            download_preview_btn,
            rename=self._build_draft_file_stem(),
            name="下载草稿件",
        )
        self.attachments.append(file_path)


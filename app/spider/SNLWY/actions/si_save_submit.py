"""SNLWY SI 保存、预览下载与提交。"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import TYPE_CHECKING

from DrissionPage.errors import BaseError

from app.core.logging.logger import log
from app.core.task.errors import ElementNotFoundError, ElementOperationError
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
            self.page.run_js("""
                window.__snlwyMessagesBeforeSubmit = new WeakSet(
                    document.querySelectorAll('.el-message--success, .el-message--error')
                );
            """)
            time.sleep(5)
            self._wait_submit_result()
        # raise "测试保存"

    def _click_submit_confirm(self: "FzSnlwySiTask", attempt: int) -> tuple[str, dict]:
        """在点击前采样按钮落点，保留驱动的实际返回结果。"""
        selector = selectors.SUBMIT_CONFIRM_BUTTON
        name = f"提交确认按钮（第{attempt}次）"
        probe = {}
        try:
            button = self.dom._find(selector, name=name)
            try:
                probe = button.run_js("""
                    const rect = this.getBoundingClientRect();
                    const x = rect.left + rect.width / 2;
                    const top = document.elementFromPoint(x, rect.top + 3);
                    const center = document.elementFromPoint(x, rect.top + rect.height / 2);
                    const label = el => el ? el.tagName + (
                        el.classList.length ? '.' + [...el.classList].join('.') : ''
                    ) : null;
                    return {
                        matches: document.evaluate(arguments[0], document, null,
                            XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null).snapshotLength,
                        disabled: this.matches(':disabled') || this.getAttribute('aria-disabled') === 'true',
                        inSubmitDialog: this.closest('.el-message-box')?.textContent.includes('是否提交') ?? false,
                        top: label(top),
                        center: label(center),
                        topHits: this.contains(top),
                        centerHits: this.contains(center)
                    };
                """, selector.removeprefix("x:"))
            except BaseError as exc:
                probe = {"采样异常": type(exc).__name__}
            if not button.states.is_clickable:
                raise ElementOperationError(f"{name}元素不可点击：{selector}；等待=5s")
            log(f"点击{name}")
            started_at = time.perf_counter()
            try:
                result = button.click(by_js=True, wait_stop=False, timeout=5)
            finally:
                elapsed = time.perf_counter() - started_at
                log(f"{name}点击调用耗时={elapsed:.2f}秒")
        except (ElementNotFoundError, ElementOperationError, BaseError) as exc:
            log(f"{name}点击异常：{type(exc).__name__}；点击前={probe}")
            raise

        if result is False:
            reason = "驱动返回点击失败"
        elif probe.get("inSubmitDialog") is False:
            reason = "定位到的按钮不在提交确认弹窗内"
        elif probe.get("disabled"):
            reason = "点击前按钮处于禁用状态"
        elif probe.get("centerHits") or probe.get("topHits"):
            reason = "落点探测命中按钮，实际事件及官网响应待核对"
        elif probe.get("center") or probe.get("top"):
            reason = "探测点被其他元素覆盖"
        else:
            reason = "未取得按钮落点"
        return reason, probe

    def _wait_submit_result(self: "FzSnlwySiTask", timeout: float = 60) -> None:
        """等待官网提示，确认弹窗仍打开时最多点击三次。"""
        attempts = 1
        reason, probe = self._click_submit_confirm(attempts)
        deadline = time.monotonic() + timeout
        retry_interval = 10
        next_retry_at = time.monotonic() + retry_interval
        confirm_xpath = selectors.SUBMIT_CONFIRM_BUTTON.removeprefix("x:")
        while time.monotonic() < deadline:
            try:
                status = self.page.run_js("""
                    const previous = window.__snlwyMessagesBeforeSubmit;
                    const visible = el => el.getClientRects().length > 0 &&
                        getComputedStyle(el).visibility === 'visible';
                    const messages = selector => Array.from(document.querySelectorAll(selector))
                        .filter(el => !previous?.has(el) && visible(el))
                        .map(el => (el.innerText || '').trim());
                    const button = document.evaluate(arguments[0], document, null,
                        XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    const dialog = button?.closest('.el-message-box');
                    return {
                        success: messages('.el-message--success').includes('操作成功'),
                        error: messages('.el-message--error').filter(Boolean).join('；'),
                        dialog_visible: Boolean(dialog && visible(dialog) && visible(button))
                    };
                """, confirm_xpath)
            except BaseError:
                # 提交后页面切换时，JS 上下文可能暂时不可用。
                time.sleep(0.2)
                continue
            if status['error']:
                raise ElementOperationError(f"官网提示：{status['error']}")
            if status['success']:
                return
            if next_retry_at is not None and time.monotonic() >= next_retry_at:
                if not status['dialog_visible']:
                    next_retry_at = None
                else:
                    log(
                        f"提交确认按钮（第{attempts}次）点击后{retry_interval}s无官网结果，"
                        f"弹窗仍可见；判断={reason}；点击前={probe}"
                    )
                    if attempts >= 3:
                        raise ElementOperationError(
                            f"已点击{attempts}次提交确认按钮，弹窗仍未关闭且未检测到提交成功提示"
                        )
                    attempts += 1
                    reason, probe = self._click_submit_confirm(attempts)
                    next_retry_at = time.monotonic() + retry_interval
            time.sleep(0.2)
        log(
            f"提交确认按钮（第{attempts}次）等待官网结果超时；"
            f"判断={reason}；点击前={probe}"
        )
        raise ElementOperationError(f"未检测到提交成功提示（操作成功）：等待={timeout}s")

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


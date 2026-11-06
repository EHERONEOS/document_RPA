from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import time
from uuid import uuid4

from app.core.logging.logger import Logger
from DrissionPage._elements.none_element import NoneElement
from DrissionPage._elements.chromium_element import ChromiumElement
from DrissionPage._pages.chromium_base import ChromiumBase

from app.core.browser.window import ensure_browser_window_ready
from app.core.task.errors import RpaError
from app.core.page.screenshot_layout import EXPAND_LAYOUT, RESTORE_LAYOUT



class Screenshot:
    """截图能力封装。"""

    ERROR_PREFIX = "error"
    PROCESS_PREFIX = "执行截图"

    def __init__(
        self,
        page: ChromiumBase,
        screenshot_dir: str  = "runtime/screenshots",
        *,
        expand_root_selector: str | None = None,
        ) :
        self.page = page
        self.logger = Logger()
        self.screenshot_dir = Path(screenshot_dir)
        self.expand_root_selector = expand_root_selector

    @contextmanager
    def _expanded_layout(self):
        """业务和失败截图共用；布局处理失败时仍尽力保留现场截图。"""
        if not self.expand_root_selector:
            yield
            return
        key = f"__rpa_screenshot_{uuid4().hex}"
        try:
            try:
                expanded = self.page.run_js(EXPAND_LAYOUT, key, self.expand_root_selector)
                if expanded:
                    # 让富文本等控件按展开后的尺寸重绘；登录页等未命中则不等待。
                    time.sleep(0.2)
            except Exception as exc:
                self.logger.warn(f"长截图布局展开失败，仍尝试截图：{exc}")
            yield
        finally:
            try:
                self.page.run_js(RESTORE_LAYOUT, key)
            except Exception as exc:
                # 恢复失败不能掩盖截图异常，也不能丢弃已经生成的截图。
                self.logger.error(f"长截图布局恢复失败：{exc}")


    def page_shot(self, jobno: str, job_type: str, error: bool = True, retry: int = 3):
        """页面截图。"""
        for attempt in range(1, retry + 1):
            try:
                ensure_browser_window_ready(self.page)
                file_name = self.build_file_name(jobno, job_type, error)
                with self._expanded_layout():
                    file_path = self.page.get_screenshot(path=self.screenshot_dir, name=file_name, full_page=True)
                return file_path
            except Exception as e:
                self.logger.error(f"截图失败，第{attempt}/{retry}次: {e}")
        raise RpaError("页面截图失败")



    def element_shot(self, element: ChromiumElement, jobno: str, job_type: str, error: bool = True, retry: int = 3):
        """元素截图。"""
        for attempt in range(1, retry + 1):
            try:
                ensure_browser_window_ready(self.page)
                file_name = self.build_file_name(jobno, job_type, error)
                file_path = element.get_screenshot(path=self.screenshot_dir, name=file_name)
                return file_path
            except Exception as e:
                self.logger.error(f"截图失败，第{attempt}/{retry}次: {e}")
        raise RpaError("元素截图失败")

    def build_file_name(self, jobno: str, job_type: str, error: bool):
        """按业务命名规则生成截图文件名。"""
        prefix = "error" if error else "执行截图"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name =  f"{prefix}_{jobno}_{job_type}_{timestamp}.png"
        return file_name



    

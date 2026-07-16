from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging.logger import Logger
from DrissionPage._elements.none_element import NoneElement
from DrissionPage._elements.chromium_element import ChromiumElement
from DrissionPage._pages.chromium_base import ChromiumBase



class Screenshot:
    """截图能力封装。"""

    ERROR_PREFIX = "error"
    PROCESS_PREFIX = "执行截图"

    def __init__(
        self,
        page: ChromiumBase,
        screenshot_dir: str  = "runtime/screenshots"
        ) :
        self.page = page
        self.logger = Logger()
        self.screenshot_dir = Path(screenshot_dir)


    def page_shot(self, jobno: str, job_type: str,error: bool = True):
        """页面截图。"""
        try:
            file_name = self.build_file_name(jobno, job_type, error)
            file_path = self.page.get_screenshot(path=self.screenshot_dir, name=file_name, full_page=True)
            return file_path
        except Exception as e:
            self.logger.error(f"截图失败: {e}")
            pass

    def element_shot(self, element: ChromiumElement, jobno: str, job_type: str,error: bool = True):
        """元素截图。"""
        try:
            file_name = self.build_file_name(jobno, job_type, error)
            file_path = element.get_screenshot(path=self.screenshot_dir, name=file_name)
            return file_path
        except Exception as e:
            self.logger.error(f"截图失败: {e}")
            pass

    def build_file_name(self, jobno: str, job_type: str, error: bool):
        """按业务命名规则生成截图文件名。"""
        prefix = "error" if error else "执行截图"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name =  f"{prefix}_{jobno}_{job_type}_{timestamp}.png"
        return file_name



    
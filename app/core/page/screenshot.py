from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging.logger import log
from DrissionPage._elements.none_element import NoneElement


class Screenshot:
    """截图能力封装。"""

    ERROR_PREFIX = "error"
    PROCESS_PREFIX = "执行截图"

    def __init__(
        self,
        page: Any | None = None,
        *,
        screenshot_dir: str | Path = "runtime/screenshots",
    ) -> None:
        self.page = page
        self.screenshot_dir = Path(screenshot_dir)

    def bind_page(self, page: Any) -> "Screenshot":
        """绑定页面对象，便于后续复用同一个实例。"""
        self.page = page
        return self

    def page_shot(
        self,
        order_no: str,
        order_type: str,
        *,
        is_error: bool = True,
        full_page: bool = True,
    ) -> str:
        """页面截图。"""
        self._ensure_page()
        file_path = self.build_screenshot_path(order_no, order_type, is_error=is_error)
        self._save_page_screenshot(file_path, full_page=full_page)
        log(f"保存页面截图 path={file_path}")
        return str(file_path)

    def element_shot(
        self,
        order_no: str,
        order_type: str,
        target: Any,
        *,
        is_error: bool = False,
        locator: str | None = None,
        timeout: int = 2,
    ) -> str:
        """元素截图，target 可传 locator 或元素对象。"""
        self._ensure_page()
        element = self._resolve_element(target=target, locator=locator, timeout=timeout)
        file_path = self.build_screenshot_path(order_no, order_type, is_error=is_error)
        self._save_element_screenshot(element, file_path)
        log(f"保存元素截图 path={file_path}")
        return str(file_path)

    def build_screenshot_path(self, order_no: str, order_type: str, *, is_error: bool) -> Path:
        """按业务命名规则生成截图路径。"""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.build_screenshot_name(order_no, order_type, is_error=is_error)}.png"
        return self.screenshot_dir / filename

    def build_screenshot_name(self, order_no: str, order_type: str, *, is_error: bool) -> str:
        """生成截图文件名。"""
        prefix = self.ERROR_PREFIX if is_error else self.PROCESS_PREFIX
        return self._build_name(prefix, order_no, order_type)

    def _build_name(self, prefix: str, order_no: str, order_type: str) -> str:
        order_no = self._safe_filename(order_no)
        order_type = self._safe_filename(order_type)
        time_text = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{order_no}_{order_type}_{time_text}"

    def _safe_filename(self, value: str) -> str:
        invalid_chars = '<>:"/\\|?*'
        sanitized = "".join("_" if char in invalid_chars else char for char in str(value))
        sanitized = sanitized.strip().strip(".")
        return sanitized or "unknown"

    def _ensure_page(self) -> None:
        if self.page is None:
            raise RuntimeError("未绑定页面对象，无法执行截图/录屏")

    def _resolve_element(self, *, target: Any, locator: str | None, timeout: int) -> Any:
        if target is not None and hasattr(target, "get_screenshot"):
            return target

        actual_locator = locator or target
        if not actual_locator:
            raise ValueError("元素截图必须传入元素对象或 locator")

        if not hasattr(self.page, "ele"):
            raise RuntimeError("当前页面对象不支持元素定位")

        element = self.page.ele(actual_locator, timeout=timeout)
        if element is None or isinstance(element, NoneElement):
            raise RuntimeError(f"元素不存在，无法截图：{actual_locator}")
        return element

    def _save_page_screenshot(self, file_path: Path, *, full_page: bool) -> None:
        if not hasattr(self.page, "get_screenshot"):
            raise RuntimeError("当前页面对象不支持页面截图")
        self.page.get_screenshot(path=str(file_path.parent), name=file_path.name, full_page=full_page)

    def _save_element_screenshot(self, element: Any, file_path: Path) -> None:
        if not hasattr(element, "get_screenshot"):
            raise RuntimeError("当前元素对象不支持截图")
        element.get_screenshot(path=str(file_path.parent), name=file_path.name)

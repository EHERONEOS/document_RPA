from app.core.logging.logger import log
from app.core.task.errors import ElementNotFoundError


class DomHelper:
    """页面 DOM 操作封装。"""

    def __init__(self, page):
        self.page = page

    def _find(self, locator, name, required):
        element = self.page.ele(locator, timeout=0)
        if element is None and required:
            raise ElementNotFoundError(f"{name}元素不存在：{locator}")
        return element

    def click(self, locator, name, required=True):
        """点击元素。"""
        element = self._find(locator, name, required)
        if element is None:
            return False
        element.click()
        log(f"点击{name}")
        return True

    def input_text(self, locator, value, name, required=True):
        """输入文本。"""
        element = self._find(locator, name, required)
        if element is None:
            return False
        element.input(value, clear=True)
        log(f"输入{name}")
        return True

    def get_text(self, locator, name, required=True):
        """获取元素文本。"""
        element = self._find(locator, name, required)
        if element is None:
            return ""
        return getattr(element, "text", "") or ""

    def get_value(self, locator, name, required=True):
        """获取 input value。"""
        element = self._find(locator, name, required)
        if element is None:
            return ""
        value = element.attr("value")
        return "" if value is None else str(value)

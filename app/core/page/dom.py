from app.core.logging.logger import log
from app.core.task.errors import ElementNotFoundError
from DrissionPage._elements.none_element import NoneElement
from DrissionPage._pages.chromium_base import ChromiumBase



class DomHelper:
    """页面 DOM 操作封装。"""

    def __init__(self, page:ChromiumBase):
        self.page = page

    @staticmethod
    def _is_missing_element(element) -> bool:
        return element is None or isinstance(element, NoneElement)

    def _find(self, locator, name=None, required=True, timeout=2):
        name = locator if name is None else name
        element = self.page.ele(locator, timeout=timeout)
        if self._is_missing_element(element) and required:
            raise ElementNotFoundError(f"{name}元素不存在：{locator}")
        return element

    def click(self, locator, name=None, required=True, timeout=2):
        """点击元素。"""
        name = locator if name is None else name
        element = self._find(locator, name, required, timeout)
        if self._is_missing_element(element):
            return False
        element.click()
        log(f"点击{name}")
        return True

    def click_all(self, locator, name=None, required=True, timeout=2):
        """点击所有匹配元素。"""
        name = locator if name is None else name
        elements = self.page.eles(locator, timeout=timeout)
        if not elements:
            if required:
                raise ElementNotFoundError(f"{name}元素不存在：{locator}")
            return False
        for element in elements:
            element.click()
        log(f"点击全部{name}")
        return True

    def input_text(self, locator, value, name=None, required=True, timeout=2):
        """输入文本。"""
        name = locator if name is None else name
        element = self._find(locator, name, required, timeout)
        if self._is_missing_element(element):
            return False
        element.click()
        element.input(value, clear=True)
        log(f"输入{name}")
        return True

    def select(self, locator, value, name=None, by="text", required=True, timeout=2):
        """选择 select 选项。"""
        name = locator if name is None else name
        element = self._find(locator, name, required, timeout)
        if self._is_missing_element(element):
            return False

        try:
            if by == "text":
                element.select.by_text(value, timeout=timeout)
            elif by == "value":
                element.select.by_value(value, timeout=timeout)
            elif by == "index":
                element.select.by_index(value, timeout=timeout)
            else:
                raise ValueError(f"不支持的 select 选择方式：{by}")
        except RuntimeError as exc:
            raise ElementNotFoundError(f"{name}选项不存在：{value}") from exc

        log(f"选择{name}")
        return True

    def get_text(self, locator, name=None, required=True, timeout=2):
        """获取元素文本。"""
        element = self._find(locator, name, required, timeout)
        if self._is_missing_element(element):
            return ""
        return getattr(element, "text", "") or ""

    def get_value(self, locator, name=None, required=True, timeout=2):
        """获取 input value。"""
        element = self._find(locator, name, required, timeout)
        if self._is_missing_element(element):
            return ""
        value = element.value
        return "" if value is None else str(value)

    def get_select_value(self, locator, name=None,by="text", required=True, timeout=2):
        """获取 select 当前选中值。"""
        element = self._find(locator, name, required, timeout)
        if self._is_missing_element(element):
            return ""
        if by == 'value':
            return element.value
        if by == 'text':
            selected_option = element.ele('css:option:checked', timeout=timeout)
            return selected_option.text if selected_option else ""
        raise ElementNotFoundError(f'不支持的 select 取值方式: {by}')

    def get_select_text(self, locator, name=None, required=True, timeout=2):
        """获取 select 当前选中展示文本。"""
        element = self._find(locator, name, required, timeout)
        if self._is_missing_element(element):
            return ""

        if element.select.is_multi:
            return [
                getattr(option, "text", "") or ""
                for option in element.select.selected_options
            ]

        option = element.select.selected_option
        if option is None:
            return ""
        return getattr(option, "text", "") or ""

    def in_frame(self, locator, name=None, required=True, timeout=2):
        """切换到 iframe。"""
        iframe = self._find(locator, name, required, timeout)
        if self._is_missing_element(iframe):
            return None
        return DomHelper(iframe)

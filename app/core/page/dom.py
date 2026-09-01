import re
import time

from app.core.logging.logger import log
from app.core.task.errors import ElementNotFoundError, ElementOperationError
from DrissionPage.errors import BaseError, CanNotClickError, NoRectError
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
        name = name or locator
        try:
            element = self.page.ele(locator, timeout=timeout)
        except BaseError as exc:
            raise ElementOperationError(
                f"查找{name}失败：定位器={locator}；等待={timeout}s"
                f"原始异常={type(exc).__name__}: {exc}"
            ) from exc
        if self._is_missing_element(element):
            if required:
                raise ElementNotFoundError(
                    f"{name}元素不存在：{locator}；等待={timeout}s"
                )
            return False
        return element

    def _find_eles(self, locator, name=None, required=True, timeout=2):
        name = name or locator
        try:
            elements = self.page.eles(locator, timeout=timeout)
        except BaseError as exc:
            raise ElementOperationError(
                f"查找{name}失败：定位器={locator}；等待={timeout}s"
                f"原始异常={type(exc).__name__}: {exc}"
            ) from exc
        if not elements and required:
            raise ElementNotFoundError(
                f"{name}元素不存在：{locator}；等待={timeout}s"
            )
        return elements

    def click(self, locator, name=None, required=True, timeout=2):
        """点击元素。"""
        name = name or locator
        element = self._find(locator, name, required, timeout)
        if not element:
            return False
        if not element.states.is_clickable:
            if required:
                raise ElementOperationError(
                    f"{name}元素不可点击：{locator}；等待={timeout}s"
                )
            return False
        log(f"点击{name}")
        element.click()
        return True

    def click_all(self, locator, name=None, required=True, timeout=2):
        """点击所有匹配元素。"""
        name = name or locator
        elements = self._find_eles(locator, name, required, timeout)
        log(f"点击全部{name}")
        for element in elements:
            element.click()
        return True
   
    def select_radio(self, selector, value, name=None, required=True, timeout=2):
        """按可见文本在单选框子选项中选中指定项。"""
        name = name or selector
        expected_text = str(value).strip()
        for option in self.page.eles(selector, timeout=timeout):
            if str(getattr(option, "text", "") or "").strip() != expected_text:
                continue
            log(f"选择{name}")
            option.click()
            return True

        if required:
            raise ElementNotFoundError(f"{name}选项不存在：{value}")
        return False  


    def input_text(self, locator, value, name=None, required=True, blur=True, timeout=2):
        """输入文本。"""
        name = name or locator
        element = self._find(locator, name, required, timeout)
        if not element:
            return False
        expected_value = str(value)
        original_value = str(element.value or "")
        if original_value == expected_value:
            return True
        log(f"输入{name}")
        element.click()
        element.input(expected_value, clear=True)
        if blur:
            self.page.run_js("arguments[0].blur();", element)
        return True


    def select(self, locator, value, name=None, by="text", required=True, timeout=2):
        """选择 select 选项。"""
        name = name or locator
        element = self._find(locator, name, required, timeout)
        if not element:
            return False

        try:
            log(f"选择{name}")
            if by == "text":
                element.select.by_text(value, timeout=timeout)
            elif by == "value":
                element.select.by_value(value, timeout=timeout)
            elif by == "index":
                element.select.by_index(value, timeout=timeout)
            else:
                raise ElementNotFoundError(f"不支持的 select 选择方式：{by}")
        except RuntimeError as exc:
            raise ElementNotFoundError(f"{name}选项不存在：{value}") from exc
        self.page.run_js("arguments[0].blur();", element)
        return True

    def select_by_word(self, locator, value, child_locator, name=None, required=True, timeout=2):
        """非原生select下拉选择 通过文本匹配"""
        name = name or locator
        element = self._find(locator, name, required, timeout)
        if not element:
            return False

        element.click()
        for option in self.page.eles(child_locator, timeout=timeout):
            if str(getattr(option, "text", "") or "").strip() != str(value).strip():
                continue
            option.click()
            return True

        if required:
            raise ElementNotFoundError(f"{name}选项不存在：{value}")
        return False

    def get_text(self, locator, name=None, required=True, timeout=2):
        """获取元素文本。"""
        element = self._find(locator, name, required, timeout)
        if not element:
            return ""
        return getattr(element, "text", "") or ""

    def get_value(self, locator, name=None, required=True, timeout=2):
        """获取 input value。"""
        element = self._find(locator, name, required, timeout)
        if not element:
            return ""
        value = element.value
        return "" if value is None else str(value)

    def get_select_value(self, locator, name=None,by="text", required=True, timeout=2):
        """获取 select 当前选中值。"""
        element = self._find(locator, name, required, timeout)
        if not element:
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
        if not element:
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
        if not iframe:
            return None
        log(f"切换到{name or locator}")
        return DomHelper(iframe)

    def get_shadow_root(self, locator, name=None, required=True, timeout=2):
        """获取开放式 Shadow DOM 的根节点。"""
        host = self._find(locator, name, required, timeout)
        if not host:
            return None
        log(f"获取{name or locator}的 Shadow Root")
        return DomHelper(host.shadow_root)




   
    def search_select_element(self, element, value, option_locator, option_text, name=None, timeout=2):
        """在已定位的可搜索下拉框中输入筛选值并选择精确匹配的候选项。"""
        name = name or option_text
        log(f"输入{name}")
        element.click()
        element.input(value, clear=True)
        time.sleep(0.5)
        for option in self.page.eles(option_locator, timeout=timeout):
            if (option.text or "").strip() == option_text:
                log(f"选择{name}")
                option.click()
                return True
        raise ElementNotFoundError(f"{name}选项不存在：{option_text}")

    def search_select_by_first_word(
        self,
        locator,
        value,
        option_locator,
        name=None,
        required=True,
        timeout=2,
        wait_time=3
    ):
        """通过搜索框定位器搜索目标值的第一个英文单词，并选择完全匹配项。"""
        name = name or locator
        element = self._find(locator, name, required, timeout)
        if not element:
            return False

        target_text = str(value).strip()
        if not target_text:
            if required:
                raise ElementNotFoundError(f"{name}目标值为空")
            return False

        keyword_match = re.search(r"[A-Za-z]+", target_text)
        search_keyword = keyword_match.group(0) if keyword_match else target_text.split()[0]

        normalize = lambda text: re.sub(r"\s+", " ", str(text or "")).strip().casefold()

        log(f"搜索并选择{name}，搜索关键词：{search_keyword}")
        element.click()
        element.input(search_keyword, clear=True)
        time.sleep(wait_time)
        for option in self.page.eles(option_locator, timeout=timeout):
            if normalize(option.text) != normalize(target_text):
                continue
            log(f"选择{name}")
            option.click()
            self.page.run_js("arguments[0].blur();", element)
            return True

        if required:
            raise ElementNotFoundError(
                f"{name}选项不存在：{target_text}；搜索关键词：{search_keyword}"
            )
        return False





    


    def search_select(self, locator, value, child_locator, name=None, required=True, timeout=2):
        """搜索并选择"""
        name = name or locator
        element = self._find(locator, name, required, timeout)
        if not element:
            return False

        original_value = element.value
        if original_value == value:
            return True
        log(f"搜索并选择{name}")
        element.click()
        element.input(value, clear=True)
        time.sleep(1)

        child_elements = self.page.eles(child_locator, timeout=timeout)
        for child_element in child_elements:
            if value in (getattr(child_element, "text", "") or ""):
                child_element.click()
                return True

        if required:
            raise ElementNotFoundError(f"{name}选项不存在：{value}")
        return False



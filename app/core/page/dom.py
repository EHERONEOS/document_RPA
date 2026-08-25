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

    def _page_url(self) -> str:
        try:
            return str(self.page.url or "")
        except Exception:
            return "<无法获取>"

    @staticmethod
    def _state_value(element, state_name) -> str:
        try:
            return str(bool(getattr(element.states, state_name)))
        except Exception as exc:
            return f"<无法获取:{type(exc).__name__}>"

    def _element_status(self, element) -> str:
        return "，".join(
            f"{label}={self._state_value(element, state_name)}"
            for label, state_name in (
                ("有布局尺寸", "has_rect"),
                ("可见", "is_displayed"),
                ("已启用", "is_enabled"),
                ("可点击", "is_clickable"),
            )
        )

    def _operation_error(self, action, locator, name, element, exc):
        return ElementOperationError(
            f"{action}{name}失败：定位器={locator}；页面地址={self._page_url()}；"
            f"原始异常={type(exc).__name__}: {exc}；元素状态：{self._element_status(element)}"
        )

    def _perform(self, action, locator, name, element, operation):
        try:
            return operation()
        except BaseError as exc:
            raise self._operation_error(action, locator, name, element, exc) from exc

    def _find(self, locator, name=None, required=True, timeout=2):
        name = name or locator
        try:
            element = self.page.ele(locator, timeout=timeout)
        except BaseError as exc:
            raise ElementOperationError(
                f"查找{name}失败：定位器={locator}；等待={timeout}s；页面地址={self._page_url()}；"
                f"原始异常={type(exc).__name__}: {exc}"
            ) from exc
        if self._is_missing_element(element):
            if required:
                raise ElementNotFoundError(
                    f"{name}元素不存在：{locator}；等待={timeout}s；页面地址={self._page_url()}"
                )
            return False
        return element

    def click(self, locator, name=None, required=True, timeout=2):
        """点击元素。"""
        name = name or locator
        element = self._find(locator, name, required, timeout)
        if not element:
            return False
        log(f"点击{name}")
        self._perform("点击", locator, name, element, element.click)
        return True

    def click_if_clickable(self, locator, name=None, timeout=2):
        """仅在元素存在且可点击时点击，否则返回 False。"""
        name = name or locator
        element = self._find(locator, name, required=False, timeout=timeout)
        if not element:
            return False
        try:
            if not element.states.is_clickable:
                return False
            log(f"点击{name}")
            self._perform("点击", locator, name, element, element.click)
        except (CanNotClickError, NoRectError, ElementOperationError):
            return False
        return True

    def count_clickable(self, locator, timeout=2):
        """返回定位器匹配且当前处于可点击状态的元素数量。"""
        return sum(element.states.is_clickable for element in self.page.eles(locator, timeout=timeout))

    def click_first_clickable(self, locator, name=None, required=True, timeout=2):
        """点击第一个可点击元素，跳过隐藏或失去尺寸的同类元素。"""
        name = name or locator
        for element in self.page.eles(locator, timeout=timeout):
            if not element.states.is_clickable:
                continue
            try:
                log(f"点击{name}")
                self._perform("点击", locator, name, element, element.click)
                return True
            except (CanNotClickError, NoRectError, ElementOperationError):
                continue
        if required:
            raise ElementNotFoundError(f"{name}可点击元素不存在：{locator}")
        return False

    def handle_alert(self, *, accept=True, timeout=2):
        """处理 JavaScript 弹窗并返回提示文本；未出现弹窗时返回空字符串。"""
        alert_text = self.page.handle_alert(accept=accept, timeout=timeout)
        return "" if alert_text is False or alert_text is None else str(alert_text)

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

    def click_all(self, locator, name=None, required=True, timeout=2):
        """点击所有匹配元素。"""
        name = name or locator
        elements = self.page.eles(locator, timeout=timeout)
        if not elements:
            if required:
                raise ElementNotFoundError(f"{name}元素不存在：{locator}")
            return False
        log(f"点击全部{name}")
        for element in elements:
            element.click()
        return True

    def input_text(self, locator, value, name=None, required=True, timeout=2):
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
        self._perform("点击", locator, name, element, element.click)
        self._perform(
            "输入",
            locator,
            name,
            element,
            lambda: element.input(expected_value, clear=True),
        )
        if str(element.value or "") != expected_value:
            # 部分旧站点会拦截键盘事件；仅在常规输入回读失败时使用标准 DOM 事件回退。
            self.page.run_js(
                """
                const element = arguments[0];
                const value = arguments[1];
                const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), 'value');
                if (descriptor && descriptor.set) {
                    descriptor.set.call(element, value);
                } else {
                    element.value = value;
                }
                element.dispatchEvent(new Event('input', {bubbles: true}));
                element.dispatchEvent(new Event('change', {bubbles: true}));
                """,
                element,
                expected_value,
            )
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

    # def wait_eles_loaded(self, locator,any_one=False, required=True, timeout=10):
    #     """等待元素加待元素被加载到 DOM"""
    #     success =  self.page.wait.eles_loaded(locator, timeout=timeout,any_one=any_one)
    #     if required or not success:
    #         raise ElementNotFoundError(f"等待元素{locator} 加载超时")
    #     return True

import unittest
from unittest.mock import Mock, patch

from app.core.page.dom import DomHelper
from app.core.task.base_task import BaseRpaTask
from app.core.task.errors import ElementNotFoundError, ElementOperationError, FormValidationError


class ElementNameTests(unittest.TestCase):
    def test_empty_name_falls_back_to_locator_in_missing_element_error(self):
        page = Mock()
        page.ele.return_value = None

        with self.assertRaisesRegex(ElementNotFoundError, r"#shipper元素不存在：#shipper"):
            DomHelper(page).click("#shipper", name="")

    def test_fill_passes_configured_name_to_dom_helper(self):
        task = object.__new__(BaseRpaTask)
        task.content = {"shipperTitle": "ACME"}
        task.dom = Mock()

        BaseRpaTask._fill_or_select_if_present(
            task,
            "input",
            "#shp_name",
            "shipperTitle",
            name="发货人",
        )

        task.dom.input_text.assert_called_once_with(
            "#shp_name",
            "ACME",
            name="发货人",
            timeout=2,
        )

    def test_click_logs_configured_name(self):
        page = Mock()
        page.ele.return_value = Mock()

        with patch("app.core.page.dom.log") as log:
            DomHelper(page).click("#search", name="搜索按钮")

        log.assert_called_once_with("点击搜索按钮")

    def test_missing_element_error_includes_locator_timeout_and_page_url(self):
        page = Mock()
        page.url = "https://example.test/si"
        page.ele.return_value = None

        with self.assertRaisesRegex(
            ElementNotFoundError,
            r"订舱号元素不存在：#booking；等待=5s；页面地址=https://example\.test/si",
        ):
            DomHelper(page).click("#booking", name="订舱号", timeout=5)

    def test_non_rect_click_error_includes_locator_and_element_status(self):
        from DrissionPage.errors import NoRectError

        page = Mock()
        page.url = "https://example.test/si"
        element = Mock()
        element.click.side_effect = NoRectError
        element.states.has_rect = False
        element.states.is_displayed = False
        element.states.is_enabled = True
        element.states.is_clickable = False
        page.ele.return_value = element

        with self.assertRaisesRegex(
            ElementOperationError,
            r"(?s)点击卖方公司名称失败：定位器=#seq1_companyName0；页面地址=https://example\.test/si；"
            r"原始异常=NoRectError.*有布局尺寸=False.*可见=False",
        ):
            DomHelper(page).click("#seq1_companyName0", name="卖方公司名称")

    def test_click_if_clickable_skips_element_without_clickable_state(self):
        page = Mock()
        element = Mock()
        element.states.is_clickable = False
        page.ele.return_value = element

        with patch("app.core.page.dom.log") as log:
            result = DomHelper(page).click_if_clickable("#cookie", name="Cookie 同意按钮")

        self.assertFalse(result)
        element.click.assert_not_called()
        log.assert_not_called()

    def test_click_if_clickable_clicks_available_element(self):
        page = Mock()
        element = Mock()
        element.states.is_clickable = True
        page.ele.return_value = element

        with patch("app.core.page.dom.log") as log:
            result = DomHelper(page).click_if_clickable("#cookie", name="Cookie 同意按钮")

        self.assertTrue(result)
        element.click.assert_called_once_with()
        log.assert_called_once_with("点击Cookie 同意按钮")

    def test_count_clickable_ignores_hidden_elements(self):
        page = Mock()
        hidden_element = Mock()
        hidden_element.states.is_clickable = False
        visible_element = Mock()
        visible_element.states.is_clickable = True
        page.eles.return_value = [hidden_element, visible_element]

        result = DomHelper(page).count_clickable("//*[text()='Delete']")

        self.assertEqual(result, 1)

    def test_click_first_clickable_skips_hidden_element(self):
        page = Mock()
        hidden_element = Mock()
        hidden_element.states.is_clickable = False
        visible_element = Mock()
        visible_element.states.is_clickable = True
        page.eles.return_value = [hidden_element, visible_element]

        result = DomHelper(page).click_first_clickable("//*[text()='Delete']", name="删除集装箱")

        self.assertTrue(result)
        hidden_element.click.assert_not_called()
        visible_element.click.assert_called_once_with()

    def test_search_select_element_selects_exact_option(self):
        page = Mock()
        element = Mock()
        wrong_option = Mock()
        wrong_option.text = "UN | UNSPECIFIED"
        expected_option = Mock()
        expected_option.text = "UN | UNPACKED"
        page.eles.return_value = [wrong_option, expected_option]

        with patch("app.core.page.dom.time.sleep"):
            result = DomHelper(page).search_select_element(
                element,
                "UN",
                ".option",
                "UN | UNPACKED",
                "包装单位",
            )

        self.assertTrue(result)
        element.input.assert_called_once_with("UN", clear=True)
        wrong_option.click.assert_not_called()
        expected_option.click.assert_called_once_with()

    def test_validation_error_uses_configured_name(self):
        task = object.__new__(BaseRpaTask)
        task.remain_content = {"shipperTitle": "ACME"}
        task.dom = Mock()
        task.dom.get_value.return_value = "OTHER"

        with self.assertRaisesRegex(FormValidationError, "发货人 值不匹配"):
            BaseRpaTask.verify_from_value(
                task,
                "input",
                "#shp_name",
                "shipperTitle",
                name="发货人",
            )

        task.dom.get_value.assert_called_once_with("#shp_name", name="发货人")


if __name__ == "__main__":
    unittest.main()

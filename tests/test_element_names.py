import unittest
from unittest.mock import Mock, patch

from app.core.page.dom import DomHelper
from app.core.task.base_task import BaseRpaTask
from app.core.task.errors import ElementNotFoundError, FormValidationError


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

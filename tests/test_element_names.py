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

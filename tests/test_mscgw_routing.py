"""MSCGW 路由和登录骨架的离线测试。"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from app.control.dependencies import queue_manifest
from app.core.page.dom import DomHelper
from app.core.page.http import HttpHelper
from app.core.task.dispatcher import dispatch_context
from app.core.task.errors import ElementNotFoundError, LoginError
from app.core.task.router import CarrierRoute, resolve_queue_route
from app.queue.message import build_task_context
from app.spider.MSCGW import selectors
from app.spider.MSCGW.base import MscgwBase
from app.spider.MSCGW.common.login import LoginMixin
from app.spider.MSCGW.router import ROUTES
from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "message_list" / "FHT_MSCGW_SI.json"


class MscgwRoutingTests(unittest.TestCase):
    def load_template(self):
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def test_template_context_uses_registered_mscgw_route(self):
        context = build_task_context(self.load_template())

        self.assertEqual("FHT_MSCGW_SI", context.queue_name)
        self.assertEqual(("FHT", "MSC", "SI"), (
            context.customer_code,
            context.carrier_code,
            context.business_code,
        ))
        route = resolve_queue_route(context.queue_name)
        self.assertEqual("app.spider.MSCGW.router", route.router_module)

    def test_dispatcher_calls_fht_mscgw_handler(self):
        context = build_task_context(self.load_template())
        handler = Mock(return_value=True)

        with patch.dict(ROUTES, {"FHT_MSCGW_SI": CarrierRoute("FHT", "SI", handler)}):
            self.assertTrue(dispatch_context(context))

        handler.assert_called_once_with(context)

    def test_manifest_tracks_mscgw_package(self):
        manifest = queue_manifest("FHT_MSCGW_SI", PROJECT_ROOT)

        self.assertIn("app/spider/MSCGW/base.py", manifest)
        self.assertIn("app/spider/MSCGW/selectors.py", manifest)
        self.assertIn("app/spider/MSCGW/tasks/fht_mscgw_si.py", manifest)

    def test_mscgw_base_uses_login_mixin(self):
        self.assertIs(MscgwBase.login, LoginMixin.login)

    def test_fht_business_step_is_intentionally_empty(self):
        task = object.__new__(FhtMscgwSiTask)

        self.assertIsNone(task.execute_business())


class HttpHelperRequestTests(unittest.TestCase):
    @patch("app.core.page.http.requests.request")
    def test_request_forwards_request_arguments_and_returns_response(self, request):
        response = Mock()
        request.return_value = response
        helper = HttpHelper(Mock())

        result = helper.request(
            "POST",
            "http://127.0.0.1:8081/api/mscgw/login",
            json={"websiteAccount": "account", "websitePassword": "password"},
            timeout=15,
        )

        self.assertIs(response, result)
        request.assert_called_once_with(
            method="POST",
            url="http://127.0.0.1:8081/api/mscgw/login",
            params=None,
            data=None,
            json={"websiteAccount": "account", "websitePassword": "password"},
            headers=None,
            cookies=None,
            timeout=15,
        )
        response.raise_for_status.assert_called_once_with()

    @patch("app.core.page.http.requests.request", side_effect=requests.ConnectionError("offline"))
    def test_request_converts_request_errors(self, request):
        helper = HttpHelper(Mock())

        with self.assertRaisesRegex(ElementNotFoundError, "HTTP 请求失败"):
            helper.request("GET", "http://127.0.0.1:8081/health")


class MscgwLoginTests(unittest.TestCase):
    def test_login_screen_is_not_mistaken_for_authenticated_session(self):
        task = object.__new__(LoginMixin)
        task.page = SimpleNamespace(
            url=selectors.LOGIN_URL,
            ele=Mock(return_value=Mock()),
        )

        self.assertFalse(task._is_logged_in())

    def test_mymsc_page_without_authentication_controls_is_authenticated(self):
        task = object.__new__(LoginMixin)
        task.page = SimpleNamespace(
            url="https://www.mymsc.com/myMSC/shipments",
            ele=Mock(return_value=None),
        )

        self.assertTrue(task._is_logged_in())

    def test_credentials_are_required_before_any_login_form_operation(self):
        task = object.__new__(LoginMixin)
        task.website_info = {}
        task.http = Mock()

        with self.assertRaisesRegex(LoginError, "缺少网站账号或密码"):
            task._login_with_credentials()

        task.http.request.assert_not_called()

    def test_login_service_cookies_are_applied_to_browser_session(self):
        task = object.__new__(LoginMixin)
        task.website_info = {
            "websiteAccount": "account@example.test",
            "websitePassword": "test-password",
        }
        task.http = Mock()
        task.http.request.return_value.json.return_value = {
            "code": 200,
            "data": {"session": "cookie-value"},
        }
        task.page = Mock()
        task._open_home_page = Mock()
        task._is_logged_in = Mock(return_value=True)

        task._login_with_credentials()

        task.http.request.assert_called_once_with(
            "POST",
            selectors.LOGIN_API_URL,
            json={
                "websiteAccount": "account@example.test",
                "websitePassword": "test-password",
            },
            timeout=task.login_wait_seconds,
        )
        task.page.set.cookies.assert_called_once_with({"session": "cookie-value"})
        task._open_home_page.assert_called_once_with()

    def test_login_service_error_falls_back_to_browser_automation(self):
        task = object.__new__(LoginMixin)
        task.website_info = {
            "websiteAccount": "account@example.test",
            "websitePassword": "test-password",
        }
        task.http = Mock()
        task.http.request.return_value.json.return_value = {
            "code": 401,
            "message": "账号或密码错误",
        }
        task.page = Mock()
        task.logger = Mock()
        task._login_with_browser = Mock()

        task._login_with_credentials()

        task.page.set.cookies.assert_not_called()
        task._login_with_browser.assert_called_once_with(
            "account@example.test", "test-password"
        )
        task.logger.warn.assert_called_once()

    def test_cookie_login_failure_falls_back_to_browser_automation(self):
        task = object.__new__(LoginMixin)
        task.website_info = {
            "websiteAccount": "account@example.test",
            "websitePassword": "test-password",
        }
        task.http = Mock()
        task.http.request.return_value.json.return_value = {
            "code": 200,
            "data": {"session": "cookie-value"},
        }
        task.page = Mock()
        task.logger = Mock()
        task._open_home_page = Mock()
        task._is_logged_in = Mock(return_value=False)
        task._login_with_browser = Mock()

        task._login_with_credentials()

        task.page.set.cookies.assert_called_once_with({"session": "cookie-value"})
        task._login_with_browser.assert_called_once_with(
            "account@example.test", "test-password"
        )

    def test_native_event_dom_input_writes_and_verifies_value(self):
        password_element = SimpleNamespace(value="")
        page = Mock()
        page.ele.return_value = password_element

        def apply_password(script, element, value):
            self.assertIn("InputEvent", script)
            self.assertIn("descriptor.set.call", script)
            element.value = value

        page.run_js.side_effect = apply_password
        self.assertTrue(
            DomHelper(page).input_text_with_native_events(
                selectors.IDENTITY_PASSWORD,
                "test-password",
                "MSC 登录密码",
                timeout=10,
            )
        )

        page.ele.assert_called_once_with(
            selectors.IDENTITY_PASSWORD,
            timeout=10,
        )
        self.assertEqual("test-password", password_element.value)

    def test_identity_form_uses_javascript_click_after_b2c_button_move(self):
        submit_button = Mock()
        task = object.__new__(LoginMixin)
        task.dom = Mock()
        task.dom._find.return_value = submit_button
        task.logger = Mock()

        task._submit_identity_form()

        task.dom._find.assert_called_once_with(
            selectors.IDENTITY_SUBMIT,
            "MSC 登录提交按钮",
            timeout=10,
        )
        submit_button.click.assert_called_once_with(by_js=True, timeout=10)

    def test_all_nonempty_b2c_error_messages_are_reported(self):
        task = object.__new__(LoginMixin)
        task.page = SimpleNamespace(
            eles=Mock(return_value=[
                SimpleNamespace(text=""),
                SimpleNamespace(text="The username or password is invalid."),
            ]),
        )

        with self.assertRaisesRegex(LoginError, "username or password is invalid"):
            task._raise_if_identity_error()


if __name__ == "__main__":
    unittest.main()

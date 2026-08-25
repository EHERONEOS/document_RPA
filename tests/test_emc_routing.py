import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.control.dependencies import queue_manifest
from app.core.page.dom import DomHelper
from app.core.task.dispatcher import dispatch_context
from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError
from app.core.task.router import CarrierRoute, resolve_queue_route
from app.queue.message import build_task_context
from app.spider.EMC import selectors
from app.spider.EMC.base import EmcBase
from app.spider.EMC.common.emc_si_base import EmcSiBaseTask
from app.spider.EMC.common.login import LoginMixin
from app.spider.EMC.router import ROUTES
from app.spider.EMC.tasks.asy_emc_si import AsyEmcSiTask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "message_list" / "ASY_EMC_SI.json"


class EmcRoutingTests(unittest.TestCase):
    def load_template(self):
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def test_template_context_uses_registered_emc_route(self):
        context = build_task_context(self.load_template())

        self.assertEqual("ASY_EMC_SI", context.queue_name)
        self.assertEqual(("ASY", "EMC", "SI"), (
            context.customer_code,
            context.carrier_code,
            context.business_code,
        ))
        route = resolve_queue_route(context.queue_name)
        self.assertEqual("app.spider.EMC.router", route.router_module)

    def test_dispatcher_calls_asy_emc_handler(self):
        context = build_task_context(self.load_template())
        handler = Mock(return_value=True)

        with patch.dict(ROUTES, {"ASY_EMC_SI": CarrierRoute("ASY", "SI", handler)}):
            self.assertTrue(dispatch_context(context))

        handler.assert_called_once_with(context)

    def test_asy_task_uses_emc_common_flow_and_login_mixin(self):
        self.assertTrue(issubclass(AsyEmcSiTask, EmcSiBaseTask))
        self.assertIs(EmcBase.login, LoginMixin.login)

    def test_manifest_tracks_emc_package(self):
        manifest = queue_manifest("ASY_EMC_SI", PROJECT_ROOT)

        self.assertIn("app/spider/EMC/base.py", manifest)
        self.assertIn("app/spider/EMC/selectors.py", manifest)
        self.assertIn("app/spider/EMC/tasks/asy_emc_si.py", manifest)


class EmcSiPolicyTests(unittest.TestCase):
    def make_task(self, *, rpa_operate="", role="AISHIYI"):
        task = object.__new__(AsyEmcSiTask)
        task.context = SimpleNamespace(task={"rpaOperate": rpa_operate})
        task.customer_role = role
        task.dom = Mock()
        task.dom.handle_alert.return_value = "保存成功"
        task.result_save_type = 1
        return task

    def test_explicit_save_draft_overrides_submit_role(self):
        task = self.make_task(rpa_operate="SAVE_DRAFT", role="AISHIYI")

        task._save_or_submit()

        self.assertEqual(1, task.result_save_type)
        self.assertEqual(1, task.dom.click.call_count)
        self.assertIn("保存草稿", task.dom.click.call_args.args[1])

    def test_submit_direct_overrides_non_submit_role(self):
        task = self.make_task(rpa_operate="SUBMIT_DIRECT", role="OTHER")
        task.dom.handle_alert.return_value = "提交成功"

        task._save_or_submit()

        self.assertEqual(0, task.result_save_type)
        self.assertIn("提交", task.dom.click.call_args.args[1])

    def test_unknown_nonempty_template_field_is_rejected(self):
        task = object.__new__(AsyEmcSiTask)
        task.content = {"bookingNo": "BKG", "unsupported": "value"}

        with self.assertRaisesRegex(Exception, "不支持字段.*unsupported"):
            task._validate_known_top_level_fields()

    def test_template_content_fields_are_accepted_by_contract(self):
        task = object.__new__(AsyEmcSiTask)
        template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        task.content = template["content"]

        task._validate_known_top_level_fields()

    def test_sequences_require_filing_by(self):
        task = object.__new__(AsyEmcSiTask)
        task.context = SimpleNamespace(remain_content={})
        task.content = {"seqs": [{"commodities": []}]}

        with self.assertRaisesRegex(Exception, "seqs.*Filling by"):
            task._fill_filing_information()

    @patch("app.spider.EMC.common.emc_si_base.SessionPage")
    def test_official_draft_download_reuses_page_cookies(self, session_page_class):
        session_page = Mock()
        session_page.response = SimpleNamespace(
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.7 test",
        )
        session_page_class.return_value = session_page
        task = object.__new__(AsyEmcSiTask)
        task.page = Mock()
        task.page.cookies.return_value = [{"name": "session", "value": "value"}]

        with tempfile.TemporaryDirectory() as download_dir:
            task.browser_manager = SimpleNamespace(settings=SimpleNamespace(download_dir=download_dir))
            task.context = SimpleNamespace(queue_name="ASY_EMC_SI", rpa_message_id="message-1")

            output_path = task._download_official_draft_pdf("aio", "doc", "EGLV123")

            self.assertEqual(b"%PDF-1.7 test", output_path.read_bytes())

        session_page.set.cookies.assert_called_once_with([{"name": "session", "value": "value"}])
        session_page.close.assert_called_once()


class EmcLoginOtpTests(unittest.TestCase):
    def make_login(self, role, has_otp_page):
        task = object.__new__(LoginMixin)
        task.context = SimpleNamespace(customer_role=role)
        task.page = Mock()
        task.page.eles.return_value = [Mock()] if has_otp_page else []
        task.dom = Mock()
        task.website_info = {"emailAccount": "otp@example.test", "emailPassword": "secret"}
        return task

    @patch("app.spider.EMC.common.login.read_latest_otp")
    def test_email_otp_is_not_read_without_otp_page(self, read_latest_otp):
        task = self.make_login("FULI", has_otp_page=False)

        task._complete_email_otp_if_required()

        read_latest_otp.assert_not_called()

    def test_login_status_accepts_a_page_readiness_timeout(self):
        task = object.__new__(LoginMixin)
        task.page = Mock()
        task.page.eles.return_value = [Mock()]

        self.assertTrue(task._is_logged_in(timeout=10))

        task.page.eles.assert_called_once_with("x://*[@id='LogoUserInfo']", timeout=10)

    @patch("app.spider.EMC.common.login.os.getenv", return_value="imap.example.test")
    @patch("app.spider.EMC.common.login.read_latest_otp", return_value="654321")
    def test_email_otp_is_read_for_configured_role_on_otp_page(self, read_latest_otp, getenv):
        task = self.make_login("FULI", has_otp_page=True)

        task._complete_email_otp_if_required()

        read_latest_otp.assert_called_once_with(
            "imap.example.test",
            "otp@example.test",
            "secret",
            subject_marker="Verification code",
        )
        self.assertEqual(6, task.dom.input_text.call_count)
        task.dom.click.assert_called_once()


class EmcPageNavigationTests(unittest.TestCase):
    def test_menu_navigation_does_not_click_hidden_contact_entry(self):
        task = object.__new__(AsyEmcSiTask)
        task.si_url = "https://example.test/si"
        task.page = SimpleNamespace(url="https://example.test/home", wait=Mock())
        task.dom = Mock()
        task.dom.click_if_clickable.return_value = True

        task._open_shipping_instruction()

        task.dom.click_if_clickable.assert_called_once()
        self.assertIn("提单资料指示", task.dom.click.call_args.args[1])

    def test_non_rect_clickable_element_is_skipped(self):
        class NoRectStates:
            @property
            def is_clickable(self):
                from DrissionPage.errors import NoRectError

                raise NoRectError

        page = Mock()
        page.ele.return_value = SimpleNamespace(states=NoRectStates())

        self.assertFalse(DomHelper(page).click_if_clickable("x://hidden", "隐藏元素"))

    def test_input_falls_back_to_dom_events_when_keyboard_input_is_ignored(self):
        page = Mock()
        element = Mock()
        element.value = ""
        page.ele.return_value = element

        self.assertTrue(DomHelper(page).input_text("x://input", "142652346611", "订舱号"))

        element.input.assert_called_once_with("142652346611", clear=True)
        fallback_script = page.run_js.call_args_list[0].args[0]
        self.assertIn("dispatchEvent", fallback_script)


class EmcSearchResultTests(unittest.TestCase):
    class ResultElement:
        def __init__(self, text=""):
            self.text = text
            self.clicked = False

        def click(self):
            self.clicked = True

    class ResultRow:
        def __init__(self, booking_no, status):
            self.booking = EmcSearchResultTests.ResultElement(booking_no)
            self.status = EmcSearchResultTests.ResultElement(status)
            self.split_bill = EmcSearchResultTests.ResultElement()

        def ele(self, locator, timeout=0):
            elements = {
                selectors.SEARCH_RESULT_BOOKING_NO: self.booking,
                selectors.SEARCH_RESULT_STATUS: self.status,
                selectors.SEARCH_RESULT_SPLIT_BILL: self.split_bill,
            }
            return elements.get(locator)

    def make_task(self, rows, booking_no="142652346611"):
        task = object.__new__(AsyEmcSiTask)
        task.content = {"bookingNo": booking_no, "blankBill": False, "splitBill": False}
        task.page = SimpleNamespace(
            eles=Mock(return_value=rows),
            wait=SimpleNamespace(ele_displayed=Mock(return_value=True)),
        )
        task.dom = Mock()
        task.dom.get_text.return_value = ""
        task._dismiss_never_show_tip = Mock()
        task._input_and_verify = Mock()
        task._raise_for_alert = Mock()
        task._done = Mock()
        return task

    def test_search_uses_the_row_matching_the_requested_booking_number(self):
        first_row = self.ResultRow("142652342836", "Processing")
        target_row = self.ResultRow("142652346611", "Waiting for Creating")
        task = self.make_task([first_row, target_row])

        task._search_shipping_instruction()

        self.assertFalse(first_row.status.clicked)
        self.assertTrue(target_row.status.clicked)
        task.page.wait.ele_displayed.assert_called_once_with(selectors.SHIPPER_INPUT, timeout=30)
        task._done.assert_called_once_with("bookingNo", "blankBill", "splitBill")

    def test_search_reports_when_the_requested_booking_number_is_absent(self):
        task = self.make_task([self.ResultRow("142652342836", "Processing")])

        with self.assertRaisesRegex(BusinessError, "未查询到订舱号 142652346611"):
            task._search_shipping_instruction()

    def test_create_si_reports_when_the_form_does_not_load(self):
        task = self.make_task([])
        task.page.wait.ele_displayed.return_value = False

        with self.assertRaisesRegex(ElementNotFoundError, "创建 SI 后表单未在 30 秒内加载"):
            task._wait_for_shipping_instruction_form()


class EmcInputVerificationTests(unittest.TestCase):
    def make_task(self, actual_value):
        task = object.__new__(AsyEmcSiTask)
        task.dom = Mock()
        task.dom.get_value.return_value = actual_value
        return task

    def test_numeric_input_accepts_equivalent_decimal_precision(self):
        task = self.make_task("20381")

        task._input_and_verify("x://weight", "20381.000", "ENS 品名毛重", required=True, numeric=True)

        task.dom.input_text.assert_called_once_with("x://weight", "20381.000", "ENS 品名毛重", timeout=5)

    def test_text_input_keeps_strict_precision_comparison(self):
        task = self.make_task("20381")

        with self.assertRaises(FormValidationError):
            task._input_and_verify("x://weight", "20381.000", "普通文本", required=True)


class EmcVgmTests(unittest.TestCase):
    def make_task(self, checked=True, has_rect=True):
        toggle = SimpleNamespace(states=SimpleNamespace(is_checked=checked))
        responsible = SimpleNamespace(states=SimpleNamespace(has_rect=has_rect))

        def elements(locator, timeout=0):
            if locator == selectors.VGM_TOGGLE:
                return [toggle]
            if locator == selectors.VGM_RESPONSIBLE_PARTY:
                return [responsible]
            return []

        task = object.__new__(AsyEmcSiTask)
        task.page = SimpleNamespace(
            eles=Mock(side_effect=elements),
        )
        task.dom = Mock()
        return task, toggle

    def test_enables_vgm_only_when_checkbox_is_not_selected(self):
        task, toggle = self.make_task(checked=False)
        task.dom.click.side_effect = lambda *args, **kwargs: setattr(toggle.states, "is_checked", True)

        task._enable_vgm()

        task.dom.click.assert_called_once_with(selectors.VGM_TOGGLE, "EMC VGM 开关", timeout=3)

    def test_does_not_toggle_an_enabled_vgm_checkbox_off(self):
        task, _ = self.make_task(checked=True)

        task._enable_vgm()

        task.dom.click.assert_not_called()

    def test_reports_when_vgm_responsible_party_does_not_display(self):
        task, _ = self.make_task(checked=True, has_rect=False)

        with patch("app.spider.EMC.common.emc_si_base.time.monotonic", side_effect=(0, 1, 15)):
            with patch("app.spider.EMC.common.emc_si_base.time.sleep"):
                with self.assertRaisesRegex(ElementNotFoundError, "VGM 开启后责任方字段未在 15 秒内显示"):
                    task._enable_vgm()


class EmcPaymentTypeTests(unittest.TestCase):
    def test_compare_mode_keeps_the_official_default_payment_type(self):
        task = object.__new__(AsyEmcSiTask)
        task.content = {"paymentType": "Collect", "paymentTypeOfficialMode": "比对"}
        task.logger = Mock()
        task._done = Mock()

        task._finish_metadata_fields()

        task.logger.info.assert_called_once()
        task._done.assert_any_call("paymentType")
        task._done.assert_any_call("paymentTypeOfficialMode")


if __name__ == "__main__":
    unittest.main()

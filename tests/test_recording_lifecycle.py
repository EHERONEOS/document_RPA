import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from app.core.browser.manager import BrowserManager
from app.core.browser.options import BrowserOptions
from app.core.page.recorder import Recorder
from app.core.task.base_task import BaseRpaTask
from app.core.task.context import TaskContext
from app.spider.HPL.base import HplBase
from capturesdk import CaptureSDKError


def build_context(enable_result_publish=True):
    return TaskContext(
        task={},
        task_id="task-1",
        queue_name="QTCT_ZIM_SI",
        rpa_message_id="message-1",
        customer_code="QTCT",
        carrier_code="ZIM",
        business_code="SI",
        website_info={},
        content={},
        remain_content={},
        enable_result_publish=enable_result_publish,
    )


class SuccessfulTask(BaseRpaTask):
    carrier_code = "ZIM"
    enable_record = True

    def __init__(self, *args, **kwargs):
        self.events = []
        super().__init__(*args, **kwargs)

    def login(self):
        self.events.append("login")

    def execute_business(self):
        self.events.append("business")


class RecordingLifecycleTests(unittest.TestCase):
    def test_browser_manager_skips_proxy_when_proxy_is_disabled(self):
        chromium_options = Mock()
        chromium_options_class = Mock(return_value=chromium_options)
        browser = Mock()
        browser.latest_tab = Mock()
        drission_page = SimpleNamespace(
            ChromiumOptions=chromium_options_class,
            Chromium=Mock(return_value=browser),
        )
        task = SimpleNamespace(
            use_proxy=False,
            get_browser_proxy=Mock(return_value="192.168.40.240:42150"),
        )
        context = SimpleNamespace(queue_name="FHT_HPL_SI", rpa_message_id="message-1")

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = BrowserManager.__new__(BrowserManager)
            manager.browser_lease = None
            manager.account_session_coordinator = None
            manager.build_options = Mock(
                return_value=BrowserOptions(
                    port=9222,
                    user_data_path=f"{temp_dir}/hpl-profile",
                    download_path=f"{temp_dir}/downloads",
                )
            )

            with (
                patch("app.core.browser.manager.enable_detached_chromium_launch"),
                patch("app.core.browser.manager.ensure_browser_window_ready"),
                patch.dict(sys.modules, {"DrissionPage": drission_page}),
            ):
                manager.start(context, task)

        task.get_browser_proxy.assert_not_called()
        chromium_options.set_proxy.assert_not_called()

    def test_browser_manager_sets_proxy_directly_on_chromium_options(self):
        chromium_options = Mock()
        chromium_options_class = Mock(return_value=chromium_options)
        browser = Mock()
        browser.latest_tab = Mock()
        chromium_class = Mock(return_value=browser)
        drission_page = SimpleNamespace(
            ChromiumOptions=chromium_options_class,
            Chromium=chromium_class,
        )
        task = SimpleNamespace(
            incognito=False,
            wait_page_load=False,
            use_proxy=True,
            get_browser_proxy=Mock(return_value="192.168.40.240:42150"),
        )
        context = SimpleNamespace(queue_name="FHT_HPL_SI", rpa_message_id="message-1")

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = BrowserManager.__new__(BrowserManager)
            manager.browser_lease = {
                "port": 9222,
                "user_data_path": f"{temp_dir}/hpl-profile",
            }
            manager.settings = SimpleNamespace(download_dir=f"{temp_dir}/downloads")
            manager.account_session_coordinator = None

            with (
                patch("app.core.browser.manager.enable_detached_chromium_launch"),
                patch("app.core.browser.manager.ensure_browser_window_ready"),
                patch.dict(sys.modules, {"DrissionPage": drission_page}),
            ):
                manager.start(context, task)

        chromium_options.set_proxy.assert_called_once_with("192.168.40.240:42150")

    def test_browser_manager_build_options_does_not_request_task_proxy(self):
        manager = BrowserManager.__new__(BrowserManager)
        manager.browser_lease = {"port": 9222, "user_data_path": "/tmp/hpl-profile"}
        manager.settings = SimpleNamespace(download_dir="/tmp/downloads")
        task = SimpleNamespace(
            incognito=False,
            wait_page_load=False,
            use_proxy=True,
            get_browser_proxy=Mock(return_value="192.168.40.240:42150"),
        )
        context = SimpleNamespace(queue_name="FHT_HPL_SI", rpa_message_id="message-1")

        options = manager.build_options(context, task)

        self.assertFalse(hasattr(options, "proxy"))
        task.get_browser_proxy.assert_not_called()

    def test_hpl_uses_first_proxy_data_for_browser_startup(self):
        task = HplBase.__new__(HplBase)
        task.getProxyData = Mock(return_value=[b"192.168.40.240:42150"])

        self.assertEqual(task.get_browser_proxy(), "192.168.40.240:42150")

    def test_cookie_storage_uses_native_redis_client_methods(self):
        cookies_redis = Mock()
        proxy_redis = Mock()

        with patch(
            "app.core.task.base_task.get_redis_db_client",
            side_effect=[cookies_redis, proxy_redis],
        ) as get_redis_db_client:
            task = SuccessfulTask(
                build_context(),
                browser_manager=Mock(),
                notifier=Mock(),
                publisher=Mock(),
                oss_client=Mock(),
            )

        self.assertIs(task.util_redis, cookies_redis)
        self.assertIs(task.redis_client, proxy_redis)
        self.assertEqual(
            get_redis_db_client.call_args_list,
            [call(BaseRpaTask.REDIS_MAIN), call(BaseRpaTask.REDIS_HEART_BEAT)],
        )

        task.page = Mock()
        task.page.cookies.return_value = [{"name": "session", "value": "abc"}]
        task.save_cookies("cookies:ZIM_account")
        cookies_redis.set.assert_called_once_with(
            "cookies:ZIM_account",
            json.dumps(task.page.cookies.return_value, ensure_ascii=False),
        )

        cookies_redis.get.return_value = json.dumps(task.page.cookies.return_value)
        task.set_page_cookies("cookies:ZIM_account")
        cookies_redis.get.assert_called_once_with("cookies:ZIM_account")
        task.page.set.cookies.assert_called_once_with(task.page.cookies.return_value)

    def test_recorder_rejects_ambiguous_browser_windows(self):
        page = Mock()
        page.process_id = 123
        client = Mock()
        client.wait_for_browser_hwnd.side_effect = CaptureSDKError("multiple browser windows")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.core.page.recorder.CaptureSDKClient", return_value=client):
                recorder = Recorder(page, record_dir=temp_dir, queue_name="QTCT_ZIM_SI")
                with self.assertRaisesRegex(CaptureSDKError, "multiple browser windows"):
                    recorder.start()

        client.wait_for_browser_hwnd.assert_called_once_with(123)

    def test_recorder_restores_browser_window_before_starting_capture(self):
        page = Mock()
        page.process_id = 123
        client = Mock()
        client.wait_for_browser_hwnd.return_value = 456
        client.start.return_value = Mock(is_running=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("app.core.page.recorder.CaptureSDKClient", return_value=client),
                patch("app.core.page.recorder.ensure_browser_window_ready") as restore_window,
            ):
                recorder = Recorder(page, record_dir=temp_dir, queue_name="QTCT_ZIM_SI")
                recorder.start()

        restore_window.assert_called_once_with(hwnd=456)
        client.start.assert_called_once()

    def test_recording_starts_after_login_and_is_returned_with_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "QTCT_ZIM_SI_20260728_160000_001.mp4"
            video_path.touch()
            browser_manager = Mock()
            browser_manager.start.return_value = object()
            publisher = Mock()
            oss_client = Mock()
            oss_client.oss_upload.return_value = {
                "objectName": "records/video.mp4",
                "filename": video_path.name,
            }
            recorder = Mock()
            recorder.stop.return_value = video_path

            task = SuccessfulTask(
                build_context(),
                browser_manager=browser_manager,
                notifier=Mock(),
                publisher=publisher,
                oss_client=oss_client,
            )
            recorder.start.side_effect = lambda: task.events.append("recording")

            with (
                patch("app.core.task.base_task.platform.system", return_value="Windows"),
                patch("app.core.task.base_task.Recorder", return_value=recorder),
            ):
                self.assertTrue(task.run())

            recorder.start.assert_called_once_with()
            recorder.stop.assert_called_once_with()
            oss_client.oss_upload.assert_called_once_with(video_path, is_remove=True)
            self.assertEqual(task.events, ["login", "recording", "business"])
            result = publisher.publish_result.call_args.args[0]
            self.assertEqual(result.executeRecordFiles[0]["files"][0]["fileObjectName"], "records/video.mp4")

    def test_recording_upload_failure_does_not_block_success_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "QTCT_ZIM_SI_20260728_160000_001.mp4"
            video_path.touch()
            browser_manager = Mock()
            browser_manager.start.return_value = object()
            publisher = Mock()
            oss_client = Mock()
            oss_client.oss_upload.side_effect = RuntimeError("OSS unavailable")
            recorder = Mock()
            recorder.stop.return_value = video_path

            task = SuccessfulTask(
                build_context(),
                browser_manager=browser_manager,
                notifier=Mock(),
                publisher=publisher,
                oss_client=oss_client,
            )

            with (
                patch("app.core.task.base_task.platform.system", return_value="Windows"),
                patch("app.core.task.base_task.Recorder", return_value=recorder),
            ):
                self.assertTrue(task.run())

            result = publisher.publish_result.call_args.args[0]
            self.assertTrue(result.success)
            self.assertEqual(result.executeRecordFiles, [])

    def test_recording_requires_result_publish(self):
        browser_manager = Mock()
        browser_manager.start.return_value = object()
        publisher = Mock()

        task = SuccessfulTask(
            build_context(enable_result_publish=False),
            browser_manager=browser_manager,
            notifier=Mock(),
            publisher=publisher,
            oss_client=Mock(),
        )

        with patch("app.core.task.base_task.Recorder") as recorder_class:
            self.assertTrue(task.run())

        recorder_class.assert_not_called()
        publisher.publish_result.assert_not_called()

    def test_recording_is_skipped_outside_windows(self):
        browser_manager = Mock()
        browser_manager.start.return_value = object()
        publisher = Mock()
        task = SuccessfulTask(
            build_context(),
            browser_manager=browser_manager,
            notifier=Mock(),
            publisher=publisher,
            oss_client=Mock(),
        )

        with (
            patch("app.core.task.base_task.platform.system", return_value="Linux"),
            patch("app.core.task.base_task.Recorder") as recorder_class,
        ):
            self.assertTrue(task.run())

        recorder_class.assert_not_called()
        result = publisher.publish_result.call_args.args[0]
        self.assertEqual(result.executeRecordFiles, [])


if __name__ == "__main__":
    unittest.main()

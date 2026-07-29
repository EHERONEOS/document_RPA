import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.core.page.recorder import Recorder
from app.core.task.base_task import BaseRpaTask
from app.core.task.context import TaskContext
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

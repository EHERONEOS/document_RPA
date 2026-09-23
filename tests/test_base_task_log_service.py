"""T2.5/T2.6/T2.8：base_task 终态上报四要素 + 记录文件降级链 + 失败截图完整 url。

不启动浏览器：用 fake browser_manager 让 run() 走异常路径，
验证 finally 中 finish_execution 拿到 status/remark/imgUrl/文件四要素。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.integrations.file_storage import infer_media_type
from app.core.logging import log_session
from app.core.logging.log_session import execution_log_session
from app.core.task.base_task import BaseRpaTask
from app.core.task.context import TaskContext


class FakeReportClient:
    """捕获上报调用的假客户端（与 log_session 会话协议对齐）。"""

    def __init__(self, create_ok=True):
        self.create_ok = create_ok
        self.created_payloads = []
        self.logs = []
        self.finish_calls = []

    def create_execution(self, payload):
        self.created_payloads.append(payload)
        return 42 if self.create_ok else None

    def enqueue(self, **kwargs):
        self.logs.append(kwargs)

    def finish_execution(self, *, execution_id, status, remark="", fail_img_url="", record_files=None):
        self.finish_calls.append(
            {
                "executionId": execution_id,
                "status": status,
                "remark": remark,
                "failImgUrl": fail_img_url,
                "recordFiles": list(record_files or []),
            }
        )


class FakeOss:
    """可控的 OssClient 替身。"""

    def __init__(self, fail=False, response=None):
        self.fail = fail
        self.response = response or {}
        self.calls = []

    def oss_upload(self, file_path, is_remove=True):
        self.calls.append((str(file_path), is_remove))
        if self.fail:
            raise RuntimeError("OSS 不可用")
        return dict(self.response)


class FakeFileStorage:
    """按文件名动态生成 LAN url 的假局域网上传。"""

    def __init__(self, base="http://lan"):
        self.base = base
        self.calls = []

    def upload_lan(self, file_path):
        self.calls.append(str(file_path))
        name = Path(file_path).name
        return {"url": f"{self.base}/{name}", "fileName": name, "fileSize": 2048}


class FakeBrowserManager:
    def start(self, context, task):
        raise RuntimeError("浏览器启动失败（测试模拟异常路径）")


class FakeRecorder:
    def __init__(self, path):
        self.path = path

    def stop(self):
        return self.path


def _make_task(tmp_path, runtime_mode="queue", enable_result_publish=True):
    context = TaskContext(
        task={},
        task_id="1",
        queue_name="QTCT_ZIM_SI",
        rpa_message_id="MSG-T25",
        customer_code="QTCT",
        carrier_code="ZIM",
        business_code="SI",
        website_info={"id": "zim"},
        content={"jobNo": "J1"},
        remain_content={},
        runtime_mode=runtime_mode,
        enable_notify=False,  # 不触发通知，保持单测聚焦
        enable_result_publish=enable_result_publish,
    )
    return context


def _make_task_with_fake_report(monkeypatch, tmp_path, runtime_mode="queue"):
    """构造 BaseRpaTask，并把日志上报替换为假客户端。"""
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "true")
    client = FakeReportClient()
    monkeypatch.setattr(log_session, "get_report_client", lambda: client)

    fake_redis = lambda index: object()  # noqa: E731 - 避免 Redis 连接
    monkeypatch.setattr("app.core.task.base_task.get_redis_db_client", fake_redis)

    # 结果回传关闭：本测试聚焦 run() finally 的日志服务终态上报，不触发真实回传
    context = _make_task(tmp_path, runtime_mode=runtime_mode, enable_result_publish=False)
    oss = FakeOss(response={"objectName": "rpa/a.png", "filename": "a.png", "url": "http://oss/a.png"})
    task = BaseRpaTask(
        context,
        browser_manager=FakeBrowserManager(),
        notifier=object(),
        publisher=object(),
        oss_client=oss,
        file_storage=FakeFileStorage(),
    )
    return task, client, oss


def test_run_finally_reports_finish_with_four_elements(monkeypatch, tmp_path):
    """异常路径走 run() finally：status/remark/imgUrl/文件 四要素正确（T2.5 验收）。

    真实链路是 consumer 的 execution_log_session 包住 dispatch→run()，
    测试里同样先开会话再 run()，finish 才有绑定的上下文。
    """
    task, client, _ = _make_task_with_fake_report(monkeypatch, tmp_path)
    # 预置已采集的记录文件（模拟业务截图/录屏上传后状态）
    task.log_record_files = [
        {"type": "SCREEN_RECORDING_FILE", "mediaType": "VIDEO", "fileName": "f.mp4",
         "url": "http://lan/f.mp4", "storage": "LAN", "fileSize": 2048},
    ]
    task.fail_img_url = "http://oss/fail.png"

    with execution_log_session(task.context):
        success = task.run()
    assert success is False  # 异常路径
    assert len(client.finish_calls) == 1  # run() 的终态上报；会话退出不再重复
    call = client.finish_calls[0]
    assert call["status"] == "FAILED"
    assert "浏览器启动失败" in call["remark"]
    assert call["failImgUrl"] == "http://oss/fail.png"
    assert call["recordFiles"][0]["url"] == "http://lan/f.mp4"


def test_run_local_mode_reports_nothing(monkeypatch, tmp_path):
    """local 模式（local_runner 双保险）：run() 不产生任何上报。"""
    task, client, _ = _make_task_with_fake_report(monkeypatch, tmp_path, runtime_mode="local")
    task.run()
    assert client.finish_calls == [] and client.created_payloads == []


def test_error_screenshot_records_full_url(monkeypatch, tmp_path):
    """OSS 失败 → 局域网兜底；fail_img_url 记录完整地址，TaskResult.img 仍为空串。"""
    task, _, oss = _make_task_with_fake_report(monkeypatch, tmp_path)
    oss.fail = True
    task.screenshot = type(
        "FakeScreenshot", (), {"page_shot": lambda *a, **kw: str(tmp_path / "shot.png")}
    )()
    (tmp_path / "shot.png").write_bytes(b"png")

    result_img = task._upload_error_screenshot()
    assert result_img == ""  # objectName 为空（OSS 失败）
    assert task.fail_img_url == "http://lan/shot.png"  # 完整地址来自 LAN 上传响应


def test_business_record_files_fallback_chain(monkeypatch, tmp_path):
    """业务文件 OSS 失败 → LAN 记录进日志服务；OSS 成功 → 分组 + OSS 记录。"""
    task, _, oss = _make_task_with_fake_report(monkeypatch, tmp_path)
    shot = tmp_path / "s1.png"
    shot.write_bytes(b"png")

    # 1) OSS 失败 → 走 LAN：不进结果协议分组，仅进日志服务记录
    oss.fail = True
    task.business_record_files = [("SUBMIT_RESULT_SCREENSHOT", str(shot))]
    grouped = task._collect_business_record_files()
    assert grouped == []
    assert len(task.log_record_files) == 1
    entry = task.log_record_files[0]
    assert entry["storage"] == "LAN" and entry["url"] == "http://lan/s1.png"
    assert entry["mediaType"] == "IMAGE"

    # 2) OSS 成功 → 结果协议分组照旧 + 日志服务记 OSS 完整地址
    oss.fail = False
    task.log_record_files = []
    grouped = task._collect_business_record_files()
    assert grouped[0]["files"][0]["fileObjectName"] == "rpa/a.png"
    entry = task.log_record_files[0]
    assert entry["storage"] == "OSS" and entry["url"] == "http://oss/a.png"


def test_infer_media_type():
    assert infer_media_type("a.MP4") == "VIDEO"
    assert infer_media_type(Path("b.mov")) == "VIDEO"
    assert infer_media_type("c.png") == "IMAGE"
    assert infer_media_type("d.jpg") == "IMAGE"

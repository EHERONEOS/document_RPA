"""T2.3/T2.8：LogReportClient 降级与攒批（对照设计 §6.2 / §10 单测建议）。"""

from __future__ import annotations

import pytest
import requests

from app.core.logging import report_client
from app.core.logging.report_client import LogReportClient, reset_report_client


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self.payload = payload or {"code": 0, "message": "ok", "data": {}}
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"HTTP {self.status}")

    def json(self):
        return self.payload


@pytest.fixture()
def enabled_env(monkeypatch):
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "true")
    monkeypatch.setenv("RPA_LOG_SERVICE_URL", "http://log-service.local")
    monkeypatch.setenv("RPA_LOG_SERVICE_TOKEN", "t-1")
    reset_report_client()
    yield
    reset_report_client()


def test_disabled_client_never_sends(monkeypatch):
    monkeypatch.delenv("RPA_LOG_SERVICE_ENABLED", raising=False)
    monkeypatch.delenv("RPA_LOG_SERVICE_URL", raising=False)
    reset_report_client()
    client = LogReportClient()
    assert client.enabled is False

    class _BoomSession:
        def post(self, *args, **kwargs):
            raise AssertionError("未开启时不应发起任何 HTTP 请求")

    client._session = _BoomSession()
    client.create_execution({"rpaMessageId": "M"})  # no-op
    client.enqueue(1, 1, "INFO", "x")  # no-op
    client.finish_execution(execution_id=1, status="SUCCESS")  # no-op
    client.flush()  # no-op


def test_unreachable_server_does_not_raise_or_block(enabled_env):
    """服务不可达：enqueue 不阻塞、flush 不抛错（§6.2 降级）。"""
    monkey_patch_env = enabled_env  # noqa: F841 - fixture 已设置环境
    client = LogReportClient()
    client._session = requests.Session()
    # 指向必然拒绝连接的保留端口
    client._session.post = lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("refused"))
    for seq in range(5):
        client.enqueue(execution_id=7, seq=seq, level="INFO", message=f"m{seq}")
    client.flush()  # 不抛错
    assert client._queue.empty()  # 队列已排空（失败即丢弃并 WARN）


def test_batching_groups_by_execution(enabled_env):
    client = LogReportClient()
    calls = []

    def fake_post(path, json=None, headers=None, timeout=None):
        calls.append((path, json))
        return FakeResponse({"code": 0, "data": {"executionId": 1}})

    client._session.post = fake_post

    assert client.create_execution({"rpaMessageId": "M"}) == 1
    for seq in range(120):  # 执行1：120 条
        client.enqueue(execution_id=1, seq=seq, level="INFO", message=f"a{seq}")
    for seq in range(30):  # 执行2：30 条
        client.enqueue(execution_id=2, seq=seq, level="ERROR", message=f"b{seq}")
    client.flush()

    log_calls = [(p, b) for p, b in calls if p.endswith("/logs/batch")]
    sizes = [len(b["logs"]) for _, b in log_calls]
    assert sum(sizes) == 150
    assert all(size <= 50 for size in sizes)  # 攒批上限 50
    for _, body in log_calls:  # 单个批次不混执行
        execution_ids = {body["executionId"]}
        assert len(execution_ids) == 1
    exec1_total = sum(len(b["logs"]) for _, b in log_calls if b["executionId"] == 1)
    assert exec1_total == 120


def test_finish_payload_shape(enabled_env):
    client = LogReportClient()
    calls = []
    client._session.post = lambda path, json=None, headers=None, timeout=None: (
        calls.append((path, json)),
        FakeResponse({"code": 0, "data": {"executionId": 9}}),
    )[1]

    client.finish_execution(
        execution_id=9,
        status="FAILED",
        remark="元素不存在",
        fail_img_url="http://oss/e.png",
        record_files=[{"type": "SCREEN_RECORDING_FILE", "mediaType": "VIDEO", "fileName": "a.mp4",
                       "url": "http://lan/a.mp4", "storage": "LAN", "fileSize": 5}],
    )
    path, body = calls[-1]
    assert path.endswith("/executions/finish")
    assert body["status"] == "FAILED" and body["remark"] == "元素不存在"
    assert body["failImgUrl"] == "http://oss/e.png"
    assert body["recordFiles"][0]["storage"] == "LAN"
    assert calls and calls[0][0].endswith("/logs/batch") is False

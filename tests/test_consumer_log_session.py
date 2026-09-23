"""T2.4/T2.8：consumer 接入验证——会话在 skip_test_job 之后开启、TEST 单零记录。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.logging import log_session
from app.queue import consumer


class FakeReportClient:
    def __init__(self):
        self.created_payloads = []
        self.logs = []
        self.finish_calls = []

    def create_execution(self, payload):
        self.created_payloads.append(payload)
        return 42

    def enqueue(self, **kwargs):
        self.logs.append(kwargs)

    def finish_execution(self, **kwargs):
        self.finish_calls.append(kwargs)


class FakeCoordinator:
    def acquire_slot(self, account_key, profile_name, owner_pid=None):
        return {"lease_id": "L-1"}

    def release_slot(self, account_key, lease_id):
        pass


@pytest.fixture()
def fake_client(monkeypatch):
    client = FakeReportClient()
    monkeypatch.setattr(log_session, "get_report_client", lambda: client)
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "true")
    return client


def _demo_task():
    return json.loads((Path("message_list/msg_demo.json")).read_text(encoding="utf-8"))


def _test_task():
    task = _demo_task()
    task["content"]["jobNo"] = "TEST-NO-1"  # 命中 skip_test_job
    return task


def test_handle_message_binds_session(monkeypatch, fake_client):
    captured = {}

    def fake_dispatch(context):
        captured["ctx"] = log_session.current_context()
        from app.core.logging.logger import Logger

        Logger().info("dispatch 内的日志（应自动上报）")
        return True

    monkeypatch.setattr(consumer, "dispatch_context", fake_dispatch)

    result = consumer.handle_message(_demo_task(), account_session_coordinator=FakeCoordinator())
    assert result is True
    ctx = captured["ctx"]
    assert ctx is not None and ctx.execution_id == 42  # dispatch 期间会话已绑定
    assert ctx.rpa_message_id == str(_demo_task()["rpaMessageId"])
    assert ctx.queue_name.endswith("SI") or ctx.queue_name  # 队列名来自 rpaTaskTopic
    assert fake_client.created_payloads[0]["jobId"]  # jobId 从 content 解析
    assert len(fake_client.logs) == 1 and fake_client.logs[0]["message"].endswith("（应自动上报）")
    # 会话退出后线程上下文清空
    assert log_session.current_context() is None


def test_handle_message_skip_test_job_creates_nothing(monkeypatch, fake_client):
    monkeypatch.setattr(
        consumer, "dispatch_context", lambda context: pytest.fail("测试单不应进入 dispatch")
    )
    result = consumer.handle_message(_test_task(), account_session_coordinator=FakeCoordinator())
    assert result is False  # 被 skip_test_job 过滤
    assert fake_client.created_payloads == []  # 不产生任何执行记录
    assert fake_client.logs == []

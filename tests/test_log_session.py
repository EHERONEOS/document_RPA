"""T2.2/T2.8：log_service_enabled 分支 + 执行日志会话行为（对照设计 §6.1/§6.2/§6.3）。"""

from __future__ import annotations

import pytest

from app.core.logging import log_session
from app.core.logging.log_session import (
    current_context,
    execution_log_session,
    finish_execution,
    log_service_enabled,
    report_log,
)
from app.core.task.context import TaskContext


def _make_task_context(runtime_mode="queue"):
    return TaskContext(
        task={},
        task_id="98123",
        queue_name="QTCT_ZIM_SI",
        rpa_message_id="MSG-1",
        customer_code="QTCT",
        carrier_code="ZIM",
        business_code="SI",
        website_info={"id": "zim"},
        content={"jobNo": "JOB001"},
        remain_content={},
        runtime_mode=runtime_mode,
    )


class FakeReportClient:
    """捕获上报调用的假客户端。"""

    def __init__(self, create_ok=True):
        self.create_ok = create_ok
        self.created_payloads = []
        self.logs = []
        self.finish_calls = []

    def create_execution(self, payload):
        self.created_payloads.append(payload)
        return 42 if self.create_ok else None

    def enqueue(self, *, execution_id, seq, level, message, source_file="", source_line=0, log_time=None):
        self.logs.append({"executionId": execution_id, "seq": seq, "level": level, "message": message})

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


@pytest.fixture()
def fake_client(monkeypatch):
    client = FakeReportClient()
    monkeypatch.setattr(log_session, "get_report_client", lambda: client)
    return client


def test_log_service_enabled_branches(monkeypatch):
    # 未开启 → False
    monkeypatch.delenv("RPA_LOG_SERVICE_ENABLED", raising=False)
    assert log_service_enabled("queue") is False
    # 开启（各种写法）
    for value in ("1", "true", "Yes", "ON"):
        monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", value)
        assert log_service_enabled("queue") is True, value
    # 非法值
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "on ")
    assert log_service_enabled("queue") is True
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "false")
    assert log_service_enabled("queue") is False
    # 说明事项 1 双保险：local 模式即使开了开关也强制关闭
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "true")
    assert log_service_enabled("local") is False
    assert log_service_enabled("") is False


def test_session_disabled_is_noop(monkeypatch, fake_client):
    monkeypatch.delenv("RPA_LOG_SERVICE_ENABLED", raising=False)
    task_context = _make_task_context(runtime_mode="local")  # local 强制关闭
    with execution_log_session(task_context) as session_context:
        assert session_context is None
        assert current_context() is None  # 不绑定上下文
        report_log("这条不会被上报")
    assert fake_client.created_payloads == [] and fake_client.logs == []


def test_session_binds_context_and_reports(monkeypatch, fake_client):
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "true")
    task_context = _make_task_context()
    with execution_log_session(task_context) as session_context:
        assert session_context is not None
        assert session_context.execution_id == 42
        assert current_context() is session_context
        assert session_context.job_id == "JOB001"  # content.jobNo 优先
        report_log("打开门户", level="INFO", source_file="app/x.py", source_line=10)
        report_log("登录成功", level="SUCCESS")
        assert session_context.seq == 2
        assert [item["seq"] for item in fake_client.logs] == [1, 2]
        assert fake_client.logs[1]["executionId"] == 42
        finish_execution(success=True, fail_img="http://oss/ok.png", record_files=[{"type": "T"}])
    # 会话退出后上下文被清理（ContextVar 隔离）
    assert current_context() is None
    assert fake_client.finish_calls == [
        {
            "executionId": 42,
            "status": "SUCCESS",
            "remark": "",
            "failImgUrl": "http://oss/ok.png",
            "recordFiles": [{"type": "T"}],
        }
    ]


def test_session_exception_falls_back_to_failed(monkeypatch, fake_client):
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "true")
    task_context = _make_task_context()
    with pytest.raises(ValueError, match="页面炸了"):
        with execution_log_session(task_context):
            report_log("执行中")
            raise ValueError("页面炸了")
    assert len(fake_client.finish_calls) == 1
    call = fake_client.finish_calls[0]
    assert call["status"] == "FAILED"
    assert "页面炸了" in call["remark"]


def test_session_create_failure_degrades(monkeypatch, uid_like=None):
    """创建执行记录失败 → 降级为本地打印，日志入队被丢弃、不抛错。"""
    monkeypatch.setenv("RPA_LOG_SERVICE_ENABLED", "true")
    client = FakeReportClient(create_ok=False)
    monkeypatch.setattr(log_session, "get_report_client", lambda: client)
    with execution_log_session(_make_task_context()) as session_context:
        assert session_context.execution_id is None
        report_log("不会入队")  # execution_id=None 时静默丢弃
    assert client.logs == [] and client.finish_calls == []


def test_finish_execution_without_context_is_noop(fake_client):
    finish_execution(success=True)  # 无会话：不应抛错、不应上报
    assert fake_client.finish_calls == []

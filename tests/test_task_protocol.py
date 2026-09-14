from __future__ import annotations

import uuid

import pytest

from app.core.task.protocol import (
    TaskRuntimeIdentity,
    TaskStatus,
    build_task_event,
    can_transition,
    normalize_task_run_id,
)
from app.core.task.reporter import TaskEventReporter
from app.queue.message import build_task_context


def test_build_context_reuses_or_generates_task_run_id():
    run_id = str(uuid.uuid4())
    task = {
        "rpaTaskTopic": "FHT_MSCGW_SI",
        "rpaMessageId": "message-1",
        "taskRunId": run_id,
        "websiteInfo": {},
        "content": {},
    }

    context = build_task_context(task)

    assert context.task_run_id == run_id
    assert context.rpa_message_id == "message-1"
    assert uuid.UUID(build_task_context({**task, "taskRunId": ""}).task_run_id)


def test_task_run_id_must_be_uuid_when_supplied():
    with pytest.raises(ValueError, match="taskRunId"):
        normalize_task_run_id("not-a-uuid")


def test_task_state_transition_rules_and_event_envelope():
    assert can_transition(None, TaskStatus.STARTED)
    assert can_transition(TaskStatus.STARTED, TaskStatus.RUNNING)
    assert not can_transition(TaskStatus.SUCCEEDED, TaskStatus.RUNNING)

    event = build_task_event(
        TaskRuntimeIdentity(str(uuid.uuid4()), "message-1", "FHT_MSCGW_SI"),
        "task_step_changed",
        TaskStatus.RUNNING,
        device_id="dev-1",
        step_id="legacy.dispatch",
    )

    assert uuid.UUID(event["eventId"])
    assert event["deviceId"] == "DEV-1"
    assert event["status"] == "RUNNING"
    assert event["stepId"] == "legacy.dispatch"


class _Publisher:
    def __init__(self):
        self.events = []

    def publish_event(self, event):
        self.events.append(event)


def test_reporter_emits_started_step_and_finished_events():
    publisher = _Publisher()
    reporter = TaskEventReporter(
        device_id="dev-1",
        enrollment_token="token",
        redis_url="redis://unused",
        heartbeat_seconds=60,
        publisher=publisher,
    )
    reporter.start(TaskRuntimeIdentity(str(uuid.uuid4()), "message-1", "QUEUE"))
    reporter.step_changed("legacy.dispatch")
    reporter.finish(True)

    assert [event["type"] for event in publisher.events] == [
        "task_started",
        "task_step_changed",
        "task_finished",
    ]
    assert [event["status"] for event in publisher.events] == [
        "STARTED",
        "RUNNING",
        "SUCCEEDED",
    ]
    assert all(event["token"] == "token" for event in publisher.events)

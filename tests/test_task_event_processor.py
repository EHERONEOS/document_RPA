from __future__ import annotations

from unittest.mock import Mock

import pytest

from queue_control_platform.server.config import _require_flow_development_database
from queue_control_platform.server.event_processor import EventProcessor
from queue_control_platform.server.redis_bus import RedisStreamBus
from queue_control_platform.server.repository import _column_value


class _Repository:
    def __init__(self):
        self.events = []
        self.snapshots = []

    def record_agent_event(self, event_id, event):
        self.events.append((event_id, event))
        return event_id != "duplicate"

    def list_device_assignments(self, device_id):
        self.snapshots.append(device_id)
        return [{"queueName": "QUEUE", "desiredState": "RUNNING"}]


class _Bus:
    def __init__(self):
        self.acknowledged = []
        self.commands = []

    def read_events(self, _consumer_name):
        return [
            ("duplicate", {"type": "task_heartbeat", "deviceId": "DEV-1"}),
            ("new", {"type": "heartbeat", "deviceId": "DEV-1"}),
        ]

    def acknowledge_event(self, event_id):
        self.acknowledged.append(event_id)

    def send_command(self, device_id, command):
        self.commands.append((device_id, command))


def test_event_processor_acks_duplicate_and_syncs_only_device_heartbeat():
    repository = _Repository()
    bus = _Bus()

    assert EventProcessor(repository, bus).run_once() == 2
    assert bus.acknowledged == ["duplicate", "new"]
    assert repository.snapshots == ["DEV-1"]
    assert bus.commands == [
        ("DEV-1", {"action": "sync", "assignments": [{"queueName": "QUEUE", "desiredState": "RUNNING"}]})
    ]


def test_information_schema_column_names_are_case_insensitive():
    assert _column_value({"IS_NULLABLE": "NO"}, "is_nullable") == "NO"
    assert _column_value({"is_nullable": "YES"}, "is_nullable") == "YES"


def test_flow_platform_rejects_the_legacy_control_database():
    with pytest.raises(RuntimeError, match="queue_control_flow_dev"):
        _require_flow_development_database("mysql://user:password@127.0.0.1:3306/queue_control")


def test_event_group_starts_at_the_stream_tail():
    client = Mock()
    client.xautoclaim.return_value = ("0-0", [], [])
    client.xreadgroup.return_value = []
    bus = RedisStreamBus("redis://unused")
    bus._redis = client

    assert bus.read_events("test-consumer", block_ms=0) == []
    client.xgroup_create.assert_called_once_with(
        "queue-control:events", "queue-control-platform-v2", id="$", mkstream=True
    )

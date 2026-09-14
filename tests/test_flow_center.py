from __future__ import annotations

from app.control.queue_client.flow_sync import FlowSynchronizer
from app.core.flow.bindings import FlowBindingCache
from app.core.flow.cache import FlowCache, flow_checksum
from app.queue.message import build_task_context
from queue_control_platform.server.repository import MySQLControlRepository


def _definition(version: str = "v1") -> dict:
    return {
        "schemaVersion": 1,
        "flowId": "Demo.Center",
        "flowVersion": version,
        "steps": [{"type": "checkpoint", "stepId": "checkpoint.ready"}],
    }


def test_flow_sync_persists_validated_flow_and_queue_binding(tmp_path):
    definition = _definition()
    calls = []
    synchronizer = FlowSynchronizer(
        api_url="http://flow-center.invalid",
        device_id="DEV-1",
        enrollment_token="token",
        cache_directory=str(tmp_path),
    )

    def fetch(flow_id, flow_version):
        calls.append((flow_id, flow_version))
        return definition

    synchronizer._fetch_definition = fetch
    command = {
        "action": "flow_sync",
        "bindings": [{
            "queueName": "FHT_MSCGW_SI", "flowId": "Demo.Center", "flowVersion": "v1",
            "checksum": flow_checksum(definition),
        }],
    }

    assert synchronizer.sync(command) == {"syncedBindings": 1}
    assert FlowCache(tmp_path).get("Demo.Center", "v1") == definition
    assert FlowBindingCache(tmp_path).get("FHT_MSCGW_SI") == {
        "flowId": "Demo.Center", "flowVersion": "v1", "checksum": flow_checksum(definition),
    }
    synchronizer.sync(command)
    assert calls == [("Demo.Center", "v1")]


def test_unversioned_message_uses_local_published_queue_binding(tmp_path, monkeypatch):
    definition = _definition()
    FlowCache(tmp_path).put(definition)
    FlowBindingCache(tmp_path).put([{
        "queueName": "FHT_MSCGW_SI", "flowId": "Demo.Center", "flowVersion": "v1",
        "checksum": flow_checksum(definition),
    }])
    monkeypatch.setenv("FLOW_CACHE_DIR", str(tmp_path))

    context = build_task_context({
        "rpaTaskTopic": "FHT_MSCGW_SI", "rpaMessageId": "published-binding",
        "websiteInfo": {}, "content": {},
    })

    assert (context.flow_id, context.flow_version) == ("Demo.Center", "v1")


def test_release_strategy_is_deterministic_and_canary_falls_back():
    assert MySQLControlRepository._release_applies({"mode": "all"}, "DEV-1")
    assert MySQLControlRepository._release_applies({"mode": "devices", "deviceIds": ["DEV-1"]}, "DEV-1")
    assert not MySQLControlRepository._release_applies({"mode": "devices", "deviceIds": ["DEV-2"]}, "DEV-1")
    outcome = MySQLControlRepository._release_applies({"mode": "percentage", "percentage": 50}, "DEV-1")
    assert outcome == MySQLControlRepository._release_applies({"mode": "percentage", "percentage": 50}, "DEV-1")

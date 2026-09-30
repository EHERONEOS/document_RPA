"""Web 日志列表删除接口：单条/批量删除均级联清理关联日志和记录文件。"""

from __future__ import annotations

from queue_control_platform.server.rpa_log.db import db_cursor
from queue_control_platform.tests.conftest import create_execution, pytestmark  # noqa: F401

AUTH = {"Authorization": "Bearer local-dev"}


def test_delete_execution_batch_cascades_related_logs_and_files(client, clean_db, uid):
    first_id = create_execution(client, f"{uid}A")["executionId"]
    second_id = create_execution(client, f"{uid}B")["executionId"]

    client.post(
        "/api/v1/logs/batch",
        json={
            "executionId": first_id,
            "logs": [{"seq": 1, "message": "打开页面"}, {"seq": 2, "message": "输入发货人"}],
        },
        headers=AUTH,
    )
    client.post(
        "/api/v1/logs/batch",
        json={"executionId": second_id, "logs": [{"seq": 1, "message": "打开页面"}]},
        headers=AUTH,
    )
    client.post(
        "/api/v1/executions/finish",
        json={
            "executionId": second_id,
            "status": "SUCCESS",
            "recordFiles": [
                {"type": "SCREEN_RECORDING_FILE", "mediaType": "VIDEO", "fileName": "a.mp4", "url": "http://x/a.mp4"}
            ],
        },
        headers=AUTH,
    )

    resp = client.post(
        "/api/v1/executions/delete",
        json={"executionIds": [first_id, second_id, 999999]},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == {
        "requested": 3,
        "deleted": 2,
        "deletedLogCount": 3,
        "deletedFileCount": 1,
    }

    assert client.get(
        "/api/v1/execution/detail", params={"executionId": first_id}
    ).status_code == 404
    assert client.get(
        "/api/v1/execution/detail", params={"executionId": second_id}
    ).status_code == 404

    with db_cursor() as cursor:
        for table in ("rpa_execution", "rpa_execution_log", "rpa_execution_file"):
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table}")
            assert int(cursor.fetchone()["count"]) == 0


def test_delete_executions_requires_non_empty_ids(client):
    resp = client.post("/api/v1/executions/delete", json={"executionIds": []})
    assert resp.status_code == 422

"""同一消息ID新增执行记录时，自动废弃旧的 RUNNING 记录。"""

from __future__ import annotations

from queue_control_platform.tests.conftest import create_execution, pytestmark  # noqa: F401

AUTH = {"Authorization": "Bearer local-dev"}


def test_new_execution_deprecates_running_same_message(client, clean_db, uid):
    finished = create_execution(client, uid)["executionId"]
    client.post(
        "/api/v1/executions/finish",
        json={"executionId": finished, "status": "SUCCESS"},
        headers=AUTH,
    )

    running_one = create_execution(client, uid, device="T-DEV-02")["executionId"]
    running_two = create_execution(client, uid, device="T-DEV-02")["executionId"]
    unaffected = create_execution(client, f"{uid}-OTHER")["executionId"]
    latest = create_execution(client, uid, device="T-DEV-03")["executionId"]

    deprecated_rows = client.get(
        "/api/v1/executions",
        params={"rpaMessageId": uid, "status": "DEPRECATED"},
    ).json()["data"]["list"]
    assert [row["executionId"] for row in deprecated_rows] == [running_two, running_one]

    deprecated = client.get(
        "/api/v1/execution/detail", params={"executionId": running_one}
    ).json()["data"]["execution"]
    assert deprecated["status"] == "DEPRECATED"
    assert deprecated["finishedAt"] is not None
    assert deprecated["durationSeconds"] is not None

    latest_detail = client.get(
        "/api/v1/execution/detail", params={"executionId": latest}
    ).json()["data"]["execution"]
    assert latest_detail["status"] == "RUNNING"

    unaffected_detail = client.get(
        "/api/v1/execution/detail", params={"executionId": unaffected}
    ).json()["data"]["execution"]
    assert unaffected_detail["status"] == "RUNNING"

"""T1.4/T1.6：查询接口——模糊/精确筛选、分页排序、详情、维表统计。"""

from __future__ import annotations

from queue_control_platform.tests.conftest import create_execution, pytestmark  # noqa: F401


def test_list_filters_fuzzy_and_exact(client, clean_db, uid):
    a = create_execution(client, f"{uid}A001", queue="QT_ZIM_SI", device="DEV-A")["executionId"]
    b = create_execution(client, f"{uid}B002", queue="QT_ZIM_SI_V2", device="DEV-B")["executionId"]

    # 消息ID 后缀模糊
    rows = client.get("/api/v1/executions", params={"rpaMessageId": "A001"}).json()["data"]["list"]
    assert [r["executionId"] for r in rows] == [a]
    # 队列精确
    rows = client.get("/api/v1/executions", params={"queueName": "QT_ZIM_SI"}).json()["data"]["list"]
    assert [r["executionId"] for r in rows] == [a]
    # 设备精确
    rows = client.get("/api/v1/executions", params={"deviceName": "DEV-B"}).json()["data"]["list"]
    assert [r["executionId"] for r in rows] == [b]
    # 状态精确
    rows = client.get("/api/v1/executions", params={"status": "RUNNING"}).json()["data"]
    assert rows["total"] == 2
    # JobId 后缀模糊
    rows = client.get("/api/v1/executions", params={"jobId": "B002"}).json()["data"]["list"]
    assert [r["executionId"] for r in rows] == [b]


def test_list_pagination_order(client, clean_db, uid):
    for i in range(3):
        create_execution(client, f"{uid}{i:03d}")
    page1 = client.get("/api/v1/executions", params={"page": 1, "pageSize": 2}).json()["data"]
    page2 = client.get("/api/v1/executions", params={"page": 2, "pageSize": 2}).json()["data"]
    assert page1["total"] == 3 and len(page1["list"]) == 2 and len(page2["list"]) == 1
    ids = [r["executionId"] for r in page1["list"]] + [r["executionId"] for r in page2["list"]]
    assert ids == sorted(ids, reverse=True)  # id DESC，新的在前


def test_detail_not_found(client, clean_db):
    assert client.get("/api/v1/execution/detail", params={"executionId": 424242}).status_code == 404


def test_devices_queues_stats(client, clean_db, uid):
    create_execution(client, uid, queue="QT_ZIM_SI", device="DEV-A")
    second = create_execution(client, f"{uid}X", queue="QT_MSC_SI", device="DEV-A")["executionId"]
    client.post(
        "/api/v1/executions/finish",
        json={"executionId": second, "status": "SUCCESS", "durationSeconds": 30},
        headers={"Authorization": "Bearer local-dev"},
    )

    devices = client.get("/api/v1/devices").json()["data"]
    assert len(devices) == 1
    device = devices[0]
    assert device["deviceName"] == "DEV-A"
    assert device["todayCount"] == 2
    assert device["boundQueueCount"] == 2
    assert device["successRate"] == 100.0

    queues = client.get("/api/v1/queues").json()["data"]
    by_queue = {q["queueName"]: q for q in queues}
    assert by_queue["QT_ZIM_SI"]["todayCount"] == 1
    assert by_queue["QT_ZIM_SI"]["avgDurationSeconds"] is None  # 未终态无耗时
    assert by_queue["QT_MSC_SI"]["avgDurationSeconds"] == 30

    stats = client.get("/api/v1/stats/summary").json()["data"]
    assert stats == {"todayTotal": 2, "successCount": 1, "failedCount": 0, "runningCount": 1}

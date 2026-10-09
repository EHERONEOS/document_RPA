"""T1.2/T1.6：Agent 上报接口——鉴权、uk 幂等、日志批量校验、finish 终态幂等。"""

from __future__ import annotations

from queue_control_platform.tests.conftest import DB_READY, create_execution  # noqa: F401
from queue_control_platform.tests.conftest import pytestmark  # noqa: F401

AUTH = {"Authorization": "Bearer local-dev"}


def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"db": "ok"}


def test_agent_api_requires_token(client, clean_db, uid):
    resp = client.post("/api/v1/executions", json={"rpaMessageId": uid, "queueName": "Q"})
    assert resp.status_code == 401
    resp = client.post(
        "/api/v1/executions", json={"rpaMessageId": uid, "queueName": "Q"}, headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401


def test_create_field_validation(client, clean_db):
    resp = client.post("/api/v1/executions", json={"rpaMessageId": "M", "queueName": "x" * 129}, headers=AUTH)
    assert resp.status_code == 422  # 超过 VARCHAR(128)
    resp = client.post("/api/v1/executions", json={"rpaMessageId": "M"}, headers=AUTH)
    assert resp.status_code == 422  # 缺 queueName


def test_logs_batch_limit_and_count(client, clean_db, uid):
    execution_id = create_execution(client, uid)["executionId"]

    resp = client.post(
        "/api/v1/logs/batch",
        json={"executionId": execution_id, "logs": [{"seq": i, "message": f"m{i}"} for i in range(201)]},
        headers=AUTH,
    )
    assert resp.status_code == 400  # 单批 ≤200（§5.1）

    resp = client.post(
        "/api/v1/logs/batch",
        json={
            "executionId": execution_id,
            "logs": [
                {"seq": 1, "level": "info", "message": "第一条"},  # level 自动归一化为 INFO
                {"seq": 2, "level": "SUCCESS", "message": "登录成功", "sourceFile": "a.py", "sourceLine": 10},
            ],
        },
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["accepted"] == 2

    detail = client.get("/api/v1/execution/detail", params={"executionId": execution_id}).json()["data"]
    assert [log["seq"] for log in detail["logs"]] == [2, 1]  # seq DESC
    assert detail["logs"][1]["level"] == "INFO"
    assert detail["execution"]["logCount"] == 2

    # 终态后日志仍可追加（§9.2）
    client.post(
        "/api/v1/executions/finish",
        json={"executionId": execution_id, "status": "SUCCESS"},
        headers=AUTH,
    )
    resp = client.post(
        "/api/v1/logs/batch", json={"executionId": execution_id, "logs": [{"seq": 3, "message": "收尾"}]}, headers=AUTH
    )
    assert resp.status_code == 200


def test_finish_idempotent_first_wins(client, clean_db, uid):
    execution_id = create_execution(client, uid)["executionId"]

    body = {
        "executionId": execution_id,
        "status": "FAILED",
        "remark": "元素不存在",
        "failImgObjectName": "rpa/f.png",  # 失败截图存 objectName（同录屏方案）
    }
    assert client.post("/api/v1/executions/finish", json=body, headers=AUTH).status_code == 200

    # 重复 finish 以首次为准（§9.2）：拒绝
    resp = client.post(
        "/api/v1/executions/finish", json={"executionId": execution_id, "status": "SUCCESS"}, headers=AUTH
    )
    assert resp.status_code == 409

    detail = client.get("/api/v1/execution/detail", params={"executionId": execution_id}).json()["data"]
    assert detail["execution"]["status"] == "FAILED"
    assert detail["execution"]["remark"] == "元素不存在"
    assert detail["execution"]["failImgObjectName"] == "rpa/f.png"
    assert detail["execution"]["durationSeconds"] is not None  # 服务端补算

    # 不存在的执行
    resp = client.post("/api/v1/executions/finish", json={"executionId": 99999, "status": "SUCCESS"}, headers=AUTH)
    assert resp.status_code == 404


def test_finish_writes_record_files(client, clean_db, uid):
    execution_id = create_execution(client, uid)["executionId"]
    body = {
        "executionId": execution_id,
        "status": "SUCCESS",
        "recordFiles": [
            {"type": "SCREEN_RECORDING_FILE", "mediaType": "VIDEO", "fileName": "a.mp4", "url": "http://x/a.mp4",
             "storage": "LAN", "fileSize": 1024},
            {"type": "SUBMIT_RESULT_SCREENSHOT", "mediaType": "IMAGE", "fileName": "b.png",
             "objectName": "rpa/b.png", "storage": "OSS"},
        ],
    }
    assert client.post("/api/v1/executions/finish", json=body, headers=AUTH).status_code == 200
    files = client.get("/api/v1/execution/files", params={"executionId": execution_id}).json()["data"]
    assert [f["fileName"] for f in files] == ["a.mp4", "b.png"]
    assert files[0]["storage"] == "LAN"
    # 截图与录屏同方案：存 objectName，查看页经 /files/oss-url 换临时地址
    assert files[1]["objectName"] == "rpa/b.png"
    assert files[1]["url"] == ""


def test_finish_accepts_object_name_and_local_video(client, clean_db, uid):
    """视频 OSS 成功只带 objectName、失败只带 remark：二者都不能再因缺 url 被 422。"""
    execution_id = create_execution(client, uid)["executionId"]
    body = {
        "executionId": execution_id,
        "status": "SUCCESS",
        "recordFiles": [
            {
                "type": "SCREEN_RECORDING_FILE",
                "mediaType": "VIDEO",
                "fileName": "ok.mp4",
                "objectName": "original/ok.mp4",
                "storage": "OSS",
                "fileSize": 2048,
            },
            {
                "type": "SCREEN_RECORDING_FILE",
                "mediaType": "VIDEO",
                "fileName": "fail.mp4",
                "storage": "LOCAL",
                "fileSize": 1024,
                "remark": "上传oss失败 视频本地路径:/tmp/fail.mp4",
            },
        ],
    }
    resp = client.post("/api/v1/executions/finish", json=body, headers=AUTH)
    assert resp.status_code == 200, resp.text
    files = client.get("/api/v1/execution/files", params={"executionId": execution_id}).json()["data"]
    assert files[0]["objectName"] == "original/ok.mp4"
    assert files[0]["url"] == ""
    assert files[1]["storage"] == "LOCAL"
    assert "上传oss失败" in files[1]["remark"]


def test_recreate_same_message_inserts_new_record(client, clean_db, uid):
    """相同消息再次消费：插入新记录（2026-09 调整：取消消息ID唯一键）。

    每次消费独立成条：第一次的终态与日志不受影响，第二次从 RUNNING 开始。
    """
    first_id = create_execution(client, uid)["executionId"]
    client.post("/api/v1/executions/finish", json={"executionId": first_id, "status": "SUCCESS"}, headers=AUTH)

    second = create_execution(client, uid, device="T-DEV-02")  # 同消息重投
    second_id = second["executionId"]
    assert second_id != first_id  # 新记录
    assert second["status"] == "RUNNING"

    first = client.get("/api/v1/execution/detail", params={"executionId": first_id}).json()["data"]["execution"]
    second_detail = client.get("/api/v1/execution/detail", params={"executionId": second_id}).json()["data"]["execution"]
    assert first["status"] == "SUCCESS"  # 首次终态不受影响
    assert second_detail["status"] == "RUNNING"  # 第二次独立走自己的生命周期
    assert second_detail["deviceName"] == "T-DEV-02"

    # 同一消息两次消费在列表中都可见
    listing = client.get("/api/v1/executions", params={"messageId": uid}).json()["data"]
    assert listing["total"] == 2

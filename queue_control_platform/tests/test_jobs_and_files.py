"""T1.5/T1.6：RUNNING 超时置 TIMEOUT；T1.3/T1.6：文件服务白名单/大小限制/静态访问。"""

from __future__ import annotations

from datetime import datetime, timedelta

from queue_control_platform.tests.conftest import create_execution, pytestmark  # noqa: F401

AUTH = {"Authorization": "Bearer local-dev"}


# ---------------------------------------------------------------------------
# T1.5 RUNNING 超时
# ---------------------------------------------------------------------------

def test_running_timeout_marked(client, clean_db, uid):
    from queue_control_platform.server.rpa_log.jobs import mark_running_timeout
    from queue_control_platform.server.rpa_log.settings import get_settings

    threshold_hours = get_settings().running_timeout_hours
    stale = (datetime.now() - timedelta(hours=threshold_hours + 1)).strftime("%Y-%m-%d %H:%M:%S")
    stale_id = create_execution(client, uid, startedAt=stale)["executionId"]
    fresh_id = create_execution(client, f"{uid}F")["executionId"]  # 新鲜 RUNNING 不动

    assert mark_running_timeout() >= 1

    stale_row = client.get("/api/v1/execution/detail", params={"executionId": stale_id}).json()["data"]["execution"]
    assert stale_row["status"] == "TIMEOUT"
    assert stale_row["durationSeconds"] == int(threshold_hours * 3600)  # finished=started+阈值，口径一致
    assert stale_row["finishedAt"] is not None

    fresh_row = client.get("/api/v1/execution/detail", params={"executionId": fresh_id}).json()["data"]["execution"]
    assert fresh_row["status"] == "RUNNING"
    assert fresh_row["finishedAt"] is None


def test_timeout_row_listed_by_status_filter(client, clean_db, uid):
    from queue_control_platform.server.rpa_log.jobs import mark_running_timeout

    stale = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    create_execution(client, uid, startedAt=stale)
    mark_running_timeout()
    data = client.get("/api/v1/executions", params={"status": "TIMEOUT"}).json()["data"]
    assert data["total"] == 1


# ---------------------------------------------------------------------------
# T1.3 文件服务
# ---------------------------------------------------------------------------

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def test_upload_and_static_access(client, clean_db):
    resp = client.post(
        "/api/v1/files/upload",
        files={"file": ("shot.png", PNG_BYTES, "image/png")},
        headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["storage"] == "LAN"
    assert data["fileName"] == "shot.png"
    assert data["fileSize"] == len(PNG_BYTES)
    assert "/files/" in data["url"]

    static_path = data["url"].split("/files/", 1)[1]
    static = client.get(f"/files/{static_path}")
    assert static.status_code == 200
    assert static.content == PNG_BYTES


def test_upload_extension_whitelist(client, clean_db):
    resp = client.post(
        "/api/v1/files/upload",
        files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
        headers=AUTH,
    )
    assert resp.status_code == 400


def test_upload_requires_token(client, clean_db):
    resp = client.post("/api/v1/files/upload", files={"file": ("shot.png", PNG_BYTES, "image/png")})
    assert resp.status_code == 401


def test_upload_size_limit_413(client, clean_db, monkeypatch):
    from queue_control_platform.server.rpa_log.routes import files as files_route

    monkeypatch.setattr(files_route, "MAX_UPLOAD_SIZE", 16)
    resp = client.post(
        "/api/v1/files/upload",
        files={"file": ("big.mp4", b"x" * 64, "video/mp4")},
        headers=AUTH,
    )
    assert resp.status_code == 413

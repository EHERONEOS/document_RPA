"""pytest 公共夹具：独立测试库 rpa_platform_test（与真实数据完全隔离）。

2026-09-23 事故修复：此前测试直接清空统一库 rpa_platform 的 rpa_* 表，
曾误删用户真实执行记录。现所有测试写入 rpa_platform_test 库，真实库永不被测试触碰。
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest
import pymysql

# 测试的文件上传也隔离到临时目录，不污染真实 files/
os.environ["RPA_LOG_FILES_DIR"] = os.path.join(tempfile.gettempdir(), "rpa-platform-test-files")

TEST_DB_URL = "mysql://root:root_password@127.0.0.1:3306/rpa_platform_test"  # 仅本地 docker 开发测试用
TEST_DB = "rpa_platform_test"

_configured = False


def _ensure_test_db() -> bool:
    """创建独立测试库并幂等建表；任一步失败视为环境不可用。"""
    global _configured
    if _configured:
        return True
    try:
        conn = pymysql.connect(host="127.0.0.1", port=3306, user="root",
                               password="root_password", charset="utf8mb4", autocommit=True)
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {TEST_DB} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.close()
        from queue_control_platform.server.rpa_log import db as rpa_db
        rpa_db.configure(TEST_DB_URL)
        from queue_control_platform.server.rpa_log.init_db import initialize_schema
        initialize_schema()
        _configured = True
        return True
    except Exception:  # noqa: BLE001 - MySQL 不可用/无权限时跳过整套测试
        return False


DB_READY = _ensure_test_db()

pytestmark = pytest.mark.skipif(not DB_READY, reason="本地 MySQL 不可用（先 docker compose up -d）")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from queue_control_platform.server.repository import MySQLControlRepository
    from queue_control_platform.server.web import create_app

    # 不进入 context manager：跳过 lifespan（不启动超时扫描/事件处理线程，测试内手动调用）
    repository = MySQLControlRepository(TEST_DB_URL)
    return TestClient(create_app(repository, None, None))


@pytest.fixture()
def clean_db():
    """每条用例前清空测试库的 RPA 日志业务表。"""
    from queue_control_platform.server.rpa_log.db import db_cursor

    with db_cursor() as cursor:
        for table in ("rpa_execution_log", "rpa_execution_file", "rpa_execution", "rpa_device", "rpa_queue"):
            cursor.execute(f"TRUNCATE TABLE {table}")
    yield


@pytest.fixture()
def uid() -> str:
    return uuid.uuid4().hex[:12].upper()


def create_execution(client, message_id: str, queue: str = "QT_ZIM_SI", device: str = "T-DEV-01", **overrides) -> dict:
    body = {
        "rpaMessageId": message_id,
        "jobId": overrides.pop("jobId", f"JOB{message_id}"),
        "queueName": queue,
        "deviceName": device,
        "startedAt": overrides.pop("startedAt", None),
    }
    body.update(overrides)
    resp = client.post("/api/v1/executions", json=body, headers={"Authorization": "Bearer local-dev"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]

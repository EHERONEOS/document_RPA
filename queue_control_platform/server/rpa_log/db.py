"""MySQL 连接管理（RPA 日志模块）：PyMySQL + DBUtils 连接池。

并入平台后不再有独立的 RPA_LOG_MYSQL_URL：默认复用平台的
QUEUE_CONTROL_MYSQL_URL（统一库 rpa_platform）；测试可用 configure() 注入。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from urllib.parse import unquote, urlparse

import pymysql
from dbutils.pooled_db import PooledDB
from pymysql.cursors import DictCursor

_override_url: str | None = None
_pool: PooledDB | None = None


def configure(mysql_url: str | None) -> None:
    """测试/嵌入场景注入连接 URL；传入 None 恢复默认（平台配置）。"""
    global _override_url, _pool
    _override_url = mysql_url
    _pool = None


def _mysql_url() -> str:
    if _override_url and _override_url.strip():
        return _override_url.strip()
    # 延迟导入避免与平台包初始化顺序耦合；PlatformSettings 负责读 .env
    from queue_control_platform.server.config import PlatformSettings

    return PlatformSettings.from_environment().mysql_url


def _get_pool() -> PooledDB:
    global _pool
    if _pool is None:
        parsed = urlparse(_mysql_url())
        if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname:
            raise RuntimeError("QUEUE_CONTROL_MYSQL_URL 必须是 mysql://user:password@host:port/database")
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=8,
            ping=1,  # 取连接时自动 ping 保活
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=unquote(parsed.username or "root"),
            password=unquote(parsed.password or ""),
            database=(parsed.path or "").lstrip("/"),
            charset="utf8mb4",
            autocommit=True,
            cursorclass=DictCursor,
        )
    return _pool


@contextmanager
def db_cursor() -> Iterator[DictCursor]:
    """借出一个 DictCursor，用完归还连接池（autocommit 模式）。"""
    conn = _get_pool().connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
    finally:
        conn.close()  # PooledDB 语义：close() 即归还池


def ping() -> bool:
    """健康检查用：SELECT 1 探活。"""
    try:
        with db_cursor() as cursor:
            cursor.execute("SELECT 1")
            return True
    except Exception:
        return False

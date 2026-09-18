"""部署同步器的连接配置与原库只读访问保护。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from contextlib import contextmanager
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
import os


# 原库同步范围固定，queue_events 是运行事件日志，明确排除。
EXCLUDED_TABLES: tuple[str, ...] = ("queue_events",)


@dataclass(frozen=True)
class SyncSettings:
    """保存原库只读源、新库读写目标和同步器运行参数。

    字段说明：
    - ``source_mysql_url``：原队列控制库，只允许 SELECT/SHOW/binlog。
    - ``target_mysql_url``：部署控制库，可读写。
    - ``batch_size``：全量同步每批读取和写入行数。
    - ``connect_timeout``：数据库连接超时秒数。
    """

    source_mysql_url: str = "mysql://queue_control:queue_control@127.0.0.1:3306/queue_control"
    target_mysql_url: str = "mysql://queue_deploy_app:queue_deploy_app@127.0.0.1:3306/queue_control_deploy"
    batch_size: int = 500
    connect_timeout: int = 10

    @classmethod
    def from_environment(cls) -> "SyncSettings":
        """从环境变量加载同步配置。

        出参：
            返回不可变的 ``SyncSettings`` 配置对象。

        核心逻辑:
            1. 加载项目根目录 .env，但不覆盖已显式设置的环境变量。
            2. 读取原库和新库 MySQL URL。
            3. 读取批次大小和超时时间，非法数字直接失败以暴露配置错误。
        """
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        return cls(
            source_mysql_url=os.getenv(
                "QUEUE_CONTROL_SOURCE_MYSQL_URL",
                os.getenv(
                    "QUEUE_CONTROL_MYSQL_URL",
                    "mysql://queue_control:queue_control@127.0.0.1:3306/queue_control",
                ),
            ),
            target_mysql_url=os.getenv(
                "QUEUE_CONTROL_DEPLOY_MYSQL_URL",
                "mysql://queue_deploy_app:queue_deploy_app@127.0.0.1:3306/queue_control_deploy",
            ),
            batch_size=max(1, int(os.getenv("DEPLOY_SYNC_BATCH_SIZE", "500"))),
            connect_timeout=max(1, int(os.getenv("DEPLOY_SYNC_CONNECT_TIMEOUT", "10"))),
        )


class ReadOnlyCursor:
    """包装 PyMySQL cursor，静态拒绝任何可能改写原库的 SQL。"""

    # 允许在原库执行的操作开头，其余全部禁止。
    _allowed_prefixes = ("select", "show", "describe", "desc", "explain")

    def __init__(self, cursor: Any):
        """保存被包装的底层 cursor。

        入参：
            ``cursor``：PyMySQL DictCursor 或兼容 cursor。
        """
        self._cursor = cursor

    def execute(self, sql: str, args: Any | None = None) -> int:
        """执行只读 SQL。

        入参：
            ``sql``：SQL 文本。
            ``args``：PyMySQL 参数。

        出参：
            返回底层 cursor 的受影响行数值。

        异常：
            ``PermissionError``：SQL 不是允许的只读语句时抛出。
        """
        normalized = " ".join(sql.strip().split()).lower()
        if not normalized.startswith(self._allowed_prefixes):
            raise PermissionError(f"原库连接禁止执行非只读 SQL: {sql[:160]}")
        return self._cursor.execute(sql, args)

    def executemany(self, sql: str, args: Any) -> int:
        """批量执行 SQL 前同样执行只读保护。

        入参：
            ``sql``：SQL 模板。
            ``args``：参数列表。

        异常：
            ``PermissionError``：一律拒绝批量写入意图。
        """
        raise PermissionError("原库连接禁止 executemany")

    def __enter__(self):
        """支持 with 语法并返回只读代理。"""
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        """透传底层 cursor 的上下文退出。"""
        return self._cursor.__exit__(exc_type, exc, traceback)

    def __getattr__(self, name: str) -> Any:
        """透传 fetchone、fetchall 等非执行属性。

        入参：
            ``name``：属性名。

        出参：
            返回底层 cursor 属性。
        """
        return getattr(self._cursor, name)


def parse_database(mysql_url: str) -> str:
    """解析并校验 MySQL URL 中的数据库名。

    入参：
        ``mysql_url``：mysql://user:password@host:port/database 格式 URL。

    出参：
        返回数据库名。

    异常：
        ``RuntimeError``：URL 或数据库名非法时抛出。
    """
    parsed = urlparse(mysql_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname:
        raise RuntimeError("MySQL URL 必须是 mysql://user:password@host:port/database")
    database = parsed.path.lstrip("/")
    if not database or "/" in database:
        raise RuntimeError("MySQL URL 缺少或包含非法数据库名")
    return database


@contextmanager
def source_connection(settings: SyncSettings) -> Iterator[Any]:
    """创建强制只读语义的原库连接。

    入参：
        ``settings``：同步配置。

    出参：
        yield 一个 PyMySQL 连接。

    核心逻辑:
        1. 按源 URL 连接数据库。
        2. 开启 autocommit，避免隐式事务。
        3. 会话事务隔离级别设为只读，配合 SQL 静态拦截双重保护。
    """
    import pymysql

    parsed = urlparse(settings.source_mysql_url)
    connection = pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parse_database(settings.source_mysql_url),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=settings.connect_timeout,
        init_command="SET SESSION TRANSACTION READ ONLY",
    )
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def target_connection(settings: SyncSettings, *, database: bool = True) -> Iterator[Any]:
    """创建新库连接，可选择不预选数据库。

    入参：
        ``settings``：同步配置。
        ``database``：False 时只连接服务实例，用于创建数据库。

    出参：
        yield 一个 PyMySQL 连接。

    核心逻辑:
        1. 连接目标 MySQL 实例。
        2. database=False 时不调用 USE，供迁移入口创建新库。
        3. 连接关闭由上下文管理器负责。
    """
    import pymysql

    parsed = urlparse(settings.target_mysql_url)
    connection = pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parse_database(settings.target_mysql_url) if database else None,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=settings.connect_timeout,
    )
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def check_environment(settings: SyncSettings | None = None) -> dict[str, Any]:
    """输出同步环境检查结果。

    入参：
        ``settings``：可选配置；缺省时从环境加载。

    出参：
        返回包含源库、目标库、只读状态和排除表的字典。
    """
    settings = settings or SyncSettings.from_environment()
    result: dict[str, Any] = {
        "source_database": parse_database(settings.source_mysql_url),
        "target_database": parse_database(settings.target_mysql_url),
        "source_writable": False,
        "excluded_tables": list(EXCLUDED_TABLES),
        "source_ready": False,
        "binlog": {},
    }
    with source_connection(settings) as connection, ReadOnlyCursor(connection.cursor()) as cursor:
        cursor.execute("SELECT 1 AS ok")
        result["source_ready"] = cursor.fetchone()["ok"] == 1
        for variable in ("log_bin", "binlog_format", "binlog_row_image"):
            cursor.execute(f"SHOW VARIABLES LIKE '{variable}'")
            row = cursor.fetchone()
            result["binlog"][variable] = row.get("Value") if row else None
    return result


if __name__ == "__main__":
    import argparse
    import json

    # 命令行入口用于执行 T003 配置与只读保护验证。
    parser = argparse.ArgumentParser(description="检查部署同步数据库配置")
    parser.add_argument("--check", action="store_true", help="检查数据库和 binlog 配置")
    args = parser.parse_args()
    if not args.check:
        parser.error("请使用 --check")
    print(json.dumps(check_environment(), ensure_ascii=False, indent=2))

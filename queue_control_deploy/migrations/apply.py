"""部署控制库迁移执行入口。"""
from __future__ import annotations

import argparse
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from queue_control_deploy.sync.config import SyncSettings, parse_database, target_connection


# 按编号顺序执行，前序文件创建数据库，后序文件创建表和种子数据。
MIGRATION_FILES: tuple[str, ...] = (
    "001_create_database.sql",
    "002_create_mirror_tables.sql",
    "003_create_deploy_tables.sql",
    "004_seed_queue_catalog.sql",
    "005_add_deploy_command_requester.sql",
)


def read_sql(filename: str) -> str:
    """读取迁移 SQL 文件。

    入参：
        ``filename``：迁移文件名。

    出参：
        返回 SQL 文本。
    """
    path = Path(__file__).resolve().parent / filename
    return path.read_text(encoding="utf-8")


def split_sql_statements(sql: str) -> list[str]:
    """把普通分号分隔 SQL 拆成可单条执行的语句。

    入参：
        ``sql``：迁移文件文本。

    出参：
        返回非空 SQL 语句列表。

    核心逻辑:
        本迁移只包含 DDL/DML，不含存储过程；因此可按分号安全拆分。
    """
    statements: list[str] = []
    for raw_statement in sql.split(";"):
        statement = raw_statement.strip()
        if statement and any(line.strip() and not line.strip().startswith("--") for line in statement.splitlines()):
            statements.append(statement)
    return statements


def apply_migrations(settings: SyncSettings | None = None, admin_url: str | None = None) -> list[str]:
    """按顺序执行全部新库迁移。

    入参：
        ``settings``：可选同步配置。

    出参：
        返回本次实际执行的迁移文件列表。

    核心逻辑:
        1. 迁移状态保存在新库 ``schema_migrations``。
        2. 先连接不选库的实例执行建库。
        3. 随后选择新库，在事务中执行 DDL/DML 并记录版本。
    """
    base_settings = settings or SyncSettings.from_environment()
    settings = admin_settings(base_settings, admin_url)
    executed: list[str] = []
    with target_connection(settings, database=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE IF NOT EXISTS %s" % "`queue_control_deploy`")
        connection.commit()

    with target_connection(base_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(128) PRIMARY KEY,
                    applied_at DATETIME(6) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute("SELECT version FROM schema_migrations")
            applied = {row["version"] for row in cursor.fetchall()}
        for filename in MIGRATION_FILES:
            if filename in applied:
                continue
            with connection.cursor() as cursor:
                for statement in split_sql_statements(read_sql(filename)):
                    cursor.execute(statement)
                cursor.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, UTC_TIMESTAMP(6))",
                    (filename,),
                )
            connection.commit()
            executed.append(filename)
    return executed


def admin_settings(settings: SyncSettings | None = None, admin_url: str | None = None) -> SyncSettings:
    """获取具备建库权限的迁移连接配置。

    入参：
        ``settings``：可选基础配置。

    出参：
        返回目标地址替换为管理员 URL 的配置。

    核心逻辑:
        1. 优先读取 ``QUEUE_CONTROL_DEPLOY_ADMIN_MYSQL_URL``。
        2. 未配置时沿用目标应用账号，适合账号已具备建库权限的环境。
    """
    base = settings or SyncSettings.from_environment()
    resolved_admin_url = admin_url or os.getenv("QUEUE_CONTROL_DEPLOY_ADMIN_MYSQL_URL")
    return replace(base, target_mysql_url=resolved_admin_url) if resolved_admin_url else base


def main() -> None:
    """提供 ``python -m queue_control_deploy.migrations.apply`` 命令。"""
    parser = argparse.ArgumentParser(description="创建 queue_control_deploy 数据库和全部表")
    parser.add_argument("--admin-url", help="具备建库权限的 MySQL URL；缺省使用目标应用账号或环境变量")
    args = parser.parse_args()
    executed = apply_migrations(admin_url=args.admin_url)
    print("applied migrations:")
    for filename in executed:
        print(f"- {filename}")
    if not executed:
        print("- none (all migrations already applied)")


if __name__ == "__main__":
    main()

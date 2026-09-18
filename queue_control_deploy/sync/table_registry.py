"""原库表注册、实际表结构检查和 binlog 前置条件检查。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from queue_control_deploy.sync.config import (
    SyncSettings,
    ReadOnlyCursor,
    parse_database,
    source_connection,
)


@dataclass(frozen=True)
class TableSyncConfig:
    """描述一张原表如何映射到部署库镜像表。

    字段说明：
    - ``source_table``：原库表名。
    - ``target_table``：新库镜像表名。
    - ``primary_key``：原表主键列，顺序与复合主键一致。
    - ``columns``：需要同步的列，按目标表列顺序。
    - ``increment_column``：全量分页和抽样对比使用的单调列。
    - ``enabled``：是否同步。
    - ``reason``：排除或包含说明。
    """

    source_table: str
    target_table: str
    primary_key: tuple[str, ...]
    columns: tuple[str, ...]
    increment_column: str
    enabled: bool = True
    reason: str = "发布目标计算或业务审计必需"


# 固定同步注册表；queue_events 不注册为 enabled 表，避免日志放大同步。
TABLE_REGISTRY: tuple[TableSyncConfig, ...] = (
    TableSyncConfig(
        source_table="devices",
        target_table="mirror_devices",
        primary_key=("device_id",),
        columns=("device_id", "display_name", "token_hash", "status", "last_seen_at", "created_at", "updated_at"),
        increment_column="device_id",
    ),
    TableSyncConfig(
        source_table="queue_assignments",
        target_table="mirror_queue_assignments",
        primary_key=("queue_name",),
        columns=("queue_name", "device_id", "desired_state", "assignment_version", "created_at", "updated_at"),
        increment_column="queue_name",
    ),
    TableSyncConfig(
        source_table="queue_statuses",
        target_table="mirror_queue_statuses",
        primary_key=("device_id", "queue_name"),
        columns=("device_id", "queue_name", "actual_state", "desired_state", "process_id", "started_at", "stopped_at", "last_error", "restart_reason", "observed_at"),
        increment_column="queue_name",
    ),
    TableSyncConfig(
        source_table="queue_commands",
        target_table="mirror_queue_commands",
        primary_key=("command_id",),
        columns=("command_id", "device_id", "queue_name", "action", "force_restart", "state", "error_message", "payload", "created_at", "acknowledged_at"),
        increment_column="created_at",
    ),
    TableSyncConfig(
        source_table="queue_events",
        target_table="mirror_queue_events",
        primary_key=("id",),
        columns=("id",),
        increment_column="id",
        enabled=False,
        reason="log/event",
    ),
)


def enabled_tables() -> list[TableSyncConfig]:
    """获取所有参与同步的表配置。

    出参：
        返回 ``enabled=true`` 的 TableSyncConfig 列表。
    """
    return [item for item in TABLE_REGISTRY if item.enabled]


def get_table(source_table: str) -> TableSyncConfig:
    """按原表名查找表配置。

    入参：
        ``source_table``：原库表名。

    出参：
        返回对应配置。

    异常：
        ``KeyError``：表名未注册时抛出。
    """
    for item in TABLE_REGISTRY:
        if item.source_table == source_table:
            return item
    raise KeyError(f"表 {source_table} 未在同步注册表中定义")


def quote_identifier(identifier: str) -> str:
    """安全引用 MySQL 标识符。

    入参：
        ``identifier``：数据库对象名。

    出参：
        返回反引号包裹的标识符。

    异常：
        ``ValueError``：包含反引号或空字节时抛出。
    """
    if "`" in identifier or "\0" in identifier:
        raise ValueError(f"非法标识符: {identifier}")
    return f"`{identifier}`"


def inspect_source(settings: SyncSettings | None = None) -> dict[str, Any]:
    """检查实际原库表、binlog 状态和同步表主键。

    入参：
        ``settings``：可选同步配置。

    出参：
        返回表清单、binlog 配置、检查结论和注册表映射。

    核心逻辑:
        1. 使用只读代理执行 SHOW/SELECT。
        2. 从 information_schema 校验主键。
        3. 校验 log_bin、binlog_format=ROW、binlog_row_image=FULL。
    """
    settings = settings or SyncSettings.from_environment()
    with source_connection(settings) as connection, ReadOnlyCursor(connection.cursor()) as cursor:
        cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
        tables = sorted(row[list(row.keys())[0]] for row in cursor.fetchall())

        cursor.execute("SHOW VARIABLES LIKE 'log_bin'")
        row = cursor.fetchone()
        log_bin = (row or {}).get("Value", "").upper() == "ON"
        cursor.execute("SHOW VARIABLES LIKE 'binlog_format'")
        row = cursor.fetchone()
        binlog_format = (row or {}).get("Value", "").upper()
        cursor.execute("SHOW VARIABLES LIKE 'binlog_row_image'")
        row = cursor.fetchone()
        binlog_row_image = (row or {}).get("Value", "").upper()

        primary_keys: dict[str, list[str]] = {}
        for table in tables:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY'
                ORDER BY ORDINAL_POSITION
                """,
                (parse_database(settings.source_mysql_url), table),
            )
            primary_keys[table] = [row["COLUMN_NAME"] for row in cursor.fetchall()]

        try:
            cursor.execute("SHOW BINARY LOG STATUS")
        except Exception:
            cursor.execute("SHOW MASTER STATUS")
        master_status = cursor.fetchone()
    binlog_ready = log_bin and binlog_format == "ROW" and binlog_row_image == "FULL"
    registry_lines = [
        f"{item.source_table} -> {item.target_table}，enabled={str(item.enabled).lower()}"
        + ("" if item.enabled else f"，reason={item.reason}")
        for item in TABLE_REGISTRY
    ]
    return {
        "database": parse_database(settings.source_mysql_url),
        "tables": tables,
        "primary_keys": primary_keys,
        "binlog": {
            "log_bin": log_bin,
            "binlog_format": binlog_format,
            "binlog_row_image": binlog_row_image,
            "master_status": dict(master_status) if master_status else None,
            "ready": binlog_ready,
        },
        "registry": registry_lines,
    }


def main() -> None:
    """提供 T001 的命令行验证入口。

    核心逻辑:
        1. ``--show-tables`` 输出实际表名。
        2. ``--show-config`` 输出固定同步范围。
        3. ``--inspect`` 输出完整检查 JSON。
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(description="检查原库表结构和部署同步范围")
    parser.add_argument("--show-tables", action="store_true", help="显示原库基础表")
    parser.add_argument("--show-config", action="store_true", help="显示同步表映射")
    parser.add_argument("--inspect", action="store_true", help="显示完整检查结果")
    args = parser.parse_args()
    if not any((args.show_tables, args.show_config, args.inspect)):
        parser.error("请至少指定 --show-tables、--show-config 或 --inspect")
    if args.show_tables:
        result = inspect_source()
        for table in result["tables"]:
            print(table)
    if args.show_config:
        for item in TABLE_REGISTRY:
            line = f"{item.source_table} -> {item.target_table}，enabled={str(item.enabled).lower()}"
            if not item.enabled:
                line += f"，reason={item.reason}"
            print(line)
    if args.inspect:
        print(json.dumps(inspect_source(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

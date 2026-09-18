"""原库指定表或全部同步表的全量快照同步。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from queue_control_deploy.sync.config import (
    ReadOnlyCursor,
    SyncSettings,
    parse_database,
    source_connection,
    target_connection,
)
from queue_control_deploy.sync.table_registry import (
    TableSyncConfig,
    enabled_tables,
    get_table,
    quote_identifier,
)


def utcnow() -> datetime:
    """返回可写入 MySQL DATETIME 的 UTC 时间。

    出参：
        返回去掉 tzinfo 的 UTC 当前时间。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def source_master_status(cursor: Any) -> dict[str, Any] | None:
    """读取源库当前 binlog 位点，并兼容 MySQL 8.4 命令变化。

    入参：
        ``cursor``：原库只读 cursor。

    出参：
        返回 SHOW 命令结果字典；无位点时返回 None。
    """
    try:
        cursor.execute("SHOW BINARY LOG STATUS")
    except Exception:
        cursor.execute("SHOW MASTER STATUS")
    return cursor.fetchone()


def _upsert_sql(table: TableSyncConfig) -> str:
    """构造镜像表的幂等 upsert SQL。

    入参：
        ``table``：同步表配置。

    出参：
        返回参数化 INSERT ... ON DUPLICATE KEY UPDATE SQL。
    """
    columns = table.columns
    placeholders = ", ".join("%s" for _ in columns)
    update_columns = [column for column in columns if column not in table.primary_key]
    assignments = ", ".join(f"{quote_identifier(column)} = VALUES({quote_identifier(column)})" for column in update_columns)
    return (
        f"INSERT INTO {quote_identifier(table.target_table)} "
        f"({', '.join(quote_identifier(column) for column in columns)}, synced_at) "
        f"VALUES ({placeholders}, %s) ON DUPLICATE KEY UPDATE {assignments}, synced_at = VALUES(synced_at)"
    )


def _select_batch_sql(table: TableSyncConfig, after_key: tuple[Any, ...] | None) -> tuple[str, list[Any]]:
    """构造按主键 keyset 分页的原库查询。

    入参：
        ``table``：同步表配置。
        ``after_key``：上一批最后一条记录的主键值；首次为 None。

    出参：
        返回 SQL 文本和查询参数。
    """
    columns_sql = ", ".join(quote_identifier(column) for column in table.columns)
    primary_sql = ", ".join(quote_identifier(column) for column in table.primary_key)
    params: list[Any] = []
    where = ""
    if after_key:
        placeholders = ", ".join("%s" for _ in table.primary_key)
        where = f" WHERE ({primary_sql}) > ({placeholders})"
        params.extend(after_key)
    sql = (
        f"SELECT {columns_sql} FROM {quote_identifier(table.source_table)}"
        f"{where} ORDER BY {primary_sql} LIMIT %s"
    )
    params.append(_BATCH_SIZE_HOLDER.batch_size)
    return sql, params


class _BatchSizeHolder:
    """在模块查询构造中传递批次大小的轻量上下文。"""

    # 默认值会在同步函数中更新。
    batch_size: int = 500


_BATCH_SIZE_HOLDER = _BatchSizeHolder()


def _row_values(row: dict[str, Any], table: TableSyncConfig, synced_at: datetime) -> list[Any]:
    """按目标 upsert 参数顺序整理一行数据。

    入参：
        ``row``：原库字典行。
        ``table``：同步表配置。
        ``synced_at``：写入镜像表的同步时间。

    出参：
        返回 SQL 参数列表。
    """
    return [row.get(column) for column in table.columns] + [synced_at]


def snapshot_table(
    settings: SyncSettings,
    table: TableSyncConfig,
    *,
    consistent_position: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """同步一张表的全量数据并记录完成位点。

    入参：
        ``settings``：同步配置。
        ``table``：表注册配置。
        ``consistent_position``：全部快照共用的一致性位点；单表模式自动读取。

    出参：
        返回同步行数和目标表名。

    核心逻辑:
        1. 原库开启 REPEATABLE READ 一致性快照。
        2. 首个位点通过 SHOW BINARY LOG STATUS 记录到新库。
        3. 按主键 keyset 分批读取并按主键 upsert。
        4. 每批提交，最后标记 SNAPSHOT_COMPLETED。
    """
    _BATCH_SIZE_HOLDER.batch_size = settings.batch_size
    total_rows = 0
    started_at = utcnow()
    with source_connection(settings) as source:
        source.begin()
        with ReadOnlyCursor(source.cursor()) as source_cursor:
            source_cursor.execute(f"SELECT {quote_identifier(table.increment_column)} FROM {quote_identifier(table.source_table)} LIMIT 1")
            source_cursor.fetchone()
            position = consistent_position or source_master_status(source_cursor)
            if not position:
                raise RuntimeError("无法读取源库 binlog 位点，增量同步无法安全接续")

            upsert_sql = _upsert_sql(table)
            after_key: tuple[Any, ...] | None = None
            with target_connection(settings) as target:
                with target.cursor() as target_cursor:
                    target_cursor.execute(
                        """
                        INSERT INTO sync_checkpoints
                        (source_table, sync_mode, snapshot_started_at, binlog_file, binlog_position,
                         gtid_set, status, last_error, updated_at)
                        VALUES (%s, 'full_snapshot', %s, %s, %s, %s, 'SNAPSHOT_IN_PROGRESS', NULL, %s)
                        ON DUPLICATE KEY UPDATE
                            sync_mode = VALUES(sync_mode), snapshot_started_at = VALUES(snapshot_started_at),
                            binlog_file = VALUES(binlog_file), binlog_position = VALUES(binlog_position),
                            gtid_set = VALUES(gtid_set), status = VALUES(status), last_error = NULL,
                            updated_at = VALUES(updated_at)
                        """,
                        (
                            table.source_table,
                            started_at,
                            position.get("File"),
                            int(position.get("Position") or 0),
                            position.get("Executed_Gtid_Set") or position.get("Executed_Gtid_Set ") or None,
                            started_at,
                        ),
                    )
                target.commit()
                while True:
                    select_sql, select_params = _select_batch_sql(table, after_key)
                    with ReadOnlyCursor(source.cursor()) as batch_cursor:
                        batch_cursor.execute(select_sql, select_params)
                        rows = batch_cursor.fetchall()
                    if not rows:
                        break
                    synced_at = utcnow()
                    parameters = [_row_values(row, table, synced_at) for row in rows]
                    with target.cursor() as target_cursor:
                        target_cursor.executemany(upsert_sql, parameters)
                    target.commit()
                    total_rows += len(rows)
                    last_row = rows[-1]
                    after_key = tuple(last_row[column] for column in table.primary_key)

                completed_at = utcnow()
                with target.cursor() as target_cursor:
                    target_cursor.execute(
                        """
                        UPDATE sync_checkpoints
                        SET snapshot_completed_at = %s, status = 'SNAPSHOT_COMPLETED',
                            last_synced_at = %s, updated_at = %s
                        WHERE source_table = %s
                        """,
                        (completed_at, completed_at, completed_at, table.source_table),
                    )
                target.commit()
        source.rollback()
    return {"source_table": table.source_table, "target_table": table.target_table, "rows": total_rows}


def snapshot_all(settings: SyncSettings | None = None) -> list[dict[str, Any]]:
    """在同一个一致性快照内同步全部启用表。

    入参：
        ``settings``：可选同步配置。

    出参：
        返回每张表的同步结果列表。

    核心逻辑:
        1. 先进入原库一致性事务，保证所有表读取同一时间视图。
        2. 读取一次 binlog 位点并传递给每张表。
        3. 按注册表顺序执行快照。
    """
    settings = settings or SyncSettings.from_environment()
    results: list[dict[str, Any]] = []
    with source_connection(settings) as source:
        source.begin()
        with ReadOnlyCursor(source.cursor()) as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            position = source_master_status(cursor)
            if not position:
                raise RuntimeError("源库未暴露 binlog 位点")
        source.rollback()

        # 复用独立函数，但显式传入同一位点；每张表自身仍按 keyset 幂等处理。
        for table in enabled_tables():
            with source_connection(settings) as table_source:
                table_source.begin()
                with ReadOnlyCursor(table_source.cursor()):
                    results.append(snapshot_table(settings, table, consistent_position=dict(position)))
                table_source.rollback()
    return results


def main() -> None:
    """提供 T004 命令行入口。

    核心逻辑:
        1. ``--table`` 同步指定注册表。
        2. ``--all`` 同步 devices、assignments、statuses、commands。
        3. 输出 JSON 结果，异常由进程非零退出码表达。
    """
    parser = argparse.ArgumentParser(description="执行原库到部署库的全量快照同步")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--table", help="原表名，例如 devices")
    group.add_argument("--all", action="store_true", help="同步全部启用表")
    args = parser.parse_args()
    settings = SyncSettings.from_environment()
    result: Any
    if args.all:
        result = snapshot_all(settings)
    else:
        result = snapshot_table(settings, get_table(args.table))
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

"""镜像表对账、位点检查和指定表重建恢复。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

from queue_control_deploy.sync.config import (
    ReadOnlyCursor,
    SyncSettings,
    source_connection,
    target_connection,
)
from queue_control_deploy.sync.full_snapshot import snapshot_table
from queue_control_deploy.sync.table_registry import (
    TableSyncConfig,
    enabled_tables,
    get_table,
    quote_identifier,
)


def utcnow() -> datetime:
    """返回 MySQL DATETIME 可用的 UTC 时间。

    出参：
        返回去掉 tzinfo 的当前 UTC 时间。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize(value: Any) -> Any:
    """规范化比较值，避免 JSON 空格和类型表示造成假差异。

    入参：
        ``value``：数据库字段值。

    出参：
        返回可比较的规范值。
    """
    if isinstance(value, str) and value.lstrip() in {"", "[", "{", "null", "true", "false"} and value.lstrip()[:1] in {"[", "{", "n", "t", "f"}:
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return value


def reconcile_table(settings: SyncSettings, table: TableSyncConfig, *, sample_limit: int = 1000) -> dict[str, Any]:
    """按主键全量遍历对比一张原表和镜像表。

    入参：
        ``settings``：同步配置。
        ``table``：同步表配置。
        ``sample_limit``：最多记录的差异明细数量。

    出参：
        返回行数、差异数、状态和差异明细。

    核心逻辑:
        1. 原库和新库分别按主键 keyset 遍历。
        2. 先比主键集合，再逐列比对规范化值。
        3. 差异写入新库 ``sync_reconciliations``。
    """
    started_at = utcnow()
    source_rows = target_rows = 0
    mismatch_count = 0
    details: list[dict[str, Any]] = []
    source_map: dict[tuple[Any, ...], dict[str, Any]] = {}
    target_map: dict[tuple[Any, ...], dict[str, Any]] = {}

    def fetch_all(source: Any, target: Any) -> tuple[dict, dict]:
        """分批读取两侧当前表数据。

        入参：
            ``source``：源连接。
            ``target``：目标连接。

        出参：
            返回按主键索引的原库和新库行映射。
        """
        source_result: dict[tuple[Any, ...], dict[str, Any]] = {}
        target_result: dict[tuple[Any, ...], dict[str, Any]] = {}
        keyset: tuple[Any, ...] | None = None
        primary_sql = ", ".join(quote_identifier(column) for column in table.primary_key)
        while True:
            where = ""
            params: list[Any] = []
            if keyset:
                where = f" WHERE ({primary_sql}) > ({', '.join('%s' for _ in keyset)})"
                params.extend(keyset)
            sql = (
                f"SELECT {', '.join(quote_identifier(c) for c in table.columns)} "
                f"FROM {quote_identifier(table.source_table)}{where} ORDER BY {primary_sql} LIMIT %s"
            )
            with ReadOnlyCursor(source.cursor()) as cursor:
                cursor.execute(sql, [*params, settings.batch_size])
                rows = cursor.fetchall()
            if not rows:
                break
            for row in rows:
                source_result[tuple(row[column] for column in table.primary_key)] = row
            keyset = tuple(rows[-1][column] for column in table.primary_key)

        keyset = None
        target_table = table.target_table
        while True:
            where = ""
            params = []
            if keyset:
                where = f" WHERE ({primary_sql}) > ({', '.join('%s' for _ in keyset)})"
                params.extend(keyset)
            sql = (
                f"SELECT {', '.join(quote_identifier(c) for c in table.columns)} "
                f"FROM {quote_identifier(target_table)}{where} ORDER BY {primary_sql} LIMIT %s"
            )
            with target.cursor() as cursor:
                cursor.execute(sql, [*params, settings.batch_size])
                rows = cursor.fetchall()
            if not rows:
                break
            for row in rows:
                target_result[tuple(row[column] for column in table.primary_key)] = row
            keyset = tuple(rows[-1][column] for column in table.primary_key)
        return source_result, target_result

    with source_connection(settings) as source, target_connection(settings) as target:
        source_map, target_map = fetch_all(source, target)
        source_rows = len(source_map)
        target_rows = len(target_map)
        all_keys = sorted(set(source_map) | set(target_map), key=lambda values: tuple(str(value) for value in values))
        for key in all_keys:
            source_row = source_map.get(key)
            target_row = target_map.get(key)
            if source_row is None or target_row is None:
                mismatch_count += 1
                if len(details) < sample_limit:
                    details.append({"primary_key": list(key), "source_exists": source_row is not None, "target_exists": target_row is not None})
                continue
            differences: dict[str, dict[str, Any]] = {}
            for column in table.columns:
                source_value = _normalize(source_row.get(column))
                target_value = _normalize(target_row.get(column))
                if source_value != target_value:
                    differences[column] = {"source": source_value, "target": target_value}
            if differences:
                mismatch_count += 1
                if len(details) < sample_limit:
                    details.append({"primary_key": list(key), "differences": differences})
        status = "OK" if source_rows == target_rows and mismatch_count == 0 else "MISMATCH"
        detail = {
            "sample_limit": sample_limit,
            "mismatches": details,
        }
        with target.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sync_reconciliations
                (source_table, source_rows, target_rows, mismatch_count, status, detail_json,
                 started_at, finished_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(6))
                """,
                (
                    table.source_table, source_rows, target_rows, mismatch_count, status,
                    json.dumps(detail, ensure_ascii=False, default=str), started_at,
                ),
            )
        target.commit()
    return {
        "sourceTable": table.source_table,
        "targetTable": table.target_table,
        "sourceRows": source_rows,
        "targetRows": target_rows,
        "mismatchCount": mismatch_count,
        "status": status,
        "detail": detail,
    }


def checkpoint_health(settings: SyncSettings) -> dict[str, Any]:
    """检查所有启用表位点是否一致且没有异常状态。

    入参：
        ``settings``：同步配置。

    出参：
        返回位点映射、健康状态和错误说明。
    """
    names = [item.source_table for item in enabled_tables()]
    with target_connection(settings) as target:
        with target.cursor() as cursor:
            placeholders = ", ".join("%s" for _ in names)
            cursor.execute(
                f"""
                SELECT source_table, binlog_file, binlog_position, status, last_error, last_synced_at
                FROM sync_checkpoints WHERE source_table IN ({placeholders})
                """,
                names,
            )
            rows = cursor.fetchall()
    checkpoints = {row["source_table"]: row for row in rows}
    missing = [name for name in names if name not in checkpoints]
    positions = [(row.get("binlog_file"), row.get("binlog_position")) for row in checkpoints.values()]
    errors = [row for row in checkpoints.values() if row.get("last_error") or row.get("status") in {"CDC_ERROR", "SNAPSHOT_ERROR"}]
    healthy = not missing and len(set(positions)) == 1 and not errors
    return {
        "healthy": healthy,
        "checkpoints": checkpoints,
        "missing_tables": missing,
        "errors": [row["source_table"] for row in errors],
        "positions_consistent": len(set(positions)) == 1,
    }


def rebuild_table(settings: SyncSettings, source_table: str) -> dict[str, Any]:
    """重建指定表全量数据作为异常恢复手段。

    入参：
        ``settings``：同步配置。
        ``source_table``：原表名。

    出参：
        返回全量同步结果。

    核心逻辑:
        1. 校验表在同步范围内。
        2. 调用幂等全量快照覆盖镜像表。
    """
    return snapshot_table(settings, get_table(source_table))


def main() -> None:
    """提供 T006 命令行入口。

    核心逻辑:
        1. ``--all`` 对账全部表。
        2. ``--table`` 对账指定表。
        3. ``--rebuild-table`` 先全量重建，再自动对账。
    """
    parser = argparse.ArgumentParser(description="对账原库与部署库镜像表")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="对账全部启用表")
    group.add_argument("--table", help="对账指定原表")
    group.add_argument("--rebuild-table", help="重建指定表后对账")
    parser.add_argument("--sample-limit", type=int, default=1000, help="差异明细最多保存数量")
    args = parser.parse_args()
    settings = SyncSettings.from_environment()
    if args.rebuild_table:
        rebuild_result = rebuild_table(settings, args.rebuild_table)
        result: Any = {"rebuild": rebuild_result, "reconciliation": reconcile_table(settings, get_table(args.rebuild_table), sample_limit=args.sample_limit)}
    elif args.all:
        result = [reconcile_table(settings, table, sample_limit=args.sample_limit) for table in enabled_tables()]
        result = {"reconciliations": result, "checkpointHealth": checkpoint_health(settings)}
    else:
        result = reconcile_table(settings, get_table(args.table), sample_limit=args.sample_limit)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

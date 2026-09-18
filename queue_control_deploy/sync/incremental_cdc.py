"""基于 MySQL ROW binlog 的镜像表增量同步。"""
from __future__ import annotations

import argparse
import json
import os
import signal
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse

from queue_control_deploy.sync.config import SyncSettings, parse_database, target_connection
from queue_control_deploy.sync.table_registry import (
    TableSyncConfig,
    enabled_tables,
    get_table,
    quote_identifier,
)


class _StopSync(Exception):
    """内部信号，用于优雅结束非阻塞同步。"""


class IncrementalSyncer:
    """消费 binlog ROW 事件并将变更幂等写入镜像表。

    核心职责：
    - 只消费注册表事件，queue_events 天然被过滤。
    - INSERT/UPDATE upsert，DELETE 按主键删除。
    - 事务内行变更与位点在 XidEvent 提交，避免半事务位点。
    """

    def __init__(
        self,
        settings: SyncSettings,
        *,
        server_id: int,
        blocking: bool = True,
        max_events: int | None = None,
    ):
        """初始化增量同步器。

        入参：
            ``settings``：同步配置。
            ``server_id``：MySQL 复制协议中的唯一 server_id。
            ``blocking``：True 时长期阻塞消费；False 便于测试。
            ``max_events``：最多处理的事件数，测试或单步消费用。
        """
        self.settings = settings
        self.server_id = server_id
        self.blocking = blocking
        self.max_events = max_events
        self.tables = {item.source_table: item for item in enabled_tables()}
        self._stop_requested = False

    def _register_signal(self) -> None:
        """注册 SIGINT/SIGTERM 优雅停止。"""
        def handler(signum: int, frame: Any) -> None:
            self._stop_requested = True

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def _connection_settings(self) -> dict[str, Any]:
        """把源 MySQL URL 转成 mysql-replication 所需参数。

        出参：
            返回包含 host、port、user、passwd、charset 的字典。
        """
        parsed = urlparse(self.settings.source_mysql_url)
        return {
            "host": parsed.hostname,
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or ""),
            "passwd": unquote(parsed.password or ""),
            "charset": "utf8mb4",
            "connect_timeout": self.settings.connect_timeout,
        }

    def _control_connection_settings(self) -> dict[str, Any]:
        """构造 binlog 解码所需 information_schema 控制连接参数。

        出参：
            返回带默认 database 的源连接字典。

        核心逻辑:
            mysql-replication 使用控制连接读取列元数据，仍只查询原库结构。
        """
        return {**self._connection_settings(), "database": parse_database(self.settings.source_mysql_url)}

    def _ordered_values(self, values: dict[str, Any], table: TableSyncConfig) -> list[Any]:
        """按注册表列顺序整理 binlog 行值。

        入参：
            ``values``：mysql-replication 解码后的字段字典。
            ``table``：同步表配置。

        出参：
            返回与 ``table.columns`` 一一对应的值列表。

        核心逻辑:
            当源库 ``binlog_row_metadata=MINIMAL`` 时，库包会返回
            ``UNKNOWN_COL0`` 等序号列；ROW FULL 事件仍按表列顺序携带值，
            这里按注册表列顺序映射，不要求生产库改元数据配置。
        """
        keys = list(values)
        if keys and keys[0].startswith("UNKNOWN_COL"):
            return [values.get(f"UNKNOWN_COL{index}") for index in range(len(table.columns))]
        return [values.get(column) for column in table.columns]

    def _json_text(self, value: Any) -> Any:
        """把对象值安全转为 MySQL JSON 可接收文本。

        入参：
            ``value``：binlog 解码后的字段值。

        出参：
            返回原始值或 JSON 字符串。
        """
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (dict, list)) else value

    def _upsert_sql(self, table: TableSyncConfig) -> str:
        """构造目标镜像表 upsert SQL。

        入参：
            ``table``：同步表配置。

        出参：
            返回 INSERT ... ON DUPLICATE KEY UPDATE SQL。
        """
        columns = table.columns
        update_columns = [column for column in columns if column not in table.primary_key]
        assignments = ", ".join(
            f"{quote_identifier(column)} = VALUES({quote_identifier(column)})" for column in update_columns
        )
        return (
            f"INSERT INTO {quote_identifier(table.target_table)} "
            f"({', '.join(quote_identifier(column) for column in columns)}, synced_at) "
            f"VALUES ({', '.join('%s' for _ in columns)}, %s) "
            f"ON DUPLICATE KEY UPDATE {assignments}, synced_at = VALUES(synced_at)"
        )

    def _apply_row_event(self, cursor: Any, event: Any) -> int:
        """应用一个 ROW 事件包含的全部行变更。

        入参：
            ``cursor``：新库 cursor。
            ``event``：WriteRowsEvent/UpdateRowsEvent/DeleteRowsEvent。

        出参：
            返回处理行数。

        异常：
            ``KeyError``：事件表未注册时抛出。
        """
        table = self.tables.get(event.table)
        if not table or event.schema != parse_database(self.settings.source_mysql_url):
            return 0
        synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
        processed = 0
        for row in event.rows:
            if isinstance(event, _WRITE_EVENT):
                values = row["values"]
                cursor.execute(self._upsert_sql(table), [self._json_text(value) for value in self._ordered_values(values, table)] + [synced_at])
            elif isinstance(event, _UPDATE_EVENT):
                values = row["after_values"]
                cursor.execute(self._upsert_sql(table), [self._json_text(value) for value in self._ordered_values(values, table)] + [synced_at])
            elif isinstance(event, _DELETE_EVENT):
                values = row["values"]
                where = " AND ".join(f"{quote_identifier(column)} = %s" for column in table.primary_key)
                cursor.execute(
                    f"DELETE FROM {quote_identifier(table.target_table)} WHERE {where}",
                    tuple(self._ordered_values(values, table)[table.columns.index(column)] for column in table.primary_key),
                )
            else:
                continue
            processed += 1
        return processed

    def _save_checkpoint(self, cursor: Any, checkpoint: dict[str, Any], error: str | None = None) -> None:
        """保存一个表的同步状态和位点。

        入参：
            ``cursor``：新库 cursor。
            ``checkpoint``：包含 source_table/log_file/log_pos/timestamp 的位点。
            ``error``：异常状态写入的错误信息；正常为 None。
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cursor.execute(
            """
            INSERT INTO sync_checkpoints
            (source_table, sync_mode, snapshot_completed_at, binlog_file, binlog_position,
             last_event_time, last_synced_at, status, last_error, updated_at)
            VALUES (%s, 'incremental_cdc', UTC_TIMESTAMP(6), %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                sync_mode = VALUES(sync_mode), binlog_file = VALUES(binlog_file),
                binlog_position = VALUES(binlog_position), last_event_time = VALUES(last_event_time),
                last_synced_at = VALUES(last_synced_at), status = VALUES(status),
                last_error = VALUES(last_error), updated_at = VALUES(updated_at)
            """,
            (
                checkpoint["source_table"], checkpoint["log_file"], int(checkpoint["log_pos"]),
                checkpoint.get("event_time"), now, "CDC_ERROR" if error else "CDC_STREAMING",
                error, now,
            ),
        )

    def load_checkpoints(self, connection: Any) -> dict[str, tuple[str | None, int | None]]:
        """从新库加载每个表的恢复位点。

        入参：
            ``connection``：新库连接。

        出参：
            返回 source_table -> (binlog_file, binlog_position)。

        异常：
            ``RuntimeError``：各表位点不一致时抛出，避免错误消费。
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT source_table, binlog_file, binlog_position FROM sync_checkpoints")
            rows = cursor.fetchall()
        checkpoints = {
            row["source_table"]: (row["binlog_file"], int(row["binlog_position"]) if row["binlog_position"] is not None else None)
            for row in rows
            if row["source_table"] in self.tables
        }
        missing = [name for name in self.tables if name not in checkpoints]
        if missing:
            raise RuntimeError(f"缺少全量快照位点，请先执行 full_snapshot --all: {','.join(missing)}")
        positions = set(checkpoints.values())
        if len(positions) != 1:
            raise RuntimeError(f"同步表 binlog 位点不一致: {checkpoints}")
        return checkpoints

    def run_once(self) -> int:
        """执行一轮可结束的 binlog 消费。

        出参：
            返回处理事件数。

        核心逻辑:
            1. 校验并加载统一全量位点。
            2. 打开 binlog 流和新库事务。
            3. 行事件写入目标，XidEvent 时提交数据和位点。
            4. 阻塞模式下由信号打断；非阻塞模式流结束即返回。
        """
        from pymysqlreplication import BinLogStreamReader
        from pymysqlreplication.event import XidEvent
        from pymysqlreplication.row_event import (
            DeleteRowsEvent,
            UpdateRowsEvent,
            WriteRowsEvent,
        )

        global _WRITE_EVENT, _UPDATE_EVENT, _DELETE_EVENT
        _WRITE_EVENT, _UPDATE_EVENT, _DELETE_EVENT = WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent

        target_conn = None
        stream = None
        processed = 0
        try:
            with target_connection(self.settings) as target_conn:
                checkpoints = self.load_checkpoints(target_conn)
                log_file, log_pos = next(iter(checkpoints.values()))
                if not log_file or log_pos is None:
                    raise RuntimeError("全量快照位点为空")

                stream = BinLogStreamReader(
                    connection_settings=self._connection_settings(),
                    ctl_connection_settings=self._control_connection_settings(),
                    server_id=self.server_id,
                    resume_stream=True,
                    blocking=self.blocking,
                    only_events=[WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent, XidEvent],
                    log_file=log_file,
                    log_pos=log_pos,
                    only_schemas=[parse_database(self.settings.source_mysql_url)],
                    only_tables=set(self.tables),
                    verify_checksum=True,
                    slave_heartbeat=max(1, self.settings.connect_timeout),
                )
                position = {"log_file": log_file, "log_pos": log_pos}
                checkpoint: dict[str, Any] | None = position
                with target_conn.cursor() as cursor:
                    while not self._stop_requested:
                        if self.max_events is not None and processed >= self.max_events:
                            break
                        event = stream.fetchone()
                        if event is None:
                            break
                        if isinstance(event, XidEvent):
                            # stream.log_pos 已指向当前事务结束位点。
                            position.update(
                                log_file=stream.log_file,
                                log_pos=stream.log_pos,
                                event_time=datetime.fromtimestamp(event.timestamp, timezone.utc).replace(tzinfo=None),
                            )
                            # 每张启用表共享同一事务结束位点，重启后可作为统一恢复点。
                            for table_config in enabled_tables():
                                self._save_checkpoint(
                                    cursor,
                                    {"source_table": table_config.source_table, **position},
                                )
                            target_conn.commit()
                            processed += 1
                            continue
                        changed = self._apply_row_event(cursor, event)
                        if changed:
                            processed += 1
                # 无行事件且未遇到 XidEvent 时不推进位点，保持位点安全。
                target_conn.rollback()
        except Exception as exc:
            # 上面的 with 已回滚并关闭失败事务；另开连接只记录错误状态，不推进位点。
            try:
                with target_connection(self.settings) as error_conn:
                    with error_conn.cursor() as cursor:
                        for table_config in enabled_tables():
                            self._save_checkpoint(
                                cursor,
                                {
                                    "source_table": table_config.source_table,
                                    "log_file": checkpoint.get("log_file") if checkpoint else None,
                                    "log_pos": checkpoint.get("log_pos") if checkpoint else None,
                                },
                                error=str(exc),
                            )
                    error_conn.commit()
            except Exception:
                pass
            raise
        finally:
            if stream is not None:
                stream.close()
        return processed

    def run_forever(self) -> None:
        """长期消费增量事件，异常后记录错误并按固定间隔重试。"""
        import time

        self._register_signal()
        retry_seconds = int(os.getenv("DEPLOY_SYNC_CDC_RETRY_SECONDS", "5"))
        while not self._stop_requested:
            try:
                count = self.run_once()
                if not self.blocking and count == 0 and not self._stop_requested:
                    time.sleep(retry_seconds)
            except Exception:
                if self._stop_requested:
                    break
                time.sleep(retry_seconds)


_WRITE_EVENT: Any = None
_UPDATE_EVENT: Any = None
_DELETE_EVENT: Any = None


def main() -> None:
    """提供 T005 命令行入口。"""
    parser = argparse.ArgumentParser(description="消费 MySQL binlog 并实时同步镜像表")
    parser.add_argument("--server-id", type=int, default=int(os.getenv("DEPLOY_SYNC_SERVER_ID", "91001")), help="复制 client 的唯一 server_id")
    parser.add_argument("--non-blocking", action="store_true", help="没有事件时结束，而不是保持实时流")
    parser.add_argument("--max-events", type=int, default=None, help="最多处理事件数量，用于验证")
    args = parser.parse_args()
    settings = SyncSettings.from_environment()
    syncer = IncrementalSyncer(settings, server_id=args.server_id, blocking=not args.non_blocking, max_events=args.max_events)
    if args.non_blocking:
        print(syncer.run_once())
    else:
        syncer.run_forever()


if __name__ == "__main__":
    main()

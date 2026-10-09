"""幂等建表：RPA 日志模块 3 张 rpa_* 表（DDL 与设计文档 §4.1–4.3 一致）。

可重复执行（CREATE TABLE IF NOT EXISTS），与平台 initialize_schema 同模式。
目标库 = QUEUE_CONTROL_MYSQL_URL 指向的统一库（rpa_platform，库由
queue_control_platform/docker/initdb/01-init.sql 初始化）。

2026-10 表结构精简：删除 rpa_device / rpa_queue 两张维表——
设备/队列统计页改由 rpa_execution 聚合推导，启动时自动清理旧表（数据为可再生的缓存）。
"""

from __future__ import annotations

from .db import db_cursor

DDL_STATEMENTS: tuple[str, ...] = (
    # §4.1 执行记录主表
    """
    CREATE TABLE IF NOT EXISTS rpa_execution (
        id               BIGINT AUTO_INCREMENT PRIMARY KEY,
        rpa_message_id   VARCHAR(64)  NOT NULL COMMENT '消息ID task.rpaMessageId',
        job_id           VARCHAR(64)  NOT NULL DEFAULT '' COMMENT 'JobId: content.jobNo/blNo/bookingNo/shippingNo',
        queue_name       VARCHAR(128) NOT NULL COMMENT '完整队列名 task.rpaTaskTopic',
        device_name      VARCHAR(128) NOT NULL COMMENT '设备名 QUEUE_CONTROL_DEVICE_ID 或主机名',
        task_id          VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '回传 task.id',
        customer_code    VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '由队列名解析',
        carrier_code     VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '由队列名解析',
        business_code    VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '由队列名解析',
        status           VARCHAR(16)  NOT NULL DEFAULT 'RUNNING' COMMENT 'RUNNING/SUCCESS/FAILED/TIMEOUT/DEPRECATED',
        remark           TEXT         NULL COMMENT '失败原因 = TaskResult.remark（仅失败）',
        fail_img_url     VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '失败截图完整地址（存量字段；新记录改用 fail_img_object_name）',
        fail_img_object_name VARCHAR(512) NOT NULL DEFAULT '' COMMENT '失败截图 OSS objectName；查看页经 /v1/file/url 换临时地址',
        log_count        INT          NOT NULL DEFAULT 0 COMMENT '日志条数（冗余计数）',
        started_at       DATETIME(6)  NOT NULL COMMENT '消息接收时间',
        finished_at      DATETIME(6)  NULL COMMENT '结果回传时间（终态写入）',
        duration_seconds INT          NULL COMMENT '耗时（秒）= finished_at - started_at，终态写入',
        create_time      DATETIME(6)  NOT NULL COMMENT '创建时间（列表页展示列）',
        update_time      DATETIME(6)  NOT NULL,
        INDEX idx_message_queue (rpa_message_id, queue_name),
        INDEX idx_job_id (job_id),
        INDEX idx_queue_status_time (queue_name, status, create_time),
        INDEX idx_status_time (status, create_time),
        INDEX idx_device_time (device_name, create_time)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA 执行记录'
    """,
    # §4.2 执行日志明细表
    """
    CREATE TABLE IF NOT EXISTS rpa_execution_log (
        id             BIGINT AUTO_INCREMENT PRIMARY KEY,
        execution_id   BIGINT       NOT NULL,
        seq            BIGINT       NOT NULL COMMENT '执行内递增序号，Agent 侧生成',
        level          VARCHAR(10)  NOT NULL COMMENT 'INFO/WARN/ERROR/SUCCESS',
        message        TEXT         NOT NULL,
        source_file    VARCHAR(255) NOT NULL DEFAULT '' COMMENT '调用位置文件（现有 _caller() 逻辑复用）',
        source_line    INT          NOT NULL DEFAULT 0,
        log_time       DATETIME(3)  NOT NULL COMMENT 'Agent 侧日志产生时间',
        create_time    DATETIME(3)  NOT NULL,
        INDEX idx_exec_seq (execution_id, seq)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA 执行日志明细'
    """,
    # §4.3 记录文件表
    """
    CREATE TABLE IF NOT EXISTS rpa_execution_file (
        id            BIGINT AUTO_INCREMENT PRIMARY KEY,
        execution_id  BIGINT        NOT NULL,
        file_type     VARCHAR(64)   NOT NULL COMMENT 'type: SCREEN_RECORDING_FILE / 业务截图类型',
        media_type    VARCHAR(10)   NOT NULL COMMENT 'VIDEO / IMAGE（按后缀推断）',
        file_name     VARCHAR(255)  NOT NULL,
        url           VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '完整访问地址（OSS 或局域网）；视频 OSS 成功时为空，改用 object_name',
        object_name   VARCHAR(512)  NOT NULL DEFAULT '' COMMENT 'OSS objectName；查看页经 /v1/file/url 换临时地址',
        remark        VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '上传失败等说明（如本地路径）',
        storage       VARCHAR(10)   NOT NULL DEFAULT 'OSS' COMMENT 'OSS / LAN / LOCAL',
        file_size     BIGINT        NOT NULL DEFAULT 0,
        create_time   DATETIME(6)   NOT NULL,
        INDEX idx_exec (execution_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA 执行记录文件'
    """,
    # §4.4 设备/队列维表已删除（2026-10）：统计改由 rpa_execution 聚合，见 repository.list_device_stats。
)

TABLE_NAMES = ("rpa_execution", "rpa_execution_log", "rpa_execution_file")

# 2026-10 精简：设备/队列维表降级为派生数据，启动时清理旧表（幂等）。
_DROP_LEGACY_TABLES: tuple[str, ...] = ("rpa_device", "rpa_queue")

# CREATE TABLE IF NOT EXISTS 不会给存量表加列，启动时补齐 2026-09-30 的 objectName 直存字段。
_FILE_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("object_name", "ALTER TABLE rpa_execution_file ADD COLUMN object_name VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'OSS objectName' AFTER url"),
    ("remark", "ALTER TABLE rpa_execution_file ADD COLUMN remark VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '上传失败等说明' AFTER object_name"),
)

# 2026-10-09：截图链路对齐录屏——失败截图不再存完整 url，改存 objectName 换临时地址。
_EXECUTION_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    (
        "fail_img_object_name",
        "ALTER TABLE rpa_execution ADD COLUMN fail_img_object_name VARCHAR(512) NOT NULL DEFAULT '' "
        "COMMENT '失败截图 OSS objectName' AFTER fail_img_url",
    ),
)


def _existing_columns(cursor, table: str) -> set[str]:
    """查表已存在的列名集合（小写）。"""
    cursor.execute(
        """
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        """,
        (table,),
    )
    return {
        str(row.get("COLUMN_NAME") or row.get("column_name") or list(row.values())[0]).lower()
        for row in cursor.fetchall()
    }


def _ensure_file_columns(cursor) -> None:
    """给已存在的 rpa_execution_file 补 object_name / remark（幂等）。"""
    existing = _existing_columns(cursor, "rpa_execution_file")
    for column, ddl in _FILE_COLUMN_MIGRATIONS:
        if column.lower() not in existing:
            cursor.execute(ddl)


def _ensure_execution_columns(cursor) -> None:
    """给已存在的 rpa_execution 补 fail_img_object_name（幂等）。"""
    existing = _existing_columns(cursor, "rpa_execution")
    for column, ddl in _EXECUTION_COLUMN_MIGRATIONS:
        if column.lower() not in existing:
            cursor.execute(ddl)


def _drop_legacy_dimension_tables(cursor) -> None:
    """删除 rpa_device / rpa_queue 旧维表（幂等；数据可由执行记录再推导）。"""
    for table in _DROP_LEGACY_TABLES:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")


def initialize_schema() -> list[str]:
    """逐条执行幂等 DDL，返回已确认存在的表名。"""
    with db_cursor() as cursor:
        for ddl in DDL_STATEMENTS:
            cursor.execute(ddl)
        _ensure_file_columns(cursor)
        _ensure_execution_columns(cursor)
        _drop_legacy_dimension_tables(cursor)
        cursor.execute("SHOW TABLES")
        return sorted(row[list(row)[0]] for row in cursor.fetchall())


def main() -> None:
    tables = initialize_schema()
    print(f"[init_db] rpa_log schema ready, tables: {', '.join(tables)}")


if __name__ == "__main__":
    main()

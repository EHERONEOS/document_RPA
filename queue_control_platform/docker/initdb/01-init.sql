-- 统一库初始化（幂等，可重复执行）。2026-09 起平台表与 RPA 日志表共用一个库；
-- 2026-10 表结构精简：queue_statuses 并入 queue_assignments、删除 rpa_device/rpa_queue 维表。
-- MySQL 官方镜像仅在空数据卷首次初始化时执行 /docker-entrypoint-initdb.d；
-- 老数据卷由 init_db / initialize_schema 手工补跑，语句本身幂等。
CREATE DATABASE IF NOT EXISTS rpa_platform
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 平台账号读写统一库（QUEUE_CONTROL_MYSQL_URL 指向 rpa_platform）
CREATE USER IF NOT EXISTS 'queue_control'@'%' IDENTIFIED BY 'queue_control';
GRANT ALL PRIVILEGES ON rpa_platform.* TO 'queue_control'@'%';
FLUSH PRIVILEGES;

-- 历史遗留：2026-09 之前的 queue_control / rpa_log 两个旧库已不再使用。
-- 存量环境如需彻底清理，手工执行 cleanup_legacy_databases.sql（先备份）。

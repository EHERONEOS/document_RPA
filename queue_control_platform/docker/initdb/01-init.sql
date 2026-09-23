-- 统一库初始化（幂等，可重复执行）。2026-09 起平台表与 RPA 日志表共用一个库。
-- MySQL 官方镜像仅在空数据卷首次初始化时执行 /docker-entrypoint-initdb.d；
-- 老数据卷由 init_db / 本脚本手工补跑，语句本身幂等。
CREATE DATABASE IF NOT EXISTS rpa_platform
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 平台账号需要能读写统一库（QUEUE_CONTROL_MYSQL_URL 指向 rpa_platform）
CREATE USER IF NOT EXISTS 'queue_control'@'%' IDENTIFIED BY 'queue_control';
GRANT ALL PRIVILEGES ON rpa_platform.* TO 'queue_control'@'%';
-- 兼容保留：历史 queue_control / rpa_log 库的访问授权（存量库未删除）
GRANT ALL PRIVILEGES ON queue_control.* TO 'queue_control'@'%';
GRANT ALL PRIVILEGES ON rpa_log.* TO 'queue_control'@'%';
FLUSH PRIVILEGES;

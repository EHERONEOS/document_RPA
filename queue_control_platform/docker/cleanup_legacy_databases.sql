-- 旧库清理脚本（手工执行，不要放进 initdb 自动目录！）。
--
-- 背景：2026-09 平台表与 RPA 日志表统一进 rpa_platform 库后，早期的
-- queue_control（平台 5 表）与 rpa_log（日志 5 表）两个旧库仅作兼容保留，
-- 代码已不读写。2026-10 表结构精简（queue_statuses 并入 queue_assignments、
-- 删除 rpa_device / rpa_queue）后确认不再回退，可安全清理。
--
-- 用法（中央机 MySQL，先备份再执行）：
--   mysqldump -uroot -p --databases queue_control rpa_log > legacy_backup_$(date +%F).sql
--   mysql -uroot -p < cleanup_legacy_databases.sql
--
-- 表级迁移（queue_statuses → queue_assignments 等）由服务启动时的
-- initialize_schema 自动完成，无需本脚本；本脚本只处理两个整库。
DROP DATABASE IF EXISTS queue_control;
DROP DATABASE IF EXISTS rpa_log;

-- 可选：rpa_platform 库内还有 task_commands / task_events / task_runs 三张
-- 更早期模块的孤儿表（当前代码零引用）。确认无用后取消注释一并清理：
-- USE rpa_platform;
-- DROP TABLE IF EXISTS task_commands;
-- DROP TABLE IF EXISTS task_events;
-- DROP TABLE IF EXISTS task_runs;

-- 回收对旧库的授权（若从未授权过会报 1141 错误，可忽略）。
-- 新初始化的环境（2026-10 后的 01-init.sql）不再授予这两项权限。
REVOKE ALL PRIVILEGES ON `queue_control`.* FROM 'queue_control'@'%';
REVOKE ALL PRIVILEGES ON `rpa_log`.* FROM 'queue_control'@'%';
FLUSH PRIVILEGES;

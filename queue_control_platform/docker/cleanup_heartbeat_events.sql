-- 清理 queue_events 中历史堆积的心跳流水（配合服务端心跳不落库改造）。
--
-- 背景：Agent 每 15 秒上报一次心跳，改造前全部写入 queue_events（纯审计、
-- 无读取方），表无限膨胀。改造上线后新心跳不再落库，本脚本清理存量。
--
-- 用法（连 rpa_platform 库执行，建议低峰期）：
--   mysql -h <host> -u <user> -p rpa_platform < cleanup_heartbeat_events.sql
--
-- 说明：
-- 1. 分批删除（每批 10000 行，批间小睡），避免大事务锁表与主从延迟；
-- 2. 删完后可选执行 OPTIMIZE TABLE 回收磁盘空间（会短暂阻塞写入，低峰执行）；
-- 3. 如只想保留最近 N 天的心跳，把下方 1=1 改为
--    received_at < NOW() - INTERVAL 7 DAY。

DELIMITER $$

DROP PROCEDURE IF EXISTS cleanup_heartbeat_events$$

CREATE PROCEDURE cleanup_heartbeat_events()
BEGIN
    DECLARE affected INT DEFAULT 1;
    WHILE affected > 0 DO
        DELETE FROM queue_events
        WHERE event_type = 'heartbeat' AND 1 = 1
        LIMIT 10000;
        SET affected = ROW_COUNT();
        IF affected > 0 THEN
            DO SLEEP(0.2);  -- 批间让位给业务写入
        END IF;
    END WHILE;
END$$

DELIMITER ;

CALL cleanup_heartbeat_events();
DROP PROCEDURE IF EXISTS cleanup_heartbeat_events;

-- 可选：回收空间（重建表，短暂阻塞写入；磁盘不紧张可跳过）
-- OPTIMIZE TABLE queue_events;

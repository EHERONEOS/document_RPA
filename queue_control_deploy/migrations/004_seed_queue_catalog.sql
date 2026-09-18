-- 写入当前已知船司队列归属；重复执行通过 ON DUPLICATE KEY 保持幂等。
INSERT INTO queue_control_deploy.queue_catalog
(queue_name, release_unit, enabled, description, created_at, updated_at)
VALUES
('QTCT_ZIM_SI', 'carrier:ZIM', TRUE, 'ZIM SI Worker', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
('QTCT_ZIM_VGM', 'carrier:ZIM', TRUE, 'ZIM VGM Worker', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
('FHT_MSCGW_SI', 'carrier:MSCGW', TRUE, 'MSCGW SI Worker', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE
    release_unit = VALUES(release_unit),
    enabled = VALUES(enabled),
    description = VALUES(description),
    updated_at = UTC_TIMESTAMP(6);

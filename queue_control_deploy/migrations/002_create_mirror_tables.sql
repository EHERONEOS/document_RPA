-- 原库镜像表和同步控制表；synced_at 仅属于新库，不由原库同步字段提供。
CREATE TABLE IF NOT EXISTS queue_control_deploy.mirror_devices (
    device_id VARCHAR(128) PRIMARY KEY,
    display_name VARCHAR(255) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    last_seen_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    synced_at DATETIME(6) NOT NULL,
    INDEX idx_mirror_devices_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.mirror_queue_assignments (
    queue_name VARCHAR(255) PRIMARY KEY,
    device_id VARCHAR(128) NOT NULL,
    desired_state VARCHAR(32) NOT NULL,
    assignment_version BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    synced_at DATETIME(6) NOT NULL,
    INDEX idx_mirror_assignment_device (device_id),
    INDEX idx_mirror_assignment_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.mirror_queue_statuses (
    device_id VARCHAR(128) NOT NULL,
    queue_name VARCHAR(255) NOT NULL,
    actual_state VARCHAR(32) NOT NULL,
    desired_state VARCHAR(32) NOT NULL,
    process_id BIGINT NULL,
    started_at DATETIME(6) NULL,
    stopped_at DATETIME(6) NULL,
    last_error TEXT NOT NULL,
    restart_reason JSON NOT NULL,
    observed_at DATETIME(6) NOT NULL,
    synced_at DATETIME(6) NOT NULL,
    PRIMARY KEY (device_id, queue_name),
    INDEX idx_mirror_status_queue (queue_name),
    INDEX idx_mirror_status_observed_at (observed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.mirror_queue_commands (
    command_id CHAR(36) PRIMARY KEY,
    device_id VARCHAR(128) NOT NULL,
    queue_name VARCHAR(255) NULL,
    action VARCHAR(32) NOT NULL,
    force_restart BOOLEAN NOT NULL,
    state VARCHAR(32) NOT NULL,
    error_message TEXT NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    acknowledged_at DATETIME(6) NULL,
    synced_at DATETIME(6) NOT NULL,
    INDEX idx_mirror_command_device_created (device_id, created_at),
    INDEX idx_mirror_command_created_at (created_at),
    INDEX idx_mirror_command_acknowledged_at (acknowledged_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.sync_checkpoints (
    source_table VARCHAR(128) PRIMARY KEY,
    sync_mode VARCHAR(32) NOT NULL,
    snapshot_started_at DATETIME(6) NULL,
    snapshot_completed_at DATETIME(6) NULL,
    binlog_file VARCHAR(128) NULL,
    binlog_position BIGINT NULL,
    gtid_set TEXT NULL,
    last_event_time DATETIME(6) NULL,
    last_synced_at DATETIME(6) NULL,
    status VARCHAR(32) NOT NULL,
    last_error TEXT NULL,
    updated_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.sync_reconciliations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_table VARCHAR(128) NOT NULL,
    source_rows BIGINT NOT NULL,
    target_rows BIGINT NOT NULL,
    mismatch_count BIGINT NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    detail_json JSON NOT NULL,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    INDEX idx_reconcile_table_time (source_table, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

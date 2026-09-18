-- 队列归属、发布版本、发布批次、目标和部署命令审计表。
CREATE TABLE IF NOT EXISTS queue_control_deploy.queue_catalog (
    queue_name VARCHAR(255) PRIMARY KEY,
    release_unit VARCHAR(128) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    description VARCHAR(512) NOT NULL DEFAULT '',
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    UNIQUE KEY uk_queue_catalog_unit_name (release_unit, queue_name),
    INDEX idx_queue_catalog_unit (release_unit)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.releases (
    release_id CHAR(36) PRIMARY KEY,
    release_unit VARCHAR(128) NOT NULL,
    version VARCHAR(64) NOT NULL,
    git_commit CHAR(64) NOT NULL,
    artifact_file_name VARCHAR(255) NOT NULL,
    artifact_path VARCHAR(1024) NOT NULL,
    artifact_url VARCHAR(1024) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    manifest_json JSON NOT NULL,
    dependency_changed BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    UNIQUE KEY uk_release_unit_version (release_unit, version),
    INDEX idx_release_unit_status (release_unit, status),
    INDEX idx_release_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.release_rollouts (
    rollout_id CHAR(36) PRIMARY KEY,
    release_id CHAR(36) NOT NULL,
    mode VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    drain_timeout_seconds INT NOT NULL,
    requested_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_rollout_release FOREIGN KEY (release_id)
        REFERENCES queue_control_deploy.releases(release_id),
    INDEX idx_rollout_release_status (release_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.release_targets (
    target_id CHAR(36) PRIMARY KEY,
    rollout_id CHAR(36) NOT NULL,
    release_id CHAR(36) NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    affected_queues JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    command_id CHAR(36) NULL,
    active_version VARCHAR(64) NULL,
    last_error TEXT NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_target_rollout FOREIGN KEY (rollout_id)
        REFERENCES queue_control_deploy.release_rollouts(rollout_id),
    CONSTRAINT fk_target_release FOREIGN KEY (release_id)
        REFERENCES queue_control_deploy.releases(release_id),
    UNIQUE KEY uk_rollout_device (rollout_id, device_id),
    INDEX idx_target_device_status (device_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.device_release_state (
    device_id VARCHAR(128) NOT NULL,
    release_unit VARCHAR(128) NOT NULL,
    active_version VARCHAR(64) NULL,
    active_git_commit CHAR(64) NULL,
    active_sha256 CHAR(64) NULL,
    desired_version VARCHAR(64) NULL,
    status VARCHAR(32) NOT NULL,
    capabilities_json JSON NULL,
    last_error TEXT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (device_id, release_unit),
    INDEX idx_device_release_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS queue_control_deploy.deploy_commands (
    command_id CHAR(36) PRIMARY KEY,
    device_id VARCHAR(128) NOT NULL,
    action VARCHAR(32) NOT NULL,
    payload_json JSON NOT NULL,
    state VARCHAR(32) NOT NULL,
    error_message TEXT NULL,
    redis_stream_id VARCHAR(64) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    INDEX idx_deploy_command_device_time (device_id, created_at),
    INDEX idx_deploy_command_state (state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

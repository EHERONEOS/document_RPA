-- 为部署命令审计补充请求人，便于追踪操作来源。
ALTER TABLE queue_control_deploy.deploy_commands
    ADD COLUMN requested_by VARCHAR(128) NOT NULL AFTER redis_stream_id;

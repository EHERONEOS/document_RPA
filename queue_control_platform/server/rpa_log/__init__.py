"""RPA 日志模块（原 rpa-log-service，已并入平台单服务）。

对外提供：Agent 上报 API（/api/v1/executions 等）、Web 查询 API、
局域网文件服务（/files/*）与 RUNNING 超时扫描。数据库连接复用平台的
QUEUE_CONTROL_MYSQL_URL（统一库），见 db.py。
"""

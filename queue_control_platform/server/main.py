"""独立队列控制中心的 FastAPI 命令行入口（后台服务合并后的唯一后台）。

启动（默认端口 8766）::

    uv run python -m queue_control_platform.server.main
"""
import uvicorn

from queue_control_platform.server.config import PlatformSettings
from queue_control_platform.server.event_processor import EventProcessor
from queue_control_platform.server.rpa_log.init_db import initialize_schema as init_rpa_schema
from queue_control_platform.server.redis_bus import RedisStreamBus
from queue_control_platform.server.repository import MySQLControlRepository
from queue_control_platform.server.web import create_app


# 初始化数据库和事件处理器后，通过 Uvicorn 启动独立维护页面与 API。
def main() -> None:
    settings = PlatformSettings.from_environment()
    repository = MySQLControlRepository(settings.mysql_url)
    repository.initialize_schema()
    init_rpa_schema()  # RPA 日志模块 5 张 rpa_* 表（幂等，统一库）
    bus = RedisStreamBus(settings.redis_url)
    processor = EventProcessor(repository, bus)
    app = create_app(repository, bus, processor)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()

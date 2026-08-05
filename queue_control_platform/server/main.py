"""独立队列控制中心的命令行入口。"""
from queue_control_platform.server.config import PlatformSettings
from queue_control_platform.server.event_processor import EventProcessor
from queue_control_platform.server.redis_bus import RedisStreamBus
from queue_control_platform.server.repository import MySQLControlRepository
from queue_control_platform.server.web import create_app


# 初始化数据库和事件处理器后启动独立维护页面与 API。
def main() -> None:
    settings = PlatformSettings.from_environment()
    repository = MySQLControlRepository(settings.mysql_url)
    repository.initialize_schema()
    bus = RedisStreamBus(settings.redis_url)
    processor = EventProcessor(repository, bus)
    processor.start()
    app = create_app(repository, bus)
    try:
        app.run(
            host=settings.host,
            port=settings.port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    finally:
        processor.stop()


if __name__ == "__main__":
    main()

from app.config.settings import Settings
from app.queue.consumer import start_consumers


def main():
    """队列 Worker 入口。"""
    settings = Settings.from_env()
    start_consumers(settings.rpa_queues)


if __name__ == "__main__":
    main()

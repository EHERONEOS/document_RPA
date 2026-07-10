import sys
from pathlib import Path


def ensure_project_root_on_path() -> None:
    """允许通过 python app/main.py 直接启动。"""
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


ensure_project_root_on_path()

from app.config.settings import Settings  # noqa: E402
from app.queue.consumer import start_consumers  # noqa: E402


def main() -> None:
    """队列 Worker 入口。"""
    settings = Settings.from_env()
    start_consumers(settings.to_queue_worker_config())


if __name__ == "__main__":
    main()

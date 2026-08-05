"""机器侧队列控制客户端的命令行入口。"""
from pathlib import Path

from app.control.queue_client.client import QueueControlClient
from app.control.queue_client.config import QueueClientSettings


# 读取本仓库路径下的配置并持续运行机器侧队列控制客户端。
def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    settings = QueueClientSettings.from_environment(project_root)
    QueueControlClient(settings).run_forever()


if __name__ == "__main__":
    main()

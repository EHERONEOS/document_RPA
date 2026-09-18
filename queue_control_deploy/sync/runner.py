"""增量同步常驻运行入口。"""
from __future__ import annotations

import os

from queue_control_deploy.sync.config import SyncSettings
from queue_control_deploy.sync.incremental_cdc import IncrementalSyncer


def main() -> None:
    """启动生产模式的 binlog 实时同步器。

    核心逻辑:
        1. 加载环境配置。
        2. 优先使用环境变量中的唯一 server_id。
        3. 进入阻塞式实时消费，直到收到停止信号。
    """
    settings = SyncSettings.from_environment()
    server_id = int(os.getenv("DEPLOY_SYNC_SERVER_ID", "91001"))
    IncrementalSyncer(settings, server_id=server_id, blocking=True).run_forever()


if __name__ == "__main__":
    main()

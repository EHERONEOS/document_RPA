#!/usr/bin/env python3
"""部署目标查询命令行工具。"""
from __future__ import annotations

import argparse
import json

from queue_control_deploy.server.config import DeploySettings
from queue_control_deploy.server.repository import DeployRepository


def main() -> int:
    """查询指定发布单元的目标设备和受影响队列。

    核心逻辑:
        1. 加载部署配置。
        2. 从新库 queue_catalog 与 mirror_queue_assignments 聚合。
        3. 输出 JSON。
    """
    parser = argparse.ArgumentParser(description="查询部署目标")
    parser.add_argument("targets", choices=["targets"], help="查询类型")
    parser.add_argument("--release-unit", required=True, help="发布单元，例如 carrier:ZIM")
    args = parser.parse_args()
    repository = DeployRepository(DeploySettings.from_environment())
    if args.targets == "targets":
        print(json.dumps(repository.calculate_targets(args.release_unit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

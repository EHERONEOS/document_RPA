"""本地模拟 Agent 上报（M0 / T0.4，联调用）。

直连 rpa-log-service API（§5.1 / §12），支持三种剧本::

    uv run python scripts/mock_agent.py --scenario success
    uv run python scripts/mock_agent.py --scenario failed
    uv run python scripts/mock_agent.py --scenario running   # 只建 RUNNING 记录，不上报终态

默认地址/取自环境变量 RPA_LOG_SERVICE_URL / RPA_LOG_SERVICE_TOKEN，可用参数覆盖。
上报失败只打印错误退出码，不影响其它剧本（与真实 Agent 的降级精神一致，但联调脚本直接报错便于发现问题）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

import requests

SCENARIOS = ("success", "failed", "running")

BASE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="模拟 RPA Agent 向 rpa-log-service 上报一次完整执行")
    parser.add_argument("--scenario", choices=SCENARIOS, default="success", help="执行剧本")
    parser.add_argument("--base-url", default=os.getenv("RPA_LOG_SERVICE_URL", "http://127.0.0.1:8766"))
    parser.add_argument("--token", default=os.getenv("RPA_LOG_SERVICE_TOKEN", "local-dev"))
    parser.add_argument("--queue", default="QTCT_ZIM_SI", help="队列名")
    parser.add_argument("--device", default=os.getenv("RPA_LOG_DEVICE_NAME", "RPA-DEV-MOCK"))
    parser.add_argument(
        "--message-id",
        default=None,
        help="消息ID；缺省按时间戳自动生成，保证重复执行互不冲突",
    )
    return parser.parse_args()


class MockAgent:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def _post(self, path: str, body: dict) -> dict:
        resp = self.session.post(f"{self.base_url}/api/v1{path}", json=body, timeout=10)
        print(f"POST {path} -> HTTP {resp.status_code} {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"业务错误: {data}")
        return data["data"]

    def create_execution(self, message_id: str, job_id: str, queue: str, device: str) -> int:
        started_at = datetime.now().strftime(BASE_TIME_FORMAT)
        data = self._post(
            "/executions",
            {
                "rpaMessageId": message_id,
                "jobId": job_id,
                "queueName": queue,
                "deviceName": device,
                "taskId": "98123",
                "startedAt": started_at,
                "customerCode": "QTCT",
                "carrierCode": "ZIM",
                "businessCode": "SI",
            },
        )
        return int(data["executionId"])

    def push_logs(self, execution_id: int, logs: list[dict]) -> None:
        self._post("/logs/batch", {"executionId": execution_id, "logs": logs})

    def finish(self, execution_id: int, body: dict) -> None:
        self._post("/executions/finish", {"executionId": execution_id, **body})


def _log(seq: int, level: str, message: str, started: datetime) -> dict:
    now = datetime.now()
    return {
        "seq": seq,
        "level": level,
        "message": message,
        "sourceFile": "scripts/mock_agent.py",
        "sourceLine": 0,
        "logTime": now.strftime(BASE_TIME_FORMAT) + f".{now.microsecond // 1000:03d}",
    }


def run_scenario(scenario: str, args: argparse.Namespace) -> None:
    message_id = args.message_id or f"MOCK{datetime.now().strftime('%Y%m%d%H%M%S')}{scenario[:1].upper()}"
    job_id = f"ZIMUSBKK{datetime.now().strftime('%H%M%S')}"
    queue = args.queue
    device = args.device
    started = datetime.now()

    agent = MockAgent(args.base_url, args.token)
    print(f"[mock_agent] scenario={scenario} message={message_id} queue={queue} device={device}")

    execution_id = agent.create_execution(message_id, job_id, queue, device)
    print(f"[mock_agent] executionId={execution_id} (RUNNING)")

    logs = [
        _log(1, "INFO", f"收到队列消息，开始执行任务 queue={queue} jobId={job_id}", started),
        _log(2, "INFO", "打开 ZIM 船司门户 https://www.zim.com", started),
        _log(3, "SUCCESS", "登录 ZIM 船司门户成功", started),
    ]
    if scenario == "failed":
        logs.append(_log(4, "ERROR", "【集装箱数】元素不存在：#container-no；等待=5s", started))
    agent.push_logs(execution_id, logs)

    if scenario == "running":
        print("[mock_agent] running 剧本：不报终态，保持 RUNNING（供抽屉刷新/轮询联调）")
        return

    time.sleep(1)  # 模拟耗时，让 durationSeconds 有值
    if scenario == "success":
        agent.push_logs(execution_id, [_log(5, "SUCCESS", "提单补料提交成功，任务完成", started)])
        agent.finish(
            execution_id,
            {
                "status": "SUCCESS",
                "finishedAt": datetime.now().strftime(BASE_TIME_FORMAT),
                "recordFiles": [
                    {
                        "type": "SCREEN_RECORDING_FILE",
                        "mediaType": "VIDEO",
                        "fileName": f"{queue}_{message_id}.mp4",
                        "url": "http://127.0.0.1:8766/files/2025/01/mock-recording.mp4",
                        "storage": "LAN",
                        "fileSize": 9017753,
                    }
                ],
            },
        )
    else:  # failed
        agent.finish(
            execution_id,
            {
                "status": "FAILED",
                "remark": "ZIM SI 填单失败：【集装箱数】元素不存在：#container-no；等待=5s",
                "failImgUrl": "https://fec.cgofish.com/rpa/shots/2025/01/15/mock-fail.png",
                "finishedAt": datetime.now().strftime(BASE_TIME_FORMAT),
                "recordFiles": [
                    {
                        "type": "SUBMIT_RESULT_SCREENSHOT",
                        "mediaType": "IMAGE",
                        "fileName": "si_submit_error.png",
                        "url": "https://fec.cgofish.com/rpa/shots/2025/01/15/mock-fail.png",
                        "storage": "OSS",
                    }
                ],
            },
        )
    print(f"[mock_agent] scenario={scenario} 完成")


def main() -> int:
    args = parse_args()
    try:
        run_scenario(args.scenario, args)
    except Exception as exc:  # noqa: BLE001 - 联调脚本直接报告错误
        print(f"[mock_agent] 上报失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

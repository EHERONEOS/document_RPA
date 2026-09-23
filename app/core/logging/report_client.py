"""日志服务上报客户端（设计文档 §6.2 / T2.3）。

- 单例 ``get_report_client()``；内部 ``queue.Queue`` + 单 daemon 线程攒批上报
  （满 50 条或 1s flush）→ ``POST /api/v1/logs/batch``；
- 任何异常仅本地打印 WARN，**绝不向上抛、绝不阻塞业务线程**；
- ``RPA_LOG_SERVICE_ENABLED=false`` 或 URL 为空时整体 no-op，行为与现状一致；
- 进程退出 ``atexit`` 兜底 flush。
"""

from __future__ import annotations

import atexit
import os
import queue
import threading
import time
from typing import Any

import requests

from app.core.logging.logger import log

_BATCH_SIZE = 50
_FLUSH_INTERVAL_SECONDS = 1.0
_HTTP_TIMEOUT_SECONDS = 5
_QUEUE_MAXSIZE = 20000  # 防止服务长时间不可用把内存打爆；满了丢弃并 WARN


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _service_url() -> str:
    return os.getenv("RPA_LOG_SERVICE_URL", "").strip().rstrip("/")


def _service_token() -> str:
    return os.getenv("RPA_LOG_SERVICE_TOKEN", "").strip()


class LogReportClient:
    """批量异步上报器：所有公开方法都不会抛错、不会阻塞业务。"""

    def __init__(self) -> None:
        self.enabled = _env_flag("RPA_LOG_SERVICE_ENABLED") and bool(_service_url())
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._stop = threading.Event()
        self._dropped_total = 0
        self._failed_batches = 0
        self._session = requests.Session()
        if self.enabled:
            worker = threading.Thread(target=self._worker, name="rpa-log-reporter", daemon=True)
            worker.start()
            atexit.register(self.flush)
            log(f"日志服务上报已开启 url={_service_url()}", level="INFO")

    # ------------------------------------------------------------------
    # 对外接口（全部降级安全）
    # ------------------------------------------------------------------

    def create_execution(self, payload: dict[str, Any]) -> int | None:
        """创建执行记录（uk 幂等），返回 executionId；失败返回 None（仅 WARN）。"""
        data = self._post("/api/v1/executions", payload)
        return int(data["executionId"]) if data else None

    def enqueue(
        self,
        execution_id: int | None,
        seq: int,
        level: str,
        message: str,
        source_file: str = "",
        source_line: int = 0,
        log_time: str | None = None,
    ) -> None:
        """入队一条日志；队列满或未开启时丢弃（绝不阻塞）。"""
        if not self.enabled or execution_id is None:
            return
        item = {
            "executionId": int(execution_id),
            "seq": int(seq),
            "level": str(level).upper(),
            "message": str(message),
            "sourceFile": str(source_file or ""),
            "sourceLine": int(source_line or 0),
            "logTime": log_time or time.strftime("%Y-%m-%d %H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}",
        }
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._dropped_total += 1
            if self._dropped_total == 1 or self._dropped_total % 100 == 0:
                log(f"日志上报队列已满，累计丢弃 {self._dropped_total} 条", level="WARN")

    def finish_execution(
        self,
        *,
        execution_id: int | None,
        status: str,
        remark: str = "",
        fail_img_url: str = "",
        record_files: list[dict] | None = None,
    ) -> None:
        """终态上报（服务端以首次为准幂等）；失败仅 WARN。"""
        if not self.enabled or execution_id is None:
            return
        self._post(
            "/api/v1/executions/finish",
            {
                "executionId": int(execution_id),
                "status": status,
                "remark": remark or "",
                "failImgUrl": fail_img_url or "",
                "finishedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                "durationSeconds": None,  # 服务端按 started_at 补算
                "recordFiles": list(record_files or []),
            },
        )

    def flush(self) -> None:
        """排空队列并同步发送（atexit / 停机兜底）。"""
        if not self.enabled:
            return
        pending: list[dict[str, Any]] = []
        while True:
            try:
                pending.append(self._queue.get_nowait())
            except queue.Empty:
                break
            if len(pending) >= _BATCH_SIZE:
                self._send_batch(pending)
                pending = []
        if pending:
            self._send_batch(pending)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        """攒批循环：满 50 条或 1s 发一次。"""
        while not self._stop.is_set():
            batch: list[dict[str, Any]] = []
            try:
                batch.append(self._queue.get(timeout=_FLUSH_INTERVAL_SECONDS))
            except queue.Empty:
                continue
            deadline = time.monotonic() + _FLUSH_INTERVAL_SECONDS
            while len(batch) < _BATCH_SIZE:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(self._queue.get(timeout=remaining))
                except queue.Empty:
                    break
            self._send_batch(batch)

    def _send_batch(self, batch: list[dict[str, Any]]) -> None:
        """按 executionId 分组批量上报。"""
        if not batch:
            return
        grouped: dict[int, list[dict[str, Any]]] = {}
        for item in batch:
            grouped.setdefault(item["executionId"], []).append(item)
        for execution_id, items in grouped.items():
            self._post(
                "/api/v1/logs/batch",
                {
                    "executionId": execution_id,
                    "logs": [
                        {key: item[key] for key in ("seq", "level", "message", "sourceFile", "sourceLine", "logTime")}
                        for item in items
                    ],
                },
            )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST JSON 并返回 data；任何失败仅 WARN 返回 None。"""
        headers = {}
        token = _service_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = self._session.post(
                f"{_service_url()}{path}",
                json=payload,
                headers=headers,
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            envelope = response.json()
            if envelope.get("code") != 0:
                raise RuntimeError(f"业务错误 code={envelope.get('code')} message={envelope.get('message')}")
            self._failed_batches = 0
            return envelope.get("data") or {}
        except Exception as exc:  # noqa: BLE001 - 降级：绝不向上抛
            self._failed_batches += 1
            if self._failed_batches == 1 or self._failed_batches % 20 == 0:
                log(f"日志服务上报失败（不影响业务）path={path} error={exc}", level="WARN")
            return None


_client: LogReportClient | None = None
_client_lock = threading.Lock()


def get_report_client() -> LogReportClient:
    """进程内单例；环境变量在首次调用时读取（测试可先 monkeypatch 再 reset）。"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = LogReportClient()
    return _client


def reset_report_client() -> None:
    """测试用：丢弃单例，让下一次 get_report_client() 重新读环境变量。"""
    global _client
    with _client_lock:
        _client = None

"""执行日志会话（设计文档 §6.1–§6.4 / T2.2）：ContextVar 绑定 + 懒创建执行记录 + 终态上报。

- ``log_service_enabled(runtime_mode)``：队列模式且 ``RPA_LOG_SERVICE_ENABLED`` 开启才记录；
  ``app.dev.local_runner``（runtime_mode='local'）**强制关闭**——即使开发机误配环境变量也不上报；
- ``execution_log_session(context)``：队列入口绑定会话，开启时创建 RUNNING 记录；
  退出时若尚未 finish（异常路径）兜底 ``finish_execution(FAILED)``；
- ``report_log()``：logger 的旁路上报入口，无会话时 no-op；
- 测试单（skip_test_job）在会话开启前已被过滤，不产生任何记录（§6.3）。
"""

from __future__ import annotations

import contextvars
import os
import platform
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

from app.core.logging.logger import _caller
from app.core.logging.report_client import get_report_client

TRUE_VALUES = {"1", "true", "yes", "on"}


def log_service_enabled(runtime_mode: str = "queue") -> bool:
    """队列模式且环境变量开启时才记录；local 的 runtime_mode='local' 强制关闭（双保险）。"""
    if runtime_mode != "queue":
        return False
    return os.getenv("RPA_LOG_SERVICE_ENABLED", "").strip().lower() in TRUE_VALUES


def resolve_device_name() -> str:
    """设备名：RPA_LOG_DEVICE_NAME → QUEUE_CONTROL_DEVICE_ID → 主机名（§6.1）。"""
    return (
        os.getenv("RPA_LOG_DEVICE_NAME")
        or os.getenv("QUEUE_CONTROL_DEVICE_ID")
        or platform.node()
    ).strip()


@dataclass
class ExecutionLogContext:
    """单次执行的日志上下文（线程内绑定，线程安全自增 seq）。"""

    rpa_message_id: str = ""
    job_id: str = ""
    queue_name: str = ""
    device_name: str = ""
    task_id: str = ""
    customer_code: str = ""
    carrier_code: str = ""
    business_code: str = ""
    started_at: str = ""
    execution_id: int | None = None  # 服务端执行记录 ID（懒创建）
    seq: int = 0
    finished: bool = False
    _seq_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def next_seq(self) -> int:
        with self._seq_lock:
            self.seq += 1
            return self.seq

    def _create_payload(self) -> dict:
        return {
            "rpaMessageId": self.rpa_message_id,
            "jobId": self.job_id,
            "queueName": self.queue_name,
            "deviceName": self.device_name,
            "taskId": self.task_id,
            "startedAt": self.started_at,
            "customerCode": self.customer_code,
            "carrierCode": self.carrier_code,
            "businessCode": self.business_code,
        }


_current_context: contextvars.ContextVar[ExecutionLogContext | None] = contextvars.ContextVar(
    "rpa_log_ctx", default=None
)


def current_context() -> ExecutionLogContext | None:
    """当前线程绑定的执行日志上下文；无会话时为 None。"""
    return _current_context.get()


def build_log_context(task_context) -> ExecutionLogContext:
    """从 TaskContext 构建日志上下文；jobId 取 content.jobNo→blNo→bookingNo→shippingNo（§6.3）。"""
    content = getattr(task_context, "content", None) or {}
    job_id = ""
    for key in ("jobNo", "blNo", "bookingNo", "shippingNo"):
        value = str(content.get(key) or "").strip()
        if value:
            job_id = value
            break
    return ExecutionLogContext(
        rpa_message_id=str(getattr(task_context, "rpa_message_id", "") or ""),
        job_id=job_id,
        queue_name=str(getattr(task_context, "queue_name", "") or ""),
        device_name=resolve_device_name(),
        task_id=str(getattr(task_context, "task_id", "") or ""),
        customer_code=str(getattr(task_context, "customer_code", "") or ""),
        carrier_code=str(getattr(task_context, "carrier_code", "") or ""),
        business_code=str(getattr(task_context, "business_code", "") or ""),
        started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@contextmanager
def execution_log_session(task_context):
    """队列消费入口的执行日志会话；未开启时为 no-op（行为与现状完全一致）。"""
    if not log_service_enabled(getattr(task_context, "runtime_mode", "queue")):
        yield None
        return

    log_context = build_log_context(task_context)
    token = _current_context.set(log_context)
    client = get_report_client()
    try:
        # uk_message_queue 幂等创建 RUNNING 记录；失败降级（execution_id=None，仅本地打印）
        log_context.execution_id = client.create_execution(log_context._create_payload())
        yield log_context
    except Exception as exc:
        # 兜底终态：任何未走到 base_task 结果上报的异常路径都保证有终态（§6.3）
        finish_execution(success=False, remark=str(exc))
        raise
    finally:
        _current_context.reset(token)


def report_log(message, level: str = "INFO", source_file: str = "", source_line: int = 0) -> None:
    """logger.log 的旁路上报入口：无上下文（模块导入期、工具脚本）只打印不上报。"""
    context = _current_context.get()
    if context is None or context.execution_id is None:
        return
    if not source_file:
        source_file, _, source_line = _caller()
    get_report_client().enqueue(
        execution_id=context.execution_id,
        seq=context.next_seq(),
        level=level,
        message=message,
        source_file=source_file,
        source_line=source_line,
        log_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    )


def finish_execution(*, success: bool, remark: str = "", fail_img: str = "", record_files=None) -> None:
    """终态上报（§6.4）；无会话/已终态时 no-op，全部降级安全。"""
    context = _current_context.get()
    if context is None or context.finished:
        return
    context.finished = True
    get_report_client().finish_execution(
        execution_id=context.execution_id,
        status="SUCCESS" if success else "FAILED",
        remark=remark,
        fail_img_url=fail_img,
        record_files=list(record_files or []),
    )

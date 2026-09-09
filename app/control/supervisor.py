"""支持独立重启的本地队列 Worker 生命周期监管。"""
from __future__ import annotations

import atexit
import json
import multiprocessing
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.control.worker import run_queue_worker


RUNNING_STATES = {"STARTING", "RUNNING", "DRAINING", "RESTARTING"}


# 获取带时区的当前 UTC 时间字符串。
def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class QueueRuntime:
    name: str
    desired_state: str = "RUNNING"
    state: str = "PAUSED"
    pid: int | None = None
    started_at: str | None = None
    stopped_at: str | None = None
    last_error: str = ""
    restart_requested: bool = False
    restart_reason: list[str] = field(default_factory=list)
    remove_requested: bool = False
    process: Any = None
    commands: Any = None


class QueueSupervisor:
    """为每个配置队列启动、排空、暂停和替换一个操作系统进程。"""

    # 初始化队列运行状态、进程上下文和后台监管线程。
    def __init__(
        self,
        queue_names: list[str],
        *,
        project_root: Path | None = None,
        drain_timeout_seconds: int = 1800,
        state_path: Path | None = None,
        worker_target=run_queue_worker,
        persist_state: bool = True,
        status_observer: Callable[[list[dict[str, Any]]], None] | None = None,
        account_session_coordinator=None,
    ):
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.drain_timeout_seconds = drain_timeout_seconds
        self.state_path = state_path or self.project_root / "runtime" / "control" / "state.json"
        self.worker_target = worker_target
        self.persist_state = persist_state
        self.status_observer = status_observer
        self.account_session_coordinator = account_session_coordinator
        self._context = multiprocessing.get_context("spawn")
        self._events = self._context.Queue()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._started = False
        self._runtimes = {
            name.upper(): QueueRuntime(name=name.upper())
            for name in queue_names
            if name.strip()
        }
        if self.persist_state:
            self._restore_desired_states()
        self._event_thread = threading.Thread(
            target=self._consume_events, name="queue-control-events", daemon=True
        )
        self._monitor_thread = threading.Thread(
            target=self._monitor_workers, name="queue-control-monitor", daemon=True
        )
        atexit.register(self.stop)

    def set_account_session_coordinator(self, coordinator) -> None:
        """Attach the device-wide coordinator before Queue Workers are started."""
        with self._lock:
            if self._started:
                raise RuntimeError("队列监管器已启动，不能替换账号会话协调器")
            self.account_session_coordinator = coordinator

    # 启动后台事件处理和监控线程，并拉起应运行的队列 Worker。
    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._event_thread.start()
            self._monitor_thread.start()
            for runtime in self._runtimes.values():
                if runtime.desired_state == "RUNNING":
                    self._start_worker(runtime)
            self._state_changed()

    # 停止监管器并终止当前仍存活的队列 Worker。
    def stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        with self._lock:
            for runtime in self._runtimes.values():
                self._terminate_worker(runtime)

    # 返回所有队列的运行状态。
    def queue_statuses(self) -> list[dict[str, Any]]:
        with self._lock:
            statuses = []
            for runtime in sorted(self._runtimes.values(), key=lambda item: item.name):
                statuses.append(
                    {
                        "name": runtime.name,
                        "state": runtime.state,
                        "desiredState": runtime.desired_state,
                        "pid": runtime.pid,
                        "startedAt": runtime.started_at,
                        "stoppedAt": runtime.stopped_at,
                        "lastError": runtime.last_error,
                        "restartReason": runtime.restart_reason,
                    }
                )
            return statuses

    # 将一个队列纳入当前机器监管，并按期望状态决定是否立即创建 Worker。
    def assign(self, queue_name: str, *, start: bool = True) -> None:
        normalized_name = queue_name.upper().strip()
        if not normalized_name:
            raise ValueError("队列名称不能为空")
        with self._lock:
            runtime = self._runtimes.get(normalized_name)
            if runtime is None:
                runtime = QueueRuntime(
                    name=normalized_name,
                    desired_state="RUNNING" if start else "PAUSED",
                )
                self._runtimes[normalized_name] = runtime
            else:
                was_removing = runtime.remove_requested
                runtime.remove_requested = False
                runtime.desired_state = "RUNNING" if start else "PAUSED"
                if was_removing:
                    runtime.restart_requested = True
                    runtime.restart_reason = ["重新分配队列"]
                    runtime.state = "RESTARTING"
            if start and self._started and runtime.state == "PAUSED":
                self._start_worker(runtime)
            elif not start and runtime.state in RUNNING_STATES:
                runtime.restart_requested = False
                runtime.restart_reason = []
                runtime.state = "DRAINING"
                self._request_drain(runtime)
            self._state_changed()

    # 协作式排空并移除一个队列，使该机器不再监听它。
    def unassign(self, queue_name: str) -> None:
        with self._lock:
            runtime = self._runtime(queue_name)
            if runtime.state == "PAUSED":
                del self._runtimes[runtime.name]
                self._state_changed()
                return
            process = runtime.process
            if process is None or not process.is_alive():
                del self._runtimes[runtime.name]
                self._state_changed()
                return
            runtime.desired_state = "REMOVED"
            runtime.restart_requested = False
            runtime.restart_reason = []
            runtime.remove_requested = True
            runtime.state = "DRAINING"
            self._request_drain(runtime)
            self._state_changed()

    # 请求指定 Worker 停止拉取消息并完成已接收任务。
    def pause(self, queue_name: str) -> None:
        with self._lock:
            runtime = self._runtime(queue_name)
            if runtime.state not in RUNNING_STATES:
                raise ValueError(f"队列 {runtime.name} 当前状态为 {runtime.state}，不能暂停")
            runtime.desired_state = "PAUSED"
            runtime.restart_requested = False
            runtime.restart_reason = []
            runtime.state = "DRAINING"
            self._request_drain(runtime)
            self._state_changed()

    # 使用新进程恢复指定队列。
    def resume(self, queue_name: str) -> None:
        with self._lock:
            runtime = self._runtime(queue_name)
            if runtime.state != "PAUSED":
                raise ValueError(f"队列 {runtime.name} 当前状态为 {runtime.state}，不能恢复")
            runtime.desired_state = "RUNNING"
            runtime.restart_requested = False
            runtime.restart_reason = []
            self._start_worker(runtime)
            self._state_changed()

    # 排空或强制替换指定队列 Worker，使其加载磁盘中的新代码。
    def restart(self, queue_name: str, *, force: bool = False) -> None:
        with self._lock:
            runtime = self._runtime(queue_name)
            if runtime.state == "PAUSED":
                runtime.desired_state = "RUNNING"
                self._start_worker(runtime)
            elif runtime.state in RUNNING_STATES:
                if force:
                    self._terminate_worker(runtime)
                    runtime.restart_requested = False
                    self._start_worker(runtime)
                else:
                    self._restart_runtime(runtime, ["手动重启"])
            elif runtime.state == "FAILED":
                self._terminate_worker(runtime)
                runtime.desired_state = "RUNNING"
                runtime.restart_requested = False
                runtime.restart_reason = ["故障恢复"]
                self._start_worker(runtime)
            else:
                raise ValueError(f"队列 {runtime.name} 当前状态为 {runtime.state}，不能重启")
            self._state_changed()

    # 排空并重启全部未暂停队列，使它们加载最新代码。
    def restart_all(self) -> None:
        with self._lock:
            for runtime in self._runtimes.values():
                if runtime.state == "PAUSED":
                    continue
                if runtime.state in RUNNING_STATES:
                    self._restart_runtime(runtime, ["全部队列重启"])
                elif runtime.state == "FAILED":
                    self._terminate_worker(runtime)
                    runtime.desired_state = "RUNNING"
                    runtime.restart_requested = False
                    runtime.restart_reason = ["全部队列重启"]
                    self._start_worker(runtime)
            self._state_changed()

    # 按队列名获取运行时状态，未配置时转换为用户可读错误。
    def _runtime(self, queue_name: str) -> QueueRuntime:
        try:
            return self._runtimes[queue_name.upper()]
        except KeyError as exc:
            raise ValueError(f"未配置监听队列：{queue_name}") from exc

    # 将运行中的队列切换到排空后重启的状态。
    def _restart_runtime(self, runtime: QueueRuntime, reason: list[str]) -> None:
        runtime.desired_state = "RUNNING"
        runtime.restart_requested = True
        runtime.remove_requested = False
        runtime.restart_reason = reason
        runtime.state = "RESTARTING"
        self._request_drain(runtime)

    # 创建全新 spawn 子进程来运行指定队列 Worker。
    def _start_worker(self, runtime: QueueRuntime) -> None:
        process = runtime.process
        if process is not None and process.is_alive():
            return
        runtime.commands = self._context.Queue()
        worker_args = (runtime.name, runtime.commands, self._events)
        if self.account_session_coordinator is not None:
            worker_args += (self.account_session_coordinator,)
        runtime.process = self._context.Process(
            target=self.worker_target,
            args=worker_args,
            name=f"queue-worker-{runtime.name.lower()}",
        )
        runtime.state = "STARTING"
        runtime.pid = None
        runtime.started_at = _utcnow()
        runtime.stopped_at = None
        runtime.last_error = ""
        runtime.process.start()
        runtime.pid = runtime.process.pid
        runtime.restart_requested = False

    # 终止并回收指定 Worker 进程。
    def _terminate_worker(self, runtime: QueueRuntime) -> None:
        process = runtime.process
        worker_pid = runtime.pid or (process.pid if process is not None else None)
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=3)
        self._release_worker_slots(worker_pid)
        runtime.pid = None

    def _release_worker_slots(self, worker_pid: int | None) -> None:
        if worker_pid is None or self.account_session_coordinator is None:
            return
        try:
            self.account_session_coordinator.release_worker_slots(worker_pid)
        except Exception:
            # Worker recovery must continue even if the local manager is unavailable.
            return

    # 向存活 Worker 发送协作式排空指令。
    def _request_drain(self, runtime: QueueRuntime) -> None:
        process = runtime.process
        if process is None or not process.is_alive():
            runtime.stopped_at = _utcnow()
            return
        runtime.commands.put({"type": "drain", "timeout": self.drain_timeout_seconds})

    # 持续读取 Worker 事件，并更新对应队列的运行状态。
    def _consume_events(self) -> None:
        while not self._stop_event.is_set():
            try:
                event = self._events.get(timeout=0.25)
            except queue.Empty:
                continue
            self._apply_event(event)

    # 根据单个 Worker 事件更新队列状态并持久化期望状态。
    def _apply_event(self, event: dict[str, Any]) -> None:
        queue_name = str(event.get("queue") or "").upper()
        with self._lock:
            runtime = self._runtimes.get(queue_name)
            if runtime is None:
                return
            event_type = event.get("type")
            if event_type == "ready":
                runtime.state = "RUNNING"
            elif event_type == "draining":
                runtime.state = "DRAINING" if not runtime.restart_requested else "RESTARTING"
            elif event_type == "paused":
                runtime.stopped_at = _utcnow()
                runtime.state = "RESTARTING" if runtime.restart_requested else "PAUSED"
                # Funboost 持有后台辅助线程。消费者已关闭 AMQP 通道且完成排空，
                # 在此回收进程，避免这些线程使暂停的 Worker 持续存活。
                self._terminate_worker(runtime)
                if runtime.remove_requested:
                    del self._runtimes[runtime.name]
            elif event_type == "drain_timeout":
                runtime.state = "DRAINING"
                runtime.last_error = "等待当前任务完成超时；队列仍在排空中"
            elif event_type == "failed":
                runtime.state = "FAILED"
                runtime.last_error = str(event.get("error") or "队列 Worker 异常退出")
                runtime.stopped_at = _utcnow()
                self._terminate_worker(runtime)
            self._state_changed()

    # 检测异常退出的 Worker，并在需要时创建替代进程。
    def _monitor_workers(self) -> None:
        while not self._stop_event.wait(0.25):
            with self._lock:
                for runtime in self._runtimes.values():
                    process = runtime.process
                    if process is None or process.is_alive():
                        continue
                    self._release_worker_slots(runtime.pid or process.pid)
                    runtime.pid = None
                    if runtime.restart_requested and runtime.desired_state == "RUNNING":
                        self._start_worker(runtime)
                    elif runtime.state in RUNNING_STATES:
                        runtime.state = "FAILED"
                        runtime.stopped_at = _utcnow()
                        runtime.last_error = f"Worker 已退出，exit_code={process.exitcode}"
                    self._state_changed()

    # 从本地状态文件恢复上次保存的暂停意图。
    def _restore_desired_states(self) -> None:
        try:
            saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in saved.get("queues", []):
            runtime = self._runtimes.get(str(item.get("name") or "").upper())
            if runtime is not None and item.get("desiredState") == "PAUSED":
                runtime.desired_state = "PAUSED"
                runtime.state = "PAUSED"

    # 原子写入队列期望状态，供下次启动时恢复。
    def _persist(self) -> None:
        if not self.persist_state:
            return
        payload = {
            "queues": [
                {"name": runtime.name, "desiredState": runtime.desired_state}
                for runtime in self._runtimes.values()
            ]
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.replace(self.state_path)

    # 持久化本地兼容状态，并向远端 Agent 观察者推送最新队列快照。
    def _state_changed(self) -> None:
        self._persist()
        self._notify_statuses()

    # 调用可选的状态观察者；上报失败不能影响本地消息消费。
    def _notify_statuses(self) -> None:
        if self.status_observer is None:
            return
        try:
            self.status_observer(self.queue_statuses())
        except Exception:
            return

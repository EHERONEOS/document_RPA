"""为复用同一 Chromium 用户目录的 RPA 任务提供串行执行能力。"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from time import monotonic

from app.core.logging.logger import log


_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def build_browser_profile_name(context) -> str:
    """返回 Chromium 和执行锁共用的用户目录标识。"""
    # 必须与 BrowserManager 使用同一标识，才能锁住同一个浏览器进程。
    website_info = getattr(context, "website_info", {}) or {}
    username = website_info.get("websiteUserName") or website_info.get("websiteAccount") or "default"
    carrier_code = getattr(context, "carrier_code", "") or "default"
    return f"{username}_{carrier_code}"


def _local_lock(lock_key: str) -> threading.Lock:
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(lock_key, threading.Lock())


class BrowserProfileLock:
    """同一浏览器用户目录的同机互斥锁。

    内存锁协调同一个 Worker 进程中的消费者，文件锁将保护范围扩展到同一台机器
    上的多个 Worker 进程。
    """

    def __init__(self, context, *, lock_dir=None):
        self.context = context
        self.profile_name = build_browser_profile_name(context)
        # 文件名使用哈希，避免将网站账号写入磁盘。
        profile_digest = hashlib.sha256(self.profile_name.encode("utf-8")).hexdigest()
        if lock_dir is None:
            from app.config.settings import Settings

            settings = Settings.from_env()
            lock_dir = Path(settings.browser_user_data_dir) / ".locks"
        self.lock_path = Path(lock_dir) / f"{profile_digest}.lock"
        self.lock_id = profile_digest[:12]
        self._thread_lock = _local_lock(str(self.lock_path.resolve()))
        self._lock_file = None

    def __enter__(self):
        started_at = monotonic()
        # 先协调同一 Worker 内的线程，再获取跨进程文件锁。
        if not self._thread_lock.acquire(blocking=False):
            log(
                f"等待共享浏览器会话 queue={self.context.queue_name} lock={self.lock_id}",
                level="INFO",
            )
            self._thread_lock.acquire()

        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._lock_file = self.lock_path.open("a+")
            # 文件锁用于阻止同机其他 Worker 同时接管该 profile。
            self._acquire_file_lock()
        except Exception:
            self._close_file_lock()
            self._thread_lock.release()
            raise

        waited_seconds = monotonic() - started_at
        if waited_seconds >= 0.05:
            log(
                f"已取得共享浏览器会话 queue={self.context.queue_name} "
                f"lock={self.lock_id} waited={waited_seconds:.2f}s",
                level="INFO",
            )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self._close_file_lock()
        finally:
            self._thread_lock.release()

    def _acquire_file_lock(self):
        if os.name == "nt":
            self._acquire_windows_file_lock()
            return

        import fcntl

        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(
                f"等待其他 Worker 释放浏览器会话 queue={self.context.queue_name} lock={self.lock_id}",
                level="INFO",
            )
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)

    def _acquire_windows_file_lock(self):
        import msvcrt

        self._lock_file.seek(0)
        self._lock_file.write("0")
        self._lock_file.flush()
        has_logged_waiting = False
        while True:
            try:
                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if not has_logged_waiting:
                    log(
                        f"等待其他 Worker 释放浏览器会话 queue={self.context.queue_name} lock={self.lock_id}",
                        level="INFO",
                    )
                    has_logged_waiting = True
                time.sleep(0.1)

    def _close_file_lock(self):
        if self._lock_file is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            self._lock_file.close()
            self._lock_file = None

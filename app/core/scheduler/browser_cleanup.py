"""浏览器日清理时刻计算与后台调度。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.logging.logger import log


DEFAULT_BROWSER_CLEANUP_TIME = "20:30"


def parse_cleanup_hhmm(value: str | None, *, default: str = DEFAULT_BROWSER_CLEANUP_TIME) -> tuple[int, int]:
    """解析 ``HH:MM`` 日清理时刻，非法值抛出 ``ValueError``。"""
    text = str(value or "").strip() or default
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"BROWSER_CLEANUP_TIME 必须是 HH:MM，当前值：{text}")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"BROWSER_CLEANUP_TIME 必须是 HH:MM，当前值：{text}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"BROWSER_CLEANUP_TIME 超出有效范围：{text}")
    return hour, minute


def next_cleanup_at(now: datetime, hour: int, minute: int) -> datetime:
    """返回 ``now`` 之后最近一次清理时刻，当天已过则顺延到次日。"""
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= now:
        scheduled += timedelta(days=1)
    return scheduled


class BrowserCleanupScheduler:
    """按本地时区每天在固定时刻触发一次浏览器清理。"""

    def __init__(
        self,
        *,
        hour: int,
        minute: int,
        stop_event: threading.Event,
        callback: Callable[[], object],
        now_fn: Callable[[], datetime] = datetime.now,
        wait_fn: Callable[[float], bool] | None = None,
    ):
        self.hour = hour
        self.minute = minute
        self._stop_event = stop_event
        self._callback = callback
        self._now_fn = now_fn
        self._wait_fn = wait_fn or (lambda timeout: self._stop_event.wait(timeout=timeout))

    def start(self) -> threading.Thread:
        thread = threading.Thread(
            target=self.run_forever,
            name="browser-daily-cleanup",
            daemon=True,
        )
        thread.start()
        return thread

    def run_forever(self) -> None:
        """阻塞运行，直到 ``stop_event`` 被设置。"""
        while not self._stop_event.is_set():
            now = self._now_fn()
            target = next_cleanup_at(now, self.hour, self.minute)
            remaining = max((target - now).total_seconds(), 0.01)
            if self._wait_fn(remaining):
                return
            if self._stop_event.is_set():
                return
            try:
                self._callback()
            except Exception as exc:
                log(f"浏览器日清理执行失败：{exc}", level="ERROR")



def run_immediate_cleanup(user_data_dir: str) -> list[int]:
    """立刻终止 ``user_data_dir`` 下的 RPA Chromium，不等待忙碌任务。"""
    from app.core.browser.process import find_rpa_chromium_pids, terminate_browser_pids

    pids = find_rpa_chromium_pids(user_data_dir=user_data_dir)
    terminated = terminate_browser_pids(pids)
    log(f"立即清理 RPA 浏览器完成 terminated={terminated}")
    return terminated


if __name__ == "__main__":
    from app.config.settings import Settings

    settings = Settings.from_env()
    print(run_immediate_cleanup(settings.browser_user_data_dir))

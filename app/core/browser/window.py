from __future__ import annotations

import ctypes
import platform
import time
from ctypes import wintypes
from typing import Any

from app.core.logging.logger import log


SW_RESTORE = 9
SW_SHOW = 5
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040


def browser_pid_from_page(page: Any) -> int | None:
    """Read the browser PID exposed by DrissionPage, when available."""
    candidates = [
        getattr(page, "process_id", None),
        getattr(getattr(page, "browser", None), "process_id", None),
        getattr(getattr(page, "browser", None), "_process_id", None),
    ]
    for value in candidates:
        if isinstance(value, int) and value > 0:
            return value
    return None


def ensure_browser_window_ready(
    page: Any | None = None,
    *,
    pid: int | None = None,
    hwnd: int | None = None,
) -> int | None:
    """Restore and foreground a browser window before capture-sensitive actions."""
    if platform.system() != "Windows":
        return hwnd

    target_hwnd = hwnd or _find_window_by_pid(pid or browser_pid_from_page(page))
    if not target_hwnd:
        return None

    try:
        _restore_window(target_hwnd)
    except Exception as exc:
        log(f"浏览器窗口恢复失败，继续执行：{exc}")
    return target_hwnd


def _find_window_by_pid(pid: int | None) -> int | None:
    if not pid:
        return None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnds: list[int] = []

    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid and user32.IsWindowVisible(hwnd):
            hwnds.append(int(hwnd))
        return True

    user32.EnumWindows(enum_windows_proc(callback), 0)
    return hwnds[0] if hwnds else None


def _restore_window(hwnd: int) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.SetWindowPos(
        hwnd,
        0,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
    )
    time.sleep(0.2)

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from capturesdk import CaptureSDKClient, CaptureSDKError


def find_chrome_pid_by_debug_port(port: int) -> int:
    """Find the Chrome root process started with a known DevTools port."""
    script = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -eq 'chrome.exe' -and $_.CommandLine -like '*--remote-debugging-port="
        + str(port)
        + "*' "
        "} | Select-Object -First 1 -ExpandProperty ProcessId; "
        "if ($p) { Write-Output $p }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    value = result.stdout.strip()
    if not value:
        raise CaptureSDKError(
            f"Could not find chrome.exe with --remote-debugging-port={port}."
        )
    return int(value)


def wait_for_browser_hwnd(
    client: CaptureSDKClient,
    browser_pid: int,
    timeout_seconds: float = 10.0,
) -> int:
    """Wait for Chrome's visible top-level HWND after framework launch."""
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            return client.find_browser_hwnd(browser_pid, allow_first=True)
        except CaptureSDKError as error:
            last_error = str(error)
            time.sleep(0.2)
    raise CaptureSDKError(
        f"Browser PID {browser_pid} did not expose a visible HWND. {last_error}"
    )


def print_capture_target(client: CaptureSDKClient, browser_pid: int, hwnd: int) -> None:
    print(f"Browser PID: {browser_pid}")
    print(f"Browser HWND: 0x{hwnd:x}")
    for window in client.list_browser_windows():
        if window.hwnd == hwnd:
            print(f"Window title: {window.title}")
            return


def capture_automation(
    client: CaptureSDKClient,
    hwnd: int,
    output: str | Path,
    actions: Callable[[], None],
    *,
    session_id: str,
    fps: int = 10,
) -> Path:
    """Start CaptureSDK, execute actions, then always stop and finalize MP4."""
    with client.start(
        hwnd=hwnd,
        output=output,
        session_id=session_id,
        fps=fps,
        width=1920,
        height=1080,
        bitrate_kbps=2500,
        encoder="auto",
    ) as session:
        print(f"Capture session started: {session.session_id}")
        actions()
    print(f"Capture finalized: {session.output_path}")
    return session.output_path

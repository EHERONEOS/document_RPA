from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from DrissionPage import ChromiumOptions, ChromiumPage
from capturesdk import CaptureSDKClient, CaptureSDKError

from app.core.logging.logger import log

def browser_pid_from_drissionpage(page: ChromiumPage) -> int:
    """Read the Chrome PID from DrissionPage's Chromium driver/process object."""
    candidates = [
        getattr(page, "process_id", None),
        getattr(getattr(page, "browser", None), "process_id", None),
        getattr(getattr(page, "browser", None), "_process_id", None),
    ]
    for value in candidates:
        if isinstance(value, int) and value > 0:
            return value
    raise CaptureSDKError(
        "DrissionPage did not expose a browser PID in this installed version. "
        "Launch Chrome with a known debugger port and resolve the PID in your project launcher."
    )

class Recorder:
    """录屏控制器。"""

    def __init__(
        self,
        page: Any | None = None,
        *,
        record_dir: str | Path = "runtime/records",
    ) -> None:
        self.page = page
        self.record_dir = Path(record_dir)
        base_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        self.file_path = str(self.record_dir / base_name)
        self.record_dir.mkdir(parents=True, exist_ok=True)
       


    def start(self) -> str:
        """开始录屏。"""
        client = CaptureSDKClient()
        browser_pid = browser_pid_from_drissionpage(self.page)
        hwnd = client.wait_for_browser_hwnd(browser_pid, allow_first=True)
        session = client.start(
            hwnd=hwnd,
            output=self.file_path,
            fps=10,
            width=1920,
            height=1080,
            bitrate_kbps=2500,
            encoder="cpu",
        )
        return session


        



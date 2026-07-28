from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from DrissionPage import ChromiumPage
from capturesdk import CaptureSDKClient, CaptureSDKError, CaptureSession, RecordResult

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
        self.record_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.record_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        self.client = CaptureSDKClient()
        self.session: CaptureSession | None = None

    def start(self) -> "Recorder":
        """开始录屏。"""
        if self.session and self.session.is_running:
            return self
        if self.page is None:
            raise CaptureSDKError("录屏启动失败：page 不能为空。")

        browser_pid = browser_pid_from_drissionpage(self.page)
        hwnd = self.client.wait_for_browser_hwnd(browser_pid, allow_first=True)
        self.session = self.client.start(
            hwnd=hwnd,
            output=self.file_path,
            fps=10,
            width=1920,
            height=1080,
            bitrate_kbps=2500,
            encoder="cpu",
        )
        log.info(f"录屏已开始: {self.file_path}")
        return self

    def stop(self) -> RecordResult | None:
        """停止录屏。"""
        if not self.session or not self.session.is_running:
            return None
        result = self.session.stop()
        log.info(f"录屏已停止: {result.output_path}")
        return result

    def is_running(self) -> bool:
        """录屏是否正在运行。"""
        return bool(self.session and self.session.is_running)



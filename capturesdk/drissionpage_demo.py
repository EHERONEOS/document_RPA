from __future__ import annotations

import os
from pathlib import Path

from DrissionPage import ChromiumOptions, ChromiumPage

from capturesdk import CaptureSDKClient, CaptureSDKError


OUTPUT = Path(os.environ.get("CAPTURESDK_OUTPUT", "drissionpage-demo.mp4"))
DEBUG_PORT = int(os.environ.get("DRISSIONPAGE_DEBUG_PORT", "9230"))


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


def main(mp4_file_path) -> None:
    client = CaptureSDKClient()
    options = ChromiumOptions()
    options.set_local_port(DEBUG_PORT)
    options.headless(False)
    options.set_argument("--start-maximized")
    page = ChromiumPage(addr_or_opts=options)

    try:
        browser_pid = browser_pid_from_drissionpage(page)
        hwnd = client.wait_for_browser_hwnd(browser_pid, allow_first=True)
        print(f"Browser PID: {browser_pid}")
        print(f"Browser HWND: 0x{hwnd:x}")

        # Start exactly before DrissionPage browser steps to record.
        with client.start(
            hwnd=hwnd,
            output=mp4_file_path,
            session_id="drissionpage-example",
            fps=10,
            width=1920,
            height=1080,
            bitrate_kbps=2500,
            encoder="auto",
        ):
            page.get("https://example.com")
            print(f"Page title: {page.title}")
            print(f"Heading: {page.ele('tag:h1').text}")
            page.run_js("window.scrollTo(0, document.body.scrollHeight)")

        print(f"Video created: {OUTPUT.resolve()}")
    finally:
        page.quit()


if __name__ == "__main__":
    OUTPUT = Path(r"F:\CCAM\CaptureFolder\20260727.mp4")
    main(OUTPUT)

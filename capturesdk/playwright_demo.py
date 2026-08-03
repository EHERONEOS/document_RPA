from __future__ import annotations

import os
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

from capturesdk import CaptureSDKClient, CaptureSDKError


OUTPUT = Path(os.environ.get("CAPTURESDK_OUTPUT", "playwright-demo.mp4"))
DEBUG_PORT = int(os.environ.get("PLAYWRIGHT_DEBUG_PORT", "9229"))
USER_DATA_DIR = Path(os.environ.get("PLAYWRIGHT_PROFILE", ".playwright-capturesdk-profile"))


def find_chromium_executable() -> str:
    """Use the Chromium executable downloaded by Playwright."""
    with sync_playwright() as playwright:
        executable = playwright.chromium.executable_path
    if not executable or not Path(executable).exists():
        raise CaptureSDKError("Playwright Chromium executable was not found. Run: playwright install chromium")
    return executable


def main() -> None:
    client = CaptureSDKClient()
    chromium = find_chromium_executable()
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        chromium,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR.resolve()}",
        "--start-maximized",
        "about:blank",
    ]
    browser_process = subprocess.Popen(command)

    try:
        browser_pid = client.find_browser_pid_by_debug_port(DEBUG_PORT)
        hwnd = client.wait_for_browser_hwnd(browser_pid, allow_first=True)
        print(f"Browser PID: {browser_pid}")
        print(f"Browser HWND: 0x{hwnd:x}")

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            # Start exactly before Playwright operations to record.
            with client.start(
                hwnd=hwnd,
                output=OUTPUT,
                session_id="playwright-example",
                fps=10,
                width=1920,
                height=1080,
                bitrate_kbps=2500,
                encoder="auto",
            ):
                page.goto("https://example.com", wait_until="domcontentloaded")
                page.locator("h1").wait_for()
                print(f"Page title: {page.title()}")
                print(f"Heading: {page.locator('h1').inner_text()}")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

            print(f"Video created: {OUTPUT.resolve()}")
            browser.close()
    finally:
        if browser_process.poll() is None:
            browser_process.terminate()
            try:
                browser_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                browser_process.kill()


if __name__ == "__main__":
    main()

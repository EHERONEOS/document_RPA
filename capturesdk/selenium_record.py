
import re
import subprocess
from pathlib import Path

from capturesdk import CaptureSDKClient, CaptureSDKError
from capturesdk.framework_helpers import wait_for_browser_hwnd, find_chrome_pid_by_debug_port
from utils.local_browser import connect_exist_browser, chrome_port

def run_powershell(script: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def find_chrome_pid(debugger_address: str, chromedriver_pid: int) -> int:
    """Find Chrome launched by Selenium without matching window titles."""
    port_match = re.search(r":(\d+)$", debugger_address)
    if not port_match:
        raise CaptureSDKError(f"Unexpected Selenium debugger address: {debugger_address}")

    port = port_match.group(1)
    by_port = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -eq 'chrome.exe' -and $_.CommandLine -like '*--remote-debugging-port="
        + port
        + "*' "
        "} | Select-Object -First 1 -ExpandProperty ProcessId; "
        "if ($p) { Write-Output $p }"
    )
    value = run_powershell(by_port)
    if value:
        return int(value)

    by_parent = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -eq 'chrome.exe' -and $_.ParentProcessId -eq "
        + str(chromedriver_pid)
        + " "
        "} | Select-Object -First 1 -ExpandProperty ProcessId; "
        "if ($p) { Write-Output $p }"
    )
    value = run_powershell(by_parent)
    if value:
        return int(value)

    raise CaptureSDKError("Could not find the Chrome process launched by Selenium.")



def main(mp4_file_path) -> None:
    client = CaptureSDKClient()
    driver = connect_exist_browser(chrome_port)

    try:
        debugger_address = driver.capabilities["goog:chromeOptions"]["debuggerAddress"] # 提取地址
        browser_pid = find_chrome_pid_by_debug_port(debugger_address.split(":")[1])  # 通过端口号获取进程ID
        # browser_pid = find_chrome_pid(debugger_address, driver.service.process.pid)
        hwnd = wait_for_browser_hwnd(client, browser_pid)  # 通过集成ID 获取采集所需要的句柄
        print(f"Browser PID: {browser_pid}")
        print(f"Browser HWND: 0x{hwnd:x}")

        # Start exactly before the browser actions to record.
        # 这里使用with的方式，在离开with的生命周期后，自动停止录制。
        # SDK 支持主动开始录制和停止录制。
        with client.start(
                hwnd=hwnd,
                output=mp4_file_path,
                session_id="selenium-example",
                fps=10,
                width=1920,
                height=1080,
                bitrate_kbps=2500,
                encoder="auto",
        ):
            driver.get("https://example.com")
            print(f"Page title: {driver.title}")

            # Put any Selenium interactions that should appear in the video here.
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")

        # Context exit sends Stop using this session ID and waits for finalized MP4.
        print(f"Video created: {OUTPUT.resolve()}")
    finally:
        driver.quit()

if __name__ == "__main__":
    OUTPUT = Path(r"F:\CCAM\CaptureFolder\20260727.mp4")
    main(OUTPUT)

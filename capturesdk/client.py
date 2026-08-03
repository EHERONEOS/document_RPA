from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


class CaptureSDKError(RuntimeError):
    """Raised when CaptureSDK CLI cannot start, stop, or finalize a recording."""


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    class_name: str
    title: str


@dataclass(frozen=True)
class RecordResult:
    session_id: str
    output_path: Path
    state: str
    stdout: str
    stderr: str


class CaptureSession:
    """One background CaptureSDK recording controlled by a unique session ID."""

    def __init__(
        self,
        client: "CaptureSDKClient",
        session_id: str,
        output_path: Path,
        process: subprocess.Popen,
    ) -> None:
        self._client = client
        self.session_id = session_id
        self.output_path = output_path
        self._process = process
        self._stopped = False

    @property
    def is_running(self) -> bool:
        return self._process.poll() is None

    def status(self) -> dict[str, str]:
        return self._client.status(self.session_id)

    def stop(self, timeout_seconds: float = 60.0) -> RecordResult:
        """Signal Stop and wait for WGC/FFmpeg to finalize the MP4."""
        if self._stopped:
            return RecordResult(self.session_id, self.output_path, "stopped", "", "")

        self._client._run(["record", "stop", "--session-id", self.session_id], check=True)
        try:
            stdout, stderr = self._process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            self._process.kill()
            stdout, stderr = self._process.communicate()
            raise CaptureSDKError(
                f"CaptureSDK did not finalize session '{self.session_id}' within {timeout_seconds} seconds.\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            ) from error

        self._stopped = True
        if self._process.returncode != 0:
            raise CaptureSDKError(
                f"CaptureSDK session '{self.session_id}' exited with {self._process.returncode}.\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )

        state = self.status().get("state", "completed")
        return RecordResult(self.session_id, self.output_path, state, stdout, stderr)

    def __enter__(self) -> "CaptureSession":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.is_running:
            self.stop()


class CaptureSDKClient:
    """Reusable HWND-first Python client for CaptureSDK CLI."""

    _window_pattern = re.compile(
        r'^HWND=0x([0-9a-fA-F]+)\s+PID=(\d+)\s+CLASS="([^"]*)"\s+TITLE="(.*)"$',
        re.MULTILINE,
    )

    def __init__(self, cli_path: Optional[str | Path] = None) -> None:
        default_path = Path(__file__).resolve().parent / "CaptureSDK.Cli.exe"
        self.cli_path = Path(cli_path or os.environ.get("CAPTURESDK_CLI", default_path)).resolve()
        self.working_directory = self.cli_path.parent

        if not self.cli_path.exists():
            raise CaptureSDKError(f"CaptureSDK CLI was not found: {self.cli_path}")

    def diagnose(self) -> str:
        return self._run(["diagnose"], check=True).stdout.strip()

    def list_browser_windows(self) -> list[WindowInfo]:
        result = self._run(["list-browsers"], check=True)
        return [
            WindowInfo(int(hwnd, 16), int(pid), class_name, title)
            for hwnd, pid, class_name, title in self._window_pattern.findall(result.stdout)
        ]

    def find_browser_hwnd(self, pid: int, *, allow_first: bool = False) -> int:
        matches = [window for window in self.list_browser_windows() if window.pid == pid]
        if not matches:
            raise CaptureSDKError(f"No visible browser HWND found for PID {pid}.")
        if len(matches) > 1 and not allow_first:
            candidates = ", ".join(f"0x{window.hwnd:x}" for window in matches)
            raise CaptureSDKError(
                f"PID {pid} owns multiple visible browser windows: {candidates}. "
                "Pass the exact HWND to start()."
            )
        return matches[0].hwnd

    def find_browser_pid_by_debug_port(self, port: int) -> int:
        """Find Chrome/Chromium started with a known DevTools remote-debugging port."""
        if port <= 0 or port > 65535:
            raise CaptureSDKError("port must be between 1 and 65535.")
        script = (
            "$p = Get-CimInstance Win32_Process | Where-Object { "
            "$_.Name -in @('chrome.exe','msedge.exe','chromium.exe') -and "
            "$_.CommandLine -like '*--remote-debugging-port=" + str(port) + "*' "
            "} | Select-Object -First 1 -ExpandProperty ProcessId; "
            "if ($p) { Write-Output $p }"
        )
        value = self._run_powershell(script)
        if not value:
            raise CaptureSDKError(
                f"No Chromium browser process found with --remote-debugging-port={port}."
            )
        return int(value)

    def find_browser_pid_by_parent(self, parent_pid: int) -> int:
        """Find a Chrome/Chromium child process of a known launcher process."""
        if parent_pid <= 0:
            raise CaptureSDKError("parent_pid must be positive.")
        script = (
            "$p = Get-CimInstance Win32_Process | Where-Object { "
            "$_.Name -in @('chrome.exe','msedge.exe','chromium.exe') -and "
            "$_.ParentProcessId -eq " + str(parent_pid) + " "
            "} | Select-Object -First 1 -ExpandProperty ProcessId; "
            "if ($p) { Write-Output $p }"
        )
        value = self._run_powershell(script)
        if not value:
            raise CaptureSDKError(
                f"No Chromium browser child process found for launcher PID {parent_pid}."
            )
        return int(value)

    def find_browser_hwnd_by_debug_port(
        self,
        port: int,
        *,
        allow_first: bool = False,
        timeout_seconds: float = 10.0,
    ) -> int:
        """Resolve Chromium DevTools port to visible browser HWND."""
        pid = self.find_browser_pid_by_debug_port(port)
        return self.wait_for_browser_hwnd(pid, allow_first=allow_first, timeout_seconds=timeout_seconds)

    def wait_for_browser_hwnd(
        self,
        pid: int,
        *,
        allow_first: bool = False,
        timeout_seconds: float = 10.0,
    ) -> int:
        """Wait until a launched browser process exposes a visible HWND."""
        deadline = time.monotonic() + timeout_seconds
        last_error = ""
        while time.monotonic() < deadline:
            try:
                return self.find_browser_hwnd(pid, allow_first=allow_first)
            except CaptureSDKError as error:
                last_error = str(error)
                time.sleep(0.2)
        raise CaptureSDKError(
            f"Browser PID {pid} did not expose a visible HWND. {last_error}"
        )

    def _run_powershell(self, script: str) -> str:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise CaptureSDKError(
                f"PowerShell browser discovery failed ({result.returncode}).\n{result.stderr}"
            )
        return result.stdout.strip()

    def start(
        self,
        *,
        hwnd: int,
        output: str | Path,
        session_id: Optional[str] = None,
        fps: int = 10,
        width: int = 1920,
        height: int = 1080,
        bitrate_kbps: int = 2500,
        encoder: str = "auto",
        startup_timeout_seconds: float = 15.0,
    ) -> CaptureSession:
        """Start a long-running recording for an exact browser HWND."""
        if hwnd <= 0:
            raise CaptureSDKError("hwnd must be a non-zero Windows handle.")
        if session_id is None:
            session_id = f"py-{uuid.uuid4().hex[:12]}"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
            raise CaptureSDKError("session_id must contain only letters, numbers, '-' or '_', up to 64 characters.")

        output_path = Path(output)

        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path

        output_path = output_path.resolve()
        arguments = [
            "record",
            "--hwnd", hex(hwnd),
            "--session-id", session_id,
            "--output", str(output_path),
            "--fps", str(fps),
            "--width", str(width),
            "--height", str(height),
            "--bitrate-kbps", str(bitrate_kbps),
            "--encoder", encoder,
            "--overwrite",
        ]
        process = subprocess.Popen(
            [str(self.cli_path), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=self.working_directory,
        )
        session = CaptureSession(self, session_id, output_path, process)
        self._wait_until_recording(session, startup_timeout_seconds)
        return session

    def status(self, session_id: str) -> dict[str, str]:
        result = self._run(["record", "status", "--session-id", session_id], check=False)
        if result.returncode != 0:
            return {}
        return dict(
            line.split("=", 1)
            for line in result.stdout.splitlines()
            if "=" in line
        )

    def _wait_until_recording(self, session: CaptureSession, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_status = ""
        while time.monotonic() < deadline:
            if session._process.poll() is not None:
                stdout, stderr = session._process.communicate()
                raise CaptureSDKError(
                    f"CaptureSDK session '{session.session_id}' exited early with {session._process.returncode}.\n"
                    f"stdout:\n{stdout}\nstderr:\n{stderr}"
                )

            status = session.status()
            last_status = str(status)
            if status.get("state") == "recording":
                return
            if status.get("state") == "failed":
                raise CaptureSDKError(f"CaptureSDK session '{session.session_id}' failed: {status}")
            time.sleep(0.2)

        raise CaptureSDKError(
            f"CaptureSDK session '{session.session_id}' did not enter recording state. Last status: {last_status}"
        )

    def _run(self, arguments: Sequence[str], *, check: bool) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [str(self.cli_path), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=self.working_directory,
        )
        if check and result.returncode != 0:
            raise CaptureSDKError(
                f"CaptureSDK command failed ({result.returncode}): {' '.join(arguments)}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

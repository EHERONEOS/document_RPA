"""跨平台查找和终止本机 RPA Chromium 进程。"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from collections.abc import Iterable

from app.core.logging.logger import log


_CHROMIUM_NAMES = {
    "chrome",
    "chrome.exe",
    "chromium",
    "chromium.exe",
    "msedge",
    "msedge.exe",
    "google chrome",
    "google chrome for testing",
}


def terminate_browser_pids(pids: Iterable[int | None], *, wait_seconds: float = 1.0) -> list[int]:
    """终止浏览器进程及其子进程，返回实际尝试终止的 PID。"""
    unique = sorted({int(pid) for pid in pids if pid})
    if not unique:
        return []
    if os.name == "nt":
        for pid in unique:
            _taskkill(pid)
        return unique

    targets = list(unique)
    for pid in unique:
        for child in _descendant_pids(pid):
            if child not in targets:
                targets.append(child)
    for pid in targets:
        _send_signal(pid, signal.SIGTERM)
    deadline = time.time() + max(wait_seconds, 0)
    while time.time() < deadline:
        if not any(_pid_exists(pid) for pid in targets):
            return targets
        time.sleep(0.05)
    for pid in targets:
        _send_signal(pid, signal.SIGKILL)
    return targets


def find_chromium_pids_by_debug_ports(ports: Iterable[int]) -> dict[int, list[int]]:
    """按 ``--remote-debugging-port`` 查找本机 Chromium 进程。"""
    wanted = {int(port) for port in ports if 0 < int(port) <= 65535}
    if not wanted:
        return {}

    found: dict[int, list[int]] = {port: [] for port in wanted}
    for pid, command in _iter_process_commands():
        if not _looks_like_chromium(command):
            continue
        port = _debug_port_from_command(command)
        if port in found and pid not in found[port]:
            found[port].append(pid)
    return {port: pids for port, pids in found.items() if pids}


def find_rpa_chromium_pids(
    *,
    ports: Iterable[int] | None = None,
    user_data_dir: str | os.PathLike[str] | None = None,
    exclude_ports: Iterable[int] | None = None,
) -> list[int]:
    """查找属于本机 RPA 的 Chromium 进程。

    匹配调试端口命中、或 ``--user-data-dir`` 位于给定 profile 根目录下的进程。
    ``exclude_ports`` 用于跳过仍在执行任务的槽位。
    """
    wanted_ports = {int(port) for port in (ports or []) if 0 < int(port) <= 65535}
    skipped = {int(port) for port in (exclude_ports or []) if port}
    root = _normalize_user_data_dir(user_data_dir)
    if not wanted_ports and root is None:
        return []

    pids: list[int] = []
    for pid, command in _iter_process_commands():
        if not _looks_like_chromium(command):
            continue
        port = _debug_port_from_command(command)
        if port is None or port in skipped:
            continue
        matched = port in wanted_ports
        if not matched and root is not None:
            data_dir = _user_data_dir_from_command(command)
            matched = data_dir is not None and _is_under_directory(data_dir, root)
        if matched and pid not in pids:
            pids.append(pid)
    return pids


def _taskkill(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"终止浏览器进程失败 pid={pid} error={exc}", level="ERROR")


def _send_signal(pid: int, sig: signal.Signals) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError as exc:
        log(f"向浏览器进程发信号失败 pid={pid} signal={sig.name} error={exc}", level="ERROR")
    except OSError:
        return


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _iter_process_commands() -> list[tuple[int, str]]:
    try:
        if os.name == "nt":
            return _iter_windows_process_commands()
        return _iter_posix_process_commands()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log(f"枚举浏览器进程失败：{exc}", level="ERROR")
        return []


def _iter_windows_process_commands() -> list[tuple[int, str]]:
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -in @('chrome.exe','msedge.exe','chromium.exe') } | "
        "ForEach-Object { '{0}\t{1}' -f $_.ProcessId, $_.CommandLine }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    rows: list[tuple[int, str]] = []
    for line in (result.stdout or "").splitlines():
        pid, command = _split_pid_command(line)
        if pid is not None:
            rows.append((pid, command))
    return rows


def _iter_posix_process_commands() -> list[tuple[int, str]]:
    result = subprocess.run(
        ["ps", "-axww", "-o", "pid=,command="],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    rows: list[tuple[int, str]] = []
    for line in (result.stdout or "").splitlines():
        pid, command = _split_pid_command(line)
        if pid is not None:
            rows.append((pid, command))
    return rows


def _split_pid_command(line: str) -> tuple[int | None, str]:
    text = line.strip()
    if not text:
        return None, ""
    if "\t" in text:
        pid_text, command = text.split("\t", 1)
    else:
        parts = text.split(None, 1)
        if len(parts) != 2:
            return None, ""
        pid_text, command = parts
    try:
        return int(pid_text.strip()), command.strip()
    except ValueError:
        return None, ""


def _looks_like_chromium(command: str) -> bool:
    lowered = command.lower()
    return any(name in lowered for name in _CHROMIUM_NAMES)


def _debug_port_from_command(command: str) -> int | None:
    match = re.search(r"--remote-debugging-port=(\d+)", command)
    if not match:
        return None
    port = int(match.group(1))
    if 0 < port <= 65535:
        return port
    return None


def _user_data_dir_from_command(command: str) -> str | None:
    match = re.search(r"--user-data-dir(?:=|\s+)(\"[^\"]+\"|'[^']+'|\S+)", command)
    if not match:
        return None
    return match.group(1).strip().strip("\"'")


def _normalize_user_data_dir(user_data_dir: str | os.PathLike[str] | None) -> str | None:
    if not user_data_dir:
        return None
    try:
        return str(os.path.realpath(user_data_dir))
    except OSError:
        return str(user_data_dir)


def _is_under_directory(path: str, root: str) -> bool:
    try:
        real_path = os.path.realpath(path)
        real_root = os.path.realpath(root)
    except OSError:
        real_path = path
        real_root = root
    return real_path == real_root or real_path.startswith(real_root + os.sep)


def _descendant_pids(pid: int) -> list[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-P", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    children: list[int] = []
    for token in (result.stdout or "").split():
        try:
            child = int(token)
        except ValueError:
            continue
        children.extend(_descendant_pids(child))
        children.append(child)
    return children

"""DrissionPage Chromium 启动方式定制。"""

import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock

from app.core.task.errors import BrowserStartError


_PATCH_LOCK = Lock()
_DETACHED_BROWSER_ARG = "--detached-browser-command"


def _get_drission_browser_module():
    """获取 DrissionPage 内部的浏览器启动模块。"""
    from DrissionPage._functions import browser as drission_browser

    return drission_browser


def _run_browser_detached(port, path, args):
    """在 Worker 的进程组和进程树之外启动 Chromium。"""
    command = _build_browser_command(port, path, args)

    if os.name == "nt":
        return _spawn_windows_orphan(command)
    if sys.platform == "darwin":
        return _spawn_macos_orphan(command)
    return _spawn_posix_orphan(command)


def _build_browser_command(port, path, args):
    """同步校验浏览器路径，保留 DrissionPage 的系统浏览器回退逻辑。"""
    browser_path = Path(path)
    executable = str(browser_path / "chrome") if browser_path.is_dir() else str(browser_path)
    if not Path(executable).is_file():
        # DrissionPage 仅捕获 FileNotFoundError 后才会自动查找系统 Chrome。
        raise FileNotFoundError(executable)
    return [executable, f"--remote-debugging-port={port}", *args]


def _build_launcher_command(command):
    """构建供一次性辅助进程使用的启动命令。"""
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        _DETACHED_BROWSER_ARG,
        json.dumps(command, ensure_ascii=True),
    ]


def _windows_creationflags(include_breakaway=True):
    """构建 Windows 独立进程所需的创建标志。"""
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    if include_breakaway:
        creationflags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    return creationflags


def _popen_windows_detached(command):
    """启动 Windows 独立进程，Job Object 不允许脱离时降级继续启动。"""
    kwargs = {
        "shell": False,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    try:
        return subprocess.Popen(
            command,
            creationflags=_windows_creationflags(include_breakaway=True),
            **kwargs,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) != 5:
            raise BrowserStartError(f"浏览器启动失败：{exc}") from exc
        return subprocess.Popen(
            command,
            creationflags=_windows_creationflags(include_breakaway=False),
            **kwargs,
        )


def _spawn_windows_orphan(command):
    """通过 cmd.exe 启动浏览器，避免 PyCharm 向 Python 子进程注入调试器。"""
    cmd_executable = os.environ.get("ComSpec", "cmd.exe")
    cmd_path = subprocess.list2cmdline([cmd_executable])
    chrome_command = subprocess.list2cmdline(command)
    # 传入完整命令行，避免 Popen(list) 将 start 的空标题 "" 转义为 \"\"。
    return _popen_windows_detached(
        f'{cmd_path} /d /c start "" /b {chrome_command}'
    )


def _spawn_macos_orphan(command):
    """通过 LaunchServices 启动 Chrome，避免 PyCharm 调试器拦截 Python 子进程。"""
    executable = Path(command[0])
    app_bundle = next((parent for parent in executable.parents if parent.suffix == ".app"), None)
    if app_bundle is None:
        return _spawn_posix_orphan(command)

    return subprocess.Popen(
        ["/usr/bin/open", "-n", str(app_bundle), "--args", *command[1:]],
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _spawn_posix_orphan(command):
    """通过一次性辅助进程将 Chromium 交给系统进程管理器接管。"""
    launcher_command = _build_launcher_command(command)
    return subprocess.Popen(
        launcher_command,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _orphan_and_exec(command):
    """在单线程辅助进程内派生 Chromium，使其不再是 Worker 的后代。"""
    child_pid = os.fork()
    if child_pid:
        os._exit(0)

    os.setsid()
    os.execvpe(command[0], command, os.environ)


def _run_detached_browser_command():
    """处理仅供 POSIX 辅助进程调用的 Chromium 启动命令。"""
    if len(sys.argv) != 3 or sys.argv[1] != _DETACHED_BROWSER_ARG:
        return 1

    command = json.loads(sys.argv[2])
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise BrowserStartError("浏览器启动命令格式错误")

    if os.name == "nt":
        return 1

    _orphan_and_exec(command)
    return 0


def enable_detached_chromium_launch():
    """使新启动的浏览器在队列 Worker 退出后仍继续运行。

    DrissionPage 4.1.1.4 未暴露进程会话配置，因此在创建 Chromium 前替换
    其内部启动钩子。仅当调试端口未被占用时 DrissionPage 才会调用该钩子；
    已存在的浏览器仍按原逻辑直接接管。Windows 使用 cmd.exe、macOS 使用
    LaunchServices，均避免 PyCharm 调试器拦截 Python 子进程；其他 POSIX
    环境额外二次派生并创建独立会话。
    """
    drission_browser = _get_drission_browser_module()

    with _PATCH_LOCK:
        if drission_browser._run_browser is not _run_browser_detached:
            drission_browser._run_browser = _run_browser_detached


if __name__ == "__main__":
    raise SystemExit(_run_detached_browser_command())

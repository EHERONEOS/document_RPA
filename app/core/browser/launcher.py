"""DrissionPage Chromium 启动方式定制。"""

import os
from pathlib import Path
import subprocess
from threading import Lock


_PATCH_LOCK = Lock()


def _get_drission_browser_module():
    """获取 DrissionPage 内部的浏览器启动模块。"""
    from DrissionPage._functions import browser as drission_browser

    return drission_browser


def _run_browser_detached(port, path, args):
    """在 Worker 所属终端进程组之外启动 Chromium。"""
    browser_path = Path(path)
    executable = str(browser_path / "chrome") if browser_path.is_dir() else str(browser_path)
    command = [executable, f"--remote-debugging-port={port}", *args]
    kwargs = {"shell": False, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen(command, **kwargs)


def enable_detached_chromium_launch():
    """使新启动的浏览器在队列 Worker 退出后仍继续运行。

    DrissionPage 4.1.1.4 未暴露进程会话配置，因此在创建 Chromium 前替换
    其内部启动钩子。仅当调试端口未被占用时 DrissionPage 才会调用该钩子；
    已存在的浏览器仍按原逻辑直接接管。
    """
    drission_browser = _get_drission_browser_module()

    with _PATCH_LOCK:
        if drission_browser._run_browser is not _run_browser_detached:
            drission_browser._run_browser = _run_browser_detached

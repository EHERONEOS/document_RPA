from datetime import datetime
from inspect import currentframe
from pathlib import Path
import os
import sys


_LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[34m",
    "WARN": "\033[33m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
}
_RESET = "\033[0m"
_LOGGER_FILE = Path(__file__).resolve()


def _display_path(file_path):
    path = Path(file_path).resolve()
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return path.name


def _caller():
    frame = currentframe()
    try:
        while frame:
            frame = frame.f_back
            if not frame:
                break
            if Path(frame.f_code.co_filename).resolve() != _LOGGER_FILE:
                return (
                    _display_path(frame.f_code.co_filename),
                    frame.f_code.co_name,
                    frame.f_lineno,
                )
        return "<unknown>", "<unknown>", 0
    finally:
        del frame


def _supports_color():
    if getattr(sys.stdout, "isatty", lambda: False)():
        return True
    return "PYCHARM_HOSTED" in os.environ


def _colorize(level):
    if not _supports_color():
        return level
    return f"{_LEVEL_COLORS.get(level, _RESET)}{level}{_RESET}"


def log(message, level="INFO"):
    """打印带有时间、调用位置和级别的彩色执行日志。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    level = str(level).upper()
    file_path, function, line = _caller()
    print(
        f"[{now}] [{file_path}] [{function}:{line}] [{_colorize(level)}] {message}",
        flush=True,
    )


def info(message):
    """打印 INFO 日志。"""
    log(message, level="INFO")


def warn(message):
    """打印 WARN 日志。"""
    log(message, level="WARN")


def error(message):
    """打印 ERROR 日志。"""
    log(message, level="ERROR")


class Logger:
    """简单日志对象封装。"""

    def log(self, message, level="INFO"):
        """打印指定级别日志。"""
        log(message, level=level)

    def info(self, message):
        """打印 INFO 日志。"""
        self.log(message, level="INFO")

    def warn(self, message):
        """打印 WARN 日志。"""
        self.log(message, level="WARN")

    def error(self, message):
        """打印 ERROR 日志。"""
        self.log(message, level="ERROR")

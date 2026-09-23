from datetime import datetime
from inspect import currentframe
from pathlib import Path
import os
import sys


_LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[34m",
    "SUCCESS": "\033[32m",
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
    # 执行日志会话存在时旁路上报（无上下文/未开启时为 no-op，绝不影响业务）
    _report_to_log_service(message, level, file_path, line)


def _report_to_log_service(message, level, file_path, line):
    """把日志交给当前执行的日志会话（懒导入避免循环依赖）。"""
    try:
        from app.core.logging.log_session import report_log

        report_log(message, level=level, source_file=file_path, source_line=line)
    except Exception:
        pass  # 上报链路任何问题都不影响控制台打印


def info(message):
    """打印 INFO 日志。"""
    log(message, level="INFO")


def success(message):
    """打印 SUCCESS 日志（绿色）。"""
    log(message, level="SUCCESS")


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

    def success(self, message):
        """打印 SUCCESS 日志（绿色）。"""
        self.log(message, level="SUCCESS")

    def warn(self, message):
        """打印 WARN 日志。"""
        self.log(message, level="WARN")

    def error(self, message):
        """打印 ERROR 日志。"""
        self.log(message, level="ERROR")

    def finish_execution(self, *, success, remark="", fail_img="", record_files=None):
        """日志服务终态上报（§6.4）；无执行会话时为 no-op。"""
        from app.core.logging.log_session import finish_execution as _finish_execution

        _finish_execution(
            success=success,
            remark=remark,
            fail_img=fail_img,
            record_files=record_files,
        )

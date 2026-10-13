from datetime import datetime
from inspect import currentframe
from pathlib import Path
import os
import re
import sys
import threading


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

# jobNo 维度的本地日志文件：同一单号重复消费时追加到原文件。
_JOB_LOG_DIR = Path("runtime/logs")
_ANSI_ESCAPE_RE = re.compile(r"\033\[[0-9;]*m")
_JOB_CONTEXT = threading.local()


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


def _safe_job_name(job_no):
    """将 jobNo 转换为跨平台安全的文件名片段。"""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(job_no)).strip("_")
    return safe or "unknown"


def _resolve_job_log_file(job_no, queue_name=""):
    """定位该 jobNo 的日志文件：已存在则复用（追加），否则按当前时间创建。"""
    safe_queue = _safe_job_name(queue_name) if str(queue_name or "").strip() else ""
    log_dir = _JOB_LOG_DIR / safe_queue if safe_queue else _JOB_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_job_name(job_no)
    existing = sorted(log_dir.glob(f"{safe_name}_*.log"))
    if existing:
        return existing[-1]
    created_at = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    return log_dir / f"{safe_name}_{created_at}.log"


def set_job_log_context(job_no, queue_name=""):
    """为当前线程绑定 jobNo 日志文件（按队列名分目录），后续 log() 会同步写入该文件。"""
    if job_no is None or str(job_no).strip() == "":
        return None
    file_path = _resolve_job_log_file(job_no, queue_name)
    _JOB_CONTEXT.file_path = file_path
    return file_path


def clear_job_log_context():
    """解除当前线程的 jobNo 日志文件绑定。"""
    _JOB_CONTEXT.file_path = None


def _write_job_file(line):
    """将去掉颜色码的日志行追加到当前线程绑定的日志文件。"""
    file_path = getattr(_JOB_CONTEXT, "file_path", None)
    if not file_path:
        return
    try:
        with open(file_path, "a", encoding="utf-8") as handle:
            handle.write(f"{_ANSI_ESCAPE_RE.sub('', line)}\n")
    except OSError:
        # 文件写入失败不影响控制台日志输出。
        pass


def log(message, level="INFO"):
    """打印带有时间、调用位置和级别的彩色执行日志，并同步写入 jobNo 日志文件。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    level = str(level).upper()
    file_path, function, line = _caller()
    prefix = f"[{now}] [{file_path}] [{function}:{line}]"
    print(f"{prefix} [{_colorize(level)}] {message}", flush=True)
    _write_job_file(f"{prefix} [{level}] {message}")
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

    def finish_execution(self, *, success, remark="", fail_img_object_name="", record_files=None):
        """日志服务终态上报（§6.4）；无执行会话时为 no-op。"""
        from app.core.logging.log_session import finish_execution as _finish_execution

        _finish_execution(
            success=success,
            remark=remark,
            fail_img_object_name=fail_img_object_name,
            record_files=record_files,
        )

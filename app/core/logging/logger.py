from datetime import datetime


def log(message, level="INFO"):
    """打印带级别的中文执行日志。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{str(level).upper()}] {message}")


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

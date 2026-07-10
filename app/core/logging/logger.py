from datetime import datetime


def log(message: str) -> None:
    """打印中文执行日志。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")

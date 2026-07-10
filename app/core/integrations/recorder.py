from app.core.logging.logger import log


class Recorder:
    """录屏控制器。"""

    def start(self, context) -> None:
        log(f"开始录屏 queue={context.queue_name}")

    def stop(self, context) -> str:
        log(f"停止录屏 queue={context.queue_name}")
        return ""

from app.core.logging.logger import log


class ResultPublisher:
    """任务结果回传。"""

    def publish_result(self, result):
        log(f"任务结果回传 {result.to_payload()}")

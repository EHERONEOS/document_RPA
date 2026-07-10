from app.core.logging.logger import log
from app.core.task.result import TaskResult


class ResultPublisher:
    """任务结果回传。"""

    def publish_result(self, result: TaskResult) -> None:
        log(f"任务结果回传 {result.to_payload()}")

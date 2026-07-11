from dataclasses import dataclass, field


@dataclass
class TaskResult:
    """任务回传结果。"""

    rpa_message_id: str
    queue_name: str
    success: bool
    message: str
    error_type: str = ""
    unfilled_fields: list = field(default_factory=list)
    screenshot_url: str = ""
    record_url: str = ""

    def to_payload(self):
        """转换为结果回传 payload。"""
        return {
            "rpaMessageId": self.rpa_message_id,
            "queueName": self.queue_name,
            "success": self.success,
            "message": self.message,
            "errorType": self.error_type,
            "unfilledFields": self.unfilled_fields,
            "screenshotUrl": self.screenshot_url,
            "recordUrl": self.record_url,
        }

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskResult:
    """任务回传结果。"""

    rpa_message_id: str
    queue_name: str
    success: bool
    message: str
    task_id: str = ""
    error_type: str = ""
    unfilled_fields: list = field(default_factory=list)
    screenshot_url: str = ""
    record_url: str = ""
    code: int | None = None
    save_type: int = 1
    attachments: list = field(default_factory=list)
    content: dict[str, Any] = field(default_factory=dict)

    def to_payload(self):
        """转换为结果回传 payload。"""
        return {
            "id": self.task_id,
            "rpaMessageId": self.rpa_message_id,
            "queueName": self.queue_name,
            "success": self.success,
            "message": self.message,
            "errorType": self.error_type,
            "unfilledFields": self.unfilled_fields,
            "screenshotUrl": self.screenshot_url,
            "recordUrl": self.record_url,
            "code": self.code,
            "saveType": self.save_type,
            "attachments": self.attachments,
            "content": self.content,
        }

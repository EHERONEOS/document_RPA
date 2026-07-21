from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskResult:
    """任务回传结果。"""
    task_id:str | int
    success: bool
    rpaMessageId: str
    saveType: int = 1
    img: str = ""
    code: int | None = None
    executeRecordFiles: str = ""
    remark: str = ""
    attachments: str = ""
    content: str = ""

    def to_payload(self):
        """转换为结果回传 payload。"""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "rpaMessageId": self.rpaMessageId,
            "saveType": self.saveType,
            "img": self.img,
            "executeRecordFiles": self.executeRecordFiles,
            "remark": self.remark,
            "code": self.code,
            "attachments": self.attachments,
            "content": self.content,
        }

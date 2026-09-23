"""Agent 上报接口（设计文档 §5.1）：Bearer token 鉴权，POST JSON Body，无路径参数。"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .. import repository
from ..settings import get_settings

router = APIRouter(tags=["agent"])

MAX_LOGS_PER_BATCH = 200  # §5.1：单批 ≤200 条


def ok(data) -> dict:
    """统一响应包装：``{code, message, data}``。"""
    return {"code": 0, "message": "ok", "data": data}


def verify_token(authorization: str = Header(default="")) -> None:
    """Bearer token 鉴权；服务端未配置 token 时放行（本地开发）。"""
    expected = get_settings().service_token.strip()
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class ExecutionCreate(BaseModel):
    rpaMessageId: str = Field(max_length=64)
    queueName: str = Field(max_length=128)
    jobId: str = Field(default="", max_length=64)
    deviceName: str = Field(default="", max_length=128)
    taskId: str = Field(default="", max_length=64)
    startedAt: Optional[str] = None
    customerCode: str = Field(default="", max_length=32)
    carrierCode: str = Field(default="", max_length=32)
    businessCode: str = Field(default="", max_length=32)


class LogItem(BaseModel):
    seq: int
    level: str = Field(default="INFO", max_length=10)
    message: str
    sourceFile: str = Field(default="", max_length=255)
    sourceLine: int = 0
    logTime: Optional[str] = None


class LogsBatch(BaseModel):
    executionId: int
    logs: List[LogItem]


class RecordFile(BaseModel):
    type: str = Field(max_length=64)
    mediaType: str = Field(default="IMAGE", max_length=10)
    fileName: str = Field(default="", max_length=255)
    url: str = Field(max_length=1024)
    storage: str = Field(default="OSS", max_length=10)
    fileSize: int = 0


class ExecutionFinish(BaseModel):
    executionId: int
    status: Literal["SUCCESS", "FAILED", "TIMEOUT"]
    remark: str = ""
    failImgUrl: str = Field(default="", max_length=1024)
    finishedAt: Optional[str] = None
    durationSeconds: Optional[int] = None
    recordFiles: List[RecordFile] = []


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------

@router.post("/executions")
def create_execution(body: ExecutionCreate, _: None = Depends(verify_token)) -> dict:
    """创建/幂等更新执行记录（uk_message_queue），返回 executionId（§5.1 / §12）。"""
    execution_id = repository.create_execution(
        rpa_message_id=body.rpaMessageId,
        queue_name=body.queueName,
        device_name=body.deviceName,
        job_id=body.jobId,
        task_id=body.taskId,
        started_at=body.startedAt,
        customer_code=body.customerCode,
        carrier_code=body.carrierCode,
        business_code=body.businessCode,
    )
    return ok({"executionId": execution_id, "status": "RUNNING"})


@router.post("/logs/batch")
def push_logs(body: LogsBatch, _: None = Depends(verify_token)) -> dict:
    """批量追加日志（单批 ≤200 条，§5.1）。"""
    if len(body.logs) > MAX_LOGS_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"logs batch size {len(body.logs)} exceeds limit {MAX_LOGS_PER_BATCH}",
        )
    accepted = repository.add_logs(
        body.executionId,
        [
            {
                "seq": item.seq,
                "level": item.level,
                "message": item.message,
                "source_file": item.sourceFile,
                "source_line": item.sourceLine,
                "log_time": item.logTime,
            }
            for item in body.logs
        ],
    )
    return ok({"accepted": accepted})


@router.post("/executions/finish")
def finish_execution(body: ExecutionFinish, _: None = Depends(verify_token)) -> dict:
    """结束执行；已终态的记录拒绝再次 finish（§9.2，以首次为准）。"""
    result = repository.finish_execution(
        execution_id=body.executionId,
        status=body.status,
        remark=body.remark,
        fail_img_url=body.failImgUrl,
        record_files=[
            {
                "type": item.type,
                "media_type": item.mediaType,
                "file_name": item.fileName,
                "url": item.url,
                "storage": item.storage,
                "file_size": item.fileSize,
            }
            for item in body.recordFiles
        ],
        finished_at=body.finishedAt,
        duration_seconds=body.durationSeconds,
    )
    if result["result"] == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=f"execution {body.executionId} not found")
    if result["result"] == "ALREADY_FINISHED":
        raise HTTPException(
            status_code=409,
            detail=f"execution {body.executionId} already finished with status {result.get('status')}",
        )
    return ok(
        {
            "executionId": body.executionId,
            "status": result["status"],
            "durationSeconds": result.get("durationSeconds"),
        }
    )

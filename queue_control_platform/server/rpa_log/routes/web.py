"""Web 控制台查询接口（设计文档 §5.2）：GET params，无路径参数，`{code, message, data}` 包装。

- ``/executions``        列表分页（消息ID/JobId 后缀模糊，队列/状态精确）
- ``/execution/detail``  主记录 + 日志（seq DESC）+ 文件列表
- ``/devices`` ``/queues``  维表列表 + 今日统计
- ``/stats/summary``     首页统计卡（今日总数/成功/失败/运行中）
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from .. import repository

router = APIRouter(tags=["web"])


def ok(data) -> dict:
    return {"code": 0, "message": "ok", "data": data}


def _today_start() -> datetime:
    """今日 0 点（应用时钟；与 create_time 的应用时钟口径一致）。"""
    now = datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/executions")
def list_executions(
    rpaMessageId: str = Query(default=""),
    jobId: str = Query(default=""),
    queueName: str = Query(default=""),
    deviceName: str = Query(default=""),
    status: str = Query(default=""),
    beginTime: str = Query(default=""),
    endTime: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=100),
) -> dict:
    """列表分页：消息ID/JobId 后缀模糊，队列/设备/状态精确（§5.2 / §12；设备筛选供设备页下钻）。"""
    data = repository.list_executions(
        rpa_message_id=rpaMessageId or None,
        job_id=jobId or None,
        queue_name=queueName or None,
        device_name=deviceName or None,
        status=status or None,
        begin_time=beginTime or None,
        end_time=endTime or None,
        page=page,
        page_size=pageSize,
    )
    return ok(data)


@router.get("/execution/detail")
def execution_detail(executionId: int = Query(..., ge=1)) -> dict:
    """详情：主记录 + 日志明细（seq DESC，从新到旧）+ 文件列表（§5.2 / §8.2）。"""
    execution = repository.get_execution(executionId)
    if execution is None:
        raise HTTPException(status_code=404, detail=f"execution {executionId} not found")
    return ok(
        {
            "execution": execution,
            "logs": repository.list_logs(executionId),
            "files": repository.list_files(executionId),
        }
    )


@router.get("/devices")
def list_devices() -> dict:
    """设备列表 + 统计（今日执行、成功率、最近心跳、在线状态）。"""
    return ok(repository.list_device_stats(_today_start()))


@router.get("/queues")
def list_queues() -> dict:
    """队列列表 + 统计（今日执行、成功率、平均耗时）。"""
    return ok(repository.list_queue_stats(_today_start()))


@router.get("/stats/summary")
def stats_summary() -> dict:
    """首页统计卡：今日总数 / 成功 / 失败（含 TIMEOUT）/ 运行中。"""
    return ok(repository.stats_summary(_today_start()))

"""服务内定时维护任务（设计文档 §3 CRON / T1.5）：RUNNING 超时置 TIMEOUT。

单实例部署（§11.3）：定时任务随 FastAPI 进程内的 asyncio 任务运行，
lifespan 启动 / 关停（见 main.py）。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from .db import db_cursor
from .settings import get_settings

logger = logging.getLogger("queue_control_platform.server.rpa_log.jobs")

SCAN_INTERVAL_SECONDS = 300  # 每 5 分钟扫描一次


def mark_running_timeout() -> int:
    """把 RUNNING 且 started_at 早于阈值（RPA_LOG_RUNNING_TIMEOUT_HOURS）的记录置 TIMEOUT。

    finished_at 取 started_at + 阈值（实际结束时刻未知，取超时判定点，
    保证 duration_seconds = finished_at - started_at 口径一致）。返回置位行数。
    """
    settings = get_settings()
    threshold = settings.running_timeout_hours
    cutoff = datetime.now() - timedelta(hours=threshold)
    duration_seconds = int(threshold * 3600)
    with db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE rpa_execution
            SET status = 'TIMEOUT',
                remark = %s,
                finished_at = DATE_ADD(started_at, INTERVAL %s HOUR),
                duration_seconds = %s,
                update_time = %s
            WHERE status = 'RUNNING' AND started_at < %s
            """,
            (
                f"RUNNING 超过 {threshold:g} 小时未结束，被定时任务置为 TIMEOUT",
                threshold,
                duration_seconds,
                datetime.now(),
                cutoff,
            ),
        )
        return cursor.rowcount


async def timeout_scanner_loop() -> None:
    """常驻扫描循环；任何异常只记日志，绝不中断（对齐 Agent 侧降级精神）。"""
    while True:
        try:
            marked = await asyncio.to_thread(mark_running_timeout)
            if marked:
                logger.warning("RUNNING 超时置位 TIMEOUT：%s 条", marked)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("RUNNING 超时扫描失败，下一轮重试")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

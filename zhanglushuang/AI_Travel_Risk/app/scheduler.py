"""
后台定时任务: 案件超时自动关闭 / 告警检查.
"""

import asyncio
import logging

from app.config import settings
from app.database import AsyncSessionLocal
from app.service.case import auto_close_timeout_cases

logger = logging.getLogger(__name__)


async def run_scheduler_once() -> None:
    """执行一次定时任务."""
    try:
        async with AsyncSessionLocal() as db:
            closed = await auto_close_timeout_cases(db, hours=settings.CASE_TIMEOUT_HOURS)
            await db.commit()
            if closed:
                logger.info("定时任务自动关闭案件: %s", closed)
    except Exception:
        logger.exception("定时任务执行失败")


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    """按配置间隔循环执行."""
    interval = settings.ALERT_SCHEDULER_INTERVAL_MIN
    if interval <= 0:
        logger.info("定时任务已关闭")
        return
    logger.info("定时任务启动, 间隔 %d 分钟", interval)
    while not stop_event.is_set():
        await run_scheduler_once()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval * 60)
        except asyncio.TimeoutError:
            continue


async def start_scheduler() -> asyncio.Task:
    """启动后台调度任务."""
    stop_event = asyncio.Event()
    return asyncio.create_task(scheduler_loop(stop_event))

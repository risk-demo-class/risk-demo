"""
后台调度: 告警检查 + 案件超时自动关闭
"""
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.service.alert import check_alerts
from app.service.case import auto_close_timeout_cases

logger = logging.getLogger(__name__)

_TASK: asyncio.Task | None = None


async def _scheduler_loop() -> None:
    """循环执行周期任务."""
    interval = settings.ALERT_SCHEDULER_INTERVAL_MIN * 60
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await check_alerts(db)
                await auto_close_timeout_cases(db)
            logger.info("周期任务执行完成")
        except Exception:
            logger.exception("周期任务执行失败")
        await asyncio.sleep(interval)


def start_scheduler() -> asyncio.Task:
    """启动后台调度 (FastAPI lifespan 里调用)."""
    global _TASK
    if settings.ALERT_SCHEDULER_INTERVAL_MIN <= 0:
        logger.info("告警调度已关闭 (ALERT_SCHEDULER_INTERVAL_MIN=0)")
        return None
    if _TASK and not _TASK.done():
        logger.info("调度器已在运行, 跳过重复启动")
        return _TASK
    _TASK = asyncio.create_task(_scheduler_loop())
    logger.info("后台调度已启动, 间隔 %d 分钟", settings.ALERT_SCHEDULER_INTERVAL_MIN)
    return _TASK


def is_running() -> bool:
    """调度器是否在运行."""
    return bool(_TASK and not _TASK.done())


async def stop_scheduler() -> None:
    """优雅停止调度器 (等待当前轮完成)."""
    global _TASK
    if _TASK and not _TASK.done():
        _TASK.cancel()
        try:
            await _TASK
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("停止调度器时异常")
        _TASK = None
        logger.info("后台调度已停止")

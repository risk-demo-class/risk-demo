"""
后台调度器: 自动跑案件超时关闭 + 告警检查.

设计:
- 不引入 APScheduler / Celery 等重依赖, 用 asyncio.create_task 简单循环
- 启动时由 main.py 的 lifespan 调用 start_scheduler()
- 优雅停止: stop_scheduler() 设标志 + cancel 当前 task
- 间隔可配: settings.SCHEDULER_INTERVAL_SECONDS (默认 900 秒 = 15 分钟)
- 日志: 每次执行打印 [scheduled] 跑了啥 + 几个告警

每轮执行内容:
  1. auto_close_timeout_cases(db)  → 关超时"待审核"案件 (> 24h)
  2. run_all_alert_checks(db)       → 3 个告警检查:
     ① 待审积压 > 50  (settings.ALERT_BACKLOG_THRESHOLD)
     ② 规则命中率 < 5% (settings.ALERT_RULE_HIT_RATE_MIN)
     ③ 撞黑比例 > 30%  (settings.ALERT_BLACKLIST_HIT_RATE_MAX)
"""
import asyncio
import logging
from typing import Optional

from bank_risk.app.config import settings
from bank_risk.app.database import AsyncSessionLocal
from bank_risk.app.service.alert import run_all_alert_checks
from bank_risk.app.service.case import auto_close_timeout_cases

logger = logging.getLogger(__name__)


# 全局状态: 调度器后台 task 和停止标志
_scheduler_task: Optional[asyncio.Task] = None
_stop_flag: bool = False


async def _run_once() -> dict:
    """跑一轮: 案件超时关闭 + 告警检查, 返回执行结果 (用于测试 + 日志)."""
    result = {"closed_cases": 0, "alerts_created": 0, "errors": []}
    async with AsyncSessionLocal() as db:
        try:
            result["closed_cases"] = await auto_close_timeout_cases(db)
        except Exception as e:
            result["errors"].append(f"auto_close: {e}")
            logger.exception("[scheduled] auto_close_timeout_cases 失败")
        try:
            alerts = await run_all_alert_checks(db)
            result["alerts_created"] = len(alerts) if alerts else 0
            await db.commit()
        except Exception as e:
            result["errors"].append(f"alert_check: {e}")
            logger.exception("[scheduled] run_all_alert_checks 失败")
    return result


async def _scheduler_loop() -> None:
    """主循环: 每 N 秒跑一轮, 直到 stop_flag=True."""
    global _stop_flag
    if not settings.SCHEDULER_ENABLED:
        logger.info("[scheduled] SCHEDULER_ENABLED=False, 调度器未启动")
        return

    interval_sec = settings.SCHEDULER_INTERVAL_SECONDS
    if interval_sec <= 0:
        logger.info("[scheduled] SCHEDULER_INTERVAL_SECONDS=0, 调度器未启动")
        return

    logger.info("[scheduled] 启动: 间隔 %d 秒 (案件超时 + 告警检查)", interval_sec)

    while not _stop_flag:
        try:
            result = await _run_once()
            logger.info(
                "[scheduled] 本轮: 关案 %d, 告警 %d, 错误 %d",
                result["closed_cases"], result["alerts_created"], len(result["errors"]),
            )
        except Exception as e:
            logger.exception("[scheduled] _run_once 失败: %s", e)

        # 优雅等 N 秒 (每 1s 检查 stop_flag, 避免长 sleep 卡停服)
        for _ in range(interval_sec):
            if _stop_flag:
                break
            await asyncio.sleep(1)

    logger.info("[scheduled] 停止")


def start_scheduler() -> asyncio.Task:
    """启动后台调度 task, 返回 task 句柄 (给 main.py 的 lifespan 用)."""
    global _scheduler_task, _stop_flag
    _stop_flag = False
    if _scheduler_task and not _scheduler_task.done():
        logger.warning("[scheduled] 已在运行, 跳过重复启动")
        return _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="scheduler_loop")
    return _scheduler_task


def stop_scheduler() -> None:
    """停止: 设标志 + cancel 当前 task."""
    global _stop_flag, _scheduler_task
    _stop_flag = True
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    _scheduler_task = None
    logger.info("[scheduled] stop_scheduler() 完成")


def is_running() -> bool:
    """调度器是否在跑 (供健康检查端点用)."""
    return _scheduler_task is not None and not _scheduler_task.done()

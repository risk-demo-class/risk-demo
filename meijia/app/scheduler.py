"""后台调度器: 自动跑 案件超时关闭 + 告警检查。

设计 (参考 P4-L3):
  - 不引入 APScheduler/Celery, 用 asyncio.create_task 简单循环
  - 启动时由 main.py 的 lifespan 调 start_scheduler()
  - 优雅停止: stop_scheduler() 设标志 + 等当前任务完成 (最多 10s)
  - 间隔可配: RISK_ALERT_SCHEDULER_INTERVAL_MIN (分钟), 设 0 关闭
  - 同步 DB 调用在 async 函数里直接执行 (教学规模足够, 与 Agent 工具策略一致)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import settings
from app.database import SessionLocal
from app.service.alert import run_all_alert_checks
from app.service.case import auto_close_timeout_cases

logger = logging.getLogger(__name__)

_scheduler_task: Optional[asyncio.Task] = None
_stop_flag: bool = False


def _run_once() -> dict:
    """跑一轮: 案件超时关闭 + 告警检查, 返回执行结果。"""
    result = {"closed_cases": 0, "alerts_created": 0, "errors": []}
    with SessionLocal() as db:
        try:
            result["closed_cases"] = auto_close_timeout_cases(db)
        except Exception as exc:
            result["errors"].append(f"auto_close: {exc}")
            logger.exception("[scheduled] auto_close_timeout_cases 失败")
        try:
            alerts = run_all_alert_checks(db)
            db.commit()
            result["alerts_created"] = len(alerts)
        except Exception as exc:
            result["errors"].append(f"alert_check: {exc}")
            logger.exception("[scheduled] run_all_alert_checks 失败")
    return result


async def _scheduler_loop() -> None:
    """主循环: 每 N 分钟跑一轮, 直到 stop_flag=True。"""
    global _stop_flag
    interval_min = settings.ALERT_SCHEDULER_INTERVAL_MIN
    if interval_min <= 0:
        logger.info("[scheduled] RISK_ALERT_SCHEDULER_INTERVAL_MIN=0, 调度器未启动")
        return
    interval_sec = interval_min * 60
    logger.info("[scheduled] 启动: 间隔 %d 分钟 (案件超时 + 告警检查)", interval_min)

    while not _stop_flag:
        try:
            result = _run_once()
            logger.info(
                "[scheduled] 本轮: 关案 %d, 告警 %d, 错误 %d",
                result["closed_cases"], result["alerts_created"], len(result["errors"]),
            )
        except Exception as exc:
            logger.exception("[scheduled] _run_once 失败: %s", exc)

        # 优雅等 N 分钟 (每 1s 检查 stop_flag, 避免长 sleep 卡停服)
        for _ in range(interval_sec):
            if _stop_flag:
                break
            await asyncio.sleep(1)
    logger.info("[scheduled] 停止")


def start_scheduler() -> asyncio.Task:
    """启动后台调度 task, 返回 task 句柄 (给 main.py lifespan 用)。"""
    global _scheduler_task, _stop_flag
    _stop_flag = False
    if _scheduler_task and not _scheduler_task.done():
        logger.warning("[scheduled] 已在运行, 跳过重复启动")
        return _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="scheduler_loop")
    return _scheduler_task


async def stop_scheduler() -> None:
    """优雅停止: 设标志 + 等当前 task 完成 (最多 10s)。"""
    global _stop_flag, _scheduler_task
    _stop_flag = True
    if _scheduler_task and not _scheduler_task.done():
        try:
            await asyncio.wait_for(_scheduler_task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("[scheduled] 10s 未停止, 强制 cancel")
            _scheduler_task.cancel()
    _scheduler_task = None
    logger.info("[scheduled] stop_scheduler() 完成")


def is_running() -> bool:
    """调度器是否在跑 (供健康检查端点用)。"""
    return _scheduler_task is not None and not _scheduler_task.done()

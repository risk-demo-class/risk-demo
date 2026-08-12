"""
告警服务: 风控系统自己发现异常 (案件积压 / 规则命中率突降 / 拒绝率过高等).

设计:
- check_and_alert() 通用 helper: 超阈值写 1 条 RiskAlert
- 3 个具体检查: 每个对应 1 个真实场景
- 不真发通知 (企业微信/钉钉), 只写 DB (前端 dashboard 自己查)
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.config import settings
from bank_risk.app.models import RiskAlert, RiskAssessment, RiskCase

logger = logging.getLogger(__name__)

# 告警检查时间窗口 (小时)
_ALERT_WINDOW_HOURS = 24


# 通用 helper: 写 1 条告警, 不 commit 由调用方合并事务
async def check_and_alert(
    db: AsyncSession,
    alert_type: str,
    alert_level: str,
    title: str,
    content: str,
    *,
    metric_name: Optional[str] = None,
    metric_value: Optional[float] = None,
    threshold: Optional[float] = None,
) -> Optional[RiskAlert]:
    alert = RiskAlert(
        alert_type=alert_type,
        alert_level=alert_level,
        alert_title=title,
        alert_content=content,
        metric_name=metric_name,
        metric_value=Decimal(str(metric_value)) if metric_value is not None else None,
        threshold=Decimal(str(threshold)) if threshold is not None else None,
        status="PENDING",
    )
    db.add(alert)
    logger.warning(
        "ALERT [%s %s] %s | %s (metric=%s, value=%s, threshold=%s)",
        alert_level, alert_type, title, content,
        metric_name, metric_value, threshold,
    )
    return alert


# 场景 1: 待审核案件积压 → P1 (业务级, 需运营处理)
async def check_pending_case_backlog(db: AsyncSession) -> Optional[RiskAlert]:
    count = (await db.execute(
        select(func.count(RiskCase.case_id)).where(RiskCase.case_status == "待审核")
    )).scalar() or 0
    threshold = settings.ALERT_BACKLOG_THRESHOLD
    if count > threshold:
        return await check_and_alert(
            db,
            alert_type="BUSINESS", alert_level="P1",
            title="待审核案件积压",
            content=f"当前 {count} 个待审核案件, 超过阈值 {threshold}, 请及时处理",
            metric_name="pending_case_count",
            metric_value=float(count),
            threshold=float(threshold),
        )
    return None


# 场景 2: 规则命中率突降 → P2 (模型级, 提示性)
async def check_rule_hit_rate_drop(db: AsyncSession) -> Optional[RiskAlert]:
    since = datetime.now() - timedelta(hours=_ALERT_WINDOW_HOURS)
    total = (await db.execute(
        select(func.count(RiskAssessment.assessment_id)).where(RiskAssessment.create_time >= since)
    )).scalar() or 0
    if total < 10:
        return None
    hit = (await db.execute(
        select(func.count(RiskAssessment.assessment_id)).where(
            RiskAssessment.create_time >= since,
            RiskAssessment.rule_count > 0,
        )
    )).scalar() or 0
    hit_rate = hit / total * 100
    threshold = settings.ALERT_RULE_HIT_RATE_MIN * 100  # 0.05 → 5%
    if hit_rate < threshold:
        return await check_and_alert(
            db,
            alert_type="MODEL", alert_level="P2",
            title="规则命中率突降",
            content=(
                f"最近 {_ALERT_WINDOW_HOURS} 小时规则命中率 {hit_rate:.1f}% "
                f"({hit}/{total}), 低于阈值 {threshold:.0f}%, 可能规则失效或被绕过"
            ),
            metric_name="rule_hit_rate_pct",
            metric_value=hit_rate,
            threshold=float(threshold),
        )
    return None


# 场景 3: 拒绝率过高 → P2 (业务级, 提示性)
async def check_reject_rate_high(db: AsyncSession) -> Optional[RiskAlert]:
    since = datetime.now() - timedelta(hours=_ALERT_WINDOW_HOURS)
    total = (await db.execute(
        select(func.count(RiskAssessment.assessment_id)).where(RiskAssessment.create_time >= since)
    )).scalar() or 0
    if total < 10:
        return None
    reject_count = (await db.execute(
        select(func.count(RiskAssessment.assessment_id)).where(
            RiskAssessment.create_time >= since,
            RiskAssessment.decision == "拒绝",
        )
    )).scalar() or 0
    reject_rate = reject_count / total * 100
    threshold = settings.ALERT_BLACKLIST_HIT_RATE_MAX * 100  # 0.30 → 30%
    if reject_rate > threshold:
        return await check_and_alert(
            db,
            alert_type="BUSINESS", alert_level="P2",
            title="拒绝率过高",
            content=(
                f"最近 {_ALERT_WINDOW_HOURS} 小时拒绝率 {reject_rate:.1f}% "
                f"({reject_count}/{total}), 超过阈值 {threshold:.0f}%, "
                f"可能黑名单太宽松或风控误伤"
            ),
            metric_name="reject_rate_pct",
            metric_value=reject_rate,
            threshold=float(threshold),
        )
    return None


# 一次性跑 3 个检查 (给路由 / 定时任务用)
async def run_all_alert_checks(db: AsyncSession) -> list[RiskAlert]:
    results = []
    for check_fn in (check_pending_case_backlog, check_rule_hit_rate_drop, check_reject_rate_high):
        alert = await check_fn(db)
        if alert:
            results.append(alert)
    return results

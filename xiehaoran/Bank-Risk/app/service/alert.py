"""风控告警服务 (银行语义): 待审核积压 / 规则命中率突降 / 撞黑率过高等检查."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models_risk import RiskAlert, RiskAssessment, RiskBlacklist, RiskCase

logger = logging.getLogger(__name__)


async def _count_pending_cases(db: AsyncSession) -> int:
    return int((await db.execute(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")
    )).scalar() or 0)


async def _rule_hit_rate_window(db: AsyncSession) -> float:
    since = datetime.now() - timedelta(hours=settings.ALERT_CHECK_WINDOW_HOURS)
    total = int((await db.execute(
        select(func.count()).select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since)
    )).scalar() or 0)
    if total == 0:
        return 0.0
    hit = int((await db.execute(
        select(func.count()).select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since, RiskAssessment.rule_count > 0)
    )).scalar() or 0)
    return round(hit / total * 100, 2)


async def _blacklist_hit_rate_window(db: AsyncSession) -> float:
    since = datetime.now() - timedelta(hours=settings.ALERT_CHECK_WINDOW_HOURS)
    total = int((await db.execute(
        select(func.count()).select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since)
    )).scalar() or 0)
    if total == 0:
        return 0.0
    # 撞黑: event_data 中含黑名单命中标记 (简化判定: decision=freeze 视为撞黑/极高风险)
    hit = int((await db.execute(
        select(func.count()).select_from(RiskAssessment)
        .where(RiskAssessment.create_time >= since, RiskAssessment.decision == "freeze")
    )).scalar() or 0)
    return round(hit / total * 100, 2)


async def run_all_alert_checks(db: AsyncSession) -> list[RiskAlert]:
    """触发 3 类告警检查, 命中阈值则写 risk_alert 表."""
    new_alerts: list[RiskAlert] = []

    # 场景 1: 待审核案件积压
    pending = await _count_pending_cases(db)
    if pending >= settings.ALERT_PENDING_CASE_THRESHOLD:
        new_alerts.append(RiskAlert(
            alert_type="BUSINESS", alert_level="P1",
            alert_title="待审核案件积压", alert_content=f"当前待审核案件 {pending} 件, 超过阈值 {settings.ALERT_PENDING_CASE_THRESHOLD}",
            metric_name="pending_cases", metric_value=pending,
            threshold=settings.ALERT_PENDING_CASE_THRESHOLD, status="PENDING"))

    # 场景 2: 规则命中率突降
    hit_rate = await _rule_hit_rate_window(db)
    if hit_rate < settings.ALERT_RULE_HIT_RATE_MIN:
        new_alerts.append(RiskAlert(
            alert_type="MODEL", alert_level="P2",
            alert_title="规则命中率偏低", alert_content=f"近 {settings.ALERT_CHECK_WINDOW_HOURS}h 规则命中率 {hit_rate}% < 阈值 {settings.ALERT_RULE_HIT_RATE_MIN}%",
            metric_name="rule_hit_rate", metric_value=hit_rate,
            threshold=settings.ALERT_RULE_HIT_RATE_MIN, status="PENDING"))

    # 场景 3: 撞黑率过高
    bl_rate = await _blacklist_hit_rate_window(db)
    if bl_rate > settings.ALERT_BLACKLIST_HIT_RATE_MAX:
        new_alerts.append(RiskAlert(
            alert_type="SECURITY", alert_level="P1",
            alert_title="撞黑/冻结率过高", alert_content=f"近 {settings.ALERT_CHECK_WINDOW_HOURS}h 冻结率 {bl_rate}% > 阈值 {settings.ALERT_BLACKLIST_HIT_RATE_MAX}%",
            metric_name="blacklist_hit_rate", metric_value=bl_rate,
            threshold=settings.ALERT_BLACKLIST_HIT_RATE_MAX, status="PENDING"))

    for a in new_alerts:
        db.add(a)
    return new_alerts

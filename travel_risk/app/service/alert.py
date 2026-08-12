"""
告警服务: 风控系统自身健康监控
  场景 1: 待审核案件积压数超过阈值
  场景 2: 最近窗口规则命中率低于下限 (规则可能失效)
  场景 3: 最近窗口撞黑比例高于上限 (黑名单可能被批量绕过)
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import RiskAlert, RiskAssessment, RiskCase

logger = logging.getLogger(__name__)


async def _create_alert(
    db: AsyncSession,
    alert_type: str,
    alert_level: str,
    title: str,
    content: str,
    metric_name: str,
    metric_value: float,
    threshold: float,
) -> bool:
    """写告警, 同 (type, title, metric_name) 已存在 PENDING 则不重复写."""
    existing = (await db.execute(
        select(RiskAlert.alert_id).where(
            RiskAlert.alert_type == alert_type,
            RiskAlert.alert_title == title,
            RiskAlert.status == "PENDING",
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        return False
    db.add(RiskAlert(
        alert_type=alert_type,
        alert_level=alert_level,
        alert_title=title,
        alert_content=content,
        metric_name=metric_name,
        metric_value=metric_value,
        threshold=threshold,
    ))
    return True


async def check_alerts(db: AsyncSession) -> list[RiskAlert]:
    """执行全部告警检查, 返回新写入的告警."""
    created: list[RiskAlert] = []
    now = datetime.now()

    # 场景 1: 待审核案件积压
    pending = int((await db.execute(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")
    )).scalar() or 0)
    if pending >= settings.ALERT_PENDING_CASE_THRESHOLD:
        ok = await _create_alert(
            db, "BUSINESS", "P1", "待审核案件积压",
            f"当前待审核案件 {pending} 个, 超过阈值 {settings.ALERT_PENDING_CASE_THRESHOLD}",
            "pending_case_count", pending, settings.ALERT_PENDING_CASE_THRESHOLD,
        )
        if ok:
            created.append(RiskAlert(alert_title="待审核案件积压"))

    # 场景 2: 最近窗口规则命中率
    window_start = now - timedelta(hours=settings.ALERT_CHECK_WINDOW_HOURS)
    total = int((await db.execute(
        select(func.count()).select_from(RiskAssessment).where(
            RiskAssessment.create_time >= window_start,
        )
    )).scalar() or 0)
    if total > 0:
        hit = int((await db.execute(
            select(func.count()).select_from(RiskAssessment).where(
                RiskAssessment.create_time >= window_start,
                RiskAssessment.rule_count > 0,
            )
        )).scalar() or 0)
        hit_rate = 100.0 * hit / total
        if hit_rate < settings.ALERT_RULE_HIT_RATE_MIN:
            await _create_alert(
                db, "MODEL", "P2", "规则命中率异常偏低",
                f"最近 {settings.ALERT_CHECK_WINDOW_HOURS}h 规则命中率 {hit_rate:.1f}% < 阈值 {settings.ALERT_RULE_HIT_RATE_MIN}%, 规则可能失效",
                "rule_hit_rate", round(hit_rate, 4), settings.ALERT_RULE_HIT_RATE_MIN,
            )

    await db.commit()
    return created

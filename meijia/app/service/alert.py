"""告警服务 (P4-L2): 风控系统自己发现异常 (案件积压 / 命中率突降 / 拒绝率过高)。

教学价值: 风控不是写完规则就完事, 要持续监控。
设计:
  - check_and_alert() 通用 helper: 超阈值写 1 条 RiskAlert (不 commit, 由调用方合并事务)
  - 3 个具体检查, 每个对应 1 个真实场景
  - 不真发通知 (企业微信/钉钉), 只写 DB (前端 dashboard / 告警列表自己查)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models_risk import RiskAlert, RiskAssessment, RiskCase

logger = logging.getLogger(__name__)


def check_and_alert(
    db: Session,
    alert_type: str,
    alert_level: str,
    title: str,
    content: str,
    *,
    metric_name: str | None = None,
    metric_value: float | None = None,
    threshold: float | None = None,
) -> RiskAlert:
    """写 1 条告警 (不 commit, 由调用方提交事务)。"""
    alert = RiskAlert(
        alert_type=alert_type, alert_level=alert_level,
        alert_title=title, alert_content=content,
        metric_name=metric_name,
        metric_value=float(metric_value) if metric_value is not None else None,
        threshold=float(threshold) if threshold is not None else None,
        status="PENDING",
    )
    db.add(alert)
    logger.warning(
        "ALERT [%s %s] %s | %s (metric=%s, value=%s, threshold=%s)",
        alert_level, alert_type, title, content, metric_name, metric_value, threshold,
    )
    return alert


# 场景 1: 待审核案件积压 → P1 (业务级, 需运营处理)
def check_pending_case_backlog(db: Session) -> RiskAlert | None:
    count = db.scalar(select(func.count(RiskCase.case_id)).where(RiskCase.case_status == "待审核")) or 0
    threshold = settings.ALERT_PENDING_CASE_THRESHOLD
    if count > threshold:
        return check_and_alert(
            db, alert_type="BUSINESS", alert_level="P1",
            title="待审核案件积压",
            content=f"当前 {count} 个待审核案件, 超过阈值 {threshold}, 请及时处理",
            metric_name="pending_case_count", metric_value=float(count), threshold=float(threshold),
        )
    return None


# 场景 2: 规则命中率突降 → P2 (模型级, 提示性)
# 命中率 < 阈值: 规则可能失效 / 黑产绕过 / 阈值设错
def check_rule_hit_rate_drop(db: Session) -> RiskAlert | None:
    window_hours = settings.ALERT_CHECK_WINDOW_HOURS
    since = datetime.now() - timedelta(hours=window_hours)
    total = db.scalar(select(func.count(RiskAssessment.assessment_id)).where(RiskAssessment.created_at >= since)) or 0
    if total < 10:  # 评估数太少跳过, 避免冷启动误报
        return None
    hit = db.scalar(select(func.count(RiskAssessment.assessment_id)).where(
        RiskAssessment.created_at >= since, RiskAssessment.rule_count > 0,
    )) or 0
    hit_rate = hit / total * 100
    threshold = settings.ALERT_RULE_HIT_RATE_MIN
    if hit_rate < threshold:
        return check_and_alert(
            db, alert_type="MODEL", alert_level="P2",
            title="规则命中率突降",
            content=f"最近 {window_hours} 小时规则命中率 {hit_rate:.1f}% ({hit}/{total}), 低于阈值 {threshold}%, 可能规则失效或被绕过",
            metric_name="rule_hit_rate_pct", metric_value=hit_rate, threshold=float(threshold),
        )
    return None


# 场景 3: 拒绝率过高 (代理"撞黑率"指标) → P2 (业务级, 提示性)
# 简化: 用 decision='拒绝' 的比例近似撞黑比例
def check_blacklist_hit_rate_high(db: Session) -> RiskAlert | None:
    window_hours = settings.ALERT_CHECK_WINDOW_HOURS
    since = datetime.now() - timedelta(hours=window_hours)
    total = db.scalar(select(func.count(RiskAssessment.assessment_id)).where(RiskAssessment.created_at >= since)) or 0
    if total < 10:
        return None
    reject_count = db.scalar(select(func.count(RiskAssessment.assessment_id)).where(
        RiskAssessment.created_at >= since, RiskAssessment.decision == "拒绝",
    )) or 0
    reject_rate = reject_count / total * 100
    threshold = settings.ALERT_BLACKLIST_HIT_RATE_MAX
    if reject_rate > threshold:
        return check_and_alert(
            db, alert_type="BUSINESS", alert_level="P2",
            title="拒绝率过高",
            content=f"最近 {window_hours} 小时拒绝率 {reject_rate:.1f}% ({reject_count}/{total}), 超过阈值 {threshold}%, 可能黑名单太宽松或风控误伤",
            metric_name="reject_rate_pct", metric_value=reject_rate, threshold=float(threshold),
        )
    return None


def run_all_alert_checks(db: Session) -> list[RiskAlert]:
    """一次性跑 3 个检查 (不 commit, 由调用方提交事务)。"""
    results = []
    for check_fn in (check_pending_case_backlog, check_rule_hit_rate_drop, check_blacklist_hit_rate_high):
        alert = check_fn(db)
        if alert:
            results.append(alert)
    return results

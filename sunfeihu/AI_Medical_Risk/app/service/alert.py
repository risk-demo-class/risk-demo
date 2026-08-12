"""医疗风控聚合告警检查；仅写 risk_alert，不改业务单据。"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models_business import MedicalInsuranceClaim, MedicalPrescription
from app.models_risk import RiskAlert, RiskAssessment, RiskCase


async def _upsert_alert(
    db: AsyncSession,
    *,
    alert_type: str,
    alert_level: str,
    title: str,
    content: str,
    metric_name: str,
    metric_value: float,
    threshold: float,
) -> bool:
    existing = (await db.execute(select(RiskAlert).where(
        RiskAlert.metric_name == metric_name,
        RiskAlert.status.in_(("PENDING", "HANDLING")),
    ).limit(1))).scalar_one_or_none()
    if metric_value < threshold:
        if existing:
            existing.status = "RESOLVED"
            existing.handler = "system"
            existing.resolve_time = datetime.now()
        return False
    if existing:
        existing.metric_value = Decimal(str(metric_value))
        existing.alert_content = content
        return False
    db.add(RiskAlert(
        alert_type=alert_type,
        alert_level=alert_level,
        alert_title=title,
        alert_content=content,
        metric_name=metric_name,
        metric_value=Decimal(str(metric_value)),
        threshold=Decimal(str(threshold)),
        status="PENDING",
    ))
    return True


async def run_alert_checks(db: AsyncSession) -> dict[str, int]:
    now = datetime.now()
    created = 0
    pending = int((await db.execute(select(func.count()).select_from(RiskCase).where(
        RiskCase.case_status.in_(("待审核", "审核中"))
    ))).scalar_one())
    created += await _upsert_alert(
        db, alert_type="BUSINESS", alert_level="P1", title="待审核案件积压",
        content=f"当前待处理案件 {pending} 个，请安排审核。", metric_name="pending_case_count",
        metric_value=pending, threshold=settings.ALERT_PENDING_CASE_THRESHOLD,
    )

    since = now - timedelta(hours=24)
    total = int((await db.execute(select(func.count()).select_from(RiskAssessment).where(
        RiskAssessment.create_time >= since
    ))).scalar_one())
    high = int((await db.execute(select(func.count()).select_from(RiskAssessment).where(
        RiskAssessment.create_time >= since,
        RiskAssessment.decision.in_(("人工审核", "拒绝")),
    ))).scalar_one())
    high_rate = high / total if total else 0.0
    created += await _upsert_alert(
        db, alert_type="BUSINESS", alert_level="P1", title="24 小时高风险命中率偏高",
        content=f"近 24 小时高风险 {high}/{total}，命中率 {high_rate:.1%}。",
        metric_name="high_risk_rate_24h", metric_value=high_rate,
        threshold=settings.ALERT_HIGH_RISK_RATE_THRESHOLD,
    )

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    doctor_totals = select(
        func.sum(MedicalPrescription.total_amount).label("amount")
    ).where(MedicalPrescription.issued_at >= day_start).group_by(
        MedicalPrescription.doctor_id
    ).subquery()
    doctor_max = float((await db.execute(select(func.max(doctor_totals.c.amount)))).scalar_one_or_none() or 0)
    created += await _upsert_alert(
        db, alert_type="BUSINESS", alert_level="P2", title="单医生处方金额异常",
        content=f"今日单医生处方累计最高金额 {doctor_max:.2f} 元，建议复核异常开方行为。",
        metric_name="doctor_prescription_amount_peak", metric_value=doctor_max,
        threshold=settings.ALERT_DOCTOR_AMOUNT_THRESHOLD,
    )
    hospital_totals = select(
        func.sum(MedicalInsuranceClaim.total_amount).label("amount")
    ).where(MedicalInsuranceClaim.claim_at >= day_start).group_by(
        MedicalInsuranceClaim.hospital_id
    ).subquery()
    hospital_max = float((await db.execute(select(func.max(hospital_totals.c.amount)))).scalar_one_or_none() or 0)
    created += await _upsert_alert(
        db, alert_type="BUSINESS", alert_level="P2", title="单医院医保申报金额异常",
        content=f"今日单医院医保申报累计最高金额 {hospital_max:.2f} 元，建议复核异常申报。",
        metric_name="hospital_claim_amount_peak", metric_value=hospital_max,
        threshold=settings.ALERT_HOSPITAL_CLAIM_THRESHOLD,
    )
    await db.commit()
    return {"created": created, "checked": 4}

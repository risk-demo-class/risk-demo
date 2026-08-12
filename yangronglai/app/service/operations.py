"""Operational queries for dashboards, cases, analysts and Agent tools."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import BankCard, LoanApplication, LoginLog, Transaction, UserInfo
from app.models_risk import (
    RiskActionLog,
    RiskAppeal,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeatureSnapshot,
    RiskRule,
    RiskRuleHit,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def model_dict(instance: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _json_value(getattr(instance, field)) for field in fields}


async def dashboard_stats(session: AsyncSession) -> dict:
    total = int(await session.scalar(select(func.count()).select_from(RiskAssessment)) or 0)
    pending_cases = int(
        await session.scalar(
            select(func.count()).select_from(RiskCase).where(RiskCase.status.in_(["PENDING", "IN_REVIEW"]))
        )
        or 0
    )
    pending_appeals = int(
        await session.scalar(
            select(func.count())
            .select_from(RiskAppeal)
            .where(RiskAppeal.status.in_(["SUBMITTED", "UNDER_REVIEW", "NEEDS_INFO"]))
        )
        or 0
    )
    average_score = float(await session.scalar(select(func.avg(RiskAssessment.final_score))) or 0)
    decision_rows = (
        await session.execute(
            select(RiskAssessment.decision, func.count())
            .group_by(RiskAssessment.decision)
            .order_by(func.count().desc())
        )
    ).all()
    decision_distribution = {decision: int(count) for decision, count in decision_rows}
    pass_count = decision_distribution.get("通过", 0)
    action_count = total - pass_count
    level_rows = (
        await session.execute(
            select(RiskAssessment.risk_level, func.count()).group_by(RiskAssessment.risk_level)
        )
    ).all()
    top_rule_rows = (
        await session.execute(
            select(RiskRuleHit.rule_id, RiskRuleHit.rule_name, func.count().label("hits"))
            .group_by(RiskRuleHit.rule_id, RiskRuleHit.rule_name)
            .order_by(desc("hits"))
            .limit(8)
        )
    ).all()
    scenario_rows = (
        await session.execute(
            select(RiskAssessment.scenario, func.count(), func.avg(RiskAssessment.final_score))
            .group_by(RiskAssessment.scenario)
        )
    ).all()
    return {
        "total_assessments": total,
        "pending_cases": pending_cases,
        "pending_appeals": pending_appeals,
        "average_score": round(average_score, 2),
        "pass_count": pass_count,
        "risk_action_count": action_count,
        "pass_rate": round(pass_count / total * 100, 2) if total else 0,
        "decision_distribution": decision_distribution,
        "risk_level_distribution": {level: count for level, count in level_rows},
        "scenario_distribution": {
            scenario: {"count": count, "average_score": round(float(avg_score or 0), 2)}
            for scenario, count, avg_score in scenario_rows
        },
        "top_rules": [
            {"rule_id": rule_id, "rule_name": rule_name, "hits": hits}
            for rule_id, rule_name, hits in top_rule_rows
        ],
    }


async def list_assessments(
    session: AsyncSession,
    *,
    scenario: str | None = None,
    decision: str | None = None,
    user_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    filters = []
    if scenario:
        filters.append(RiskAssessment.scenario == scenario)
    if decision:
        filters.append(RiskAssessment.decision == decision)
    if user_id:
        filters.append(RiskAssessment.user_id == user_id)
    total = int(
        await session.scalar(select(func.count()).select_from(RiskAssessment).where(*filters)) or 0
    )
    rows = (
        await session.scalars(
            select(RiskAssessment)
            .where(*filters)
            .order_by(RiskAssessment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    fields = (
        "assessment_id", "event_id", "user_id", "scenario", "rule_score", "model_score",
        "graph_score", "final_score", "risk_level", "decision", "hit_count", "decision_reason",
        "created_at",
    )
    return {"total": total, "page": page, "page_size": page_size, "items": [model_dict(row, fields) for row in rows]}


async def assessment_detail(session: AsyncSession, assessment_id: str) -> dict | None:
    assessment = await session.get(RiskAssessment, assessment_id)
    if assessment is None:
        return None
    event = await session.get(RiskEvent, assessment.event_id)
    feature = await session.scalar(
        select(RiskFeatureSnapshot).where(RiskFeatureSnapshot.event_id == assessment.event_id)
    )
    hits = (
        await session.scalars(
            select(RiskRuleHit).where(RiskRuleHit.event_id == assessment.event_id)
            .order_by(RiskRuleHit.risk_score.desc())
        )
    ).all()
    result = model_dict(
        assessment,
        (
            "assessment_id", "event_id", "user_id", "scenario", "rule_score", "model_score",
            "graph_score", "final_score", "risk_level", "decision", "hit_count", "decision_reason",
            "created_at",
        ),
    )
    result["event"] = (
        model_dict(event, ("request_id", "source_id", "event_data", "event_time", "created_at"))
        if event else None
    )
    result["features"] = feature.features if feature else None
    result["hits"] = [
        model_dict(hit, ("rule_id", "rule_name", "risk_score", "risk_level", "decision", "evidence", "rule_version"))
        for hit in hits
    ]
    return result


async def list_cases(
    session: AsyncSession,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    filters = [RiskCase.status == status] if status else []
    total = int(await session.scalar(select(func.count()).select_from(RiskCase).where(*filters)) or 0)
    rows = (
        await session.scalars(
            select(RiskCase)
            .where(*filters)
            .order_by(RiskCase.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    fields = (
        "case_id", "assessment_id", "source_id", "user_id", "scenario", "status", "risk_detail",
        "reviewer", "review_comment", "reviewed_at", "created_at", "updated_at",
    )
    return {"total": total, "page": page, "page_size": page_size, "items": [model_dict(row, fields) for row in rows]}


async def review_case(
    session: AsyncSession,
    case_id: str,
    *,
    decision: str,
    reviewer: str,
    comment: str = "",
) -> dict | None:
    case = await session.get(RiskCase, case_id)
    if case is None:
        return None
    if decision not in {"APPROVED", "REJECTED", "CLOSED"}:
        raise ValueError("decision must be APPROVED, REJECTED or CLOSED")
    if case.status not in {"PENDING", "IN_REVIEW"}:
        raise ValueError(f"case in terminal status: {case.status}")
    before = model_dict(case, ("status", "reviewer", "review_comment"))
    case.status = decision
    case.reviewer = reviewer
    case.review_comment = comment
    case.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        RiskActionLog(
            operator=reviewer,
            action_type="REVIEW_CASE",
            target_type="case",
            target_id=case_id,
            before_value=before,
            after_value={"status": decision, "reviewer": reviewer, "review_comment": comment},
            remark="人工案件审核",
        )
    )
    await session.commit()
    return model_dict(
        case,
        ("case_id", "assessment_id", "user_id", "scenario", "status", "reviewer", "review_comment", "reviewed_at"),
    )


async def request_case_review(
    session: AsyncSession,
    case_id: str,
    *,
    operator: str,
    reason: str,
) -> dict | None:
    case = await session.get(RiskCase, case_id)
    if case is None:
        return None
    if case.status == "PENDING":
        case.status = "IN_REVIEW"
    session.add(
        RiskActionLog(
            operator=operator,
            action_type="REQUEST_CASE_REVIEW",
            target_type="case",
            target_id=case_id,
            before_value=None,
            after_value={"status": case.status, "reason": reason},
            remark="经批准的 Agent 审核请求",
        )
    )
    await session.commit()
    return {"case_id": case_id, "status": case.status, "requested_by": operator, "reason": reason}


async def customer_360(session: AsyncSession, user_id: str) -> dict | None:
    user = await session.get(UserInfo, user_id)
    if user is None:
        return None
    cards = (await session.scalars(select(BankCard).where(BankCard.user_id == user_id))).all()
    transaction_count = int(
        await session.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)) or 0
    )
    transaction_amount = float(
        await session.scalar(select(func.sum(Transaction.amount)).where(Transaction.user_id == user_id)) or 0
    )
    loan_count = int(
        await session.scalar(select(func.count()).select_from(LoanApplication).where(LoanApplication.user_id == user_id)) or 0
    )
    login_count = int(
        await session.scalar(select(func.count()).select_from(LoginLog).where(LoginLog.user_id == user_id)) or 0
    )
    latest = (
        await session.scalars(
            select(RiskAssessment).where(RiskAssessment.user_id == user_id)
            .order_by(RiskAssessment.created_at.desc()).limit(10)
        )
    ).all()
    return {
        "user": model_dict(user, ("user_id", "name", "credit_score", "register_at", "kyc_level")),
        "cards": [model_dict(card, ("card_id", "bank_code", "card_type", "credit_limit", "status")) for card in cards],
        "activity": {
            "transaction_count": transaction_count,
            "transaction_amount": round(transaction_amount, 2),
            "loan_count": loan_count,
            "login_count": login_count,
        },
        "latest_assessments": [
            model_dict(item, ("assessment_id", "scenario", "final_score", "risk_level", "decision", "created_at"))
            for item in latest
        ],
    }


async def rule_effectiveness(session: AsyncSession) -> dict:
    total = int(await session.scalar(select(func.count()).select_from(RiskAssessment)) or 0)
    rules = (await session.scalars(select(RiskRule).where(RiskRule.deleted_at.is_(None)).order_by(RiskRule.rule_id))).all()
    hit_rows = (
        await session.execute(select(RiskRuleHit.rule_id, func.count()).group_by(RiskRuleHit.rule_id))
    ).all()
    hit_counts = dict(hit_rows)
    return {
        "total_assessments": total,
        "rules": [
            {
                "rule_id": rule.rule_id,
                "rule_name": rule.rule_name,
                "enabled": rule.is_enabled,
                "hits": hit_counts.get(rule.rule_id, 0),
                "hit_rate": round(hit_counts.get(rule.rule_id, 0) / total, 6) if total else 0,
            }
            for rule in rules
        ],
    }

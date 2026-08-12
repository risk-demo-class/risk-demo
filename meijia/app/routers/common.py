from sqlalchemy.orm import Session

from app.models_business import BlacklistExtra
from app.models_risk import RiskAssessment, RiskCase, RiskRule


def page_meta(total: int, page: int, page_size: int) -> dict:
    return {"total": total, "page": page, "page_size": page_size}


def rule_dict(row: RiskRule) -> dict:
    return {
        "rule_id": row.rule_id, "rule_name": row.rule_name,
        "rule_category": row.rule_category, "event_type": row.event_type,
        "condition": row.rule_condition, "risk_level": row.risk_level,
        "risk_score": row.risk_score, "action": row.action,
        "enabled": row.enabled, "priority": row.priority, "version": row.version,
    }


def assessment_dict(row: RiskAssessment) -> dict:
    return {
        "assessment_id": row.assessment_id, "event_id": row.event_id,
        "user_id": row.user_id, "rule_count": row.rule_count,
        "final_score": row.final_score, "risk_level": row.risk_level,
        "decision": row.decision, "blocked_by": row.blocked_by,
        "ml_score": row.ml_score, "ml_decision": row.ml_decision,
        "created_at": row.created_at,
    }


def case_dict(db: Session, row: RiskCase) -> dict:
    assessment = db.get(RiskAssessment, row.assessment_id)
    return {
        "case_id": row.case_id, "assessment_id": row.assessment_id,
        "user_id": row.user_id, "case_status": row.case_status,
        "case_category": row.case_category,
        "final_score": assessment.final_score if assessment else None,
        "risk_level": assessment.risk_level if assessment else None,
        "reviewer": row.reviewer, "review_comment": row.review_comment,
        "reviewed_at": row.reviewed_at, "created_at": row.created_at,
    }


def blacklist_dict(row: BlacklistExtra) -> dict:
    return {
        "entry_id": row.entry_id, "type": row.type,
        "value": row.value_masked or row.value, "reason": row.reason,
        "status": row.status, "expire_at": row.expire_at,
        "created_by": row.created_by, "created_at": row.created_at,
    }

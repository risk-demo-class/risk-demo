from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.engine.rule import InvalidRuleCondition, validate_condition
from app.models_risk import RiskRule
from app.routers.common import rule_dict
from app.schemas import RuleUpdate
from app.service.action_log import record_action

router = APIRouter(prefix="/api/rules", tags=["规则"])


@router.get("")
def list_rules(db: Session = Depends(get_session)):
    rows = list(db.scalars(select(RiskRule).where(RiskRule.deleted_at.is_(None)).order_by(desc(RiskRule.priority), RiskRule.rule_id)))
    return {"items": [rule_dict(row) for row in rows], "total": len(rows)}


@router.put("/{rule_id}/toggle")
def toggle_rule(rule_id: str, db: Session = Depends(get_session), operator: str = Header(default="admin", alias="X-Operator")):
    rule = db.get(RiskRule, rule_id)
    if not rule or rule.deleted_at:
        raise HTTPException(404, "规则不存在")
    before = {"enabled": rule.enabled, "version": rule.version}
    try:
        rule.enabled = not rule.enabled
        rule.version += 1
        record_action(
            db, operator=operator, action_type="TOGGLE_RULE", target_type="rule",
            target_id=rule_id, before_value=before,
            after_value={"enabled": rule.enabled, "version": rule.version},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return rule_dict(rule)


@router.put("/{rule_id}")
def update_rule(rule_id: str, data: RuleUpdate, db: Session = Depends(get_session), operator: str = Header(default="admin", alias="X-Operator")):
    rule = db.get(RiskRule, rule_id)
    if not rule or rule.deleted_at:
        raise HTTPException(404, "规则不存在")
    if rule.version != data.version:
        raise HTTPException(409, f"规则已被其他操作更新，当前版本为 {rule.version}")
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    if "rule_condition" in changes:
        try:
            validate_condition(changes["rule_condition"])
        except InvalidRuleCondition as exc:
            raise HTTPException(422, str(exc)) from exc
    if not changes:
        return rule_dict(rule)
    before = {key: getattr(rule, key) for key in changes}
    try:
        for key, value in changes.items():
            setattr(rule, key, value)
        rule.version += 1
        record_action(
            db, operator=operator, action_type="UPDATE_RULE", target_type="rule",
            target_id=rule_id, before_value=before,
            after_value={key: getattr(rule, key) for key in changes},
            remark=f"version {rule.version}",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return rule_dict(rule)

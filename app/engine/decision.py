"""Engine 层：严格按七步完成报名事件的风控决策与审计。"""

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.feature import build_credential_features, build_features, build_refund_features
from app.engine.rule import evaluate_condition
from app.models import CredentialVerification, Enrollment, RefundRequest, RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskRule
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16].upper()}"


def _calculate_decision(hits: list[RuleHitInfo]) -> tuple[int, str, str]:
    """将命中规则归并为一个分数、风险等级和处置结论。"""
    if not hits:
        return 0, "低风险", "通过"

    final_score = min(100, max(item.risk_score for item in hits) + 3 * (len(hits) - 1))
    if final_score >= 80:
        return final_score, "高风险", "拒绝"
    if final_score >= 60:
        return final_score, "中风险", "人工审核"
    return final_score, "低风险", "通过"


def _match_rules(session: Session, event_type: str, features: dict[str, float]) -> list[RuleHitInfo]:
    """读取启用规则，并返回本次事件命中的规则。"""
    rules = session.scalars(
        select(RiskRule).where(
            RiskRule.is_enabled.is_(True),
            RiskRule.event_type.in_([event_type, "通用"]),
        )
    ).all()
    hits: list[RuleHitInfo] = []
    for rule in rules:
        try:
            condition = json.loads(rule.rule_condition)
        except json.JSONDecodeError:
            continue
        if evaluate_condition(condition, features):
            hits.append(
                RuleHitInfo(
                    rule_id=rule.rule_id,
                    rule_name=rule.rule_name,
                    risk_score=rule.risk_score,
                )
            )
    return hits


def run_risk_check(session: Session, request: RiskCheckRequest) -> RiskCheckResponse:
    """执行旧项目同款七步引擎：上下文、事件、特征、快照、规则、决策、持久化。"""
    # 1. 构建上下文：按教育事件读取各自的业务来源。
    if request.event_type == "课程报名":
        source: Enrollment | RefundRequest | CredentialVerification | None = session.get(Enrollment, request.source_id)
    elif request.event_type == "退费申请":
        source = session.get(RefundRequest, request.source_id)
    elif request.event_type == "学历认证":
        source = session.get(CredentialVerification, request.source_id)
    else:
        source = None
    if source is None:
        raise ValueError(f"教育业务记录不存在: {request.source_id}")

    # 2. 记录标准化风险事件。
    event = RiskEvent(
        event_id=_new_id("EVT"),
        event_type=request.event_type,
        source_id=request.source_id,
        user_id=request.user_id,
        event_data=json.dumps({"source_id": request.source_id}, ensure_ascii=False),
    )
    session.add(event)
    session.flush()

    # 3. 计算报名或退款场景特征。
    if isinstance(source, Enrollment):
        features = build_features(session, source)
    elif isinstance(source, RefundRequest):
        features = build_refund_features(session, source)
    else:
        features = build_credential_features(session, source)

    # 4. 持久化特征快照，保证后续可解释与复盘。
    for feature_name, feature_value in features.items():
        entity_type = feature_name.split("_", maxsplit=1)[0]
        session.add(
            RiskFeature(
                event_id=event.event_id,
                entity_type=entity_type,
                feature_name=feature_name,
                feature_value=feature_value,
            )
        )

    # 5. 匹配规则；6. 计算最终分数与处置结论。
    hits = _match_rules(session, request.event_type, features)
    final_score, risk_level, decision = _calculate_decision(hits)

    # 7. 落审计评估，高风险事件同时创建待审案件。
    assessment = RiskAssessment(
        assessment_id=_new_id("ASM"),
        event_id=event.event_id,
        user_id=request.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_results=json.dumps([hit.model_dump() for hit in hits], ensure_ascii=False),
    )
    session.add(assessment)
    if decision in {"人工审核", "拒绝"}:
        session.add(
            RiskCase(
                case_id=_new_id("CASE"),
                assessment_id=assessment.assessment_id,
                source_id=request.source_id,
                user_id=request.user_id,
                event_type=request.event_type,
                case_status="待审核",
            )
        )
    session.commit()

    return RiskCheckResponse(
        event_id=event.event_id,
        assessment_id=assessment.assessment_id,
        user_id=request.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(hits),
        triggered_rules=hits,
    )

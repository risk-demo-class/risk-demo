from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.feature import compute_all_features
from app.engine.ml_model import predict_risk
from app.engine.rule import RuleHit, match_rules
from app.models_risk import RiskAssessment, RiskCase, RiskEvent, RiskFeature
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _decision(score: int) -> tuple[str, str]:
    if score >= settings.RISK_REJECT_THRESHOLD:
        return "极高", "拒绝"
    if score >= settings.RISK_REVIEW_THRESHOLD:
        return "高", "人工审核"
    if score >= settings.RISK_PASS_THRESHOLD:
        return "中", "标记"
    return "低", "通过"


async def run_risk_check(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """Seven fixed orchestration steps; business logic stays outside this function."""
    # 1. Prepare context.
    event_id = _id("EVT")
    event_payload = dict(request.event_data)

    # 2. Create event record.
    db.add(RiskEvent(event_id=event_id, event_type=request.event_type, event_source_id=request.source_id, user_id=request.user_id, event_data=json.dumps(event_payload, ensure_ascii=False)))

    # 3. Compute features.
    features = await compute_all_features(db, request.user_id, request.order_id, request.receive_id)

    # 4. Save immutable feature snapshot.
    for name, value in features.items():
        db.add(RiskFeature(event_id=event_id, entity_type="用户", entity_id=request.user_id, feature_name=name, feature_value=value))

    # 5. Load and evaluate rules.
    hits = await match_rules(db, request.event_type, features)

    # 6. Calculate rule + deterministic model decision.
    rule_score = max((hit.risk_score for hit in hits), default=0)
    ml_score = round(predict_risk(features) * 100)
    final_score = min(100, max(rule_score, ml_score))
    risk_level, decision = _decision(final_score)

    # 7. Persist assessment/case and respond.
    assessment_id = _id("ASM")
    hit_payload = [hit.__dict__ for hit in hits]
    db.add(RiskAssessment(assessment_id=assessment_id, event_id=event_id, user_id=request.user_id, rule_results=json.dumps(hit_payload, ensure_ascii=False), final_score=final_score, risk_level=risk_level, decision=decision))
    if decision == "人工审核":
        db.add(RiskCase(case_id=_id("CASE"), assessment_id=assessment_id, user_id=request.user_id, case_status="待审核", case_category=str(event_payload.get("business_event_type", "PAYMENT_RISK")), risk_detail=json.dumps({"features": features, "rules": hit_payload}, ensure_ascii=False), source_id=request.source_id, event_type=request.event_type))
    await db.commit()
    return RiskCheckResponse(assessment_id=assessment_id, event_id=event_id, user_id=request.user_id, final_score=final_score, risk_level=risk_level, decision=decision, rule_count=len(hits), triggered_rules=[RuleHitInfo(**hit.__dict__) for hit in hits])


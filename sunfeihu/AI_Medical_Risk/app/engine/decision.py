"""医疗风控七步决策流水线。"""
import json
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.feature import compute_all_features
from app.engine.ml_model import MlResult, predict
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models_risk import (
    RiskActionLog,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo


def _id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex}"


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    if not hits:
        return 0
    return min(max(hit.risk_score for hit in hits) + settings.RISK_MULTI_RULE_BONUS * (len(hits) - 1), 100)


def has_veto(hits: list[RuleHitResult]) -> bool:
    return any(hit.risk_level == "极高" for hit in hits)


def calculate_fused_score(
    rule_score: int,
    hits: list[RuleHitResult],
    ml_result: MlResult,
) -> int:
    """双轨加权评分；规则动作下限避免低概率模型把明确规则降级。"""
    if not ml_result.is_loaded or ml_result.score is None:
        return rule_score
    weight_sum = settings.ML_WEIGHT_RULE + settings.ML_WEIGHT_XGB
    if weight_sum <= 0:
        return rule_score
    fused = round(
        (settings.ML_WEIGHT_RULE * rule_score + settings.ML_WEIGHT_XGB * ml_result.score * 100)
        / weight_sum
    )
    action_floor = max(
        ({"通过": 0, "标记": settings.RISK_PASS_THRESHOLD,
          "人工审核": settings.RISK_MARK_THRESHOLD,
          "拒绝": settings.RISK_REVIEW_THRESHOLD}.get(hit.action, 0) for hit in hits),
        default=0,
    )
    return min(max(fused, action_floor), 100)


def score_to_level(score: int) -> str:
    if score < settings.RISK_PASS_THRESHOLD:
        return "低"
    if score < settings.RISK_MARK_THRESHOLD:
        return "中"
    if score < settings.RISK_REVIEW_THRESHOLD:
        return "高"
    return "极高"


def score_to_decision(score: int) -> str:
    if score < settings.RISK_PASS_THRESHOLD:
        return "通过"
    if score < settings.RISK_MARK_THRESHOLD:
        return "标记"
    if score < settings.RISK_REVIEW_THRESHOLD:
        return "人工审核"
    return "拒绝"


def _entity_type(feature_name: str) -> str:
    if feature_name.startswith("patient_"):
        return "患者"
    if feature_name.startswith(("doctor_", "hospital_", "device_")):
        return "机构"
    return "单据"


async def run_risk_check(
    db: AsyncSession,
    request: RiskCheckRequest,
    forced_hits: list[RuleHitResult] | None = None,
) -> RiskCheckResponse:
    event_id = _id("evt")
    db.add(RiskEvent(
        event_id=event_id,
        event_type=request.event_type,
        event_source_id=request.source_id,
        user_id=request.user_id,
        event_data=json.dumps(request.event_data or {}, ensure_ascii=False),
    ))

    features = await compute_all_features(db, request)
    for name, value in features.items():
        db.add(RiskFeature(
            event_id=event_id,
            entity_type=_entity_type(name),
            entity_id=request.user_id if name.startswith("patient_") else request.source_id,
            feature_name=name,
            feature_value=Decimal(str(value)),
        ))

    rules = await load_enabled_rules(db, request.event_type)
    hits = match_rules(rules, features)
    if forced_hits:
        existing = {hit.rule_id for hit in hits}
        hits.extend(hit for hit in forced_hits if hit.rule_id not in existing)

    rule_score = calculate_final_score(hits)
    ml_result = predict(features)
    final_score = calculate_fused_score(rule_score, hits, ml_result)
    if has_veto(hits):
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)
    risk_level = score_to_level(final_score)
    decision = score_to_decision(final_score)
    if has_veto(hits):
        risk_level, decision = "极高", "拒绝"

    assessment_id = _id("ast")
    db.add(RiskAssessment(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=request.user_id,
        rule_results=json.dumps([hit.to_dict() for hit in hits], ensure_ascii=False),
        rule_count=len(hits),
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        ml_score=ml_result.score,
        ml_decision=ml_result.decision,
    ))
    await db.flush()

    if decision in {"人工审核", "拒绝"}:
        open_case = (await db.execute(select(RiskCase.case_id).where(
            RiskCase.source_id == request.source_id,
            RiskCase.event_type == request.event_type,
            RiskCase.case_status.in_(("待审核", "审核中")),
        ).limit(1))).scalar_one_or_none()
        if open_case is None:
            auto_reject = decision == "拒绝"
            case_id = _id("cas")
            db.add(RiskCase(
                case_id=case_id,
                assessment_id=assessment_id,
                user_id=request.user_id,
                case_status="已拒绝" if auto_reject else "待审核",
                case_category=Counter((hit.rule_category for hit in hits)).most_common(1)[0][0] if hits else "通用",
                risk_detail=json.dumps([hit.to_dict() for hit in hits], ensure_ascii=False),
                reviewer="system" if auto_reject else None,
                review_comment="系统一票否决" if auto_reject else None,
                review_time=datetime.now() if auto_reject else None,
                source_id=request.source_id,
                event_type=request.event_type,
            ))
            if auto_reject:
                db.add(RiskActionLog(
                    operator="system", action_type="AUTO_REJECT_CASE",
                    target_type="case", target_id=case_id,
                    before_value=None,
                    after_value=json.dumps({"case_status": "已拒绝", "decision": decision}, ensure_ascii=False),
                    remark="极高风险一票否决自动建案",
                ))

    profile = await db.get(RiskUserProfile, request.user_id)
    if profile is None:
        profile = RiskUserProfile(user_id=request.user_id)
        db.add(profile)
    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.registration_count = int(features["patient_registration_count_7d"])
    profile.cancel_count = int(features["patient_cancel_count_30d"])
    profile.claim_count = int(features["patient_claim_count_24h"])
    profile.assessment_count = (profile.assessment_count or 0) + 1
    profile.last_assessment_time = datetime.now()
    profile.profile_data = json.dumps({
        "version": "P2",
        "features": features,
        "rule_score": rule_score,
        "ml_score": ml_result.score,
    }, ensure_ascii=False)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=request.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(hits),
        triggered_rules=[RuleHitInfo(**hit.to_dict()) for hit in hits],
        features=features,
        create_time=datetime.now(),
        ml_score=ml_result.score,
        ml_decision=ml_result.decision,
        blocked_by=next((hit.rule_id for hit in hits if hit.rule_id == "MR016"), None),
    )

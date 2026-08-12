"""银行风控 7 步决策流水线。

核心结构：事件 → 25维特征 → 规则 → 评分/模型 → 评估/案件/画像。
"""
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import ulid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.feature import compute_all_features
from app.engine.ml_model import is_model_loaded, predict
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models import (
    DeviceFingerprint,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

logger = logging.getLogger(__name__)


def _generate_id(prefix: str = "") -> str:
    return f"{prefix}{ulid.new().str.lower()}"


def _score_to_level(score: int, event_type: str = "通用") -> str:
    th = settings.get_event_thresholds(event_type)
    if score < th["pass"]:
        return "低"
    if score < th["mark"]:
        return "中"
    if score < th["review"]:
        return "高"
    return "极高"


def _score_to_decision(score: int, event_type: str = "通用") -> str:
    th = settings.get_event_thresholds(event_type)
    if score < th["pass"]:
        return "通过"
    if score < th["mark"]:
        return "标记"
    if score < th["review"]:
        return "人工审核"
    return "拒绝"


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    if not hits:
        return 0
    return min(
        max(hit.risk_score for hit in hits)
        + settings.RISK_MULTI_RULE_BONUS * (len(hits) - 1),
        100,
    )


def check_veto(hits: list[RuleHitResult]) -> bool:
    return any(hit.action == "拒绝" or hit.risk_level == "极高" for hit in hits)


@dataclass
class _RiskCheckContext:
    request: RiskCheckRequest
    user_id: str
    source_id: str
    event_id: str = ""


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    return _RiskCheckContext(
        request=request,
        user_id=request.user_id,
        source_id=request.source_id,
    )


async def _enrich_bank_context(db: AsyncSession, ctx: _RiskCheckContext) -> None:
    """步骤1扩展点；银行关联数据已由 source_id 唯一定位。"""
    return None


def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> str:
    ctx.event_id = _generate_id("evt")
    db.add(RiskEvent(
        event_id=ctx.event_id,
        event_type=ctx.request.event_type,
        event_source_id=ctx.source_id,
        user_id=ctx.user_id,
        event_data=json.dumps(ctx.request.event_data or {}, ensure_ascii=False),
    ))
    return ctx.event_id


async def _compute_features(db: AsyncSession, ctx: _RiskCheckContext) -> dict[str, float]:
    return await compute_all_features(
        db,
        user_id=ctx.user_id,
        source_id=ctx.source_id,
        event_type=ctx.request.event_type,
    )


def _classify_feature_entity(feature_name: str) -> tuple[str, str]:
    if feature_name.startswith("user_"):
        return "用户", feature_name
    if feature_name.startswith("event_"):
        return "事件", feature_name
    return "上下文", feature_name


def _save_feature_snapshot(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict[str, float],
) -> None:
    for name, value in features.items():
        entity_type, _ = _classify_feature_entity(name)
        entity_id = ctx.user_id if entity_type == "用户" else ctx.source_id
        db.add(RiskFeature(
            event_id=ctx.event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            feature_name=name,
            feature_value=value,
        ))


async def _evaluate_rules(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict[str, float],
) -> list[RuleHitResult]:
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)


def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    prob = min(max(float(prob), 0.0), 1.0)
    return min(max(round(100 * (1 - math.exp(-k * prob))), 0), 100)


def _calculate_decision(
    rules: list[RuleHitResult],
    features: dict[str, float],
    event_type: str = "通用",
) -> tuple[int, str, str, Optional[float], Optional[str]]:
    rule_score = calculate_final_score(rules)
    ml_probability: Optional[float] = None
    ml_decision: Optional[str] = None

    if is_model_loaded():
        result = predict(features)
        if result.is_loaded:
            ml_probability = result.score
            ml_decision = result.decision

    if ml_probability is None:
        final_score = rule_score
    else:
        ml_risk_score = _ml_prob_to_risk_score(ml_probability)
        final_score = round(
            settings.ML_WEIGHT_RULE * rule_score
            + settings.ML_WEIGHT_XGB * ml_risk_score
        )

    if check_veto(rules):
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)
        return final_score, "极高", "拒绝", ml_probability, ml_decision

    return (
        final_score,
        _score_to_level(final_score, event_type),
        _score_to_decision(final_score, event_type),
        ml_probability,
        ml_decision,
    )


async def _save_assessment(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    rules: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    ml_score: Optional[float],
    ml_decision: Optional[str],
) -> str:
    assessment_id = _generate_id("ast")
    db.add(RiskAssessment(
        assessment_id=assessment_id,
        event_id=ctx.event_id,
        user_id=ctx.user_id,
        rule_results=json.dumps([
            {
                "rule_id": hit.rule_id,
                "rule_name": hit.rule_name,
                "rule_category": hit.rule_category,
                "risk_level": hit.risk_level,
                "risk_score": hit.risk_score,
                "action": hit.action,
                "description": hit.description,
            }
            for hit in rules
        ], ensure_ascii=False),
        rule_count=len(rules),
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        ml_score=ml_score,
        ml_decision=ml_decision,
    ))
    return assessment_id


async def _maybe_create_case(
    db: AsyncSession,
    assessment_id: str,
    ctx: _RiskCheckContext,
    rules: list[RuleHitResult],
    final_score: int,
    decision: str,
) -> None:
    if decision not in ("人工审核", "拒绝"):
        return

    existing = (await db.execute(
        select(RiskCase.case_id).where(
            RiskCase.source_id == ctx.source_id,
            RiskCase.event_type == ctx.request.event_type,
            RiskCase.case_status.in_(("待审核", "审核中")),
        )
    )).scalar_one_or_none()
    if existing:
        return

    categories = [hit.rule_category for hit in rules]
    category = Counter(categories).most_common(1)[0][0] if categories else "银行风险"
    auto_reject = decision == "拒绝"
    case_id = _generate_id("cas")
    db.add(RiskCase(
        case_id=case_id,
        assessment_id=assessment_id,
        user_id=ctx.user_id,
        case_status="已拒绝" if auto_reject else "待审核",
        case_category=category,
        risk_detail=json.dumps({
            "event_type": ctx.request.event_type,
            "source_id": ctx.source_id,
            "final_score": final_score,
            "rules": [hit.rule_id for hit in rules],
        }, ensure_ascii=False),
        source_id=ctx.source_id,
        event_type=ctx.request.event_type,
        reviewer="system" if auto_reject else None,
        review_time=datetime.now() if auto_reject else None,
        review_comment=f"系统自动拒绝，风险分={final_score}" if auto_reject else None,
    ))

    if auto_reject:
        from app.service.action_log import record_action
        await record_action(
            db,
            operator="system",
            action_type="AUTO_REJECT_CASE",
            target_type="case",
            target_id=case_id,
            before_value=None,
            after_value={"case_status": "已拒绝", "final_score": final_score},
            remark=f"银行事件自动拒绝: {ctx.request.event_type}/{ctx.source_id}",
        )


async def _update_user_profile(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict[str, float],
    final_score: int,
    risk_level: str,
) -> None:
    """核心画像表列名保持基线不变，通过注释和 profile_data 映射银行语义。"""
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == ctx.user_id)
    )).scalar_one_or_none()
    if profile is None:
        profile = RiskUserProfile(user_id=ctx.user_id)
        db.add(profile)

    txn_count = int(features.get("user_transaction_count_30d", 0))
    loan_count = int(features.get("user_loan_application_count_30d", 0))
    txn_amount = float(features.get("user_transaction_amount_30d", 0))
    failed_logins = int(features.get("user_failed_login_count_24h", 0))
    device_count = int((await db.execute(
        select(func.count(func.distinct(DeviceFingerprint.device_id))).where(
            DeviceFingerprint.user_id == ctx.user_id,
            DeviceFingerprint.last_seen >= datetime.now().replace(microsecond=0) - timedelta(days=30),
        )
    )).scalar() or 0)

    previous_count = int(profile.assessment_count or 0)
    previous_rate = float(profile.refund_rate or 0)
    current_high_risk = 1.0 if risk_level in ("高", "极高") else 0.0

    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.total_orders = txn_count
    profile.total_refunds = loan_count
    profile.refund_rate = round(
        (previous_rate * previous_count + current_high_risk) / (previous_count + 1), 4,
    )
    profile.avg_order_amount = round(txn_amount / txn_count, 2) if txn_count else 0
    profile.address_count = device_count
    profile.complaint_count = failed_logins
    profile.assessment_count = previous_count + 1
    profile.last_assessment_time = datetime.now()
    profile.profile_data = json.dumps({
        "schema": "bank_profile_v1",
        "transaction_count_30d": txn_count,
        "loan_application_count_30d": loan_count,
        "avg_transaction_amount_30d": float(profile.avg_order_amount),
        "failed_login_count_24h": failed_logins,
        "credit_score": features.get("user_credit_score", 0),
        "kyc_level": features.get("user_kyc_level", 0),
    }, ensure_ascii=False)


def _build_response(
    ctx: _RiskCheckContext,
    features: dict[str, float],
    rules: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    event_id: str,
    assessment_id: str,
    ml_score: Optional[float] = None,
    ml_decision: Optional[str] = None,
) -> RiskCheckResponse:
    triggered = [
        RuleHitInfo(
            rule_id=hit.rule_id,
            rule_name=hit.rule_name,
            rule_category=hit.rule_category,
            risk_level=hit.risk_level,
            risk_score=hit.risk_score,
            action=hit.action,
            description=hit.description,
        )
        for hit in rules
    ]
    veto_names = [hit.rule_name for hit in rules if hit.risk_level == "极高"]
    if veto_names:
        message = "触发一票否决: " + "、".join(veto_names)
    elif decision == "通过":
        message = "银行事件正常放行"
    elif decision == "标记":
        message = "存在风险信号，已标记观察"
    else:
        message = f"银行事件决策: {decision}"

    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=ctx.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(rules),
        triggered_rules=triggered,
        features=features if settings.RISK_FEATURES_FULL_RETURN else {},
        create_time=datetime.now(),
        ml_score=ml_score,
        ml_decision=ml_decision,
        message=message,
    )


async def run_risk_check(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """复用 7 步：上下文、事件、特征、快照、规则、决策、原子化落库。"""
    # 1. 准备上下文
    ctx = _build_context(request)
    await _enrich_bank_context(db, ctx)
    # 2. 创建事件
    event_id = _create_event_record(db, ctx)
    # 3-4. 计算并保存 25 维特征
    features = await _compute_features(db, ctx)
    _save_feature_snapshot(db, ctx, features)
    # 5. 加载并匹配行业规则
    rules = await _evaluate_rules(db, ctx, features)
    # 6. 规则分与可选模型融合
    final_score, risk_level, decision, ml_score, ml_decision = _calculate_decision(
        rules, features, request.event_type
    )
    # 7. 评估、案件、画像在一个事务中落库
    await db.flush()
    assessment_id = await _save_assessment(
        db, ctx, rules, final_score, risk_level, decision, ml_score, ml_decision
    )
    await _maybe_create_case(db, assessment_id, ctx, rules, final_score, decision)
    await _update_user_profile(db, ctx, features, final_score, risk_level)
    await db.commit()

    return _build_response(
        ctx, features, rules, final_score, risk_level, decision,
        event_id, assessment_id, ml_score, ml_decision,
    )

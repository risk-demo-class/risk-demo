"""
决策引擎: 7 步流水线.

1. 准备上下文
2. 创建事件记录
3-4. 计算并保存特征快照
5. 加载并匹配规则
6. 规则 + XGBoost + LLM 融合决策
7. 落库 assessment / case / profile
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.feature import compute_all_features
from app.engine.ml_model import predict
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models import (
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
)
from app.schemas import (
    RiskCheckRequest,
    RiskCheckResponse,
    RuleHitInfo,
)

logger = logging.getLogger(__name__)


def _generate_id(prefix: str = "") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _score_to_level(score: int) -> str:
    if score < settings.RISK_PASS_THRESHOLD:
        return "低"
    if score < settings.RISK_MARK_THRESHOLD:
        return "中"
    if score < settings.RISK_REVIEW_THRESHOLD:
        return "高"
    return "极高"


def _score_to_decision(score: int) -> str:
    if score < settings.RISK_PASS_THRESHOLD:
        return "通过"
    if score < settings.RISK_MARK_THRESHOLD:
        return "标记"
    if score < settings.RISK_REVIEW_THRESHOLD:
        return "人工审核"
    return "拒绝"


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    """规则分 = max(规则分) + 额外命中数 * bonus, 上限 100."""
    if not hits:
        return 0
    max_score = max(h.risk_score for h in hits)
    extra = len(hits) - 1
    return min(max_score + settings.RISK_MULTI_RULE_BONUS * extra, 100)


def check_veto(hits: list[RuleHitResult]) -> bool:
    """极高规则一票否决."""
    return any(h.risk_level == "极高" for h in hits)


class _RiskCheckContext:
    """流水线共享上下文."""

    def __init__(
        self,
        request: RiskCheckRequest,
        user_id: str,
        order_id: Optional[str] = None,
        receive_id: Optional[str] = None,
    ):
        self.request = request
        self.user_id = user_id
        self.order_id = order_id
        self.receive_id = receive_id
        self.event_id = ""


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    """构建上下文, 下单/支付场景 source_id 即订单."""
    order_id = request.order_id
    if not order_id and request.event_type in ("下单", "支付"):
        order_id = request.source_id
    return _RiskCheckContext(
        request=request,
        user_id=request.user_id,
        order_id=order_id,
        receive_id=request.receive_id,
    )


def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> str:
    """创建 risk_event."""
    ctx.event_id = _generate_id("evt")
    event = RiskEvent(
        event_id=ctx.event_id,
        event_type=ctx.request.event_type,
        event_source_id=ctx.request.source_id,
        user_id=ctx.user_id,
        event_data=ctx.request.event_data or {},
    )
    db.add(event)
    return ctx.event_id


async def _compute_features(
    db: AsyncSession,
    ctx: _RiskCheckContext,
) -> dict[str, float]:
    return await compute_all_features(
        db,
        user_id=ctx.user_id,
        order_id=ctx.order_id,
        event_data=ctx.request.event_data,
    )


def _classify_feature_entity(feature_name: str) -> tuple[str, str]:
    """特征名前缀 -> 实体类型."""
    if feature_name.startswith("user_"):
        return "用户", feature_name
    if feature_name.startswith("order_"):
        return "订单", feature_name
    if feature_name.startswith("device_"):
        return "设备", feature_name
    if feature_name.startswith(("passenger_", "addr_")):
        return "乘客", feature_name
    if feature_name.startswith("remark_"):
        return "语义", feature_name
    return "用户", feature_name


def _save_feature_snapshot(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict[str, float],
) -> None:
    """保存特征快照到 risk_feature."""
    for fname, fval in features.items():
        entity_type, _ = _classify_feature_entity(fname)
        if entity_type == "用户":
            entity_id = ctx.user_id
        elif entity_type == "订单":
            entity_id = ctx.order_id or ctx.request.source_id
        elif entity_type == "设备":
            entity_id = (ctx.request.event_data or {}).get("device_id") or ctx.user_id
        elif entity_type == "乘客":
            entity_id = ctx.receive_id or ctx.user_id
        else:
            entity_id = ctx.order_id or ctx.user_id
        db.add(
            RiskFeature(
                event_id=ctx.event_id,
                entity_type=entity_type,
                entity_id=entity_id,
                feature_name=fname,
                feature_value=float(fval),
            )
        )


async def _evaluate_rules(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict[str, float],
) -> list[RuleHitResult]:
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)


def _calculate_decision(
    hits: list[RuleHitResult],
    ml_score: float,
    llm_score: float,
) -> tuple[int, str, str]:
    """双轨融合 + LLM bonus + 一票否决."""
    rule_score = calculate_final_score(hits)
    llm_bonus = min(max(llm_score * 0.2, 0.0), 20.0)
    final_score = int(
        round(
            settings.ML_WEIGHT_RULE * rule_score
            + settings.ML_WEIGHT_XGB * ml_score
            + llm_bonus
        )
    )
    if check_veto(hits):
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)
    return final_score, _score_to_level(final_score), _score_to_decision(final_score)


async def _save_assessment(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    hits: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    ml_score: float,
    ml_probability: float,
    ml_decision: str,
) -> str:
    assessment_id = _generate_id("asmt")
    assessment = RiskAssessment(
        assessment_id=assessment_id,
        event_id=ctx.event_id,
        user_id=ctx.user_id,
        rule_results=[h.to_dict() for h in hits],
        rule_count=len(hits),
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        ml_score=ml_score,
        ml_probability=ml_probability,
        ml_decision=ml_decision,
    )
    db.add(assessment)
    return assessment_id


async def _maybe_create_case(
    db: AsyncSession,
    assessment_id: str,
    ctx: _RiskCheckContext,
    hits: list[RuleHitResult],
    final_score: int,
    decision: str,
) -> Optional[str]:
    """人工审核 / 拒绝时创建案件."""
    if decision not in ("人工审核", "拒绝"):
        return None
    try:
        existing = (
            await db.execute(
                select(RiskCase).where(
                    RiskCase.source_id == ctx.request.source_id,
                    RiskCase.event_type == ctx.request.event_type,
                    RiskCase.case_status.in_(["待审核", "审核中"]),
                )
            )
        ).scalar_one_or_none()
        if existing:
            logger.info("已有未结案件, 跳过建案: %s", existing.case_id)
            return existing.case_id

        case_id = _generate_id("case")
        category = hits[0].rule_category if hits else "规则"
        db.add(
            RiskCase(
                case_id=case_id,
                assessment_id=assessment_id,
                user_id=ctx.user_id,
                case_status="待审核",
                case_category=category,
                risk_detail={
                    "final_score": final_score,
                    "decision": decision,
                    "rules": [h.to_dict() for h in hits],
                },
                source_id=ctx.request.source_id,
                event_type=ctx.request.event_type,
            )
        )
        return case_id
    except Exception:
        logger.exception("创建案件失败")
        raise


async def _update_user_profile(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict[str, float],
    final_score: int,
    risk_level: str,
) -> None:
    """更新用户风险画像."""
    profile = (
        await db.execute(
            select(RiskUserProfile).where(RiskUserProfile.user_id == ctx.user_id).limit(1)
        )
    ).scalar_one_or_none()
    if not profile:
        profile = RiskUserProfile(user_id=ctx.user_id)
        db.add(profile)

    total_orders = features.get("user_total_orders", 0)
    refund_count = features.get("user_refund_count", 0)
    profile.total_orders = int(total_orders)
    profile.total_refunds = int(refund_count)
    profile.refund_rate = (
        round(refund_count / total_orders, 4) if total_orders > 0 else 0
    )
    profile.avg_order_amount = features.get("user_avg_order_amount", 0)
    profile.address_count = int(features.get("user_passenger_id_count", 0))
    profile.complaint_count = int(features.get("user_cancel_count", 0))
    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.assessment_count = (profile.assessment_count or 0) + 1
    profile.last_assessment_time = datetime.now()


def _build_response(
    ctx: _RiskCheckContext,
    features: dict[str, float],
    hits: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    event_id: str,
    assessment_id: str,
    ml_score: float,
    ml_probability: float,
    ml_decision: str,
) -> RiskCheckResponse:
    triggered = [
        RuleHitInfo(
            rule_id=h.rule_id,
            rule_name=h.rule_name,
            rule_category=h.rule_category,
            risk_level=h.risk_level,
            risk_score=h.risk_score,
            action=h.action,
            description=h.description,
        )
        for h in hits
    ]
    features_out = features if settings.RISK_FEATURES_FULL_RETURN else {}
    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=ctx.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(hits),
        triggered_rules=triggered,
        features=features_out,
        ml_score=ml_score,
        ml_probability=ml_probability,
        ml_decision=ml_decision,
        llm_score=features.get("remark_llm_score", 0.0),
        create_time=datetime.now(),
    )


async def run_risk_check(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckResponse:
    """7 步决策流水线, 整体一个事务."""
    try:
        ctx = _build_context(request)
        event_id = _create_event_record(db, ctx)
        features = await _compute_features(db, ctx)
        _save_feature_snapshot(db, ctx, features)
        hits = await _evaluate_rules(db, ctx, features)

        ml_result = predict(features)
        llm_score = features.get("remark_llm_score", 0.0)
        final_score, risk_level, decision = _calculate_decision(
            hits,
            ml_score=ml_result.score,
            llm_score=llm_score,
        )

        await db.flush()
        assessment_id = await _save_assessment(
            db,
            ctx,
            hits,
            final_score,
            risk_level,
            decision,
            ml_result.score,
            ml_result.probability,
            ml_result.decision,
        )
        await _maybe_create_case(db, assessment_id, ctx, hits, final_score, decision)
        await _update_user_profile(db, ctx, features, final_score, risk_level)
        await db.commit()

        logger.info(
            "风控检查完成: user=%s source=%s final=%s decision=%s rules=%d ml=%s",
            request.user_id,
            request.source_id,
            final_score,
            decision,
            len(hits),
            ml_result.score,
        )
        return _build_response(
            ctx,
            features,
            hits,
            final_score,
            risk_level,
            decision,
            event_id,
            assessment_id,
            ml_result.score,
            ml_result.probability,
            ml_result.decision,
        )
    except Exception:
        logger.exception("run_risk_check 失败: %s", request.source_id)
        try:
            await db.rollback()
        except Exception:
            logger.exception("run_risk_check 回滚失败")
        raise

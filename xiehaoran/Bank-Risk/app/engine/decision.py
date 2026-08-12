"""
风控决策引擎 (银行语义): 串联 7 步流水线, 事件 → 特征 → 规则 → 评分 → 决策 → 持久化.

评分公式: final_score = max(各规则分) + BONUS × (额外命中数), 上限 100
双轨融合: final_score = α × rule_score + β × ml_score (α+β=1)
一票否决: 任意 risk_level="极高" / action="freeze" 命中 → 强制 freeze, 不被 XGBoost 推翻

7 步流水线:
  1. 准备上下文
  2. 创建事件记录 (risk_event)
  3-4. 计算 + 保存特征快照 (11 维, risk_feature)
  5. 加载 + 匹配规则 (DB 动态规则, 条件对齐 11 维特征)
  6. 计算评分与决策 (含一票否决 + 双轨融合)
  7. 落库 + 响应 (assessment/case/profile)
"""
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine import feature as bank_feature
from app.engine.feature import compute_all_features
from app.engine.ml_model import is_model_loaded, predict
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models_risk import (
    RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskUserProfile,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

logger = logging.getLogger(__name__)


def _generate_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex}"


def _score_to_level(score: int, event_type: str = "通用") -> str:
    th = settings.get_event_thresholds(event_type)
    if score < th["pass"]:
        return "低"
    elif score < th["mark"]:
        return "中"
    elif score < th["review"]:
        return "高"
    else:
        return "极高"


def _score_to_decision(score: int, event_type: str = "通用") -> str:
    """5 档决策: pass/review/reject/freeze/report (银行语义)."""
    th = settings.get_event_thresholds(event_type)
    if score < th["pass"]:
        return "pass"
    elif score < th["mark"]:
        return "review"
    elif score < th["review"]:
        return "reject"
    else:
        return "freeze"


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    if not hits:
        return 0
    max_score = max(h.risk_score for h in hits)
    extra_count = len(hits) - 1
    bonus = settings.RISK_MULTI_RULE_BONUS * extra_count
    return min(max_score + bonus, 100)


def check_veto(hits: list[RuleHitResult]) -> bool:
    """一票否决: action='freeze' 或 risk_level='极高'."""
    return any(h.action == "freeze" or h.risk_level == "极高" for h in hits)


# ============================================================
# 上下文
# ============================================================
@dataclass
class _RiskCheckContext:
    request: RiskCheckRequest
    user_id: str
    order_id: Optional[str] = None
    receive_id: Optional[str] = None
    event_id: str = ""


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    order_id = request.order_id
    if not order_id and request.event_type in ("transfer", "card_txn"):
        order_id = request.source_id
    return _RiskCheckContext(
        request=request,
        user_id=request.user_id,
        order_id=order_id,
        receive_id=request.receive_id,
    )


# ============================================================
# 步骤 2: 创建事件记录
# ============================================================
def _create_event_record(ctx: _RiskCheckContext) -> str:
    ctx.event_id = _generate_id("evt")
    event = RiskEvent(
        event_id=ctx.event_id,
        event_type=ctx.request.event_type,
        event_source_id=ctx.request.source_id,
        user_id=ctx.user_id,
        event_data=json.dumps(ctx.request.event_data or {}, ensure_ascii=False),
    )
    db = _get_db(ctx)
    db.add(event)
    return ctx.event_id


# ctx 需要携带 db, 简单起见在 run_risk_check 内直接操作 db
def _get_db(ctx: _RiskCheckContext):
    return getattr(ctx, "_db", None)


# ============================================================
# 步骤 3-4: 计算特征 + 保存特征快照
# ============================================================
async def _compute_features(db: AsyncSession, ctx: _RiskCheckContext) -> dict:
    # 合并事件字段 + event_data 作为特征计算的 ctx
    ctx_dict = {
        **(ctx.request.event_data or {}),
        "amount": ctx.request.event_data.get("amount") if ctx.request.event_data else None,
    }
    # 兼容前端把 amount 放顶层
    if ctx.request.event_data and "amount" in ctx.request.event_data:
        ctx_dict["amount"] = ctx.request.event_data["amount"]
    return compute_all_features(
        ctx_dict,
        user_id=ctx.user_id,
        order_id=ctx.order_id,
        receive_id=ctx.receive_id,
    )


def _classify_feature_entity(feature_name: str) -> tuple[str, str]:
    if feature_name.startswith("user_"):
        return "用户", feature_name
    if feature_name.startswith("order_"):
        return "订单", feature_name
    return "地址", feature_name


def _save_feature_snapshot(db: AsyncSession, ctx: _RiskCheckContext, features: dict) -> None:
    for fname, fval in features.items():
        entity_type, _ = _classify_feature_entity(fname)
        if entity_type == "用户":
            entity_id = ctx.user_id
        elif entity_type == "订单":
            entity_id = ctx.order_id or ctx.request.source_id
        else:
            entity_id = ctx.receive_id or ctx.user_id
        db.add(RiskFeature(
            event_id=ctx.event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            feature_name=fname,
            feature_value=fval,
        ))


# ============================================================
# 步骤 5: 加载并匹配规则
# ============================================================
async def _evaluate_rules(db: AsyncSession, ctx: _RiskCheckContext, features: dict) -> list[RuleHitResult]:
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)


# ============================================================
# 步骤 6: 计算评分与决策
# ============================================================
def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    if prob <= 0:
        return 0
    if prob >= 1:
        return 100
    return int(round(100 * (1 - math.exp(-k * prob))))


def _calculate_decision(rules, features, event_type="通用"):
    rule_score = calculate_final_score(rules)
    has_veto = check_veto(rules)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    ml_result = predict(features) if is_model_loaded() else None
    ml_score_100 = _ml_prob_to_risk_score(ml_result.score) if ml_result else 0
    ml_decision = ml_result.decision if ml_result else "pass"

    if ml_result and ml_result.is_loaded:
        final_score = int(round(settings.ML_WEIGHT_RULE * rule_score + settings.ML_WEIGHT_XGB * ml_score_100))
        final_score = max(0, min(100, final_score))
    else:
        final_score = rule_score

    risk_level = _score_to_level(final_score, event_type)
    decision = _score_to_decision(final_score, event_type)

    if has_veto:
        decision = "freeze"
        risk_level = "极高"
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)

    return final_score, risk_level, decision, ml_result.score if ml_result else 0.0, ml_decision


# ============================================================
# 步骤 7: 落库 + 响应
# ============================================================
async def _save_assessment(db, ctx, rules, final_score, risk_level, decision, ml_score=0.0, ml_decision="pass") -> str:
    assessment_id = _generate_id("ast")
    db.add(RiskAssessment(
        assessment_id=assessment_id,
        event_id=ctx.event_id,
        user_id=ctx.user_id,
        rule_results=json.dumps([h.to_dict() for h in rules], ensure_ascii=False),
        rule_count=len(rules),
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        ml_score=ml_score,
        ml_decision=ml_decision,
    ))
    return assessment_id


async def _maybe_create_case(db, assessment_id, ctx, rules, final_score, decision) -> None:
    """决策是 reject/freeze 时建案 (pass/review 不建)."""
    if decision not in ("reject", "freeze"):
        return
    open_statuses = ("待审核", "审核中")
    existing = (await db.execute(
        select(RiskCase.case_id).where(
            RiskCase.source_id == ctx.request.source_id,
            RiskCase.event_type == ctx.request.event_type,
            RiskCase.case_status.in_(open_statuses),
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        return

    case_id = _generate_id("cas")
    if rules:
        top_category = Counter(r.rule_category for r in rules).most_common(1)[0][0]
    else:
        top_category = "未知"

    is_auto_reject = decision == "freeze" or decision == "reject"
    initial_status = "已拒绝" if is_auto_reject else "待审核"

    case_kwargs = dict(
        case_id=case_id,
        assessment_id=assessment_id,
        user_id=ctx.user_id,
        case_status=initial_status,
        case_category=top_category,
        risk_detail=json.dumps([h.to_dict() for h in rules], ensure_ascii=False),
        source_id=ctx.request.source_id,
        event_type=ctx.request.event_type,
    )
    if is_auto_reject:
        case_kwargs.update(
            reviewer="system",
            review_time=datetime.now(),
            review_comment=f"系统自动处理 (final_score={final_score}, {len(rules)} 条规则命中)",
        )
    db.add(RiskCase(**case_kwargs))


async def _update_user_profile(db, ctx, features, final_score, risk_level) -> None:
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == ctx.user_id)
    )).scalar_one_or_none()
    if not profile:
        profile = RiskUserProfile(user_id=ctx.user_id)
        db.add(profile)
    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.total_orders = int(features.get("disperse_peer_cnt_raw", features.get("user_total_orders", 0)) or 0)
    profile.assessment_count = (profile.assessment_count or 0) + 1
    profile.last_assessment_time = datetime.now()


def _build_response(ctx, features, rules, final_score, risk_level, decision, event_id, assessment_id,
                    ml_score=0.0, ml_decision="pass") -> RiskCheckResponse:
    triggered_rules = [
        RuleHitInfo(
            rule_id=h.rule_id, rule_name=h.rule_name, rule_category=h.rule_category,
            risk_level=h.risk_level, risk_score=h.risk_score, action=h.action, description=h.description,
        )
        for h in rules
    ]
    features_out = features if settings.RISK_FEATURES_FULL_RETURN else {}
    return RiskCheckResponse(
        assessment_id=assessment_id, event_id=event_id, user_id=ctx.user_id,
        final_score=final_score, risk_level=risk_level, decision=decision,
        rule_count=len(rules), triggered_rules=triggered_rules,
        features=features_out, create_time=datetime.now(),
        ml_score=ml_score, ml_decision=ml_decision,
    )


async def run_risk_check(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    import math  # 局部 import, 配合 _calculate_decision 内的 math.exp 引用
    ctx = _build_context(request)
    ctx._db = db  # type: ignore

    event_id = _create_event_record(ctx)
    features = await _compute_features(db, ctx)
    _save_feature_snapshot(db, ctx, features)
    rules = await _evaluate_rules(db, ctx, features)
    final_score, risk_level, decision, ml_score, ml_decision = _calculate_decision(
        rules, features, request.event_type,
    )
    await db.flush()
    assessment_id = await _save_assessment(db, ctx, rules, final_score, risk_level, decision, ml_score, ml_decision)
    await _maybe_create_case(db, assessment_id, ctx, rules, final_score, decision)
    await _update_user_profile(db, ctx, features, final_score, risk_level)
    await db.commit()
    return _build_response(ctx, features, rules, final_score, risk_level, decision, event_id, assessment_id,
                           ml_score, ml_decision)

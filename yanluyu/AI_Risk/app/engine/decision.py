"""
教育风控决策引擎: 串联 7 步流水线, 事件 -> 特征 -> 规则 -> 评分 -> 决策 -> 持久化.

评分公式: final_score = min(max(各规则分) + BONUS * (额外命中数), 100)
双轨融合: final_score = alpha * rule_score + beta * ml_score (alpha+beta=1)
一票否决: 任何 risk_level="极高" 的规则命中 -> 强制拒绝, 不被 XGBoost 推翻

7 步流水线:
  1. 校验 + 准备上下文 (Context)
  2. 创建事件记录 (risk_event)
  3-4. 计算 + 保存特征快照 (11 维, risk_feature)
  5. 加载 + 匹配规则
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

import ulid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.feature_edu import compute_all_features
from app.engine.ml_model import is_model_loaded, predict
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models import (
    OrderInfo, RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskUserProfile,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

logger = logging.getLogger(__name__)


# ============================================================
# 工具函数 (纯计算, 无副作用, 易测试)
# ============================================================

def _generate_id(prefix: str = "") -> str:
    """生成带前缀的有序唯一 ID. 前缀区分 ID 用途 (evt/ast/cas)"""
    return f"{prefix}{ulid.new().str.lower()}"


def _score_to_level(score: int) -> str:
    """评分 -> 风险等级"""
    if score < settings.RISK_PASS_THRESHOLD:
        return "低"
    elif score < settings.RISK_MARK_THRESHOLD:
        return "中"
    elif score < settings.RISK_REVIEW_THRESHOLD:
        return "高"
    else:
        return "极高"


def _score_to_decision(score: int) -> str:
    """评分 -> 决策动作: 通过/标记/人工审核/拒绝"""
    if score < settings.RISK_PASS_THRESHOLD:
        return "通过"
    elif score < settings.RISK_MARK_THRESHOLD:
        return "标记"
    elif score < settings.RISK_REVIEW_THRESHOLD:
        return "人工审核"
    else:
        return "拒绝"


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    """核心评分公式: max(各规则分) + BONUS * (额外命中数), 上限 100."""
    if not hits:
        return 0
    max_score = max(h.risk_score for h in hits)
    extra_count = len(hits) - 1
    bonus = settings.RISK_MULTI_RULE_BONUS * extra_count
    return min(max_score + bonus, 100)


def check_veto(hits: list[RuleHitResult]) -> bool:
    """一票否决: 任意 1 条 risk_level='极高' 就 True"""
    return any(h.risk_level == "极高" for h in hits)


# ============================================================
# 步骤 1: 准备上下文
# ============================================================

@dataclass
class _RiskCheckContext:
    request: RiskCheckRequest
    user_id: str
    order_id: Optional[str] = None
    course_id: Optional[str] = None
    device_fingerprint: Optional[str] = None
    donation_id: Optional[str] = None
    event_id: str = ""


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    """步骤 1: 请求 -> Context, 补全关联 ID.

    业务规则:
      - "报名" 事件: source_id 是 order_id
      - "退费申请" 事件: source_id 是 refund_id, order_id 从 request 传或从 DB 反查
      - "打赏" 事件: source_id 是 donation_id
    """
    ctx = _RiskCheckContext(
        request=request,
        user_id=request.user_id,
        order_id=request.order_id,
        course_id=request.course_id,
        donation_id=request.donation_id,
    )

    if request.event_type == "报名":
        if not ctx.order_id:
            ctx.order_id = request.source_id
    elif request.event_type == "打赏":
        if not ctx.donation_id:
            ctx.donation_id = request.source_id

    return ctx


async def _enrich_context(db: AsyncSession, ctx: _RiskCheckContext) -> None:
    """步骤 1b: 从 DB 补全 course_id / device_fingerprint."""
    if ctx.order_id and (not ctx.course_id or not ctx.device_fingerprint):
        row = (await db.execute(
            select(OrderInfo.course_id, OrderInfo.device_fingerprint)
            .where(OrderInfo.order_id == ctx.order_id)
        )).first()
        if row:
            if not ctx.course_id:
                ctx.course_id = row.course_id
            if not ctx.device_fingerprint:
                ctx.device_fingerprint = row.device_fingerprint


# ============================================================
# 步骤 2: 创建事件记录
# ============================================================

def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> str:
    ctx.event_id = _generate_id("evt")
    event = RiskEvent(
        event_id=ctx.event_id,
        event_type=ctx.request.event_type,
        event_source_id=ctx.request.source_id,
        user_id=ctx.user_id,
        event_data=json.dumps(ctx.request.event_data or {}, ensure_ascii=False),
    )
    db.add(event)
    return ctx.event_id


# ============================================================
# 步骤 3-4: 计算特征 + 保存特征快照
# ============================================================

async def _compute_features(db: AsyncSession, ctx: _RiskCheckContext) -> dict:
    """步骤 3: 调用 feature_edu.py 计算教育风控特征"""
    return await compute_all_features(
        db,
        user_id=ctx.user_id,
        order_id=ctx.order_id,
        course_id=ctx.course_id,
        device_fingerprint=ctx.device_fingerprint,
        donation_id=ctx.donation_id,
        event_type=ctx.request.event_type,
    )


def _classify_feature_entity(feature_name: str) -> tuple[str, str]:
    """特征名前缀 -> 实体类型. 用于 risk_feature 表 entity_type."""
    if feature_name.startswith("user_"):
        return "用户", feature_name
    if feature_name.startswith("order_") or feature_name.startswith("course_"):
        return "订单", feature_name
    if feature_name.startswith("device_"):
        return "设备", feature_name
    if feature_name.startswith("learn_"):
        return "用户", feature_name
    if feature_name.startswith("donation_"):
        return "用户", feature_name
    return "用户", feature_name


def _save_feature_snapshot(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
) -> None:
    """步骤 4: 把特征落库到 risk_feature (审计回溯)."""
    for fname, fval in features.items():
        entity_type, _ = _classify_feature_entity(fname)
        if entity_type == "用户":
            entity_id = ctx.user_id
        elif entity_type == "订单":
            entity_id = ctx.order_id or ctx.request.source_id
        elif entity_type == "设备":
            entity_id = ctx.device_fingerprint or ctx.user_id
        else:
            entity_id = ctx.user_id
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

async def _evaluate_rules(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
) -> list[RuleHitResult]:
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)


# ============================================================
# 步骤 6: 计算评分与决策
# ============================================================

def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    """ML P(拒绝) -> 0-100 风险分 (sigmoid 校准)."""
    if prob <= 0:
        return 0
    if prob >= 1:
        return 100
    return int(round(100 * (1 - math.exp(-k * prob))))


def _calculate_decision(
    rules: list[RuleHitResult],
    features: dict,
) -> tuple[int, str, str, float, str]:
    """步骤 6: 算评分 + 一票否决 + 双轨融合 + 映射."""
    rule_score = calculate_final_score(rules)

    has_veto = check_veto(rules)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    # XGBoost 推理
    ml_result = predict(features) if is_model_loaded() else None
    ml_score_100 = _ml_prob_to_risk_score(ml_result.score) if ml_result else 0
    ml_decision = ml_result.decision if ml_result else "通过"

    # 双轨融合
    if ml_result and ml_result.is_loaded:
        final_score = int(round(
            settings.ML_WEIGHT_RULE * rule_score
            + settings.ML_WEIGHT_XGB * ml_score_100
        ))
        final_score = max(0, min(100, final_score))
    else:
        final_score = rule_score

    risk_level = _score_to_level(final_score)
    decision = _score_to_decision(final_score)

    # 硬性一票否决: 不被 XGBoost 推翻
    if has_veto:
        decision = "拒绝"
        risk_level = "极高"
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)

    return final_score, risk_level, decision, ml_result.score if ml_result else 0.0, ml_decision


# ============================================================
# 步骤 7: 落库 + 响应
# ============================================================

async def _save_assessment(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    rules: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    ml_score: float = 0.0,
    ml_decision: str = "通过",
) -> str:
    assessment_id = _generate_id("ast")
    rule_results_json = json.dumps(
        [h.to_dict() for h in rules], ensure_ascii=False,
    )
    db.add(RiskAssessment(
        assessment_id=assessment_id,
        event_id=ctx.event_id,
        user_id=ctx.user_id,
        rule_results=rule_results_json,
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
    """步骤 7b: 条件建案 (decision 为人工审核/拒绝时)."""
    if decision not in ("人工审核", "拒绝"):
        return

    # 去重: 同一 (source_id, event_type) + 未结案 -> skip
    open_statuses = ("待审核", "审核中")
    existing = (await db.execute(
        select(RiskCase.case_id).where(
            RiskCase.source_id == ctx.request.source_id,
            RiskCase.event_type == ctx.request.event_type,
            RiskCase.case_status.in_(open_statuses),
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        logger.info(
            "跳过建案: 已有未结案 case=%s (source_id=%s, event_type=%s)",
            existing, ctx.request.source_id, ctx.request.event_type,
        )
        return

    case_id = _generate_id("cas")
    if rules:
        top_category = Counter(r.rule_category for r in rules).most_common(1)[0][0]
    else:
        top_category = "未知"

    is_auto_reject = decision == "拒绝"
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
            review_comment=f"系统自动拒绝 (final_score={final_score}, {len(rules)} 条规则命中)",
        )

    db.add(RiskCase(**case_kwargs))
    logger.info(
        "创建案件: %s, source_id=%s, event_type=%s, 决策=%s, 分值=%d, 状态=%s",
        case_id, ctx.request.source_id, ctx.request.event_type, decision, final_score, initial_status,
    )

    if is_auto_reject:
        from app.service.action_log import record_action
        await record_action(
            db, operator="system", action_type="AUTO_REJECT_CASE",
            target_type="case", target_id=case_id,
            before_value=None,
            after_value={"case_status": "已拒绝", "final_score": final_score,
                         "decision": decision, "rule_count": len(rules)},
            remark=f"系统自动拒绝, source_id={ctx.request.source_id}",
        )


async def _update_user_profile(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
    final_score: int,
    risk_level: str,
) -> None:
    """步骤 7c: 更新用户风险画像 (upsert)."""
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == ctx.user_id)
    )).scalar_one_or_none()

    if not profile:
        profile = RiskUserProfile(user_id=ctx.user_id)
        db.add(profile)

    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.total_orders = int(features.get("user_total_orders", 0))
    profile.total_refunds = int(features.get("user_refund_count_90d", 0))
    total_orders = features.get("user_total_orders", 0)
    raw_rate = features.get("user_refund_count_90d", 0) / total_orders if total_orders > 0 else 0
    profile.refund_rate = round(min(raw_rate, 9.9999), 4)  # clamp to DECIMAL(5,4) range
    profile.avg_order_amount = features.get("order_total_amount", 0)
    profile.address_count = 0
    profile.complaint_count = 0
    profile.assessment_count = (profile.assessment_count or 0) + 1
    profile.last_assessment_time = datetime.now()


def _build_response(
    ctx: _RiskCheckContext,
    features: dict,
    rules: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    event_id: str,
    assessment_id: str,
    ml_score: float = 0.0,
    ml_decision: str = "通过",
) -> RiskCheckResponse:
    triggered_rules = [
        RuleHitInfo(
            rule_id=h.rule_id,
            rule_name=h.rule_name,
            rule_category=h.rule_category,
            risk_level=h.risk_level,
            risk_score=h.risk_score,
            action=h.action,
            description=h.description,
        )
        for h in rules
    ]

    features_out = features if settings.RISK_FEATURES_FULL_RETURN else {}

    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=ctx.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(rules),
        triggered_rules=triggered_rules,
        features=features_out,
        create_time=datetime.now(),
        ml_score=ml_score,
        ml_decision=ml_decision,
    )


# ============================================================
# 主函数: 7 步流水线串联
# ============================================================

async def run_risk_check(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckResponse:
    # 1. 准备上下文
    ctx = _build_context(request)
    await _enrich_context(db, ctx)

    # 2. 创建事件记录
    event_id = _create_event_record(db, ctx)

    # 3-4. 计算 + 保存特征快照
    features = await _compute_features(db, ctx)
    _save_feature_snapshot(db, ctx, features)

    # 5. 加载 + 匹配规则
    rules = await _evaluate_rules(db, ctx, features)

    # 6. 算决策
    final_score, risk_level, decision, ml_score, ml_decision = _calculate_decision(rules, features)

    # 7. 落库 + 响应
    await db.flush()
    assessment_id = await _save_assessment(
        db, ctx, rules, final_score, risk_level, decision, ml_score, ml_decision,
    )
    await _maybe_create_case(db, assessment_id, ctx, rules, final_score, decision)
    await _update_user_profile(db, ctx, features, final_score, risk_level)

    await db.commit()

    return _build_response(
        ctx, features, rules, final_score, risk_level, decision, event_id, assessment_id,
        ml_score, ml_decision,
    )


# ============================================================
# Demo: 演练核心评分公式 + 一票否决 + 等级/决策映射
# 跑法: python app/engine/decision.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    from app.engine.rule import RuleHitResult

    def _mock_hit(rid, score, level, action="拒绝"):
        return RuleHitResult(SimpleNamespace(
            rule_id=rid, rule_name=f"规则 {rid}", rule_category="测试",
            risk_score=score, risk_level=level, action=action, description="",
        ))

    print("=" * 60)
    print("教育风控决策引擎 - 核心能力演示 (纯计算)")
    print("=" * 60)

    print("\n[1] 评分 -> 风险等级 / 决策 映射 (4 档)")
    print(f"  {'score':<6} {'level':<6} {'decision':<8}")
    for s in [10, 30, 50, 60, 70, 80, 95, 100]:
        print(f"  {s:<6} {_score_to_level(s):<6} {_score_to_decision(s):<8}")

    print("\n[2] 评分公式: max(规则分) + 3 * (额外命中数), 上限 100")
    cases = [
        ("1 条 R001 刷单 (95分)", [_mock_hit("R001", 95, "极高")]),
        ("3 条 R001+R008+R025",  [_mock_hit("R001", 95, "极高"), _mock_hit("R008", 90, "极高"), _mock_hit("R025", 50, "中")]),
        ("0 条命中", []),
    ]
    for desc, hits in cases:
        s = calculate_final_score(hits)
        print(f"  {desc:<35} -> {s}")

    print("\n[3] 一票否决: 命中 '极高' 规则直接拒绝")
    print(f"  R001(极高) 命中 -> veto={check_veto([_mock_hit('R001', 95, '极高')])}")
    print(f"  R002(高) 命中   -> veto={check_veto([_mock_hit('R002', 80, '高')])}")

    print("\n" + "=" * 60)
    print("教育风控 8 条规则覆盖: 报名欺诈/退费滥用/身份异常/行为异常")

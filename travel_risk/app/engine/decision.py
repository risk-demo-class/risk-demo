"""
旅游风控决策引擎: 串联 7 步流水线, 事件 → 特征 → 规则 → 评分 → 决策 → 持久化.

【评分公式】final_score = min(max(各规则分) + BONUS × (额外命中数), 100)
【双轨融合】final_score = α × rule_score + β × ml_score (α+β=1, .env 可调)
【一票否决】任何 risk_level="极高" 的规则命中 → 强制拒绝, 不被 XGBoost 推翻
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
from app.engine.feature import compute_all_features
from app.engine.ml_model import is_model_loaded, predict
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models import (
    BookingInfo,
    ClaimInfo,
    ComplaintInfo,
    PaymentInfo,
    RefundChange,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

logger = logging.getLogger(__name__)


# ============================================================
# 工具函数 (纯计算, 无副作用, 易测试)
# ============================================================

def _generate_id(prefix: str = "") -> str:
    """生成带前缀的有序唯一 ID."""
    return f"{prefix}{ulid.new().str.lower()}"


def _score_to_level(score: int, event_type: str = "通用") -> str:
    """评分 → 风险等级. 阈值按 event_type 拆."""
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
    """评分 → 决策动作. 4 档: 通过 / 标记 / 人工审核 / 拒绝."""
    th = settings.get_event_thresholds(event_type)
    if score < th["pass"]:
        return "通过"
    elif score < th["mark"]:
        return "标记"
    elif score < th["review"]:
        return "人工审核"
    else:
        return "拒绝"


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    """核心评分公式: max(各规则分) + BONUS × (额外命中数), 上限 100."""
    if not hits:
        return 0
    max_score = max(h.risk_score for h in hits)
    extra_count = len(hits) - 1
    bonus = settings.RISK_MULTI_RULE_BONUS * extra_count
    return min(max_score + bonus, 100)


def check_veto(hits: list[RuleHitResult]) -> bool:
    """一票否决: 任意 1 条 risk_level="极高" 就 True, 短路返回."""
    return any(h.risk_level == "极高" for h in hits)


def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    """ML P(拒绝) → 0-100 风险分 (sigmoid 风格校准).

    risk_score = 100 * (1 - exp(-k * prob)), k=3
    校准点: 0.1→26, 0.3→59, 0.5→78, 0.7→90, 0.9→97
    """
    if prob <= 0:
        return 0
    if prob >= 1:
        return 100
    return int(round(100 * (1 - math.exp(-k * prob))))


# ============================================================
# 步骤 1: 准备上下文
# ============================================================

@dataclass
class _RiskCheckContext:
    request: RiskCheckRequest
    user_id: str
    booking_id: Optional[str] = None
    device_id: Optional[str] = None
    event_id: str = ""


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    """步骤 1b: 请求 → Context.

    业务规则:
      - "下单" 事件: source_id 就是 booking_id
      - "注册" 事件: source_id 是 user_id, 无订单维度
      - "支付"/"退改申请"/"理赔申请"/"投诉": source_id 是各业务表主键,
        booking_id 由 process_event 的 _enrich_request 预先补全
    """
    booking_id = request.booking_id
    if not booking_id and request.event_type == "下单":
        booking_id = request.source_id
    if not booking_id and request.event_type == "注册":
        booking_id = None
    return _RiskCheckContext(
        request=request,
        user_id=request.user_id,
        booking_id=booking_id,
        device_id=request.device_id,
    )


# ============================================================
# 步骤 2: 创建事件记录
# ============================================================

def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> str:
    """记 risk_event 表, 返回 event_id."""
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
    """步骤 3: 计算 28 个风控特征 (用户/订单/出行人 3 类)."""
    return await compute_all_features(
        db,
        user_id=ctx.user_id,
        booking_id=ctx.booking_id,   # 注册/无订单场景为 None, 只算用户特征
    )


def _classify_feature_entity(feature_name: str) -> tuple[str, str]:
    """特征名前缀 → 实体类型. user_* → 用户, order_* → 订单, 其他 → 出行人"""
    if feature_name.startswith("user_"):
        return "用户", feature_name
    if feature_name.startswith("order_"):
        return "订单", feature_name
    return "出行人", feature_name


def _save_feature_snapshot(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
) -> None:
    """步骤 4: 把 28 个特征落库到 risk_feature (审计回溯)."""
    for fname, fval in features.items():
        entity_type, _ = _classify_feature_entity(fname)
        if entity_type == "用户":
            entity_id = ctx.user_id
        elif entity_type == "订单":
            entity_id = ctx.booking_id or ctx.request.source_id
        else:  # 出行人
            entity_id = ctx.booking_id or ctx.user_id
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
    """步骤 5: 加载 + 匹配规则. "通用" 规则对所有 event_type 生效."""
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)


# ============================================================
# 步骤 6: 计算评分与决策
# ============================================================

def _calculate_decision(
    rules: list[RuleHitResult],
    features: dict,
    event_type: str = "通用",
) -> tuple[int, str, str, float | None, str]:
    """步骤 6: 算评分 + 一票否决 + 双轨融合 + 映射."""
    rule_score = calculate_final_score(rules)

    has_veto = check_veto(rules)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    ml_result = predict(features) if is_model_loaded() else None
    ml_score_100 = _ml_prob_to_risk_score(ml_result.score) if ml_result else 0
    ml_decision = ml_result.decision if ml_result else "通过"

    if ml_result and ml_result.is_loaded:
        final_score = int(round(
            settings.ML_WEIGHT_RULE * rule_score
            + settings.ML_WEIGHT_XGB * ml_score_100
        ))
        final_score = max(0, min(100, final_score))
    else:
        final_score = rule_score

    risk_level = _score_to_level(final_score, event_type)
    decision = _score_to_decision(final_score, event_type)

    # 硬性一票否决: 不被 XGBoost 推翻
    if has_veto:
        decision = "拒绝"
        risk_level = "极高"
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)

    # 模型未加载时 ml_score 返回 None (写库为 NULL), 避免"无模型"被误当成 0 分
    return final_score, risk_level, decision, ml_result.score if ml_result else None, ml_decision


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
    ml_score: float | None = None,
    ml_decision: str = "通过",
) -> str:
    """步骤 7a: 写 risk_assessment, 返回 assessment_id."""
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
    """步骤 7b: 条件建案 (决策是"人工审核"或"拒绝"时才建)."""
    if decision not in ("人工审核", "拒绝"):
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
        logger.info(
            "跳过建案: 已有未结案 case=%s (source_id=%s, event_type=%s)",
            existing, ctx.request.source_id, ctx.request.event_type,
        )
        return

    case_id = _generate_id("cas")
    top_category = Counter(r.rule_category for r in rules).most_common(1)[0][0] if rules else "未知"

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
    """步骤 7c: 更新用户风险画像 (upsert 模式)."""
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == ctx.user_id)
    )).scalar_one_or_none()

    if not profile:
        profile = RiskUserProfile(user_id=ctx.user_id)
        db.add(profile)

    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.total_bookings = int(features.get("user_total_bookings", 0))
    profile.total_refunds = int(features.get("user_refund_change_count", 0))
    total_bookings = features.get("user_total_bookings", 0)
    profile.refund_rate = (
        round(features.get("user_refund_change_count", 0) / total_bookings, 4)
        if total_bookings > 0 else 0
    )
    profile.avg_order_amount = features.get("user_avg_order_amount", 0)
    profile.traveler_count = int(features.get("user_traveler_count", 0))
    profile.complaint_count = int(features.get("user_complaint_count", 0))
    profile.claim_count = int(features.get("user_claim_count", 0))
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
    ml_score: float | None = None,
    ml_decision: str = "通过",
) -> RiskCheckResponse:
    """步骤 7d: 包装成 API 响应."""
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

    # 人类可读消息
    if decision == "拒绝":
        veto_rules = [h for h in rules if h.risk_level == "极高"]
        if veto_rules:
            message = f"触发一票否决: {veto_rules[0].rule_id} {veto_rules[0].rule_name}"
        elif rules:
            message = f"触发 {len(rules)} 条规则, 综合评分 {final_score} 分"
        else:
            message = f"综合评分 {final_score} 分, 触发拒绝"
    elif decision == "人工审核":
        message = f"综合评分 {final_score} 分, 命中 {len(rules)} 条规则, 转人工审核"
    elif decision == "标记":
        message = "标记观察"
    else:
        message = "正常放行"

    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=ctx.user_id,
        event_type=ctx.request.event_type,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(rules),
        triggered_rules=triggered_rules,
        features=features_out,
        create_time=datetime.now(),
        ml_score=ml_score,
        ml_decision=ml_decision,
        message=message,
    )


# ============================================================
# 主函数: 7 步流水线串联
# ============================================================

async def run_risk_check(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckResponse:
    """串流程, 不写业务. 失败任意一步 → 整个事务回滚, 不留脏数据."""
    ctx = _build_context(request)

    event_id = _create_event_record(db, ctx)

    features = await _compute_features(db, ctx)
    _save_feature_snapshot(db, ctx, features)

    rules = await _evaluate_rules(db, ctx, features)

    final_score, risk_level, decision, ml_score, ml_decision = _calculate_decision(
        rules, features, request.event_type,
    )

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
# Demo: 演练核心评分公式 + 一票否决 — 无需 DB
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
    print("旅游决策引擎 — 核心能力 (纯计算)")
    print("=" * 60)

    print("\n[1] 评分 → 风险等级 / 决策 映射 (旅游阈值):")
    for s in [10, 30, 50, 60, 70, 80, 95, 100]:
        print(f"  score={s:<4} level={_score_to_level(s):<4} decision={_score_to_decision(s):<8}")

    print("\n[2] 评分公式: max(规则分) + 3 × (额外命中数), 上限 100")
    for desc, hits in [
        ("1 条命中 [70]", [_mock_hit("R1", 70, "高")]),
        ("3 条命中 [70, 40, 20]", [_mock_hit("R1", 70, "高"), _mock_hit("R2", 40, "中"), _mock_hit("R3", 20, "低")]),
        ("0 条命中", []),
    ]:
        print(f"  {desc:<30} → {calculate_final_score(hits)}")

    print("\n[3] 一票否决 (R002/R007/R011/R017/R027 为极高):")
    print(f"  无极高 = {check_veto([_mock_hit('R1', 70, '高')])}")
    print(f"  含极高 = {check_veto([_mock_hit('R002', 95, '极高')])}")

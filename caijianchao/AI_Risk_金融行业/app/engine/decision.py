"""
金融风控决策引擎: 串联 7 步流水线, 事件 → 特征 → 规则 → 评分 → 决策 → 持久化.

【评分公式】final_score = min(max(各规则分) + BONUS × (额外命中数), 100)
【双轨融合】final_score = α × rule_score + β × ml_score (α+β=1, .env 可调)
【一票否决】任何 risk_level="极高" 的规则命中 → 强制拒绝, 不被 XGBoost 推翻

7 步流水线:
  1. 校验 + 准备上下文 (Context)
  2. 创建事件记录 (risk_event)
  3-4. 计算 + 保存特征快照 (35 维, risk_feature)
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
from app.engine.feature import compute_all_features
from app.engine.ml_model import is_model_loaded, predict
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models import (
    RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskUserProfile,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

logger = logging.getLogger(__name__)


# ============================================================
# 工具函数 (纯计算, 无副作用, 易测试)
# ============================================================

def _generate_id(prefix: str = "") -> str:
    """生成带前缀的有序唯一 ID. 前缀 区分 ID 用途 (evt 事件 / ast 评估 / cas 案件)"""
    return f"{prefix}{ulid.new().str.lower()}"


def _score_to_level(score: int) -> str:
    """评分 → 风险等级. 阈值跟 _score_to_decision 相同, 但 level 是描述性, decision 是操作性"""
    if score < settings.RISK_PASS_THRESHOLD:
        return "低"
    elif score < settings.RISK_MARK_THRESHOLD:
        return "中"
    elif score < settings.RISK_REVIEW_THRESHOLD:
        return "高"
    else:
        return "极高"


def _score_to_decision(score: int) -> str:
    """评分 → 决策动作. 4 档: 通过 / 标记 / 人工审核 / 拒绝."""
    if score < settings.RISK_PASS_THRESHOLD:
        return "通过"
    elif score < settings.RISK_MARK_THRESHOLD:
        return "标记"
    elif score < settings.RISK_REVIEW_THRESHOLD:
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


# ============================================================
# 步骤 1: 准备上下文
# ============================================================

@dataclass
class _RiskCheckContext:
    request: RiskCheckRequest
    user_id: str
    account_id: Optional[str] = None
    loan_id: Optional[str] = None
    event_id: str = ""


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    """步骤 1b: 请求 → Context, 补全 account_id.

    金融场景:
      - "交易" / "转账" / "取现" 事件: source_id 就是 txn_id, account_id 从 request 传
      - "贷款申请" 事件: source_id 是 loan_id
      - "账户变更" / "登录" 事件: source_id 是 op_id / login_id
      - "反洗钱预警" 事件: source_id 是 report_id
    """
    account_id = request.account_id
    loan_id = request.loan_id
    if not loan_id and request.event_type == "贷款申请":
        loan_id = request.source_id
    return _RiskCheckContext(
        request=request,
        user_id=request.user_id,
        account_id=account_id,
        loan_id=loan_id,
    )


# ============================================================
# 步骤 2: 创建事件记录
# ============================================================

def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> str:
    """记 risk_event 表, 返回 event_id (后续 3 张表 FK 引用)"""
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
    """步骤 3: 调 feature.py 计算 40 维金融风控特征 (事件/账户/信贷/行为 4 类)"""
    return await compute_all_features(
        db,
        account_id=ctx.account_id or ctx.user_id,
        event_data=ctx.request.event_data,
    )


# 事件级/账户统计特征名集合 (用于实体分类)
_EVENT_ACCOUNT_FEATURES = {
    "txn_amount", "channel_type", "is_counter", "hour", "operation_interval_sec",
    "country_code", "from_account_type", "to_account_type", "device_env", "loan_purpose",
    "daily_cash_total", "daily_transfer_count", "daily_fail_count", "last_txn_days",
    "is_first_large", "large_incoming_count", "per_txn_amount", "total_in_amount",
    "hold_minutes", "device_account_count", "txn_count_30d_to_new", "counterparty_reg_days",
}
# 信贷特征名集合
_CREDIT_FEATURES = {
    "credit_inquiry_3m", "credit_usage_rate", "duration_months",
    "loan_to_income_ratio", "overdue_days", "overdue_amount",
    "unsettled_lender_count", "is_approved",
}


def _classify_feature_entity(feature_name: str) -> tuple[str, str]:
    """特征名 → 实体类型. 事件/账户统计 → 账户, credit_* → 信贷, beh_* → 行为"""
    if feature_name in _CREDIT_FEATURES:
        return "信贷", feature_name
    if feature_name.startswith("beh_"):
        return "行为", feature_name
    return "账户", feature_name


def _save_feature_snapshot(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
) -> None:
    """步骤 4: 把 35 个特征落库到 risk_feature (审计回溯).

    entity_id 填充规则 (按 entity_type):
      - 账户特征 → ctx.account_id (缺失用 user_id 顶替)
      - 信贷特征 → ctx.loan_id (缺失用 user_id 顶替)
      - 行为特征 → ctx.user_id
    """
    for fname, fval in features.items():
        entity_type, _ = _classify_feature_entity(fname)
        if entity_type == "账户":
            entity_id = ctx.account_id or ctx.user_id
        elif entity_type == "信贷":
            entity_id = ctx.loan_id or ctx.user_id
        else:  # 行为
            entity_id = ctx.user_id
        # 字符串特征 (channel_type/country_code/from_account_type/to_account_type/
        # device_env/loan_purpose 等) 写入 feature_value_str, 数值写入 feature_value
        if isinstance(fval, str):
            db.add(RiskFeature(
                event_id=ctx.event_id,
                entity_type=entity_type,
                entity_id=entity_id,
                feature_name=fname,
                feature_value_str=fval,
            ))
        else:
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
    """步骤 5: 加载 + 匹配规则. "通用" 规则对所有 event_type 生效"""
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)


# ============================================================
# 步骤 6: 计算评分与决策
# ============================================================


def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    """ML P(拒绝) → 0-100 风险分 (sigmoid 风格校准)."""
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
    # 基础评分
    rule_score = calculate_final_score(rules)

    has_veto = check_veto(rules)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    # XGBoost 推理
    ml_result = predict(features) if is_model_loaded() else None
    ml_score_100 = _ml_prob_to_risk_score(ml_result.score) if ml_result else 0
    ml_decision = ml_result.decision if ml_result else "通过"

    # 双轨融合 (加权平均, 截到 [0, 100])
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

    # 去重: 同一 (source_id, event_type) + 未结案 → skip
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
    """步骤 7c: 更新用户风险画像 (upsert 模式).

    金融画像字段与 risk_user_profile 表结构对齐:
    - 交易统计: txn_cnt_30d, txn_amount_30d, avg_txn_amount, daily_fail_count 等
    - 信贷特征: credit_inquiry_3m, credit_usage_rate, loan_to_income_ratio 等
    - 行为特征: last_txn_days, modify_info_7d, device_risk_env 等
    """
    account_id = ctx.account_id or ctx.user_id
    
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.account_id == account_id)
    )).scalar_one_or_none()

    if not profile:
        profile = RiskUserProfile(account_id=account_id)
        db.add(profile)

    # 综合评估
    profile.risk_score = final_score
    profile.risk_level = risk_level

    # 交易统计特征 (从 feature.py 计算的特征映射)
    profile.txn_cnt_30d = int(features.get("daily_transfer_count", 0))
    profile.txn_amount_30d = features.get("total_in_amount", 0)
    profile.avg_txn_amount = features.get("per_txn_amount", 0)
    profile.daily_fail_count = int(features.get("daily_fail_count", 0))
    profile.device_account_count = int(features.get("device_account_count", 0))
    profile.last_txn_days = int(features.get("last_txn_days", 9999))

    # 信贷特征
    profile.credit_inquiry_3m = int(features.get("credit_inquiry_3m", 0))
    profile.credit_usage_rate = features.get("credit_usage_rate", 0)
    profile.unsettled_lender_count = int(features.get("unsettled_lender_count", 0))
    profile.loan_to_income_ratio = features.get("loan_to_income_ratio", 0)
    profile.has_overdue_30d = 1 if features.get("overdue_days", 0) >= 30 else 0

    # 行为特征
    profile.modify_info_7d = int(features.get("beh_info_change_count_30d", 0))
    profile.address_change_3m = int(features.get("beh_address_change_count_30d", 0))
    profile.device_risk_env = features.get("device_env", "正常")
    profile.is_new_user = 1 if features.get("counterparty_reg_days", 999) < 30 else 0
    profile.is_high_net_worth = 1 if features.get("total_in_amount", 0) >= 1000000 else 0
    profile.is_sleeping = 1 if features.get("last_txn_days", 0) >= 90 else 0


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
    """串流程, 不写业务. 失败任意一步 → 整个事务回滚, 不留脏数据."""
    # 1. 准备上下文
    ctx = _build_context(request)

    # 2. 创建事件记录
    event_id = _create_event_record(db, ctx)

    # 3-4. 计算 + 保存特征快照
    features = await _compute_features(db, ctx)
    _save_feature_snapshot(db, ctx, features)

    # 5. 加载 + 匹配规则
    rules = await _evaluate_rules(db, ctx, features)

    # 6. 算决策 (含一票否决 + 双轨融合)
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

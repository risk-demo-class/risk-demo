"""
电信风控决策引擎: 串联 7 步流水线, 事件 → 特征 → 规则 → 评分 → 决策 → 持久化.

参照 ai_risk/app/engine/decision.py, 适配电信业务 (msisdn 为核心枢纽, 替代 user_id).

【评分公式】final_score = min(max(各规则分) + BONUS × (额外命中数), 100)
【双轨融合】final_score = α × rule_score + β × ml_score (α+β=1, .env 可调)
【一票否决】任何 risk_level="极高" 的规则命中 → 强制关停号码, 不被 XGBoost 推翻

7 步流水线:
  1. 校验 + 准备上下文 (Context)
  2. 创建事件记录 (telecom_risk_event)
  3-4. 计算 + 保存特征快照 (25 维, telecom_risk_feature)
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
from app.models_risk import (
    TelecomCardProfile, TelecomRiskAssessment, TelecomRiskCase,
    TelecomRiskEvent, TelecomRiskFeature,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

logger = logging.getLogger(__name__)


# ============================================================
# 工具函数 (纯计算, 无副作用, 易测试)
# ============================================================

def _generate_id(prefix: str = "") -> str:
    """生成带前缀的有序唯一 ID. 前缀区分 ID 用途 (evt/ast/cas)."""
    return f"{prefix}{ulid.new().str.lower()}"


def _score_to_level(score: int, event_type: str = "通用") -> str:
    """评分 → 风险等级. 阈值按 event_type 拆, 找不到 fallback 全局默认.

    电信场景国际来电最严 (反诈法第16条), 开户次之.
    """
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
    """评分 → 决策动作. 4 档: 通过 / 标记 / 人工审核 / 关停号码.

    电信场景"拒绝"统一用"关停号码" (语义更贴近业务, 反诈法第13条).
    """
    th = settings.get_event_thresholds(event_type)
    if score < th["pass"]:
        return "通过"
    elif score < th["mark"]:
        return "标记"
    elif score < th["review"]:
        return "人工审核"
    else:
        return "关停号码"


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    """核心评分公式: max(各规则分) + BONUS × (额外命中数), 上限 100.

    4 个例子:
        1 条命中 [70]          → 70 + 0 = 70
        3 条命中 [70, 40, 20]  → 70 + 2×3 = 76
        3 条命中 [95, 80, 70]  → 95 + 2×3 = 101 → 100
        0 条命中 []            → 0
    """
    if not hits:
        return 0
    max_score = max(h.risk_score for h in hits)
    extra_count = len(hits) - 1
    bonus = settings.RISK_MULTI_RULE_BONUS * extra_count
    return min(max_score + bonus, 100)


def check_veto(hits: list[RuleHitResult]) -> bool:
    """一票否决: 任意 1 条 risk_level="极高" 就 True, 短路返回.

    电信"极高"规则: R002 GOIP固定点位 / R003 猫池一机多卡 / R005 国际诈骗来电.
    """
    return any(h.risk_level == "极高" for h in hits)


# ============================================================
# 步骤 1: 准备上下文 (校验由 process_event 在调 run_risk_check 前完成)
# ============================================================

@dataclass
class _RiskCheckContext:
    """流水线共用的中间数据 (Context Object Pattern)."""
    request: RiskCheckRequest
    msisdn: str
    event_id: str = ""


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    """步骤 1: 请求 → Context. 电信场景核心枢纽就是 msisdn."""
    return _RiskCheckContext(
        request=request,
        msisdn=request.msisdn,
    )


# ============================================================
# 步骤 2: 创建事件记录
# ============================================================

def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> str:
    """记 telecom_risk_event 表, 返回 event_id (后续 3 张表 FK 引用)."""
    ctx.event_id = _generate_id("evt")
    event = TelecomRiskEvent(
        event_id=ctx.event_id,
        event_type=ctx.request.event_type,
        event_source_id=ctx.request.source_id,
        msisdn=ctx.msisdn,
        event_data=json.dumps(ctx.request.event_data or {}, ensure_ascii=False),
    )
    db.add(event)
    return ctx.event_id


# ============================================================
# 步骤 3-4: 计算特征 + 保存特征快照
# ============================================================

async def _compute_features(db: AsyncSession, ctx: _RiskCheckContext) -> dict:
    """步骤 3: 调 feature.py 计算 25 维电信风控特征 (号卡为枢纽)."""
    return await compute_all_features(db, ctx.msisdn)


# 特征名前缀 → 实体类型 (号卡/客户/设备/渠道/物联网)
def _classify_feature_entity(feature_name: str) -> tuple[str, str]:
    """特征名前缀 → 实体类型. 用于 feature 快照落库的 entity_id 填充."""
    if feature_name.startswith("card_"):
        return "号卡", feature_name
    if feature_name.startswith("cust_"):
        return "客户", feature_name
    if feature_name.startswith("cdr_"):
        return "号卡", feature_name
    if feature_name.startswith("dev_"):
        return "设备", feature_name
    if feature_name.startswith("channel_"):
        return "渠道", feature_name
    if feature_name.startswith("iot_"):
        return "物联网", feature_name
    return "号卡", feature_name


def _save_feature_snapshot(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
) -> None:
    """步骤 4: 把 25 个特征落库到 telecom_risk_feature (审计回溯 + 训练取数).

    entity_id 填 msisdn (号卡是核心枢纽, 所有特征都归属到号卡).
    """
    for fname, fval in features.items():
        entity_type, _ = _classify_feature_entity(fname)
        db.add(TelecomRiskFeature(
            event_id=ctx.event_id,
            entity_type=entity_type,
            entity_id=ctx.msisdn,
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
    """步骤 5: 加载 + 匹配规则. "通用"规则对所有 event_type 生效."""
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)


# ============================================================
# 步骤 6: 计算评分与决策
# ============================================================

def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    """ML P(高风险) → 0-100 风险分 (sigmoid 风格校准).

    校准公式: risk_score = 100 * (1 - exp(-k * prob)), k=3
    物理意义: 指数饱和函数, 低概率压低 (避免误报), 高概率推高 (强化高风险信号).

    校准点 (k=3):
      prob=0.0 → 0   / 0.1 → 26 / 0.3 → 59 / 0.5 → 78
      prob=0.7 → 90  / 0.9 → 97 / 1.0 → 100
    """
    if prob <= 0:
        return 0
    if prob >= 1:
        return 100
    return int(round(100 * (1 - math.exp(-k * prob))))


def _calculate_decision(
    rules: list[RuleHitResult],
    features: dict,
    event_type: str = "通用",
) -> tuple[int, str, str, float, str]:
    """步骤 6: 算评分 + 一票否决 + 双轨融合 + 映射.

    双轨融合公式:
        rule_score = 0-100 整数 (max+bonus)
        ml_score   = 0-100 整数 (XGBoost P(高风险) sigmoid 校准)
        final_score = α × rule_score + β × ml_score

    一票否决双保险: 融合后再判一次 veto, 强制 decision="关停号码" + level="极高",
        final_score 抬到 RISK_VETO_MIN_SCORE, 不被 ML 推翻.
    """
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
        # XGBoost 没启用, 走纯规则
        final_score = rule_score

    risk_level = _score_to_level(final_score, event_type)
    decision = _score_to_decision(final_score, event_type)

    # 硬性一票否决: 不被 XGBoost 推翻
    if has_veto:
        decision = "关停号码"
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
    """步骤 7a: 写 telecom_risk_assessment, 返回 assessment_id."""
    assessment_id = _generate_id("ast")
    rule_results_json = json.dumps(
        [h.to_dict() for h in rules], ensure_ascii=False,
    )
    db.add(TelecomRiskAssessment(
        assessment_id=assessment_id,
        event_id=ctx.event_id,
        msisdn=ctx.msisdn,
        rule_results=rule_results_json,
        rule_count=len(rules),
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        ml_score=ml_score,
        ml_decision=ml_decision,
    ))
    return assessment_id


# 条件建案: 决策是"人工审核"或"关停号码"时才建 (通过/标记不留底)
async def _maybe_create_case(
    db: AsyncSession,
    assessment_id: str,
    ctx: _RiskCheckContext,
    rules: list[RuleHitResult],
    final_score: int,
    decision: str,
) -> None:
    """步骤 7b: 条件建案 (决策是"人工审核"或"关停号码"时才建)."""
    if decision not in ("人工审核", "关停号码"):
        return

    # 去重: 同一 (source_id, event_type) + 未结案 → skip
    open_statuses = ("待审核", "审核中")
    existing = (await db.execute(
        select(TelecomRiskCase.case_id).where(
            TelecomRiskCase.source_id == ctx.request.source_id,
            TelecomRiskCase.event_type == ctx.request.event_type,
            TelecomRiskCase.case_status.in_(open_statuses),
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

    # 自动关停的案件直接关案; 人工审核的才走待审核
    is_auto_halt = decision == "关停号码"
    initial_status = "已关停" if is_auto_halt else "待审核"

    case_kwargs = dict(
        case_id=case_id,
        assessment_id=assessment_id,
        msisdn=ctx.msisdn,
        case_status=initial_status,
        case_category=top_category,
        risk_detail=json.dumps([h.to_dict() for h in rules], ensure_ascii=False),
        source_id=ctx.request.source_id,
        event_type=ctx.request.event_type,
    )
    if is_auto_halt:
        case_kwargs.update(
            reviewer="system",
            review_time=datetime.now(),
            review_comment=f"系统自动关停 (final_score={final_score}, {len(rules)} 条规则命中)",
        )

    db.add(TelecomRiskCase(**case_kwargs))
    logger.info(
        "创建案件: %s, source_id=%s, event_type=%s, 决策=%s, 分值=%d, 状态=%s",
        case_id, ctx.request.source_id, ctx.request.event_type, decision, final_score, initial_status,
    )


async def _update_card_profile(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
    final_score: int,
    risk_level: str,
) -> None:
    """步骤 7c: 更新号卡风险画像 (upsert: 有则更新, 无则插入)."""
    profile = (await db.execute(
        select(TelecomCardProfile).where(TelecomCardProfile.msisdn == ctx.msisdn)
    )).scalar_one_or_none()

    if not profile:
        profile = TelecomCardProfile(msisdn=ctx.msisdn)
        db.add(profile)

    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.assessment_count = (profile.assessment_count or 0) + 1
    profile.last_assessment_time = datetime.now()
    # 扩展画像: 存最近 5 个关键特征 (JSON, 前端可展示)
    key_features = {
        k: features.get(k, 0) for k in (
            "card_age_days", "cust_card_count", "cdr_out_count_1h",
            "dev_cards_on_imei", "cdr_intl_incoming_24h",
        ) if k in features
    }
    profile.profile_data = json.dumps(key_features, ensure_ascii=False)


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
    """步骤 7d: 包装成 API 响应 (Pydantic 模型)."""
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
    if rules and any(h.risk_level == "极高" for h in rules):
        veto_names = [h.rule_name for h in rules if h.risk_level == "极高"]
        message = f"触发一票否决: {', '.join(veto_names)}"
    elif decision == "通过":
        message = "正常放行"
    elif decision == "标记":
        message = "标记观察"
    else:
        message = f"命中 {len(rules)} 条规则, 决策={decision}"

    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        msisdn=ctx.msisdn,
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
    """串流程, 不写业务. 失败任意一步 → 整个事务回滚, 不留脏数据.

    入口校验在 process_event 第 1 步已完成, run_risk_check 不再重复.
    """
    # 1. 准备上下文 (校验已在 process_event 完成, 不重复)
    ctx = _build_context(request)

    # 2. 创建事件记录
    event_id = _create_event_record(db, ctx)

    # 3-4. 计算 + 保存特征快照
    features = await _compute_features(db, ctx)
    _save_feature_snapshot(db, ctx, features)

    # 5. 加载 + 匹配规则
    rules = await _evaluate_rules(db, ctx, features)

    # 6. 算决策 (含一票否决 + 双轨融合)
    final_score, risk_level, decision, ml_score, ml_decision = _calculate_decision(
        rules, features, request.event_type,
    )

    # 7. 落库 + 响应
    # flush 发 SQL 但不 commit, 让 event_id 落库可被 FK 引用
    await db.flush()
    assessment_id = await _save_assessment(
        db, ctx, rules, final_score, risk_level, decision, ml_score, ml_decision,
    )
    await _maybe_create_case(db, assessment_id, ctx, rules, final_score, decision)
    await _update_card_profile(db, ctx, features, final_score, risk_level)

    # 提交事务 (一次性写 4-5 张表, 原子性)
    await db.commit()

    return _build_response(
        ctx, features, rules, final_score, risk_level, decision, event_id, assessment_id,
        ml_score, ml_decision,
    )


# ============================================================
# Demo: 演练核心评分公式 + 一票否决 + 等级/决策映射 — 无需 DB
# 跑法: python app/engine/decision.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    from app.engine.rule import RuleHitResult

    def _mock_hit(rid, score, level, action="关停号码"):
        return RuleHitResult(SimpleNamespace(
            rule_id=rid, rule_name=f"规则 {rid}", rule_category="测试",
            risk_score=score, risk_level=level, action=action, description="",
        ))

    print("=" * 60)
    print("电信风控决策引擎 — 4 大核心能力 (纯计算, 无 DB 依赖)")
    print("=" * 60)

    # 1. 评分 → 等级/决策 映射
    print("\n[1] 评分 → 风险等级 / 决策 映射 (通话事件)")
    print(f"  {'score':<6} {'level':<6} {'decision':<10}")
    for s in [10, 30, 50, 60, 70, 80, 95, 100]:
        print(f"  {s:<6} {_score_to_level(s, '通话'):<6} {_score_to_decision(s, '通话'):<10}")

    # 2. 评分公式
    print("\n[2] 评分公式: max(规则分) + 3 × (额外命中数), 上限 100")
    cases = [
        ("1 条命中 [70]",            [_mock_hit("R1", 70, "高")]),
        ("2 条命中 [70, 40]",        [_mock_hit("R1", 70, "高"), _mock_hit("R2", 40, "中")]),
        ("3 条命中 [95, 80, 70]",    [_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高"), _mock_hit("R3", 70, "高")]),
        ("0 条命中 []",              []),
    ]
    for desc, hits in cases:
        print(f"  {desc:<28} → {calculate_final_score(hits)}")

    # 3. 一票否决
    print("\n[3] 一票否决: 任意 1 条 risk_level='极高' 触发 (强制关停号码)")
    cases2 = [
        ("无极高",      [_mock_hit("R1", 70, "高"),  _mock_hit("R2", 80, "高")],  False),
        ("含 1 条极高", [_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高")], True),
    ]
    for desc, hits, expected in cases2:
        got = check_veto(hits)
        mark = "✓" if got == expected else "✗"
        print(f"  {mark} {desc:<20} 期望={expected} 实际={got}")

    # 4. 双轨融合 + 一票否决双保险
    print("\n[4] 决策: 双轨融合 + 一票否决双保险")
    print(f"  {'场景':<30} {'rule_s':<7} {'ml_s':<5} {'final':<6} {'level':<6} {'decision':<10}")
    cases3 = [
        ("R001 高频 (无 veto)",     [_mock_hit("R001", 70, "高")],     0.20),
        ("R002 极高 (有 veto)",     [_mock_hit("R002", 95, "极高")],   0.05),
    ]
    for desc, hits, ml_score in cases3:
        ml_loaded = ml_score is not None
        ml_res = SimpleNamespace(score=ml_score or 0, decision="通过", is_loaded=ml_loaded) if ml_loaded else None
        from app.engine import ml_model
        orig = ml_model.predict
        ml_model.predict = lambda f: ml_res if ml_res else orig(f)
        orig_loaded = ml_model.is_model_loaded
        ml_model.is_model_loaded = lambda: ml_loaded
        try:
            fs, lv, dc, _, _ = _calculate_decision(hits, {}, "通话")
        finally:
            ml_model.predict = orig
            ml_model.is_model_loaded = orig_loaded
        print(f"  {desc:<28} {calculate_final_score(hits):<7} {(ml_score or 0):<5} {fs:<6} {lv:<6} {dc:<10}")

    print("\n" + "=" * 60)
    print("结论: 一票否决 (veto 强制关停 + 抬分到 90) 即使 ML 给低分也无法放行")

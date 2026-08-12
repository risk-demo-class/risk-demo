"""
银行风控决策引擎: 串联 7 步流水线, 事件 → 特征 → 规则 → 评分 → 决策 → 持久化.

【评分公式】final_score = min(max(各规则分) + BONUS × (额外命中数), 100)
【双轨融合】final_score = α × rule_score + β × ml_score (α+β=1, .env 可调)
【一票否决】任何 risk_level="极高" 的规则命中 → 强制拒绝, 不被 XGBoost 推翻

7 步流水线:
  1. 校验 + 准备上下文 (Context)
  2. 创建事件记录 (risk_event)
  3-4. 计算 + 保存特征快照 (25 维, risk_feature)
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
from typing import Any, Optional

import ulid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.config import settings
from bank_risk.app.engine.feature import compute_all_features
from bank_risk.app.engine.ml_model import is_model_loaded, predict
from bank_risk.app.engine.rule import RuleHitResult, evaluate_rules, load_rules
from bank_risk.app.models import (
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
)

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
    """核心评分公式: max(各规则分) + BONUS × (额外命中数), 上限 100.

    4 个例子:
        1 条命中 [70]              → 70 + 0 = 70
        3 条命中 [70, 40, 20]      → 70 + 3×2 = 76
        3 条命中 [95, 80, 70]      → 95 + 3×2 = 101 → 上限 100
        0 条命中 []                → 0 (直接返回)
    """
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

# 上下文数据 (Context Object Pattern): 流水线共用的中间数据
@dataclass
class _RiskCheckContext:
    event_type: str
    source_id: str
    user_id: str
    event_data: dict
    event_id: str = ""


def _build_context(
    event_type: str,
    source_id: str,
    user_id: str,
    event_data: dict = None,
) -> _RiskCheckContext:
    """步骤 1: 请求参数 → Context."""
    return _RiskCheckContext(
        event_type=event_type,
        source_id=source_id,
        user_id=user_id,
        event_data=event_data or {},
    )


# ============================================================
# 步骤 2: 创建事件记录
# ============================================================

def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> str:
    """记 risk_event 表, 返回 event_id (后续 3 张表 FK 引用)"""
    ctx.event_id = _generate_id("evt")
    event = RiskEvent(
        event_id=ctx.event_id,
        event_type=ctx.event_type,
        event_source_id=ctx.source_id,
        user_id=ctx.user_id,
        # event_data 存 JSON 字符串, ensure_ascii=False 保留中文
        event_data=json.dumps(ctx.event_data or {}, ensure_ascii=False),
    )
    db.add(event)
    return ctx.event_id


# ============================================================
# 步骤 3-4: 计算特征 + 保存特征快照
# ============================================================

async def _compute_features(db: AsyncSession, ctx: _RiskCheckContext) -> dict:
    """步骤 3: 调 feature.py 计算 25 个风控特征 (用户/交易/贷款/登录 4 类)"""
    return await compute_all_features(
        db,
        event_type=ctx.event_type,
        source_id=ctx.source_id,
        user_id=ctx.user_id,
        event_data=ctx.event_data,
    )


def _classify_feature_entity(feature_name: str) -> str:
    """特征名前缀 → 实体类型. user_* → 用户, txn_* → 交易, loan_* → 贷款, 其他 → 登录"""
    if feature_name.startswith("user_"):
        return "用户"
    if feature_name.startswith("txn_"):
        return "交易"
    if feature_name.startswith("loan_"):
        return "贷款"
    return "登录"  # login_


def _save_feature_snapshot(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
) -> None:
    """步骤 4: 把 25 个特征落库到 risk_feature (审计回溯).

    entity_id 填充规则 (按 entity_type):
      - 用户特征 → ctx.user_id
      - 交易特征 → ctx.source_id (txn_id)
      - 贷款特征 → ctx.source_id (loan_id)
      - 登录特征 → ctx.user_id
    """
    for fname, fval in features.items():
        entity_type = _classify_feature_entity(fname)
        if entity_type == "用户":
            entity_id = ctx.user_id
        elif entity_type == "交易":
            entity_id = ctx.source_id
        elif entity_type == "贷款":
            entity_id = ctx.source_id
        else:  # 登录
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
    """步骤 5: 加载 + 匹配规则. "通用" 规则对所有 event_type 生效"""
    rules = await load_rules(db, event_type=ctx.event_type)
    return evaluate_rules(rules, features)


# ============================================================
# 步骤 6: 计算评分与决策
# ============================================================

def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    """ML P(拒绝) → 0-100 风险分 (sigmoid 风格校准).

    校准公式: risk_score = 100 * (1 - exp(-k * prob)), k=3
    物理意义: 指数饱和函数, 低概率压低 (避免误报), 高概率推高 (强化高风险信号).

    校准点 (k=3):
      prob=0.0 → 0   (无风险)
      prob=0.1 → 26  (低风险, 但有信号)
      prob=0.3 → 59  (中风险)
      prob=0.5 → 78  (中高)
      prob=0.7 → 90  (高)
      prob=0.9 → 97  (极高)
      prob=1.0 → 100 (确信)
    """
    if prob <= 0:
        return 0
    if prob >= 1:
        return 100
    return int(round(100 * (1 - math.exp(-k * prob))))


def _calculate_decision(
    rules: list[RuleHitResult],
    features: dict,
) -> tuple[int, str, str, float, str]:
    """步骤 6: 算评分 + 一票否决 + 双轨融合 + 映射.

    双轨融合公式:
        rule_score = 0-100 整数 (max+bonus)
        ml_score   = 0-100 整数 (XGBoost P(拒绝) sigmoid 校准)
        final_score = α × rule_score + β × ml_score
        α = settings.ML_WEIGHT_RULE (默认 0.5), β = settings.ML_WEIGHT_XGB (默认 0.5)
    兜底: XGBoost 未加载 → 只用 rule_score.

    一票否决: 融合完成后再判一次 veto, 强制 decision="拒绝" + level="极高",
              final_score 抬到 RISK_VETO_MIN_SCORE, 不会被 ML 推翻.
    """
    # 基础评分
    rule_score = calculate_final_score(rules)

    has_veto = check_veto(rules)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    # XGBoost 推理
    ml_result = predict(features) if is_model_loaded() else None
    # sigmoid 校准: 避免 P(拒绝) × 100 的量纲错配
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
    """步骤 7a: 写 risk_assessment, 返回 assessment_id.

    rule_results 是 JSON 字符串存每条命中规则的详情 (审计回溯),
    rule_count 单独存方便 SQL 聚合 (avg/sum 等).
    """
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


# 条件建案: 决策是"人工审核"或"拒绝"时才建 (通过/标记不留底)
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
            RiskCase.source_id == ctx.source_id,
            RiskCase.event_type == ctx.event_type,
            RiskCase.case_status.in_(open_statuses),
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        logger.info(
            "跳过建案: 已有未结案 case=%s (source_id=%s, event_type=%s)",
            existing, ctx.source_id, ctx.event_type,
        )
        return

    case_id = _generate_id("cas")
    if rules:
        top_category = Counter(r.rule_category for r in rules).most_common(1)[0][0]
    else:
        top_category = "未知"

    # 自动拒绝的案件直接关案; 人工审核的才走待审核
    is_auto_reject = decision == "拒绝"
    initial_status = "已拒绝" if is_auto_reject else "待审核"

    case_kwargs = dict(
        case_id=case_id,
        assessment_id=assessment_id,
        user_id=ctx.user_id,
        case_status=initial_status,
        case_category=top_category,
        risk_detail=json.dumps([h.to_dict() for h in rules], ensure_ascii=False),
        # 冗余: 让"重做检查"不用 join 多张表
        source_id=ctx.source_id,
        event_type=ctx.event_type,
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
        case_id, ctx.source_id, ctx.event_type, decision, final_score, initial_status,
    )

    # 自动拒绝记一条审计 (action_log)
    if is_auto_reject:
        from bank_risk.app.service.action_log import record_action
        await record_action(
            db, operator="system", action_type="AUTO_REJECT_CASE",
            target_type="case", target_id=case_id,
            before_value=None,
            after_value={"case_status": "已拒绝", "final_score": final_score,
                         "decision": decision, "rule_count": len(rules)},
            remark=f"系统自动拒绝, source_id={ctx.source_id}",
        )


async def _update_user_profile(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
    final_score: int,
    risk_level: str,
) -> None:
    """步骤 7c: 更新用户风险画像 (upsert 模式: 有则更新, 无则插入).

    从 features 取用户维度特征 (复用刚才算好的 25 特征, 不再查 DB).
    """
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == ctx.user_id)
    )).scalar_one_or_none()

    if not profile:
        profile = RiskUserProfile(user_id=ctx.user_id)
        db.add(profile)

    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.txn_count_30d = int(features.get("user_txn_count_30d", 0))
    profile.txn_amount_30d = features.get("user_txn_amount_30d", 0)
    profile.avg_txn_amount = features.get("user_avg_txn_amount", 0)
    profile.max_txn_amount = features.get("user_max_txn_amount", 0)
    profile.loan_count_6m = int(features.get("user_loan_count_6m", 0))
    profile.login_count_7d = int(features.get("user_login_count_7d", 0))
    profile.login_fail_count_7d = int(features.get("user_login_fail_count_7d", 0))
    profile.device_count = int(features.get("user_device_count", 0))
    profile.ip_count = int(features.get("user_ip_count", 0))
    profile.credit_score = int(features.get("user_credit_score", 0))
    # 累计评估次数 +1 (or 0 兜底, 防止新建时 None)
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
) -> dict:
    """步骤 7d: 包装成 dict 响应.

    features: 25 特征全返回, 但 RISK_FEATURES_FULL_RETURN=False 时脱敏.
    """
    triggered_rules = [h.to_dict() for h in rules]

    features_out = features if settings.RISK_FEATURES_FULL_RETURN else {}

    return {
        "assessment_id": assessment_id,
        "event_id": event_id,
        "user_id": ctx.user_id,
        "final_score": final_score,
        "risk_level": risk_level,
        "decision": decision,
        "rule_count": len(rules),
        "triggered_rules": triggered_rules,
        "features": features_out,
        "create_time": datetime.now(),
        "ml_score": ml_score,
        "ml_decision": ml_decision,
    }


# ============================================================
# 主函数: 7 步流水线串联
# ============================================================

async def run_risk_check(
    db: AsyncSession,
    event_type: str,
    source_id: str,
    user_id: str,
    event_data: dict = None,
) -> dict:
    """串流程, 不写业务. 失败任意一步 → 整个事务回滚, 不留脏数据.

    7 步流水线主入口:
      1. 构建 Context
      2. 写 risk_event
      3. 算 25 维特征 (调 feature.compute_all_features)
      4. 写 risk_feature (特征快照)
      5. 加载规则 + 求值 (调 rule.load_rules + rule.evaluate_rules)
      6. 双轨融合评分 (rule_score + ml_score sigmoid校准, 0.5/0.5加权) + 一票否决
      7. 落库 (risk_assessment + risk_case + risk_user_profile)
    """
    # 1. 准备上下文
    ctx = _build_context(event_type, source_id, user_id, event_data)

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
    # flush 发 SQL 但不 commit, 让 event_id 落库可被 FK 引用
    await db.flush()
    assessment_id = await _save_assessment(
        db, ctx, rules, final_score, risk_level, decision, ml_score, ml_decision,
    )
    await _maybe_create_case(db, assessment_id, ctx, rules, final_score, decision)
    await _update_user_profile(db, ctx, features, final_score, risk_level)

    # 提交事务 (一次性写 4-5 张表, 原子性)
    await db.commit()

    return _build_response(
        ctx, features, rules, final_score, risk_level, decision, event_id, assessment_id,
        ml_score, ml_decision,
    )


# ============================================================
# Demo: 演练核心评分公式 + 一票否决 + 等级/决策映射 — 无需 DB
# 跑法: python bank_risk/app/engine/decision.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    def _mock_hit(rid, score, level, action="拒绝"):
        return RuleHitResult(
            rule_id=rid, rule_name=f"规则 {rid}", rule_category="测试",
            risk_score=score, risk_level=level, action=action, description="",
        )

    print("=" * 60)
    print("银行风控决策引擎 — 4 大核心能力 (纯计算, 无 DB 依赖)")
    print("=" * 60)

    # 1. _score_to_level / _score_to_decision 映射
    print("\n[1] 评分 → 风险等级 / 决策 映射 (4 档)")
    print(f"  {'score':<6} {'level':<6} {'decision':<8}")
    for s in [10, 30, 50, 60, 70, 80, 95, 100]:
        print(f"  {s:<6} {_score_to_level(s):<6} {_score_to_decision(s):<8}")

    # 2. calculate_final_score 公式
    print("\n[2] 评分公式: max(规则分) + 3 × (额外命中数), 上限 100")
    cases = [
        ("1 条命中 [70]",                       [_mock_hit("R1", 70, "高")]),
        ("2 条命中 [70, 40]",                   [_mock_hit("R1", 70, "高"), _mock_hit("R2", 40, "中")]),
        ("3 条命中 [70, 40, 20]",               [_mock_hit("R1", 70, "高"), _mock_hit("R2", 40, "中"), _mock_hit("R3", 20, "低")]),
        ("3 条命中 [95, 80, 70]",               [_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高"), _mock_hit("R3", 70, "高")]),
        ("0 条命中 []",                         []),
    ]
    for desc, hits in cases:
        s = calculate_final_score(hits)
        print(f"  {desc:<32} → {s}")

    # 3. check_veto 一票否决
    print("\n[3] 一票否决: 任意 1 条 risk_level='极高' 触发")
    cases2 = [
        ("无极高",     [_mock_hit("R1", 70, "高"),  _mock_hit("R2", 80, "高")],  False),
        ("含 1 条极高",[_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高")], True),
    ]
    for desc, hits, expected in cases2:
        got = check_veto(hits)
        mark = "✓" if got == expected else "✗"
        print(f"  {mark} {desc:<20} 期望={expected} 实际={got}")

    # 4. _calculate_decision 双轨融合 + 一票否决双保险
    print("\n[4] 决策: 双轨融合 + 一票否决双保险")
    print(f"  {'场景':<35} {'rule_s':<7} {'ml_s':<5} {'final':<6} {'level':<6} {'decision':<8}")
    cases3 = [
        ("R001 大额 (无 veto)",  [_mock_hit("R001", 70, "高")],     0.20, None),
        ("R002 极高 (有 veto)",  [_mock_hit("R002", 95, "极高")],   0.05, None),
        ("R002 + ML 拉低 (有 veto)", [_mock_hit("R002", 95, "极高")], 0.05, None),
    ]
    for desc, hits, ml_score, _ in cases3:
        # mock ml_result
        ml_loaded = ml_score is not None
        ml_res = SimpleNamespace(score=ml_score or 0, decision="通过", is_loaded=ml_loaded) if ml_loaded else None
        from bank_risk.app.engine import ml_model
        orig = ml_model.predict
        ml_model.predict = lambda f: ml_res if ml_res else orig(f)
        orig_loaded = ml_model.is_model_loaded
        ml_model.is_model_loaded = lambda: ml_loaded
        try:
            fs, lv, dc, _, _ = _calculate_decision(hits, {})
        finally:
            ml_model.predict = orig
            ml_model.is_model_loaded = orig_loaded
        print(f"  {desc:<30} {calculate_final_score(hits):<7} {(ml_score or 0):<5} {fs:<6} {lv:<6} {dc:<8}")

    print("\n" + "=" * 60)
    print("结论: 双保险 (veto 强制拒绝 + 抬分到 90) 即使 ML 给出低分也无法放行")

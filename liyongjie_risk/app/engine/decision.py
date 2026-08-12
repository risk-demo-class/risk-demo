"""
银行风控系统 - 风控决策引擎
==========================
串联 7 步流水线: 事件接入 → 特征计算 → 规则匹配 → 评分 → 决策 → 持久化 → 响应.

【决策链路 (PRD 第 8 节)】
  1. 事件接入与标准化
  2. 名单快速命中 (区分本人/对手方维度)
  3. 规则引擎 (窗口聚合计算)
  4. 模型评分 (XGBoost 申请反欺诈分/交易行为分/团伙分)
  5. 综合决策
  6. 处置执行
  7. 异步落库、画像更新、名单联动、审计留痕

【决策优先级】
  名单命中 > 极高风险规则 > 高风险规则 > 模型分档
  低风险默认放行并记录.

【评分公式】
  rule_score = max(规则分) + BONUS(3) × (额外命中数), 上限 100
  ml_score_100 = sigmoid_calibrate(P(拒绝)), k=3
  final_score  = α × rule_score + β × ml_score_100   (双轨融合)
  一票否决: 任意 risk_level=4 (极高) 的规则命中 → 强制拒绝, 最低分 90

【7 步流水线】
  1. 准备上下文 + 实体补全
  2. 创建风险事件记录 (risk_event)
  3. 计算 30 维特征 (feature.py)
  4. 加载 + 匹配规则 (rule.py)
  5. 计算评分与决策 (含一票否决 + 双轨融合)
  6. 落库 (risk_event + 更新画像)
  7. 包装响应
"""
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.feature import compute_all_features
from app.engine.ml_model import is_model_loaded, predict, ml_prob_to_risk_score
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models import RiskEvent, UserProfile
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

logger = logging.getLogger(__name__)


# ============================================================
# 工具函数
# ============================================================

def _score_to_level(score: int) -> str:
    if score < settings.RISK_PASS_THRESHOLD:
        return "低"
    elif score < settings.RISK_MARK_THRESHOLD:
        return "中"
    elif score < settings.RISK_REVIEW_THRESHOLD:
        return "高"
    else:
        return "极高"


def _score_to_decision(score: int) -> str:
    """评分 → 决策动作 (PRD: PASS/CHALLENGE/MANUAL/REJECT)"""
    if score < settings.RISK_PASS_THRESHOLD:
        return "PASS"
    elif score < settings.RISK_MARK_THRESHOLD:
        return "CHALLENGE"
    elif score < settings.RISK_REVIEW_THRESHOLD:
        return "MANUAL"
    else:
        return "REJECT"


def _score_to_action(score: int, hits: list[RuleHitResult]) -> str | None:
    """根据评分和命中规则确定处置动作"""
    # 取最高风险等级的命中规则的 action
    if hits:
        for h in sorted(hits, key=lambda x: -x.risk_level):
            if h.action:
                return h.action
    if score >= settings.RISK_REVIEW_THRESHOLD:
        return "STOP_PAYMENT"
    elif score >= settings.RISK_MARK_THRESHOLD:
        return "TAG"
    return None


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    """
    规则评分公式: max(各规则分) + BONUS × (额外命中数), 上限 100.

    示例:
      1 条命中 [65]            → 65 + 0 = 65
      3 条命中 [65, 40, 20]    → 65 + 3×2 = 71
      3 条命中 [95, 80, 70]    → 95 + 3×2 = 101 → 上限 100
    """
    if not hits:
        return 0
    max_score = max(h.risk_score() for h in hits)
    extra_count = len(hits) - 1
    bonus = settings.RISK_MULTI_RULE_BONUS * extra_count
    return min(max_score + bonus, 100)


def check_veto(hits: list[RuleHitResult]) -> bool:
    """一票否决: 任意 1 条 risk_level=4 (极高) 就 True"""
    return any(h.risk_level == 4 for h in hits)


# ============================================================
# Context
# ============================================================

@dataclass
class _RiskCheckContext:
    request: RiskCheckRequest
    user_id: int
    device_id: Optional[int] = None
    ip: Optional[str] = None
    geo: Optional[str] = None


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    return _RiskCheckContext(
        request=request,
        user_id=request.user_id,
        device_id=request.device_id,
        ip=request.ip,
        geo=request.geo,
    )


# ============================================================
# 步骤 2: 创建事件记录
# ============================================================

def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> int:
    """记 risk_event 表, 返回 event_id"""
    event = RiskEvent(
        event_type=ctx.request.event_type,
        user_id=ctx.user_id,
        card_id=ctx.request.card_id,
        device_id=ctx.device_id,
        ip=ctx.ip,
        amount=ctx.request.amount,
        decision="PENDING",
        status=1,
    )
    db.add(event)
    return event


# ============================================================
# 步骤 3-4: 特征 + 规则
# ============================================================

async def _compute_features(db: AsyncSession, ctx: _RiskCheckContext) -> dict:
    return await compute_all_features(
        db,
        user_id=ctx.user_id,
        device_id=ctx.device_id,
        ip=ctx.ip,
        geo=ctx.geo,
        amount=ctx.request.amount,
        channel=ctx.request.channel,
        to_bank_code=ctx.request.to_bank_code,
        from_card_id=ctx.request.card_id,
        term_months=ctx.request.term_months,
        monthly_income=ctx.request.monthly_income,
        debt_ratio=ctx.request.debt_ratio,
        credit_query_1m=ctx.request.credit_query_1m,
    )


async def _evaluate_rules(
    db: AsyncSession, ctx: _RiskCheckContext, features: dict,
) -> list[RuleHitResult]:
    # 事件类型 → 场景映射
    event_to_scene = {
        "LOGIN": "登录",
        "TRANSFER": "转账",
        "PAYMENT": "转账",
        "WITHDRAW": "转账",
        "LOAN_APPLY": "贷款",
        "CARD_APPLY": "信用卡",
        "DISBURSE": "贷款",
        "OVERDUE": "贷款",
        "REPAY": "信用卡",
    }
    scene = event_to_scene.get(ctx.request.event_type)
    rules = await load_enabled_rules(db, scene=scene)
    return match_rules(rules, features)


# ============================================================
# 步骤 5: 评分与决策
# ============================================================

def _calculate_decision(
    rules: list[RuleHitResult],
    features: dict,
) -> tuple[int, str, str, float, str, str | None]:
    """
    算评分 + 一票否决 + 双轨融合.

    返回: (final_score, risk_level, decision, ml_score, ml_decision, action)

    双轨融合:
      rule_score = max(规则分) + BONUS × 额外命中数
      ml = XGBoost predict(features) → P(拒绝)
      ml_score_100 = sigmoid_calibrate(ml.score)
      final_score = α × rule_score + β × ml_score_100

    一票否决双保险: 融合完成后, 极高规则命中的 → 强制拒绝+极高, 分不低于 90
    """
    rule_score = calculate_final_score(rules)
    has_veto = check_veto(rules)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    # XGBoost 推理
    ml_result = predict(features) if is_model_loaded() else None
    ml_score_100 = ml_prob_to_risk_score(ml_result.score) if ml_result else 0
    ml_decision = ml_result.decision if ml_result else "PASS"

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

    # 一票否决: 不被 ML 推翻
    if has_veto:
        decision = "REJECT"
        risk_level = "极高"
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)

    action = _score_to_action(final_score, rules)

    return final_score, risk_level, decision, ml_result.score if ml_result else 0.0, ml_decision, action


# ============================================================
# 步骤 6-7: 落库 + 响应
# ============================================================

async def _update_event_and_profile(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    event: RiskEvent,
    rules: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    action: str | None,
    features: dict,
) -> None:
    """更新事件记录 + 画像 upsert"""

    # 更新事件
    event.rule_ids = ",".join([h.rule_id for h in rules]) if rules else None
    event.risk_score = final_score
    event.decision = decision
    event.action = action
    event.status = 2 if decision in ("PASS", "REJECT") else 1

    # 更新画像
    profile = (await db.execute(
        select(UserProfile).where(UserProfile.user_id == ctx.user_id)
    )).scalar_one_or_none()

    if not profile:
        profile = UserProfile(user_id=ctx.user_id)
        db.add(profile)

    profile.common_device_id = ctx.device_id
    profile.avg_txn_amount = features.get("txn_amount", 0)
    profile.txn_freq_day = features.get("user_txn_1h_count", 0) * 24
    profile.profile_at = datetime.now()


def _build_response(
    ctx: _RiskCheckContext,
    features: dict,
    rules: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    event_id: int,
    ml_score: float = 0.0,
    ml_decision: str = "PASS",
    action: str | None = None,
) -> RiskCheckResponse:
    triggered_rules = [
        RuleHitInfo(
            rule_id=h.rule_id,
            rule_name=h.rule_name,
            scene=h.scene,
            risk_level=h.risk_level,
            risk_score=h.risk_score(),
            decision=h.decision,
            action=h.action,
            description=f"规则 {h.rule_id}: {h.rule_name}",
        )
        for h in rules
    ]

    return RiskCheckResponse(
        assessment_id=f"ast_{event_id}",
        event_id=str(event_id),
        user_id=ctx.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(rules),
        triggered_rules=triggered_rules,
        features=features if settings.RISK_FEATURES_FULL_RETURN else {},
        create_time=datetime.now(),
        ml_score=ml_score,
        ml_decision=ml_decision,
        action=action,
    )


# ============================================================
# 主函数: 7 步流水线
# ============================================================

async def run_risk_check(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckResponse:
    """
    银行风控检查 7 步流水线.

    步骤:
      1. 构建上下文
      2. 创建事件记录
      3. 计算 30 维特征
      4. 加载 + 匹配规则
      5. 计算评分与决策 (一票否决 + 双轨融合)
      6. 落库 (事件 + 画像)
      7. 包装响应
    """
    # 1. Context
    ctx = _build_context(request)

    # 2. 事件记录
    event = _create_event_record(db, ctx)
    await db.flush()  # 获取 event_id

    # 3. 特征
    features = await _compute_features(db, ctx)

    # 4. 规则
    rules = await _evaluate_rules(db, ctx, features)

    # 5. 评分决策
    final_score, risk_level, decision, ml_score, ml_decision, action = \
        _calculate_decision(rules, features)

    # 6. 落库
    await _update_event_and_profile(
        db, ctx, event, rules, final_score, risk_level, decision, action, features,
    )
    await db.commit()

    # 7. 响应
    return _build_response(
        ctx, features, rules, final_score, risk_level, decision,
        event.event_id, ml_score, ml_decision, action,
    )


# ============================================================
# Demo: 演练评分公式 + 一票否决 + 双轨融合
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    def _mock_hit(rid, level, scene="转账"):
        return RuleHitResult(SimpleNamespace(
            rule_id=rid, rule_name=f"规则{rid}", scene=scene,
            risk_level=level, decision="REJECT" if level == 4 else "MANUAL",
            action="STOP_PAYMENT" if level == 4 else "TAG",
            priority=1, conditions={},
        ))

    print("=" * 60)
    print("银行风控决策引擎 — 评分公式 + 一票否决 + 双轨融合")
    print("=" * 60)

    # 1. 评分等级映射
    print("\n[1] 评分 → 等级/决策映射:")
    print(f"  {'score':<6} {'level':<6} {'decision':<12}")
    for s in [10, 30, 50, 60, 70, 80, 95, 100]:
        print(f"  {s:<6} {_score_to_level(s):<6} {_score_to_decision(s):<12}")

    # 2. 规则评分公式
    print("\n[2] 评分公式: max(规则分) + 3 × (额外命中数), 上限 100")
    cases = [
        ("1 条 [R001=95]", [_mock_hit("R001", 4)]),
        ("2 条 [R002=70, R005=70]", [_mock_hit("R002", 3), _mock_hit("R005", 3)]),
        ("3 条 [R001=95, R008=95, R010=70]", [_mock_hit("R001", 4), _mock_hit("R008", 4), _mock_hit("R010", 3)]),
    ]
    for desc, hits in cases:
        s = calculate_final_score(hits)
        print(f"  {desc:<35} → {s}")

    # 3. 一票否决
    print("\n[3] 一票否决: risk_level=4 (极高) 触发")
    cases2 = [
        ("无极高", [_mock_hit("R002", 3), _mock_hit("R005", 3)], False),
        ("含极高 R001", [_mock_hit("R001", 4), _mock_hit("R005", 3)], True),
    ]
    for desc, hits, expected in cases2:
        got = check_veto(hits)
        print(f"  {'OK' if got == expected else 'FAIL'} {desc:<25} 期望={expected} 实际={got}")

    print("\n" + "=" * 60)
    print("结论: 一票否决双保险, 即使 ML 给出低分也无法推翻极高规则")

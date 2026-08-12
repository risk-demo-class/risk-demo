"""无 HTTP、无事务的纯决策计算（规则轨道 + ML 双轨融合）。

设计:
  - 规则轨道: 最高命中分 + 多规则 bonus; 决策取命中规则里最严的 action
  - ML 轨道:  XGBoost P(拒绝) 经 sigmoid 校准成 0-100 分; 决策按 ML 阈值
  - 双轨融合: final_score = α×rule + β×ml (α+β=1), 决策取两轨更严
  - 一票否决: 命中 risk_level=极高 的规则 → 强制拒绝, 不被 ML 推翻

纯函数, 不加载模型; 模型由调用方 (service) 通过 predict() 拿到后以 MlResult 传入。
兼容旧调用: calculate_decision(hits) 不带 ml 时, 行为与旧版一致
(最严规则 action、90/70/40 等级、单条命中无 bonus)。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.config import settings
from app.engine.rule import RuleHit

ACTION_RANK = {"通过": 0, "标记": 1, "人工审核": 2, "拒绝": 3}


@dataclass(frozen=True)
class DecisionResult:
    score: int
    risk_level: str
    decision: str
    ml_score: float | None = None      # P(拒绝)
    ml_decision: str | None = None     # ML 轨道决策


def score_to_level(score: int) -> str:
    return "极高" if score >= 90 else "高" if score >= 70 else "中" if score >= 40 else "低"


def calculate_rule_score(hits: list[RuleHit]) -> int:
    """规则轨道分: max(各规则分) + BONUS×(额外命中数), 上限 100。"""
    if not hits:
        return 0
    max_score = max(hit.risk_score for hit in hits)
    bonus = settings.RISK_MULTI_RULE_BONUS * (len(hits) - 1)
    return min(max_score + bonus, 100)


def check_veto(hits: list[RuleHit]) -> bool:
    """一票否决: 任意 1 条 risk_level=极高 就 True, 短路返回。"""
    return any(hit.risk_level == "极高" for hit in hits)


def _strictest_action(actions: list[str]) -> str:
    """取动作等级最严格的一个; 空列表返回 通过。"""
    if not actions:
        return "通过"
    return max(actions, key=ACTION_RANK.__getitem__)


def _ml_prob_to_risk_score(prob: float) -> float:
    """P(拒绝) ∈[0,1] → 0-100 分 (sigmoid 校准, 避免量纲错配)。
    0.1→26, 0.3→59, 0.5→78, 0.7→90, 0.9→97"""
    return 100.0 * (1.0 - math.exp(-3.0 * prob))


def calculate_decision(hits: list[RuleHit], ml=None) -> DecisionResult:
    """双轨决策。ml 为已加载的 MlResult 时做融合, 否则纯规则。

    ml 需含 score(P 拒绝)/decision/is_loaded 三个属性。
    """
    rule_score = calculate_rule_score(hits)
    has_veto = check_veto(hits)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    rule_decision = _strictest_action([hit.action for hit in hits])

    ml_active = ml is not None and ml.is_loaded
    if ml_active:
        ml_score_100 = _ml_prob_to_risk_score(ml.score)
        final_score = int(round(
            settings.ML_WEIGHT_RULE * rule_score + settings.ML_WEIGHT_XGB * ml_score_100
        ))
        final_score = max(0, min(100, final_score))
        decision = _strictest_action([rule_decision, ml.decision])
    else:
        final_score = rule_score
        decision = rule_decision

    risk_level = score_to_level(final_score)

    if has_veto:
        # 硬性一票否决: 不被 ML 推翻
        decision = "拒绝"
        risk_level = "极高"
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)

    return DecisionResult(
        score=final_score, risk_level=risk_level, decision=decision,
        ml_score=ml.score if ml_active else None,
        ml_decision=ml.decision if ml_active else None,
    )


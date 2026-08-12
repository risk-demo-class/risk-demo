"""
决策引擎 — 双轨融合 + 一票否决 + 决策映射
rule_score = min(max(命中规则 risk_score) + 3 × (额外命中数), 100)
ml_score   = XGBoost(特征) × 100
final      = α × rule_score + β × ml_score   (默认 α=β=0.5)
一票否决   = 任意规则 risk_level=="极高" → final = max(final, 90)
"""
import logging

from app.config import settings
from app.engine import ml_model

logger = logging.getLogger(__name__)

HIGHEST_RISK_LEVEL = "极高"


def compute_rule_score(hits: list[dict]) -> float:
    """Step 1: 规则分 = max(risk_score) + 3 × (命中数-1),封顶 100。"""
    if not hits:
        return 0.0
    max_score = max(int(h["risk_score"]) for h in hits)
    extra = 3 * (len(hits) - 1)
    return float(min(max_score + extra, 100))


def compute_ml_score(features: dict) -> float:
    """Step 2: ML 分 = 模型概率 × 100。模型未加载 → 0(降级纯规则)。"""
    result = ml_model.predict(features)
    return result.score


def merge_scores(rule_score: float, ml_score: float) -> float:
    """Step 3: 双轨加权。"""
    alpha = settings.ML_WEIGHT_RULE
    beta = settings.ML_WEIGHT_XGB
    return round(alpha * rule_score + beta * ml_score, 2)


def apply_veto(final_score: float, hits: list[dict]) -> float:
    """Step 4: 一票否决 — 极高规则强制 ≥ 90。"""
    if any(h["risk_level"] == HIGHEST_RISK_LEVEL for h in hits):
        return max(final_score, float(settings.RISK_VETO_MIN_SCORE))
    return final_score


def score_to_level(final_score: float) -> str:
    if final_score < settings.RISK_PASS_THRESHOLD:
        return "低"
    if final_score < settings.RISK_MARK_THRESHOLD:
        return "中"
    if final_score < settings.RISK_REVIEW_THRESHOLD:
        return "高"
    return "极高"


def score_to_decision(final_score: float) -> str:
    """最终决策映射: 通过/标记/人工审核/拒绝"""
    if final_score < settings.RISK_PASS_THRESHOLD:
        return "通过"
    if final_score < settings.RISK_MARK_THRESHOLD:
        return "标记"
    if final_score < settings.RISK_REVIEW_THRESHOLD:
        return "人工审核"
    return "拒绝"


def calculate_decision(hits: list[dict], features: dict) -> dict:
    """
    9 函数编排的入口: 规则分 + ML 分 + 融合 + 一票否决 + 决策映射。
    返回: {rule_score, ml_score, final_score, risk_level, decision, ml_loaded}
    """
    rule_score = compute_rule_score(hits)
    ml_score = compute_ml_score(features)
    final_score = merge_scores(rule_score, ml_score)
    final_score = apply_veto(final_score, hits)

    return {
        "rule_score": rule_score,
        "ml_score": ml_score,
        "final_score": final_score,
        "risk_level": score_to_level(final_score),
        "decision": score_to_decision(final_score),
        "ml_loaded": ml_model.is_model_loaded(),
    }

# -*- coding: utf-8 -*-
"""决策引擎 —— 对应教学宝典《第 8 章：双轨融合 + 一票否决》（decision.py · 9 函数编排）

4 步数学（宝典 8.1）：
    Step 1  rule_score = min(max(各规则 risk_score) + 3 × (额外命中数), 100)
    Step 2  ml_score   = XGBoost(features).predict_proba(拒绝) × 100
    Step 3  final      = α × rule_score + β × ml_score          （默认 α=β=0.5）
    Step 4  if 任意规则 risk_level == "极高": final = max(final, 90)   ← 一票否决

决策映射（宝典 8.2）：
    0-29 低 → 通过 | 30-59 中 → 标记 | 60-79 高 → 人工审核 | 80-100 极高 → 拒绝

4 个设计哲学（宝典 8.4）：
    ① 规则保底：任何"极高"规则不被 ML 推翻
    ② AI 加分：ML 跟规则平等加权
    ③ 可调权重：0.5/0.5 是默认
    ④ 降级优雅：模型未加载 → ML 分 = 0 → 走纯规则
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.engine import ml_model
from app.engine.ml_model import MlResult

logger = logging.getLogger("ai_risk.engine.decision")

EXTRA_HIT_BONUS = 3          # 每多命中 1 条规则 +3 分（宝典 8.1 Step 1）
MAX_SCORE = 100
VETO_LEVEL = "极高"


# ------------------------------------------------------------------ ① 规则分
def calc_rule_score(hits: List[Dict[str, Any]]) -> int:
    """Step 1：最高分 + 3 × 额外命中数，上限 100。

    例（宝典 8.1）：R001(70) + R003(40) → 70 + 3 × 1 = 73
    """
    if not hits:
        return 0
    max_score = max(int(hit.get("risk_score") or 0) for hit in hits)
    extra = len(hits) - 1
    return int(min(max(max_score + EXTRA_HIT_BONUS * extra, 0), MAX_SCORE))


# ------------------------------------------------------------------ ② ML 分
def calc_ml_score(features: Dict[str, float], explain: bool = False) -> MlResult:
    """Step 2：XGBoost 概率 × 100。模型未加载 → score=0（降级，业务永不停）。"""
    result = ml_model.predict(features, explain=explain)
    if not result.is_loaded:
        logger.debug("ML 未参与评分（%s）", result.reason)
    return result


# ------------------------------------------------------------------ ③ 双轨加权
def effective_weights(alpha: Optional[float] = None, beta: Optional[float] = None,
                      ml_loaded: bool = True) -> tuple[float, float]:
    """算出**实际生效**的 α/β。

    ⚠️ 这是全项目最容易踩错的一处，务必看懂：

    宝典 8.4 ④「降级优雅：模型未加载 → ML 分 = 0 → **走纯规则**」。
    如果模型没加载还硬套 `0.5×rule + 0.5×0`，规则分 100 会被腰斩成 50 →
    决策从「拒绝」掉到「标记」，**风控直接失效**（教学环境默认就没有模型文件，
    等于所有人都在用一个瘸腿系统）。

    所以「降级」的正确含义是**权重归一化**：把 β 让出的份额还给 α。
        模型已加载： α=0.5, β=0.5  → final = 0.5×rule + 0.5×ml
        模型未加载： α=1.0, β=0.0  → final = rule            ← 纯规则
    """
    alpha = settings.ML_WEIGHT_RULE if alpha is None else alpha
    beta = settings.ML_WEIGHT_XGB if beta is None else beta
    if ml_loaded:
        return float(alpha), float(beta)
    total = alpha + beta
    # 全部权重归给规则轨（total<=0 属配置异常，兜底为纯规则）
    return (1.0 if total <= 0 else round(total / total, 6)), 0.0


def fuse_scores(rule_score: int, ml_score: float,
                alpha: Optional[float] = None, beta: Optional[float] = None,
                ml_loaded: bool = True) -> float:
    """Step 3：final = α × rule + β × ml（模型未加载时自动归一化为纯规则）。"""
    eff_alpha, eff_beta = effective_weights(alpha, beta, ml_loaded)
    return round(eff_alpha * rule_score + eff_beta * ml_score, 2)


# ------------------------------------------------------------------ ④ 一票否决
def apply_veto(final_score: float, hits: List[Dict[str, Any]]) -> tuple[float, bool]:
    """Step 4：存在"极高"规则 → final = max(final, RISK_VETO_MIN_SCORE)。"""
    veto_hits = [hit for hit in hits if hit.get("risk_level") == VETO_LEVEL]
    if not veto_hits:
        return final_score, False
    forced = max(final_score, float(settings.RISK_VETO_MIN_SCORE))
    logger.info("一票否决触发: %s → final %.2f → %.2f",
                [h["rule_id"] for h in veto_hits], final_score, forced)
    return forced, True


# ------------------------------------------------------------------ ⑤ 分数 → 等级
def score_to_risk_level(score: float) -> str:
    if score < settings.RISK_PASS_THRESHOLD:
        return "低"
    if score < settings.RISK_MARK_THRESHOLD:
        return "中"
    if score < settings.RISK_REVIEW_THRESHOLD:
        return "高"
    return "极高"


# ------------------------------------------------------------------ ⑥ 等级 → 决策
def risk_level_to_decision(risk_level: str) -> str:
    return {"低": "通过", "中": "标记", "高": "人工审核", "极高": "拒绝"}.get(risk_level, "通过")


def score_to_decision(score: float) -> str:
    return risk_level_to_decision(score_to_risk_level(score))


# ------------------------------------------------------------------ ⑦ 是否建案
def need_case(decision: str) -> bool:
    """宝典 9.3 案件创建规则：只有「人工审核 / 拒绝」建案。"""
    return decision in ("人工审核", "拒绝")


# ------------------------------------------------------------------ ⑧ 决策理由
def build_reason(hits: List[Dict[str, Any]], rule_score: int, ml_result: MlResult,
                 final_score: float, is_veto: bool, decision: str,
                 alpha: Optional[float] = None, beta: Optional[float] = None) -> str:
    parts: List[str] = []
    if hits:
        top = hits[:3]
        parts.append("命中规则 " + ", ".join(f"{h['rule_id']}({h['rule_name']}/{h['risk_score']}分)"
                                            for h in top)
                     + (f" 等 {len(hits)} 条" if len(hits) > 3 else ""))
    else:
        parts.append("未命中任何规则")
    parts.append(f"规则分 {rule_score}")
    eff_alpha, eff_beta = effective_weights(alpha, beta, ml_result.is_loaded)
    if ml_result.is_loaded:
        parts.append(f"模型分 {ml_result.score:.1f}（P={ml_result.probability:.4f} → {ml_result.decision}）")
        parts.append(f"融合 {eff_alpha}×规则 + {eff_beta}×模型 = {final_score:.2f}")
    else:
        parts.append("模型未加载 → 权重归一化 α=1.0 / β=0.0，降级为纯规则（宝典 8.4 ④）")
        parts.append(f"融合 = 规则分 {final_score:.2f}")
    if is_veto:
        parts.append(f"存在极高规则触发一票否决 → 强制 ≥ {settings.RISK_VETO_MIN_SCORE}")
    parts.append(f"最终决策 {decision}")
    return "；".join(parts)


# ------------------------------------------------------------------ ⑨ 总编排
def calculate(features: Dict[str, float], hits: List[Dict[str, Any]],
              alpha: Optional[float] = None, beta: Optional[float] = None,
              explain: bool = False) -> Dict[str, Any]:
    """双轨融合总入口（流水线步骤 6 调用）。返回可直接落库的评估字典。"""
    alpha = settings.ML_WEIGHT_RULE if alpha is None else alpha
    beta = settings.ML_WEIGHT_XGB if beta is None else beta

    rule_score = calc_rule_score(hits)                      # Step 1
    ml_result = calc_ml_score(features, explain=explain)    # Step 2
    # Step 3：模型未加载时权重归一化（α=1/β=0），避免规则分被腰斩
    eff_alpha, eff_beta = effective_weights(alpha, beta, ml_result.is_loaded)
    fused = fuse_scores(rule_score, ml_result.score, alpha, beta, ml_result.is_loaded)
    final_score, is_veto = apply_veto(fused, hits)          # Step 4

    final_int = int(round(min(max(final_score, 0), MAX_SCORE)))
    risk_level = score_to_risk_level(final_int)
    decision = risk_level_to_decision(risk_level)
    reason = build_reason(hits, rule_score, ml_result, final_score, is_veto, decision,
                          alpha, beta)

    return {
        "rule_score": rule_score,
        "ml_score": round(ml_result.score, 2),
        "ml_probability": round(ml_result.probability, 6),
        "ml_decision": ml_result.decision if ml_result.is_loaded else "",
        "ml_loaded": 1 if ml_result.is_loaded else 0,
        "ml_reason": ml_result.reason,
        "ml_contributions": ml_result.contributions,
        "fused_score": fused,
        "final_score": final_int,
        "risk_level": risk_level,
        "decision": decision,
        "is_veto": 1 if is_veto else 0,
        "weight_rule": eff_alpha,           # 实际生效权重（降级时为 1.0）
        "weight_ml": eff_beta,              # 实际生效权重（降级时为 0.0）
        "weight_rule_config": alpha,        # .env 配置值，供前端对比展示
        "weight_ml_config": beta,
        "weight_normalized": eff_alpha != alpha or eff_beta != beta,
        "hit_rules": hits,
        "hit_rule_count": len(hits),
        "need_case": need_case(decision),
        "reason": reason,
        "veto_rules": [h["rule_id"] for h in hits if h.get("risk_level") == VETO_LEVEL],
        "steps": [
            {"step": 1, "name": "规则分", "formula": "min(max(risk_score) + 3×额外命中, 100)",
             "value": rule_score},
            {"step": 2, "name": "模型分", "formula": "P(拒绝) × 100",
             "value": round(ml_result.score, 2)},
            {"step": 3, "name": "双轨加权",
             "formula": (f"{eff_alpha}×{rule_score} + {eff_beta}×{ml_result.score:.2f}"
                         + ("（模型未加载 → 归一化为纯规则）" if not ml_result.is_loaded else "")),
             "value": fused},
            {"step": 4, "name": "一票否决", "formula": f"max(final, {settings.RISK_VETO_MIN_SCORE}) if 极高规则",
             "value": final_int, "triggered": bool(is_veto)},
        ],
    }

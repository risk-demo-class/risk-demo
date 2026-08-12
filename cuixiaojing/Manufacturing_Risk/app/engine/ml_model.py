"""
XGBoost 双轨融合推理模块 (仿 AI_Risk 电商风控).

当前默认 XGB_ENABLED=False → 纯规则模式 (ML 兜底), 模型文件不存在也能跑.
训练好模型后 (.env 设 XGB_ENABLED=true, 模型放 app/engine/xgb_model.json),
推理接口会自动生效, decision.py 走 0.5×规则 + 0.5×ML 融合.

注意: 模块级 import xgboost 用 try/except 包住, 没装 xgboost 也能启动服务.
"""
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# 惰性加载 xgboost (可选依赖)
try:
    import xgboost as xgb  # noqa: F401
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False
    logger.info("xgboost 未安装, ML 双轨融合不可用 (纯规则模式)")

# 模型全局单例 (惰性加载)
_model = None


@dataclass
class PredictResult:
    """ML 推理结果"""
    score: float          # P(拒绝) ∈ [0, 1]
    decision: str         # 通过/标记/人工审核/拒绝 (ML 单维度)
    is_loaded: bool


def _resolve_model_path() -> str:
    """把配置的相对路径解析成绝对路径 (相对项目根)."""
    path = settings.XGB_MODEL_PATH
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), path)
    return path


def load_model() -> bool:
    """加载模型文件到全局单例. 成功返回 True."""
    global _model
    if not settings.XGB_ENABLED:
        _model = None
        return False
    if not _XGB_AVAILABLE:
        _model = None
        return False

    path = _resolve_model_path()
    if not os.path.exists(path):
        logger.warning("XGBoost 模型文件不存在: %s (纯规则模式)", path)
        _model = None
        return False

    try:
        _model = xgb.XGBClassifier()
        _model.load_model(path)
        logger.info("XGBoost 模型加载成功: %s", path)
        return True
    except Exception as e:
        logger.error("XGBoost 模型加载失败: %s", e)
        _model = None
        return False


def is_model_loaded() -> bool:
    """模型是否可用 (XGB_ENABLED + 已加载成功)."""
    global _model
    if not settings.XGB_ENABLED or not _XGB_AVAILABLE:
        return False
    if _model is None:
        load_model()
    return _model is not None


def _prob_to_ml_decision(prob: float) -> str:
    """ML 概率 → ML 单维度决策 (4 档阈值)."""
    if prob < settings.ML_PASS_THRESHOLD:
        return "通过"
    elif prob < settings.ML_MARK_THRESHOLD:
        return "标记"
    elif prob < settings.ML_REVIEW_THRESHOLD:
        return "人工审核"
    else:
        return "拒绝"


# 特征列顺序: 必须跟训练脚本 scripts/train_xgb_model.py 完全一致
FEATURE_COLUMNS = [
    # dealer 12
    "dealer_total_orders", "dealer_orders_30d", "dealer_orders_7d",
    "dealer_total_amount", "dealer_avg_order_amount", "dealer_max_order_amount",
    "dealer_contract_days", "dealer_contract_expired", "dealer_warranty_count",
    "dealer_repair_count", "dealer_cross_region_report_count", "dealer_blacklist_hit",
    # order 6
    "order_total_amount", "order_quantity", "order_unit_price",
    "order_is_first", "order_cross_region_report_count", "order_cross_region_flag",
    # product 3
    "product_msrp", "product_warranty_months", "product_age_months",
    # warranty 5
    "warranty_is_expired", "warranty_apply_count_30d", "sn_repair_count_90d",
    "warranty_repair_cost", "repair_cost_msrp_ratio",
]


def predict(features: dict) -> Optional[PredictResult]:
    """对 1 份特征做推理, 返回 P(拒绝) + ML 决策.

    特征缺失的列补 0 (训练时同策略); 模型不可用返回 None (调用方走纯规则).
    """
    if not is_model_loaded():
        return None

    import numpy as np
    row = [float(features.get(col, 0)) for col in FEATURE_COLUMNS]
    try:
        prob = float(_model.predict_proba(np.array([row]))[0][1])
    except Exception as e:
        logger.error("XGBoost 推理失败: %s", e)
        return None
    return PredictResult(score=prob, decision=_prob_to_ml_decision(prob), is_loaded=True)


# ============================================================
# Demo: 展示模型状态 + 推理接口 — 无模型也能跑 (纯 print)
# 跑法: python -m app.engine.ml_model
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ML 模块 — XGBoost 双轨融合 (默认关闭)")
    print("=" * 60)
    print(f"\n  xgboost 可用     = {_XGB_AVAILABLE}")
    print(f"  XGB_ENABLED      = {settings.XGB_ENABLED} (False = 纯规则)")
    print(f"  模型文件         = {_resolve_model_path()}")
    print(f"  模型已加载       = {is_model_loaded()}")
    print(f"  特征列数         = {len(FEATURE_COLUMNS)} (跟训练脚本对齐)")

    # 校准点展示 (decision.py 的 _ml_prob_to_risk_score 负责概率→风险分)
    print("\n  概率 → ML 决策映射 (ML_PASS/MARK/REVIEW = 0.30/0.60/0.80):")
    for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
        print(f"    P={p:.1f} → {_prob_to_ml_decision(p)}")

    print("\n" + "=" * 60)
    print("启用 ML: 装 xgboost → scripts/train_xgb_model.py 训练 → .env 设 XGB_ENABLED=true")

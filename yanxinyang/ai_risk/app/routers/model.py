# -*- coding: utf-8 -*-
"""L1 路由 · model_router —— 模型中心（XGBoost）

对应教学宝典第 7 章：
    * 9 个函数：load_model / get_model / is_model_loaded / predict / _features_to_array
      / _prob_to_decision / feature_importance / explain_prediction / train_and_save
    * 懒加载 + 降级（模型不存在 → 纯规则跑）
    * 3 种特征重要性：weight / gain / cover
    * 最佳 F1 阈值扫描 0.10~0.85 step 0.05

端点（3 个）：
    GET    /api/model/status        模型状态（含全部超参 + 训练指标）
    POST   /api/model/reload        重新加载 / 卸载模型（热切换，记审计）
    GET    /api/model/importance    3 种特征重要性 + 单样本试算解释
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import settings
from app.database import Session, pool
from app.engine import decision as decision_engine
from app.engine import feature as feature_engine
from app.engine import ml_model
from app.framework import HTTPError, Request, Router
from app.service.action_log import record_action

logger = logging.getLogger("ai_risk.routers.model")

router = Router(prefix="/api/model", tags=["模型中心"], name="model_router")


def _db() -> Session:
    return Session(pool.acquire())


# ====================================================================== 1
@router.get("/status", "模型状态（超参 + 训练指标 + 样本可用量）")
def status(request: Request) -> Dict[str, Any]:
    info = ml_model.model_status()
    db = _db()
    try:
        labeled = db.scalar("SELECT COUNT(*) FROM risk_assessment WHERE label IS NOT NULL")
        positives = db.scalar("SELECT COUNT(*) FROM risk_assessment WHERE label = 1")
        by_source = {r["label_source"] or "未标注": r["cnt"] for r in db.fetch_all(
            "SELECT label_source, COUNT(*) AS cnt FROM risk_assessment "
            "WHERE label IS NOT NULL GROUP BY label_source")}
        snapshots = db.scalar("SELECT COUNT(DISTINCT event_id) FROM risk_feature")
    finally:
        db.close()

    ratio = round(positives / labeled * 100, 2) if labeled else 0.0
    info["training_data"] = {
        "labeled_samples": labeled,
        "positive_samples": positives,
        "positive_ratio": ratio,
        "label_sources": by_source,
        "feature_snapshots": snapshots,
        "min_required": settings.XGB_MIN_SAMPLES,
        "ready": labeled >= settings.XGB_MIN_SAMPLES and positives >= 20,
        "hint": (f"样本足够，可执行 scripts/train_xgb_model.py 训练"
                 if labeled >= settings.XGB_MIN_SAMPLES
                 else f"样本不足：需要 ≥ {settings.XGB_MIN_SAMPLES} 条（25 维 × 50），"
                      f"当前 {labeled} 条。可先跑 scripts/gen_risk_data.py 造样本"),
    }
    info["fusion"] = {
        "formula": "final_score = α × rule_score + β × ml_score",
        "alpha": settings.ML_WEIGHT_RULE, "beta": settings.ML_WEIGHT_XGB,
        "veto_min_score": settings.RISK_VETO_MIN_SCORE,
        "degrade": "模型未加载时 ml_score = 0 且不参与融合（纯规则模式）",
    }
    info["success"] = True
    return info


# ====================================================================== 2
@router.post("/reload", "重新加载 / 卸载模型（热切换）")
def reload_model(request: Request) -> Dict[str, Any]:
    payload = request.json() if request.body else {}
    action = str(payload.get("action") or "reload").lower()
    operator = str(payload.get("operator") or request.headers.get("x-operator", "") or "admin")
    path = str(payload.get("model_path") or "") or None

    before = {"loaded": ml_model.is_model_loaded()}
    if action == "unload":
        ml_model.unload_model()
        ok, message = True, "模型已卸载，系统降级为纯规则模式"
    elif action == "reload":
        ok = ml_model.load_model(path)
        message = ("模型加载成功，双轨融合已启用" if ok
                   else f"模型加载失败，继续纯规则模式：{ml_model.model_status()['load_error']}")
    else:
        raise HTTPError(400, "action 必须是 reload 或 unload")

    db = _db()
    try:
        record_action(db, operator=operator, action_type=f"模型{action}", target_type="模型",
                      target_id=path or settings.XGB_MODEL_PATH,
                      before_value=before, after_value={"loaded": ml_model.is_model_loaded()},
                      remark=message)
        db.commit()
    finally:
        db.close()

    logger.info("模型 %s by %s → %s", action, operator, message)
    return {"success": ok, "message": message, "data": ml_model.model_status()}


# ====================================================================== 3
@router.get("/importance", "3 种特征重要性（weight / gain / cover）")
def importance(request: Request) -> Dict[str, Any]:
    if not ml_model.is_model_loaded():
        return {"success": False, "loaded": False,
                "message": "模型未加载。请先运行 scripts/train_xgb_model.py 训练，"
                           "或调用 POST /api/model/reload",
                "feature_defs": feature_engine.FEATURE_DEFS,
                "importance": {"weight": [], "gain": [], "cover": []}}

    data = ml_model.feature_importance()
    data["success"] = True
    data["loaded"] = True
    data["feature_defs"] = feature_engine.FEATURE_DEFS

    # 可选：带一组特征值做单样本试算（前端「模型试算」面板）
    sample: Dict[str, float] = {}
    for name in feature_engine.FEATURE_DEFS:
        raw = request.q(name["name"])
        if raw is not None:
            try:
                sample[name["name"]] = float(raw)
            except (TypeError, ValueError):
                raise HTTPError(400, f"特征 {name['name']} 不是数值: {raw}") from None
    if sample:
        full = {f["name"]: 0.0 for f in feature_engine.FEATURE_DEFS} | sample
        ml_result = ml_model.predict(full, explain=True)
        fused = decision_engine.calculate(full, [], explain=True)
        data["trial"] = {
            "input": sample,
            "ml_probability": ml_result.probability,
            "ml_score": ml_result.score,
            "ml_decision": ml_result.decision,
            "contributions": ml_result.contributions,
            "fusion": fused,
        }
    return data

#!/usr/bin/env python3
"""训练教育风控 XGBoost 模型并保存到 app/engine/xgb_model.json。

数据来源: risk_assessment.feature_snapshot + decision
    标签: 0 = 通过/标记, 1 = 人工审核/拒绝
先决条件:
    python scripts/init_db.py --reset --yes
    python scripts/gen_risky_users.py
    python scripts/gen_risk_data.py --count 1000
用法:
    python scripts/train_xgb_model.py [--limit N] [--hot]
    --hot  训练成功后立即热加载到内存 (服务启动时也会自动加载)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.engine import ml_model  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, load_model, train_and_save  # noqa: E402
from app.models_risk import RiskAssessment  # noqa: E402


def load_training_data(limit: int | None) -> tuple[np.ndarray, np.ndarray]:
    with SessionLocal() as db:
        stmt = select(RiskAssessment).where(
            RiskAssessment.feature_snapshot.isnot(None),
            RiskAssessment.ml_score.is_(None),  # 只取未标注 ML 的历史, 避免重复计算
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = list(db.scalars(stmt))
    X, y = [], []
    for r in rows:
        fs = r.feature_snapshot
        try:
            X.append([float(fs.get(c, 0.0) or 0.0) for c in FEATURE_COLUMNS])
        except (TypeError, ValueError):
            continue
        y.append(1 if r.decision in ("人工审核", "拒绝") else 0)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="最多取 N 条评估 (默认全部)")
    parser.add_argument("--hot", action="store_true", help="训练后立即热加载进内存")
    args = parser.parse_args()

    X, y = load_training_data(args.limit)
    if len(X) < 20:
        raise SystemExit(
            "训练数据不足 (实际 %d 条)。请先: init_db --reset --yes && gen_risky_users && gen_risk_data --count 1000"
            % len(X)
        )

    print(f"加载训练数据: {len(X)} 条, 正例 {int(np.sum(y == 1))} 条 ({np.mean(y):.2%})")
    metrics, booster = train_and_save(X, y, return_model=True)
    print("训练指标:", metrics)

    # 特征重要性 TOP10
    importance = booster.get_score(importance_type="gain")
    top = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print("\n特征重要性 TOP10 (gain):")
    for name, gain in top:
        print(f"  {name:<40} {gain:.2f}")

    if metrics.get("val_auc") is not None and metrics["val_auc"] < 0.5:
        print("\n[WARN] val_auc < 0.5, 模型可能未学到有效信号, 建议重训或补数据")

    if args.hot:
        ok = load_model()
        print(f"热加载: {'成功' if ok else '失败 (生产会自动加载, 可忽略)'}")

    print(f"\n模型已保存: {ml_model.resolve_model_path()}")


if __name__ == "__main__":
    main()

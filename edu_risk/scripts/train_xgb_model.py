"""
XGBoost 训练脚本 — 4 必做 + 5 件套抗假收敛 + 最佳 F1 阈值扫描
用法:
  python scripts/gen_edu_data.py 500 --target-pos-ratio 0.30   # 造数据
  python scripts/gen_edu_data.py 500                           # 触发风控检查产生评估(label 来源: 规则反推)
  python scripts/gen_labels.py                                 # 可选: 查看正例比例(label 规则反推)
  python scripts/train_xgb_model.py                            # 训练
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.engine import ml_model  # noqa: E402


async def build_training_frame() -> pd.DataFrame:
    """从 risk_feature 快照 + risk_assessment 组装训练集。
    label 来源(教学版): final_score >= 80 → 1 (规则反推,最终交付前升级人工标注)。
    """
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import RiskAssessment, RiskEvent, RiskFeature

    rows = []
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(RiskEvent))).scalars().all()
        for ev in events:
            asm = (await db.execute(select(RiskAssessment).where(
                RiskAssessment.event_id == ev.event_id))).scalar_one_or_none()
            if not asm:
                continue
            feats = (await db.execute(select(RiskFeature).where(
                RiskFeature.event_id == ev.event_id))).scalars().all()
            record = {f.feature_name: float(f.feature_value) for f in feats}
            record["label"] = 1 if asm.final_score >= 80 else 0
            rows.append(record)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--min-samples", type=int, default=None,
                        help="覆盖 config.XGB_MIN_SAMPLES(默认 1250)")
    args = parser.parse_args()

    print("[1/3] 组装训练集(从特征快照)...")
    df = asyncio.run(build_training_frame())
    print(f"      样本数: {len(df)}, 正例: {int(df['label'].sum()) if not df.empty else 0}")

    if df.empty:
        print("[ERROR] 没有训练数据! 先运行 gen_edu_data.py 触发风控检查。")
        sys.exit(1)

    if args.min_samples and len(df) < args.min_samples:
        print(f"[WARN] 样本 {len(df)} < {args.min_samples},结果不可靠,建议造更多数据")

    # 缺列补 0
    for col in ml_model.FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0

    print("[2/3] 训练 XGBoost(80/20 stratify + 早停 auc + scale_pos_weight≤10)...")
    metrics, model = ml_model.train_and_save(
        df, label_col="label", return_model=True, model_path=args.model_path)
    assert model is not None

    print("[3/3] 评估结果")
    print(f"  best_iteration   : {metrics['best_iteration']}")
    print(f"  val_auc          : {metrics['val_auc']:.4f}")
    print(f"  val_f1           : {metrics['val_f1']:.4f}  (best_thr={metrics['best_f1_threshold']})")
    print(f"  val_precision    : {metrics['val_precision']:.4f}")
    print(f"  val_recall       : {metrics['val_recall']:.4f}")
    print(f"  val_ks           : {metrics['val_ks']:.4f}")
    print(f"  acc vs baseline  : {metrics['acc']:.4f} vs {metrics['baseline_acc']:.4f}")
    print(f"  pos_rate         : {metrics['pos_rate']:.2%}")
    print(f"  scale_pos_weight : {metrics['scale_pos_weight']}")
    if metrics["is_fake_convergence"]:
        print("  ⚠️ 假收敛! 真收敛特征: best_iter>50 + val_auc>0.75 + val_f1>0.6 + acc>baseline+2%")
    else:
        print("  ✅ 未检测到假收敛信号")


if __name__ == "__main__":
    main()

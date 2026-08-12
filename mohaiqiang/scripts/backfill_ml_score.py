"""
物流风控系统 - XGBoost ml_score 字段回填脚本

用训好的 XGBoost 推理 risk_feature 快照, 回填 risk_assessment.ml_score/ml_decision.

【用法】
  python scripts/backfill_ml_score.py                  # 回填全部 NULL
  python scripts/backfill_ml_score.py --limit 1500     # 限制条数
  python scripts/backfill_ml_score.py --dry-run        # 只统计不写库
"""
import argparse
import asyncio
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update

from app.database import AsyncSessionLocal, async_engine
from app.engine.ml_model import FEATURE_COLUMNS, is_model_loaded, load_model, predict
from app.models import RiskAssessment, RiskFeature


async def backfill_ml_score(limit: int | None = None, dry_run: bool = False) -> None:
    if not is_model_loaded():
        print("[1] 加载 XGBoost 模型...")
        ok = load_model()
        if not ok:
            print("  [FAIL] 模型加载失败, 先跑: python scripts/train_xgb_model.py")
            return

    print(f"\n[2] 拉 ml_score=NULL 的评估 (limit={limit})...")
    async with AsyncSessionLocal() as db:
        stmt = select(
            RiskAssessment.assessment_id,
            RiskAssessment.event_id,
            RiskAssessment.decision,
        ).where(RiskAssessment.ml_score.is_(None)).order_by(RiskAssessment.create_time.desc())
        if limit:
            stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).all()
        print(f"  拉取 {len(rows)} 条 ml_score=NULL 记录")
        if not rows:
            print("  没有需要回填的记录, 退出")
            return

        print("\n[3] 用 risk_feature 快照推理 + 回填...")
        updated = 0
        pos_score_sum = 0.0
        neg_score_sum = 0.0
        pos_count = 0
        neg_count = 0
        for i, (aid, eid, dec) in enumerate(rows, 1):
            feat_rows = (await db.execute(
                select(RiskFeature.feature_name, RiskFeature.feature_value).where(
                    RiskFeature.event_id == eid
                )
            )).all()
            if not feat_rows:
                continue
            features = {col: 0.0 for col in FEATURE_COLUMNS}
            for name, value in feat_rows:
                if name in features and value is not None:
                    try:
                        features[name] = float(value)
                    except (TypeError, ValueError):
                        pass

            ml = predict(features)
            if ml is None:
                continue
            if not dry_run:
                await db.execute(
                    update(RiskAssessment)
                    .where(RiskAssessment.assessment_id == aid)
                    .values(ml_score=ml.score, ml_decision=ml.decision)
                )
                await db.commit()
            updated += 1
            if dec in ("拒绝", "人工审核"):
                pos_score_sum += ml.score
                pos_count += 1
            else:
                neg_score_sum += ml.score
                neg_count += 1
            if i % 100 == 0 or i == len(rows):
                print(f"  进度 {i}/{len(rows)}: 回填 {updated}")

        print("\n" + "=" * 60)
        print(f"回填完成: 共回填 {updated} 条 ({'DRY-RUN' if dry_run else '已写库'})")
        if pos_count and neg_count:
            pos_avg = pos_score_sum / pos_count
            neg_avg = neg_score_sum / neg_count
            sep = pos_avg - neg_avg
            print(f"  正例平均 ml_score={pos_avg:.4f}, 负例平均 ml_score={neg_avg:.4f}")
            print(f"  正负分离度: {sep:.4f} (越大越好)")
        print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 risk_assessment.ml_score")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async def _runner() -> None:
        try:
            await backfill_ml_score(limit=args.limit, dry_run=args.dry_run)
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()

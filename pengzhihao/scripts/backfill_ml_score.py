"""使用当前物流 XGBoost 模型回填历史评估的 ML 分数。"""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, load_model, predict  # noqa: E402
from app.models import RiskAssessment, RiskFeature  # noqa: E402


async def backfill_ml_score(limit: int | None = None, dry_run: bool = False):
    if not load_model():
        raise RuntimeError("物流 XGBoost 模型加载失败")
    async with AsyncSessionLocal() as db:
        stmt = select(RiskAssessment).order_by(RiskAssessment.create_time.desc())
        if limit:
            stmt = stmt.limit(limit)
        assessments = list((await db.execute(stmt)).scalars().all())
        updated = 0
        for assessment in assessments:
            rows = (await db.execute(select(
                RiskFeature.feature_name, RiskFeature.feature_value
            ).where(RiskFeature.event_id == assessment.event_id))).all()
            features = {name: float(value or 0) for name, value in rows}
            if not set(FEATURE_COLUMNS).issubset(features):
                continue
            result = predict(features)
            if result.score is not None:
                assessment.ml_score = result.score
                assessment.ml_decision = result.decision
                updated += 1
        if not dry_run:
            await db.commit()
        else:
            await db.rollback()
        print({"scanned": len(assessments), "updated": updated, "dry_run": dry_run})


def main():
    parser = argparse.ArgumentParser(description="回填物流 ML 分数")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(backfill_ml_score(args.limit, args.dry_run))


if __name__ == "__main__":
    main()

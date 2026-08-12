"""
用训练好的模型回填 risk_assessment.ml_score.
"""

import argparse
import asyncio
import logging
from collections import defaultdict

from sqlalchemy import select

from app.database import AsyncSessionLocal, async_engine
from app.engine.feature_registry import FEATURE_COLUMNS
from app.engine.ml_model import predict
from app.models import RiskAssessment, RiskFeature

logger = logging.getLogger(__name__)


async def backfill_ml_score(limit: int | None = None, dry_run: bool = False) -> int:
    """回填 ml_score."""
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(RiskAssessment).where(RiskAssessment.ml_score.is_(None))
            if limit:
                stmt = stmt.limit(limit)
            assessments = list((await db.execute(stmt)).scalars().all())
            if not assessments:
                logger.info("没有需要回填的评估记录")
                return 0

            event_ids = [a.event_id for a in assessments]
            features = list(
                (
                    await db.execute(
                        select(RiskFeature).where(RiskFeature.event_id.in_(event_ids))
                    )
                )
                .scalars()
                .all()
            )
            feature_map: dict[str, dict[str, float]] = defaultdict(dict)
            for f in features:
                feature_map[f.event_id][f.feature_name] = float(f.feature_value or 0)

            count = 0
            for assessment in assessments:
                feature_dict = {
                    name: feature_map[assessment.event_id].get(name, 0.0)
                    for name in FEATURE_COLUMNS
                }
                result = predict(feature_dict)
                if dry_run:
                    logger.info(
                        "[dry-run] %s ml_score=%.2f ml_decision=%s",
                        assessment.assessment_id,
                        result.score,
                        result.decision,
                    )
                    continue
                assessment.ml_score = result.score
                assessment.ml_probability = result.probability
                assessment.ml_decision = result.decision
                count += 1

            if not dry_run:
                await db.commit()
            logger.info("ml_score 回填完成: %d 条", count)
            return count
    except Exception:
        logger.exception("ml_score 回填失败")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 ml_score")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async def _main() -> None:
        try:
            await backfill_ml_score(args.limit, args.dry_run)
        finally:
            await async_engine.dispose()

    asyncio.run(_main())


if __name__ == "__main__":
    main()

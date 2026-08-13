"""用已训练模型补充历史 ml_score；不改写历史最终决策。"""

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine.feature import FEATURE_COLUMNS  # noqa: E402
from app.engine.ml_model import ml_model  # noqa: E402
from app.engine.scoring import ml_probability_to_risk_score, score_to_outcome  # noqa: E402
from app.engine.training import load_training_samples  # noqa: E402
from app.models_risk import RiskAssessment  # noqa: E402


async def run(limit: int) -> None:
    if not ml_model.reload():
        raise SystemExit("模型未加载，请先运行 scripts/train_xgb_model.py")
    updated = 0
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                samples = await load_training_samples(db, limit=limit or None)
                for sample in samples:
                    probability = ml_model.predict(
                        dict(zip(FEATURE_COLUMNS, sample.features, strict=True))
                    )
                    if probability is None:
                        continue
                    assessment = await db.get(RiskAssessment, sample.assessment_id)
                    if assessment is None or assessment.ml_score is not None:
                        continue
                    assessment.ml_score = Decimal(str(round(probability, 4)))
                    _, outcome = score_to_outcome(ml_probability_to_risk_score(probability))
                    assessment.ml_decision = outcome.value
                    updated += 1
        print(f"历史 ML 分补充完成：{updated} 条；历史 final_score/decision 未改写")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="补充历史 XGBoost 分数")
    parser.add_argument("--limit", type=int, default=0)
    asyncio.run(run(parser.parse_args().limit))

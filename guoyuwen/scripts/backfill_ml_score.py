"""用已训练银行模型回填历史评估的 ML 概率，不参与训练标签生成。"""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select, update

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, is_model_loaded, load_model, predict  # noqa: E402
from app.models import RiskAssessment, RiskFeature  # noqa: E402
from scripts._console import banner, footer, summary  # noqa: E402


async def backfill_ml_score(limit: int | None = None, dry_run: bool = False) -> dict:
    if not is_model_loaded() and not load_model():
        raise RuntimeError("模型加载失败，请先运行 scripts/train_xgb_model.py")

    async with AsyncSessionLocal() as db:
        statement = (
            select(RiskAssessment.assessment_id, RiskAssessment.event_id)
            .where(RiskAssessment.ml_score.is_(None))
            .order_by(RiskAssessment.create_time)
        )
        if limit:
            statement = statement.limit(limit)
        assessments = (await db.execute(statement)).all()
        updated = 0
        skipped = 0
        for assessment_id, event_id in assessments:
            rows = (
                await db.execute(
                    select(RiskFeature.feature_name, RiskFeature.feature_value).where(
                        RiskFeature.event_id == event_id
                    )
                )
            ).all()
            features = {name: float(value) for name, value in rows}
            if set(features) != set(FEATURE_COLUMNS):
                skipped += 1
                continue
            result = predict(features)
            if not dry_run:
                await db.execute(
                    update(RiskAssessment)
                    .where(RiskAssessment.assessment_id == assessment_id)
                    .values(ml_score=result.score, ml_decision=result.decision)
                )
            updated += 1
        if not dry_run:
            await db.commit()
        return {"candidates": len(assessments), "updated": updated, "skipped": skipped, "dry_run": dry_run}


async def _runner() -> int:
    parser = argparse.ArgumentParser(description="回填银行评估的 XGBoost 概率")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        banner("ML 评分回填", f"模型: app/engine/xgb_model.json | dry_run={args.dry_run}")
        result = await backfill_ml_score(args.limit, args.dry_run)
        print()
        summary(
            [
                ("候选评估", result["candidates"]),
                ("已回填", result["updated"]),
                ("跳过 (特征不全)", result["skipped"]),
                ("dry_run", result["dry_run"]),
            ],
            title="回填结果",
        )
        footer("回填完成")
        return 0
    finally:
        # 在事件循环关闭前释放全局引擎连接池，避免解释器退出时
        # aiomysql 在已关闭的 loop 上 close() 报 "Event loop is closed"
        await async_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_runner()))

"""
训练标签生成器 — 规则反推 label(教学版第 3 种 label 来源)
final_score >= 80 → label=1 (正样本),否则 0。
用法: 被 gen_edu_data.py --target-pos-ratio 调用,也可独立运行。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import RiskAssessment  # noqa: E402


async def compute_pos_ratio() -> float:
    async with AsyncSessionLocal() as db:
        total = (await db.execute(select(func.count(RiskAssessment.assessment_id)))).scalar() or 0
        if total == 0:
            return 0.0
        pos = (await db.execute(select(func.count(RiskAssessment.assessment_id)).where(
            RiskAssessment.final_score >= 80))).scalar() or 0
        return pos / total


async def main():
    ratio = await compute_pos_ratio()
    print(f"总评估数: {(await _total())}, 正例比例: {ratio:.2%}")


async def _total() -> int:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(func.count(RiskAssessment.assessment_id)))).scalar() or 0


if __name__ == "__main__":
    asyncio.run(main())

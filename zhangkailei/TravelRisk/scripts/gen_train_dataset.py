"""一键生成旅游业务数据和无 ML 痕迹的训练评估数据。"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.engine import ml_model
from scripts.gen_business_data import generate as generate_business
from scripts.gen_risk_data import generate as generate_risk


async def main(count: int, reset_business: bool) -> None:
    business = await generate_business(max(count, 120), reset=reset_business)
    # 训练标签只由规则和业务样本产生，造数期间禁用旧模型。
    ml_model._LOADED = False
    ml_model._MODEL = None
    risk = await generate_risk(count)
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE risk_assessment SET ml_score=NULL, ml_decision=NULL"))
        await db.commit()
    print({"business": business, "assessments": risk})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--reset-business", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.count, args.reset_business))

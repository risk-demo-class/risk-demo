"""
旅游风控系统 - 带日期范围的批量评估数据生成 (旅游版)
让评估记录跨天分布, 仪表盘"近 7 天评估曲线"才有数据可画.

用法:
  python scripts/gen_risk_data_with_dates.py --days 14 --per-day 25
  python scripts/gen_risk_data_with_dates.py --days 14 --per-day 25 --clean   # 先清空旧评估
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    OrderInfo,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    VisaApplication,
)
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402

ORDER_EVENT = {"机票": "机票预订", "酒店": "酒店预订", "跟团游": "跟团游预订"}


async def clean(db) -> None:
    """清空旧评估相关数据 (按依赖顺序)."""
    for model in (RiskFeature, RiskCase, RiskAssessment, RiskEvent):
        await db.execute(model.__table__.delete())
    await db.commit()
    print("已清空旧评估数据")


async def main(days: int, per_day: int, seed: int, do_clean: bool):
    random.seed(seed)
    async with AsyncSessionLocal() as db:
        if do_clean:
            await clean(db)

        orders = (await db.execute(
            select(OrderInfo.order_id, OrderInfo.user_id, OrderInfo.order_type)
        )).all()
        visas = (await db.execute(
            select(VisaApplication.visa_id, VisaApplication.user_id)
        )).all()
        pool = [(ORDER_EVENT[o.order_type], o.order_id, o.user_id) for o in orders]
        pool += [("签证申请", v.visa_id, v.user_id) for v in visas]
        random.shuffle(pool)
        if not pool:
            print("没有可用业务样本, 先跑 gen_business_data.py")
            return

        n = 0
        for offset in range(days - 1, -1, -1):
            day = (datetime.now() - timedelta(days=offset)).date()
            for _k in range(per_day):
                et, sid, uid = pool[n % len(pool)]
                n += 1
                try:
                    resp = await process_event(
                        db, RiskCheckRequest(event_type=et, source_id=sid, user_id=uid),
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"  跳过 {et}/{sid}: {type(e).__name__} {str(e)[:60]}")
                    continue
                # 回写评估/事件/特征/案件时间为目标天 (随机 8-22 点), 让趋势曲线有跨天数据
                dt = datetime(day.year, day.month, day.day,
                              random.randint(8, 22), random.randint(0, 59), random.randint(0, 59))
                await db.execute(
                    update(RiskEvent).where(RiskEvent.event_id == resp.event_id).values(create_time=dt)
                )
                await db.execute(
                    update(RiskAssessment)
                    .where(RiskAssessment.assessment_id == resp.assessment_id).values(create_time=dt)
                )
                await db.execute(
                    update(RiskFeature).where(RiskFeature.event_id == resp.event_id).values(compute_time=dt)
                )
                await db.execute(
                    update(RiskCase).where(RiskCase.assessment_id == resp.assessment_id).values(create_time=dt)
                )
                await db.commit()
        print(f"完成: 生成 {n} 条评估, 跨 {days} 天 (每天 {per_day} 条)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="旅游风控 - 跨天评估数据生成")
    parser.add_argument("--days", type=int, default=14, help="覆盖天数")
    parser.add_argument("--per-day", type=int, default=25, help="每天条数")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    parser.add_argument("--clean", action="store_true", help="先清空旧评估数据")
    args = parser.parse_args()
    asyncio.run(main(args.days, args.per_day, args.seed, args.clean))
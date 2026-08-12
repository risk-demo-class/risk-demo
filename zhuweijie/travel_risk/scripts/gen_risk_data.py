"""
旅游风控系统 - 批量生成风控评估数据
通过 process_event 跑真实 7 步流水线, 生成 risk_event / risk_feature / risk_assessment / risk_case.
用途: XGBoost 训练数据准备 + 前端演示 (案件/评估历史有数据可看).

训练数据严格化: 未训练模型时 ml_score 会被写成 0.0 (垃圾值), 生成完统一置 NULL,
与基线 gen_train_dataset.py 约定一致, 保证训练只取"无 ml 痕迹"的干净标签.

用法:
  python scripts/gen_risk_data.py                # 全部订单+签证
  python scripts/gen_risk_data.py --limit 200    # 只跑前 200 个样本
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import OrderInfo, RiskAssessment, VisaApplication  # noqa: E402
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402

ORDER_EVENT = {"机票": "机票预订", "酒店": "酒店预订", "跟团游": "跟团游预订"}


async def main(limit: int | None, seed: int):
    random.seed(seed)
    async with AsyncSessionLocal() as db:
        orders = (await db.execute(
            select(OrderInfo.order_id, OrderInfo.user_id, OrderInfo.order_type)
        )).all()
        visas = (await db.execute(
            select(VisaApplication.visa_id, VisaApplication.user_id)
        )).all()

        samples = [(ORDER_EVENT[o.order_type], o.order_id, o.user_id) for o in orders]
        samples += [("签证申请", v.visa_id, v.user_id) for v in visas]
        random.shuffle(samples)
        if limit:
            samples = samples[:limit]

        ok = 0
        for et, sid, uid in samples:
            try:
                await process_event(
                    db, RiskCheckRequest(event_type=et, source_id=sid, user_id=uid),
                )
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"  跳过 {et}/{sid}: {type(e).__name__} {str(e)[:80]}")

        # 训练数据严格化: 清掉 ml_score/ml_decision (未训练模型前的 0.0 是垃圾值)
        await db.execute(update(RiskAssessment).values(ml_score=None, ml_decision=None))
        await db.commit()
        print(f"完成: 成功 {ok} / 共 {len(samples)} 次评估, ml 痕迹已置 NULL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="旅游风控 - 批量生成评估数据")
    parser.add_argument("--limit", type=int, default=None, help="最多跑多少个样本")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.seed))
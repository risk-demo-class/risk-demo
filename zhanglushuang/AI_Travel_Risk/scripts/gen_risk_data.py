"""
生成风控评估数据.

从业务表抽取订单/签证/退改事件, 调用 process_event 生成
risk_event / risk_feature / risk_assessment / risk_case.
"""

import argparse
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.database import AsyncSessionLocal, async_engine
from app.models import OrderInfo, VisaApplication
from app.schemas import RiskCheckRequest
from app.service.event import process_event

logger = logging.getLogger(__name__)


def _event_data(order: OrderInfo) -> dict:
    return {
        "order_type": order.order_type,
        "total_amount": float(order.total_amount or 0),
        "dest_country": order.dest_country,
        "depart_date": order.depart_date.isoformat() if order.depart_date else None,
        "return_date": order.return_date.isoformat() if order.return_date else None,
        "passenger_count": order.passenger_count,
        "pay_account": order.pay_account,
        "device_id": order.device_id,
        "ip_address": order.ip_address,
        "order_remark": order.order_remark,
        "check_time": datetime.now().isoformat(),
    }


async def generate_risk_data(
    count: int = 60,
    balance_pos: bool = False,
) -> None:
    """生成风控评估数据."""
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(OrderInfo).order_by(OrderInfo.create_time.desc()).limit(count * 2)
            if balance_pos:
                stmt = stmt.where(OrderInfo.user_id.like("RISK%"))
            orders = list((await db.execute(stmt)).scalars().all())
            if balance_pos:
                orders = orders[:count]
            else:
                # 混合普通用户与高风险用户
                risk_orders = [o for o in orders if o.user_id.startswith("RISK")]
                normal_orders = [o for o in orders if not o.user_id.startswith("RISK")]
                orders = (risk_orders[: max(count // 2, 1)] + normal_orders[: count])[:count]

            done = 0
            for order in orders:
                try:
                    request = RiskCheckRequest(
                        event_type="下单",
                        source_id=order.order_id,
                        user_id=order.user_id,
                        order_id=order.order_id,
                        event_data=_event_data(order),
                    )
                    result = await process_event(db, request)
                    done += 1
                    logger.info(
                        "评估完成: %s user=%s score=%s decision=%s",
                        order.order_id,
                        order.user_id,
                        result.final_score,
                        result.decision,
                    )
                except Exception:
                    logger.exception("评估失败: order_id=%s", order.order_id)

            # 补充签证事件
            visas = list(
                (
                    await db.execute(select(VisaApplication).limit(max(count // 5, 3)))
                )
                .scalars()
                .all()
            )
            for visa in visas:
                try:
                    await process_event(
                        db,
                        RiskCheckRequest(
                            event_type="签证申请",
                            source_id=visa.visa_id,
                            user_id=visa.user_id,
                            event_data={"dest_country": visa.dest_country},
                        ),
                    )
                    done += 1
                except Exception:
                    logger.exception("签证评估失败: visa_id=%s", visa.visa_id)

            logger.info("风控评估数据生成完成: %d 条", done)
    except Exception:
        logger.exception("风控评估数据生成失败")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="生成风控评估数据")
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--balance-pos", action="store_true", help="优先高风险用户")
    args = parser.parse_args()

    async def _main() -> None:
        try:
            await generate_risk_data(args.count, args.balance_pos)
        finally:
            await async_engine.dispose()

    asyncio.run(_main())


if __name__ == "__main__":
    main()

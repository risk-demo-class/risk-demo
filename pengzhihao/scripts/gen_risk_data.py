"""把物流运单送入真实风控管道，生成训练/演示评估数据。"""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskUserProfile, Shipment,
)
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402


def _event_for(shipment: Shipment, index: int) -> str:
    if shipment.is_cross_border:
        return "跨境申报"
    if shipment.payment_type == "代收货款":
        return "代收货款"
    if shipment.inspection_status in ("疑似危险品", "拒绝收寄") or index % 3 == 0:
        return "安检验视"
    return "寄件受理"


async def generate_risk_data(count: int | None = None, reset: bool = False) -> dict:
    # 生成特征快照时禁用上一次模型；规则结果不作为训练标签。
    settings.XGB_ENABLED = False
    async with AsyncSessionLocal() as db:
        if reset:
            for model in (RiskCase, RiskAssessment, RiskFeature, RiskEvent, RiskUserProfile):
                await db.execute(delete(model))
            await db.commit()
        stmt = select(Shipment).order_by(Shipment.shipment_id)
        if count:
            stmt = stmt.limit(count)
        shipments = list((await db.execute(stmt)).scalars().all())
        ok = failed = high = 0
        decisions: dict[str, int] = {}
        for index, shipment in enumerate(shipments, 1):
            try:
                event_type = _event_for(shipment, index)
                response = await process_event(db, RiskCheckRequest(
                    event_type=event_type,
                    source_id=shipment.shipment_id,
                    user_id=shipment.sender_id,
                    event_data={
                        "waybill_no": shipment.waybill_no,
                        "risk_label": shipment.risk_label,
                        "risk_pattern": shipment.risk_pattern,
                    },
                ))
                ok += 1
                high += int(shipment.risk_label)
                decisions[response.decision] = decisions.get(response.decision, 0) + 1
            except Exception as exc:
                failed += 1
                await db.rollback()
                print(f"[失败] {shipment.shipment_id}: {type(exc).__name__}: {exc}")
        summary = {"total": len(shipments), "ok": ok, "failed": failed, "risk_label_1": high, "decisions": decisions}
        print("物流风险数据完成:", summary)
        return summary


def main():
    parser = argparse.ArgumentParser(description="生成物流风险评估数据")
    parser.add_argument("--count", type=int, default=None, help="默认处理全部运单")
    parser.add_argument("--reset", action="store_true", help="先清理风险事件/特征/评估/案件/画像")
    # 兼容旧的一键命令参数，不再改变抽样逻辑。
    parser.add_argument("--balance-pos", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--target-pos-ratio", type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()
    async def _generate_and_close():
        from app.database import async_engine
        try:
            await generate_risk_data(args.count, args.reset)
        finally:
            await async_engine.dispose()
    asyncio.run(_generate_and_close())


if __name__ == "__main__":
    main()

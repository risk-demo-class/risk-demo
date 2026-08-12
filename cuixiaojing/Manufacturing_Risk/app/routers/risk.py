"""风控检查 API"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import CrossRegionReport, OrderInfo, WarrantyRecord
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.event import process_event

risk_router = APIRouter(prefix="/api/risk", tags=["风控检查"])


@risk_router.post("/check", response_model=RiskCheckResponse)
async def api_risk_check(request: RiskCheckRequest, db: AsyncSession = Depends(get_db_async)):
    return await process_event(db, request)


@risk_router.get("/samples")
async def api_risk_samples(db: AsyncSession = Depends(get_db_async)):
    """返回各事件类型的示例业务数据 (前端"风险检查"页下拉填充用).

    每个示例: {source_id, user_id, desc}
      - 经销商订货: source=order_id, user=dealer_id
      - 保修申请/售后维修: source=warranty_id, user=经销商
      - 串货举报: source=report_id, user=reporter_id
    """
    samples = {
        "经销商订货": [],
        "保修申请": [],
        "售后维修": [],
        "串货举报": [],
    }

    # 经销商订货: 最近 15 张订单
    orders = (await db.execute(
        select(OrderInfo).order_by(OrderInfo.create_time.desc()).limit(15)
    )).scalars().all()
    for o in orders:
        samples["经销商订货"].append({
            "source_id": o.order_id,
            "user_id": o.dealer_id,
            "desc": f"{o.order_id} 金额{o.total_amount:.0f}",
        })

    # 保修/维修: 最近 15 张保修单 (join 订单拿经销商)
    wrows = (await db.execute(
        select(WarrantyRecord, OrderInfo.dealer_id)
        .join(OrderInfo, WarrantyRecord.order_id == OrderInfo.order_id)
        .order_by(WarrantyRecord.issue_date.desc())
        .limit(15)
    )).all()
    for w, dealer_id in wrows:
        entry = {
            "source_id": w.warranty_id,
            "user_id": dealer_id,
            "desc": f"{w.warranty_id} SN={w.product_sn} ({w.issue_type})",
        }
        # issue_type: 保修申请 → 保修申请事件; 维修 → 售后维修事件
        evt_key = "售后维修" if w.issue_type == "维修" else "保修申请"
        samples[evt_key].append(entry)

    # 串货举报: 最近 15 条举报
    reports = (await db.execute(
        select(CrossRegionReport).order_by(CrossRegionReport.create_time.desc()).limit(15)
    )).scalars().all()
    for r in reports:
        samples["串货举报"].append({
            "source_id": r.report_id,
            "user_id": r.reporter_id or "U005",
            "desc": f"{r.report_id} 订单{r.order_id} ({r.ship_to_region}≠{r.dealer_region})",
        })

    return samples

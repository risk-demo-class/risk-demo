"""联想搜索 API (风险检查页用户ID / 业务ID 自动补全)

两个接口:
  GET /api/suggest/users?q=U1&limit=10        用户联想 (user_id 前缀 + 姓名包含)
  GET /api/suggest/biz?type=order&q=ORD&user_id=&limit=10   业务ID联想 (事件类型感知)

设计要点:
  - 业务ID联想按事件类型切换数据源: order=订单 / refund=退改单 / visa=签证申请
  - 传 user_id 时只联想该用户的业务ID (与订单归属校验对齐)
  - LIKE 通配符转义, 防止 %/_ 注入
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import OrderInfo, OrderRefund, UserInfo, VisaApplication

suggest_router = APIRouter(prefix="/api/suggest", tags=["联想搜索"])

_MAX_LIMIT = 20


def _escape_like(q: str) -> str:
    """转义 LIKE 通配符: 反斜杠 / % / _."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@suggest_router.get("/users")
async def api_suggest_users(
    q: str = Query("", max_length=50, description="搜索词 (user_id 前缀 或 姓名包含)"),
    limit: int = Query(10, ge=1, le=_MAX_LIMIT, description="返回条数上限"),
    db: AsyncSession = Depends(get_db_async),
):
    """用户联想: user_id LIKE 'q%' 或 name LIKE '%q%'."""
    q = q.strip()
    if not q:
        return {"items": []}
    escaped = _escape_like(q)
    rows = (await db.execute(
        select(
            UserInfo.user_id, UserInfo.name,
            UserInfo.real_name_status, UserInfo.vip_level, UserInfo.account_age_days,
        )
        .where(
            (UserInfo.user_id.like(f"{escaped}%"))
            | (UserInfo.name.like(f"%{escaped}%"))
        )
        .order_by(UserInfo.user_id)
        .limit(limit)
    )).all()
    return {"items": [
        {
            "user_id": r.user_id,
            "name": r.name,
            "real_name_status": r.real_name_status,
            "vip_level": r.vip_level,
            "account_age_days": r.account_age_days,
        }
        for r in rows
    ]}


# 业务ID联想: 事件类型 → (id字段, 用户字段, label 构建)
_BIZ_TYPES = {"order", "refund", "visa"}


@suggest_router.get("/biz")
async def api_suggest_biz(
    type: str = Query(..., description="业务类型: order/refund/visa"),
    q: str = Query("", max_length=50, description="业务ID前缀"),
    user_id: str = Query("", max_length=50, description="按用户过滤 (可空)"),
    limit: int = Query(10, ge=1, le=_MAX_LIMIT, description="返回条数上限"),
    db: AsyncSession = Depends(get_db_async),
):
    """业务ID联想: 按 type 切换表, 可选按 user_id 过滤."""
    if type not in _BIZ_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的 type: {type}, 可选 order/refund/visa")
    q = q.strip()
    if not q:
        return {"items": []}
    escaped = _escape_like(q)
    prefix = f"{escaped}%"

    if type == "order":
        stmt = (
            select(
                OrderInfo.order_id, OrderInfo.user_id, OrderInfo.order_type,
                OrderInfo.total_amount, OrderInfo.dest_country,
            )
            .where(
                OrderInfo.order_id.like(prefix),
                OrderInfo.order_status != "已取消",
            )
            .order_by(OrderInfo.order_id)
            .limit(limit)
        )
        if user_id:
            stmt = stmt.where(OrderInfo.user_id == user_id)
        rows = (await db.execute(stmt)).all()
        return {"items": [
            {
                "source_id": r.order_id,
                "user_id": r.user_id,
                "label": f"{r.order_id} {r.order_type} {float(r.total_amount):.0f}元 {r.dest_country}",
            }
            for r in rows
        ]}

    if type == "refund":
        stmt = (
            select(
                OrderRefund.refund_id, OrderRefund.user_id, OrderRefund.order_id,
                OrderRefund.refund_type, OrderRefund.refund_amount, OrderRefund.refund_status,
            )
            .where(OrderRefund.refund_id.like(prefix))
            .order_by(OrderRefund.refund_id)
            .limit(limit)
        )
        if user_id:
            stmt = stmt.where(OrderRefund.user_id == user_id)
        rows = (await db.execute(stmt)).all()
        return {"items": [
            {
                "source_id": r.refund_id,
                "user_id": r.user_id,
                "label": f"{r.refund_id} {r.refund_type} {float(r.refund_amount):.0f}元 ({r.refund_status})",
            }
            for r in rows
        ]}

    # visa
    stmt = (
        select(
            VisaApplication.visa_id, VisaApplication.user_id, VisaApplication.dest_country,
            VisaApplication.visa_type, VisaApplication.submit_time,
        )
        .where(VisaApplication.visa_id.like(prefix))
        .order_by(VisaApplication.visa_id)
        .limit(limit)
    )
    if user_id:
        stmt = stmt.where(VisaApplication.user_id == user_id)
    rows = (await db.execute(stmt)).all()
    return {"items": [
        {
            "source_id": r.visa_id,
            "user_id": r.user_id,
            "label": f"{r.visa_id} {r.dest_country} {r.visa_type}",
        }
        for r in rows
    ]}

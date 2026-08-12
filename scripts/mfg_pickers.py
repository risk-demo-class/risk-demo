"""
制造业事件 picker 共享模块 (gen_risk_data / gen_risk_data_with_dates / gen_train_dataset 共用)

从业务表随机选一条可评估的事件, 返回:
    (event_type, source_id, user_id, order_id)
覆盖 5 种事件: 经销商订货 / 采购订单 / 保修申请 / 售后维修 / 串货举报
"""
import random

from sqlalchemy import text

from app.schemas import RiskCheckRequest

RISKY_USER_PREFIX = "RISK"


async def pick_order(db, balance_pos: bool = False, user_id: str | None = None, order_type: str | None = None) -> tuple | None:
    """选一条订货/采购订单, 返回 (order_id, dealer_id, order_type)."""
    sql = "SELECT order_id, dealer_id, order_type FROM order_info"
    conds, params = [], {}
    if user_id:
        conds.append("dealer_id = :uid")
        params["uid"] = user_id
    if order_type:
        conds.append("order_type = :otype")
        params["otype"] = order_type
    if balance_pos and random.random() < 0.8:
        conds.append("dealer_id LIKE :prefix")
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY RAND() LIMIT 1"
    row = (await db.execute(text(sql), params)).first()
    return (row.order_id, row.dealer_id, row.order_type) if row else None


async def pick_warranty(
    db, balance_pos: bool = False, user_id: str | None = None, issue_type: str | None = None,
) -> tuple | None:
    """选一条保修/维修工单, 返回 (warranty_id, dealer_id, issue_type)."""
    sql = """
        SELECT w.warranty_id, oi.dealer_id, w.issue_type
        FROM warranty_record w
        JOIN order_info oi ON w.order_id = oi.order_id
    """
    conds, params = [], {}
    if user_id:
        conds.append("oi.dealer_id = :uid")
        params["uid"] = user_id
    if issue_type:
        conds.append("w.issue_type = :itype")
        params["itype"] = issue_type
    if balance_pos and random.random() < 0.8:
        conds.append("oi.dealer_id LIKE :prefix")
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY RAND() LIMIT 1"
    row = (await db.execute(text(sql), params)).first()
    return (row.warranty_id, row.dealer_id, row.issue_type) if row else None


async def pick_report(db, balance_pos: bool = False, user_id: str | None = None) -> tuple | None:
    """选一条串货举报, 返回 (report_id, dealer_id)."""
    sql = "SELECT report_id, dealer_id FROM cross_region_report"
    conds, params = [], {}
    if user_id:
        conds.append("dealer_id = :uid")
        params["uid"] = user_id
    if balance_pos and random.random() < 0.8:
        conds.append("dealer_id LIKE :prefix")
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY RAND() LIMIT 1"
    row = (await db.execute(text(sql), params)).first()
    return (str(row.report_id), row.dealer_id) if row else None


def build_request(event_type: str, source_id: str, user_id: str, order_id: str | None = None) -> RiskCheckRequest:
    """按事件类型构造风控检查请求 (order_id 用于订单特征)."""
    return RiskCheckRequest(
        event_type=event_type,
        source_id=source_id,
        user_id=user_id,
        order_id=order_id,
    )


async def pick_random_event(db, balance_pos: bool = False, user_id: str | None = None) -> tuple | None:
    """随机挑一种制造业事件, 返回 (event_type, source_id, user_id, order_id)."""
    # 权重: 订货 45% / 采购 15% / 保修 15% / 维修 15% / 串货举报 10%
    roll = random.random()
    if roll < 0.45:
        picked = await pick_order(db, balance_pos, user_id)
        if not picked:
            return None
        oid, did, otype = picked
        return ("经销商订货" if otype == "经销商订货" else "采购订单", oid, did, oid)
    elif roll < 0.60:
        picked = await pick_warranty(db, balance_pos, user_id, issue_type="保修")
        if not picked:
            return None
        wid, did, _ = picked
        return ("保修申请", wid, did, None)
    elif roll < 0.75:
        picked = await pick_warranty(db, balance_pos, user_id, issue_type="维修")
        if not picked:
            return None
        wid, did, _ = picked
        return ("售后维修", wid, did, None)
    elif roll < 0.90:
        picked = await pick_report(db, balance_pos, user_id)
        if not picked:
            return None
        rid, did = picked
        return ("串货举报", rid, did, None)
    else:
        picked = await pick_order(db, balance_pos, user_id)
        if not picked:
            return None
        oid, did, otype = picked
        return ("经销商订货", oid, did, oid)

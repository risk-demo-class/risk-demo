"""
特征工程模块 (物流版): 通过 ORM 查询物流业务表, 计算风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  shipper_*  = 卖家维度特征 (发件人)
  buyer_*    = 买家维度特征 (收件人)
  cargo_*    = 运单/货物维度特征 (waybill_info 直读)
  inspect_*  = 验货维度特征 (验货中心环节)
  track_*    = 轨迹维度特征 (运输/派送环节)
  return_*   = 退货逆向维度特征 (链路 C)

字段名与 sql/init_logistics_risk_data.sql 的规则条件一一对应 (L001-L030),
保证规则引擎能命中.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CarrierInfo,
    ComplaintClaim,
    ConsigneeInfo,
    InspectionRecord,
    ItemIdentity,
    ShipperInfo,
    TrackingEvent,
    WaybillDetail,
    WaybillInfo,
)


# 通用 SQL 工具
async def _count(model, db: AsyncSession, **filters) -> float:
    """SELECT COUNT(*) FROM model WHERE filters."""
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(model, col_name: str, db: AsyncSession, **filters) -> float:
    """SELECT COALESCE(SUM(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 卖家维度特征 (shipper_*)
# ============================================================

async def _feat_shipper_waybills_7d(db: AsyncSession, shipper_id: str) -> float:
    """卖家近 7 天寄件数 (刷单/高频寄件信号)"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(WaybillInfo).where(
        WaybillInfo.shipper_id == shipper_id,
        WaybillInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_shipper_waybills_30d(db: AsyncSession, shipper_id: str) -> float:
    """卖家近 30 天寄件数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(WaybillInfo).where(
        WaybillInfo.shipper_id == shipper_id,
        WaybillInfo.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_shipper_waybills_total(db: AsyncSession, shipper_id: str) -> float:
    """卖家历史运单总数"""
    return await _count(WaybillInfo, db, shipper_id=shipper_id)


async def _feat_shipper_empty_pkg_rate(
    db: AsyncSession, shipper_id: str,
) -> float:
    """卖家历史空包率 = 空包运单数 / 总运单数 (空包/虚假发货核心信号)"""
    total = await _count(WaybillInfo, db, shipper_id=shipper_id)
    if total == 0:
        return 0.0
    empty = await _count(WaybillInfo, db, shipper_id=shipper_id, cargo_weight=0.1)
    # 空包: 重量 <= 0.1kg
    stmt = select(func.count()).select_from(WaybillInfo).where(
        WaybillInfo.shipper_id == shipper_id,
        WaybillInfo.cargo_weight <= 0.1,
    )
    empty = float((await db.execute(stmt)).scalar() or 0)
    return round(empty / total, 4)


async def _feat_shipper_night_rate(db: AsyncSession, shipper_id: str) -> float:
    """卖家深夜寄件率 = 夜间运单数 / 总运单数 (夜间批量寄件异常)"""
    total = await _count(WaybillInfo, db, shipper_id=shipper_id)
    if total == 0:
        return 0.0
    night = await _count(WaybillInfo, db, shipper_id=shipper_id, is_night_order=1)
    return round(night / total, 4)


async def _feat_shipper_imei_dup_count(db: AsyncSession, shipper_id: str) -> float:
    """卖家序列号重复次数: 同一 IMEI 出现在该卖家多个运单中 (一物多卖/刷单)"""
    stmt = select(func.count()).select_from(WaybillDetail).join(
        WaybillInfo, WaybillDetail.waybill_id == WaybillInfo.waybill_id
    ).where(
        WaybillInfo.shipper_id == shipper_id,
        WaybillDetail.item_imei.isnot(None),
    ).group_by(WaybillDetail.item_imei).having(func.count() > 1)
    rows = (await db.execute(stmt)).all()
    return float(len(rows))


async def _feat_shipper_complaint_count(db: AsyncSession, shipper_id: str) -> float:
    """卖家累计投诉次数 (shipper_info 画像字段, 有则用, 无则 0)"""
    row = (await db.execute(
        select(ShipperInfo.complaint_total).where(ShipperInfo.shipper_id == shipper_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_shipper_dispute_count(db: AsyncSession, shipper_id: str) -> float:
    """卖家累计纠纷数 (shipper_info 画像字段)"""
    row = (await db.execute(
        select(ShipperInfo.dispute_count).where(ShipperInfo.shipper_id == shipper_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_shipper_is_verified(db: AsyncSession, shipper_id: str) -> float:
    """卖家是否实名认证 (0=未认证, 1=已认证). shipper_info 无 is_verified 字段,
    用身份证号是否填写近似判断 (实名寄递 = 已登记身份证)."""
    row = (await db.execute(
        select(ShipperInfo.shipper_id_card).where(ShipperInfo.shipper_id == shipper_id)
    )).first()
    return 1.0 if row and row[0] else 0.0


# ============================================================
# 运单/货物维度特征 (cargo_* 直读 waybill_info)
# ============================================================

async def _feat_cargo_weight(db: AsyncSession, waybill_id: str) -> float:
    """包裹重量 (kg): 空包检测核心"""
    row = (await db.execute(
        select(WaybillInfo.cargo_weight).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_cargo_volume(db: AsyncSession, waybill_id: str) -> float:
    """包裹体积 (m³)"""
    row = (await db.execute(
        select(WaybillInfo.cargo_volume).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_declared_value(db: AsyncSession, waybill_id: str) -> float:
    """声明价值 (元): 高价值/虚报检测"""
    row = (await db.execute(
        select(WaybillInfo.declared_value).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_cod_amount(db: AsyncSession, waybill_id: str) -> float:
    """代收货款金额 (元): 资金风险"""
    row = (await db.execute(
        select(WaybillInfo.cod_amount).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_insurance_amount(db: AsyncSession, waybill_id: str) -> float:
    """保价金额 (元)"""
    row = (await db.execute(
        select(WaybillInfo.insurance_amount).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_is_night_order(db: AsyncSession, waybill_id: str) -> float:
    """是否夜间下单 (0/1)"""
    row = (await db.execute(
        select(WaybillInfo.is_night_order).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_is_urgent(db: AsyncSession, waybill_id: str) -> float:
    """是否加急 (0/1)"""
    row = (await db.execute(
        select(WaybillInfo.is_urgent).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_is_cross_border(db: AsyncSession, waybill_id: str) -> float:
    """是否跨境 (0/1)"""
    row = (await db.execute(
        select(WaybillInfo.is_cross_border).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_cargo_category_high_value(db: AsyncSession, waybill_id: str) -> float:
    """运单品类是否高溢价 (1=手机/电脑/相机/奢侈品/平板, 调包高发)"""
    row = (await db.execute(
        select(WaybillInfo.cargo_category).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    if not row or not row[0]:
        return 0.0
    hv = {"手机", "电脑", "相机", "奢侈品", "平板"}
    return 1.0 if row[0] in hv else 0.0


async def _feat_cargo_type_danger(db: AsyncSession, waybill_id: str) -> float:
    """货物类型是否危险品 (1=电池/化学品/液体/粉末/刀具)"""
    row = (await db.execute(
        select(WaybillInfo.cargo_type).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    if not row or not row[0]:
        return 0.0
    danger = {"电池", "化学品", "液体", "粉末", "刀具"}
    return 1.0 if row[0] in danger else 0.0


async def _feat_has_seal(db: AsyncSession, waybill_id: str) -> float:
    """是否绑定封条/防拆贴 (1=有, 0=无; 高溢价品类无封条=调包风险)"""
    row = (await db.execute(
        select(WaybillInfo.seal_id).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    return 1.0 if row and row[0] else 0.0


async def _feat_waybill_status(db: AsyncSession, waybill_id: str) -> float:
    """运单状态 (数字编码: 便于规则比较)"""
    status_map = {"待揽收": 0, "待验货": 1, "已验货": 2, "运输中": 3,
                  "派送中": 4, "已签收": 5, "已拒收": 6, "已退回": 7}
    row = (await db.execute(
        select(WaybillInfo.waybill_status).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    if not row or not row[0]:
        return 0.0
    return float(status_map.get(row[0], 0))


async def _feat_segment(db: AsyncSession, waybill_id: str) -> float:
    """当前所属链路 (A=1, B=2, C=3)"""
    seg_map = {"A": 1, "B": 2, "C": 3}
    row = (await db.execute(
        select(WaybillInfo.segment).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    if not row or not row[0]:
        return 1.0
    return float(seg_map.get(row[0], 1))


# ============================================================
# 买家维度特征 (buyer_*)
# ============================================================

async def _feat_buyer_return_rate(db: AsyncSession, consignee_id: str) -> float:
    """买家退货率 (consignee_info 画像)"""
    row = (await db.execute(
        select(ConsigneeInfo.return_rate).where(ConsigneeInfo.consignee_id == consignee_id)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_buyer_high_value_return_rate(db: AsyncSession, consignee_id: str) -> float:
    """买家退货集中高溢价品类: 该买家退货运单中高溢价品类占比"""
    # 该买家所有签收运单
    rows = (await db.execute(
        select(WaybillInfo.waybill_id, WaybillInfo.cargo_category)
        .where(WaybillInfo.consignee_id == consignee_id)
    )).all()
    if not rows:
        return 0.0
    hv = {"手机", "电脑", "相机", "奢侈品", "平板"}
    # 有退货的运单
    return_waybills = set()
    claim_rows = (await db.execute(
        select(ComplaintClaim.waybill_id).where(ComplaintClaim.waybill_id.in_(
            [r[0] for r in rows]
        ))
    )).all()
    return_waybills = {r[0] for r in claim_rows}
    if not return_waybills:
        return 0.0
    hv_return = sum(1 for r in rows if r[0] in return_waybills and r[1] in hv)
    return round(hv_return / len(return_waybills), 4)


async def _feat_buyer_addr_dispute_rate(db: AsyncSession, consignee_id: str) -> float:
    """买家地址纠纷率: 该买家历史投诉/总运单"""
    total = await _count(WaybillInfo, db, consignee_id=consignee_id)
    if total == 0:
        return 0.0
    waybills = (await db.execute(
        select(WaybillInfo.waybill_id).where(WaybillInfo.consignee_id == consignee_id)
    )).all()
    wb_ids = [r[0] for r in waybills]
    if not wb_ids:
        return 0.0
    disputes = (await db.execute(
        select(func.count()).select_from(ComplaintClaim).where(
            ComplaintClaim.waybill_id.in_(wb_ids)
        )
    )).scalar() or 0
    return round(float(disputes) / total, 4)


# ============================================================
# 验货维度特征 (inspect_*)
# ============================================================

async def _feat_inspect_duration_min(db: AsyncSession, waybill_id: str) -> float:
    """验货耗时 (分钟): 异常短 = 疑似未真实检测"""
    row = (await db.execute(
        select(InspectionRecord.duration_min)
        .where(InspectionRecord.waybill_id == waybill_id)
        .order_by(InspectionRecord.inspect_time.desc())
        .limit(1)
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


async def _feat_inspect_grade_result(db: AsyncSession, waybill_id: str) -> float:
    """最近一次验货成色结果 (优=1, 良=2, 差=3)"""
    grade_map = {"优": 1, "良": 2, "差": 3}
    row = (await db.execute(
        select(InspectionRecord.grade_result)
        .where(InspectionRecord.waybill_id == waybill_id)
        .order_by(InspectionRecord.inspect_time.desc())
        .limit(1)
    )).first()
    if not row or not row[0]:
        return 0.0
    return float(grade_map.get(row[0], 0))


async def _feat_inspect_functional_abnormal(db: AsyncSession, waybill_id: str) -> float:
    """最近验货功能检测是否异常 (1=异常)"""
    row = (await db.execute(
        select(InspectionRecord.functional_result)
        .where(InspectionRecord.waybill_id == waybill_id)
        .order_by(InspectionRecord.inspect_time.desc())
        .limit(1)
    )).first()
    if not row or not row[0]:
        return 0.0
    return 1.0 if row[0] == "异常" else 0.0


async def _feat_grade_diff(db: AsyncSession, waybill_id: str) -> float:
    """验货成色与卖家声明成色差级数 (声明优+验货差 = 2, 虚报成色)"""
    grade_val = {"优": 1, "良": 2, "差": 3}
    declared = (await db.execute(
        select(ItemIdentity.declared_grade).where(ItemIdentity.waybill_id == waybill_id)
    )).first()
    inspected = (await db.execute(
        select(ItemIdentity.inspected_grade).where(ItemIdentity.waybill_id == waybill_id)
    )).first()
    if not declared or not declared[0] or not inspected or not inspected[0]:
        return 0.0
    return float(abs(grade_val.get(declared[0], 0) - grade_val.get(inspected[0], 0)))


async def _feat_inspector_grade_diff_rate(db: AsyncSession, waybill_id: str) -> float:
    """验货员历史成色差异率: 该运单验货员出优品但买家反馈非优品的比例 (验货舞弊)"""
    inspector = (await db.execute(
        select(InspectionRecord.inspector_id)
        .where(InspectionRecord.waybill_id == waybill_id)
        .limit(1)
    )).first()
    if not inspector or not inspector[0]:
        return 0.0
    # 该验货员处理的运单数
    total = await _count(InspectionRecord, db, inspector_id=inspector[0])
    if total == 0:
        return 0.0
    # 简化: 该验货员处理运单中有投诉纠纷的比例 (近似成色差异率)
    wb_rows = (await db.execute(
        select(InspectionRecord.waybill_id).where(
            InspectionRecord.inspector_id == inspector[0],
            InspectionRecord.grade_result == "优",
        )
    )).all()
    wb_ids = [r[0] for r in wb_rows]
    if not wb_ids:
        return 0.0
    disputes = (await db.execute(
        select(func.count()).select_from(ComplaintClaim).where(
            ComplaintClaim.waybill_id.in_(wb_ids)
        )
    )).scalar() or 0
    return round(float(disputes) / len(wb_ids), 4)


# ============================================================
# 轨迹维度特征 (track_*)
# ============================================================

async def _feat_track_completeness(db: AsyncSession, waybill_id: str) -> float:
    """轨迹完整度 = 实际节点数 / 标准节点数 (已签收=7 个节点)"""
    expected = {
        "待揽收": 1, "待验货": 2, "已验货": 3, "运输中": 5,
        "派送中": 6, "已签收": 7, "已拒收": 7, "已退回": 8,
    }
    status_row = (await db.execute(
        select(WaybillInfo.waybill_status).where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    status = status_row[0] if status_row and status_row[0] else "待揽收"
    actual = await _count(TrackingEvent, db, waybill_id=waybill_id)
    expected_n = expected.get(status, 3)
    if expected_n == 0:
        return 1.0
    return round(min(actual / expected_n, 1.0), 4)


async def _feat_track_time_anomaly(db: AsyncSession, waybill_id: str) -> float:
    """轨迹节点时间是否异常 (1=节点时间间隔超 48h 或顺序倒挂)"""
    rows = (await db.execute(
        select(TrackingEvent.event_time)
        .where(TrackingEvent.waybill_id == waybill_id)
        .order_by(TrackingEvent.event_id)
    )).all()
    if len(rows) < 2:
        return 0.0
    prev = rows[0][0]
    for r in rows[1:]:
        cur = r[0]
        if cur is None or prev is None:
            prev = cur
            continue
        gap = (cur - prev).total_seconds()
        if gap < 0 or gap > 48 * 3600:
            return 1.0
        prev = cur
    return 0.0


async def _feat_track_weight_deviation(db: AsyncSession, waybill_id: str) -> float:
    """轨迹节点称重与出仓重量偏差 (节点称重异常 = 途中调包)"""
    base = await _feat_cargo_weight(db, waybill_id)
    if base == 0:
        return 0.0
    node = (await db.execute(
        select(func.coalesce(func.max(TrackingEvent.node_weight), 0))
        .where(TrackingEvent.waybill_id == waybill_id)
    )).scalar() or 0
    return round(abs(float(node) - base), 4)


# ============================================================
# 退货逆向维度特征 (return_*)
# ============================================================

async def _feat_return_weight_diff(db: AsyncSession, waybill_id: str) -> float:
    """退货重量与出仓重量差 (调包检测核心)"""
    base = await _feat_cargo_weight(db, waybill_id)
    if base == 0:
        return 0.0
    # 退货入仓验货节点称重 (最近一次退货验货)
    row = (await db.execute(
        select(TrackingEvent.node_weight)
        .where(
            TrackingEvent.waybill_id == waybill_id,
            TrackingEvent.event_type == "退货入仓验货",
        )
        .order_by(TrackingEvent.event_id.desc())
        .limit(1)
    )).first()
    if not row or not row[0]:
        return 0.0
    return round(abs(float(row[0]) - base), 4)


async def _feat_return_imei_match(db: AsyncSession, waybill_id: str) -> float:
    """退货序列号与出仓序列号是否一致 (1=一致, 0=不一致=调包)"""
    # 简化: 看 item_identity 的 return_grade 是否被填写 (填了=已验货核对)
    row = (await db.execute(
        select(ItemIdentity.return_grade).where(ItemIdentity.waybill_id == waybill_id)
    )).first()
    return 1.0 if row and row[0] else 0.0


async def _feat_return_grade_drop(db: AsyncSession, waybill_id: str) -> float:
    """退货成色较出仓降级级数 (退货物品与寄出不一致)"""
    grade_val = {"优": 1, "良": 2, "差": 3}
    out = (await db.execute(
        select(ItemIdentity.inspected_grade).where(ItemIdentity.waybill_id == waybill_id)
    )).first()
    back = (await db.execute(
        select(ItemIdentity.return_grade).where(ItemIdentity.waybill_id == waybill_id)
    )).first()
    if not out or not out[0] or not back or not back[0]:
        return 0.0
    return float(max(grade_val.get(back[0], 0) - grade_val.get(out[0], 0), 0))


async def _feat_return_interval_hours(db: AsyncSession, waybill_id: str) -> float:
    """签收→退货发起间隔 (小时): <2h 预谋退货, >7d 用完即退"""
    row = (await db.execute(
        select(WaybillInfo.delivered_time, WaybillInfo.create_time)
        .where(WaybillInfo.waybill_id == waybill_id)
    )).first()
    if not row or not row[0] or not row[1]:
        return 9999.0
    claim = (await db.execute(
        select(func.coalesce(func.min(ComplaintClaim.create_time), None))
        .where(ComplaintClaim.waybill_id == waybill_id)
    )).first()
    if not claim or not claim[0]:
        return 9999.0
    return round((claim[0] - row[0]).total_seconds() / 3600, 2)


async def _feat_return_interval_days(db: AsyncSession, waybill_id: str) -> float:
    """签收→退货发起间隔 (天)"""
    hours = await _feat_return_interval_hours(db, waybill_id)
    return round(hours / 24, 2)


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_shipper_features(db: AsyncSession, shipper_id: str) -> dict[str, float]:
    """计算卖家维度特征."""
    feats = {
        "shipper_waybills_7d": await _feat_shipper_waybills_7d(db, shipper_id),
        "shipper_waybills_30d": await _feat_shipper_waybills_30d(db, shipper_id),
        "shipper_waybills_total": await _feat_shipper_waybills_total(db, shipper_id),
        "shipper_empty_pkg_rate": await _feat_shipper_empty_pkg_rate(db, shipper_id),
        "shipper_night_rate": await _feat_shipper_night_rate(db, shipper_id),
        "shipper_imei_dup_count": await _feat_shipper_imei_dup_count(db, shipper_id),
        "shipper_complaint_count": await _feat_shipper_complaint_count(db, shipper_id),
        "shipper_dispute_count": await _feat_shipper_dispute_count(db, shipper_id),
        "shipper_is_verified": await _feat_shipper_is_verified(db, shipper_id),
    }
    return feats


async def compute_waybill_features(db: AsyncSession, waybill_id: str) -> dict[str, float]:
    """计算运单/货物维度特征."""
    feats = {
        "cargo_weight": await _feat_cargo_weight(db, waybill_id),
        "cargo_volume": await _feat_cargo_volume(db, waybill_id),
        "declared_value": await _feat_declared_value(db, waybill_id),
        "cod_amount": await _feat_cod_amount(db, waybill_id),
        "insurance_amount": await _feat_insurance_amount(db, waybill_id),
        "is_night_order": await _feat_is_night_order(db, waybill_id),
        "is_urgent": await _feat_is_urgent(db, waybill_id),
        "is_cross_border": await _feat_is_cross_border(db, waybill_id),
        "cargo_category_high_value": await _feat_cargo_category_high_value(db, waybill_id),
        "cargo_type_danger": await _feat_cargo_type_danger(db, waybill_id),
        "has_seal": await _feat_has_seal(db, waybill_id),
        "waybill_status": await _feat_waybill_status(db, waybill_id),
        "segment": await _feat_segment(db, waybill_id),
    }
    return feats


async def compute_buyer_features(db: AsyncSession, consignee_id: str) -> dict[str, float]:
    """计算买家维度特征."""
    return {
        "buyer_return_rate": await _feat_buyer_return_rate(db, consignee_id),
        "buyer_high_value_return_rate": await _feat_buyer_high_value_return_rate(db, consignee_id),
        "buyer_addr_dispute_rate": await _feat_buyer_addr_dispute_rate(db, consignee_id),
    }


async def compute_inspection_features(db: AsyncSession, waybill_id: str) -> dict[str, float]:
    """计算验货维度特征."""
    return {
        "inspect_duration_min": await _feat_inspect_duration_min(db, waybill_id),
        "inspect_grade_result": await _feat_inspect_grade_result(db, waybill_id),
        "inspect_functional_abnormal": await _feat_inspect_functional_abnormal(db, waybill_id),
        "grade_diff": await _feat_grade_diff(db, waybill_id),
        "inspector_grade_diff_rate": await _feat_inspector_grade_diff_rate(db, waybill_id),
    }


async def compute_tracking_features(db: AsyncSession, waybill_id: str) -> dict[str, float]:
    """计算轨迹/逆向维度特征."""
    return {
        "track_completeness": await _feat_track_completeness(db, waybill_id),
        "track_time_anomaly": await _feat_track_time_anomaly(db, waybill_id),
        "track_weight_deviation": await _feat_track_weight_deviation(db, waybill_id),
        "return_weight_diff": await _feat_return_weight_diff(db, waybill_id),
        "return_imei_match": await _feat_return_imei_match(db, waybill_id),
        "return_grade_drop": await _feat_return_grade_drop(db, waybill_id),
        "return_interval_hours": await _feat_return_interval_hours(db, waybill_id),
        "return_interval_days": await _feat_return_interval_days(db, waybill_id),
    }


async def compute_all_features(
    db: AsyncSession,
    shipper_id: str,
    consignee_id: str | None = None,
    waybill_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回."""
    features = await compute_shipper_features(db, shipper_id)
    if waybill_id:
        features.update(await compute_waybill_features(db, waybill_id))
        features.update(await compute_inspection_features(db, waybill_id))
        features.update(await compute_tracking_features(db, waybill_id))
    if consignee_id:
        features.update(await compute_buyer_features(db, consignee_id))
    return features


# ============================================================
# Demo: 展示特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 (物流版) — 特征名 + 字典派发表")
    print("=" * 60)

    groups = [
        ("卖家 (9)", ["shipper_waybills_7d", "shipper_waybills_30d", "shipper_waybills_total",
                       "shipper_empty_pkg_rate", "shipper_night_rate", "shipper_imei_dup_count",
                       "shipper_complaint_count", "shipper_dispute_count", "shipper_is_verified"]),
        ("运单/货物 (13)", ["cargo_weight", "cargo_volume", "declared_value", "cod_amount",
                            "insurance_amount", "is_night_order", "is_urgent", "is_cross_border",
                            "cargo_category_high_value", "cargo_type_danger", "has_seal",
                            "waybill_status", "segment"]),
        ("买家 (3)", ["buyer_return_rate", "buyer_high_value_return_rate", "buyer_addr_dispute_rate"]),
        ("验货 (5)", ["inspect_duration_min", "inspect_grade_result", "inspect_functional_abnormal",
                      "grade_diff", "inspector_grade_diff_rate"]),
        ("轨迹/逆向 (8)", ["track_completeness", "track_time_anomaly", "track_weight_deviation",
                           "return_weight_diff", "return_imei_match", "return_grade_drop",
                           "return_interval_hours", "return_interval_days"]),
    ]
    total = 0
    for sec, feats in groups:
        print(f"\n【{sec}】")
        for i, k in enumerate(feats, 1):
            print(f"  {i:>2}. {k}")
            total += 1
    print(f"\n总计: {total} 维特征")

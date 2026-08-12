"""
特征工程模块 (物流版): 通过 ORM 查询业务数据, 计算 25 个物流风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_*      = 用户维度特征 (寄件人)
  shipment_*  = 运单维度特征
  addr_*      = 收件地址维度特征

三大特征族:
  用户 (14): 寄件频率 / COD 拒收 / 危险品 / 实名 / 价值 / 重量 / 多地址
  运单 (8):  重量 / 物品种类 / 危险品与瞒报 / 申报价值 / COD 金额 / 跨境 / 夜间
  地址 (3):  地址数 / 省份数 / 新地址
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Address, Shipment, ShipmentItem, UserInfo


# 危险品类别 (运单物品明细里命中即视为含危险品)
DANGEROUS_CATEGORIES = ("电池", "液体", "化学品")


async def _count(db: AsyncSession, model, **filters) -> float:
    """SELECT COUNT(*) FROM model WHERE filters."""
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _count_since(db: AsyncSession, model, col, since: datetime, **filters) -> float:
    """SELECT COUNT(*) ... WHERE col >= since AND filters."""
    stmt = select(func.count()).select_from(model)
    stmt = stmt.where(col >= since)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(db: AsyncSession, model, col_name: str, **filters) -> float:
    """SELECT COALESCE(SUM(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 用户维度特征 (14 个)
# ============================================================

async def _feat_user_shipment_count(db: AsyncSession, user_id: str) -> float:
    """历史寄件总数"""
    return await _count(db, Shipment, user_id=user_id)


async def _feat_user_shipment_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天寄件数"""
    return await _count_since(db, Shipment, Shipment.create_time,
                              datetime.now() - timedelta(days=7), user_id=user_id)


async def _feat_user_shipment_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天寄件数"""
    return await _count_since(db, Shipment, Shipment.create_time,
                              datetime.now() - timedelta(days=30), user_id=user_id)


async def _feat_user_cod_count(db: AsyncSession, user_id: str) -> float:
    """代收货款 (COD) 单数"""
    return await _count(db, Shipment, user_id=user_id, shipment_type="代收货款")


async def _feat_user_cod_reject_rate(db: AsyncSession, user_id: str) -> float:
    """代收拒收率 = 拒收 COD 单数 / COD 总单数 (无 COD 记录返回 0)"""
    cod_total = await _feat_user_cod_count(db, user_id)
    if cod_total == 0:
        return 0.0
    rejected = await _count(db, Shipment,
                            user_id=user_id, shipment_type="代收货款", is_rejected=1)
    return round(rejected / cod_total, 4)


async def _feat_user_dangerous_count(db: AsyncSession, user_id: str) -> float:
    """含危险品运单数 (运单明细里出现 电池/液体/化学品)"""
    subq = (
        select(ShipmentItem.shipment_id)
        .join(Shipment, ShipmentItem.shipment_id == Shipment.shipment_id)
        .where(
            Shipment.user_id == user_id,
            ShipmentItem.item_category.in_(DANGEROUS_CATEGORIES),
        )
        .subquery()
    )
    stmt = select(func.count()).select_from(subq)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_undeclared_count(db: AsyncSession, user_id: str) -> float:
    """危险品瞒报次数 (含危险品 但 is_dangerous_declared=0)"""
    subq = (
        select(ShipmentItem.shipment_id)
        .join(Shipment, ShipmentItem.shipment_id == Shipment.shipment_id)
        .where(
            Shipment.user_id == user_id,
            ShipmentItem.item_category.in_(DANGEROUS_CATEGORIES),
            Shipment.is_dangerous_declared == 0,
        )
        .subquery()
    )
    stmt = select(func.count()).select_from(subq)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_real_name_status(db: AsyncSession, user_id: str) -> float:
    """实名状态 (0/1), 查不到用户返回 0"""
    row = (await db.execute(
        select(UserInfo.real_name_status).where(UserInfo.user_id == user_id)
    )).first()
    return float(row.real_name_status) if row and row.real_name_status else 0.0


async def _feat_user_account_age_days(db: AsyncSession, user_id: str) -> float:
    """账号年龄 (天)"""
    row = (await db.execute(
        select(UserInfo.account_age_days).where(UserInfo.user_id == user_id)
    )).first()
    return float(row.account_age_days) if row and row.account_age_days else 0.0


async def _feat_user_address_count(db: AsyncSession, user_id: str) -> float:
    """收件地址数量"""
    return await _count(db, Address, user_id=user_id)


async def _feat_user_cross_province_count(db: AsyncSession, user_id: str) -> float:
    """跨省寄件数 (寄出省 != 目的省)"""
    stmt = select(func.count()).select_from(Shipment).where(
        Shipment.user_id == user_id,
        Shipment.origin_province != Shipment.dest_province,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_declared_value(
    db: AsyncSession, user_id: str, total: float | None = None,
) -> float:
    """平均申报价值"""
    if total is None:
        total = await _feat_user_shipment_count(db, user_id)
    if total == 0:
        return 0.0
    amount = await _sum(db, Shipment, "declared_value", user_id=user_id)
    return round(amount / total, 2)


async def _feat_user_avg_weight(
    db: AsyncSession, user_id: str, total: float | None = None,
) -> float:
    """平均寄件重量 (kg)"""
    if total is None:
        total = await _feat_user_shipment_count(db, user_id)
    if total == 0:
        return 0.0
    weight = await _sum(db, Shipment, "weight_kg", user_id=user_id)
    return round(weight / total, 2)


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """取消运单数"""
    return await _count(db, Shipment, user_id=user_id, status="已取消")


# ============================================================
# 运单维度特征 (8 个)
# ============================================================

async def _feat_shipment_weight_kg(db: AsyncSession, shipment_id: str) -> float:
    """运单总重量"""
    row = (await db.execute(
        select(Shipment.weight_kg).where(Shipment.shipment_id == shipment_id)
    )).first()
    return float(row.weight_kg) if row and row.weight_kg else 0.0


async def _feat_shipment_item_count(db: AsyncSession, shipment_id: str) -> float:
    """运单物品行数"""
    return await _count(db, ShipmentItem, shipment_id=shipment_id)


async def _feat_shipment_dangerous_flag(db: AsyncSession, shipment_id: str) -> float:
    """是否含危险品 (1/0): 明细中出现 电池/液体/化学品"""
    cnt = await _count(
        db, ShipmentItem, shipment_id=shipment_id,
    )
    if cnt == 0:
        return 0.0
    stmt = select(func.count()).select_from(ShipmentItem).where(
        ShipmentItem.shipment_id == shipment_id,
        ShipmentItem.item_category.in_(DANGEROUS_CATEGORIES),
    )
    return 1.0 if (await db.execute(stmt)).scalar() else 0.0


async def _feat_shipment_undeclared_flag(db: AsyncSession, shipment_id: str) -> float:
    """是否瞒报 (含危险品但未申报, 1/0)"""
    dangerous = await _feat_shipment_dangerous_flag(db, shipment_id)
    if dangerous == 0:
        return 0.0
    row = (await db.execute(
        select(Shipment.is_dangerous_declared).where(Shipment.shipment_id == shipment_id)
    )).first()
    declared = row.is_dangerous_declared if row else 0
    return 1.0 if not declared else 0.0


async def _feat_shipment_declared_value(db: AsyncSession, shipment_id: str) -> float:
    """申报价值 (元)"""
    row = (await db.execute(
        select(Shipment.declared_value).where(Shipment.shipment_id == shipment_id)
    )).first()
    return float(row.declared_value) if row and row.declared_value else 0.0


async def _feat_shipment_cod_amount(db: AsyncSession, shipment_id: str) -> float:
    """代收货款金额 (元)"""
    row = (await db.execute(
        select(Shipment.cod_amount).where(Shipment.shipment_id == shipment_id)
    )).first()
    return float(row.cod_amount) if row and row.cod_amount else 0.0


async def _feat_shipment_is_cross_border(db: AsyncSession, shipment_id: str) -> float:
    """是否跨境 (1/0): shipment_type='跨境' 或目的国家非空"""
    row = (await db.execute(
        select(Shipment.shipment_type, Shipment.dest_country)
        .where(Shipment.shipment_id == shipment_id)
    )).first()
    if not row:
        return 0.0
    return 1.0 if row.shipment_type == "跨境" or (row.dest_country and row.dest_country != "中国") else 0.0


async def _feat_shipment_is_night(db: AsyncSession, shipment_id: str) -> float:
    """是否夜间寄件 (0-6 点, 1/0)"""
    row = (await db.execute(
        select(Shipment.create_time).where(Shipment.shipment_id == shipment_id)
    )).first()
    if row and row.create_time:
        return 1.0 if 0 <= row.create_time.hour < 6 else 0.0
    return 0.0


# ============================================================
# 地址维度特征 (3 个)
# ============================================================

async def _feat_addr_total_count(db: AsyncSession, user_id: str) -> float:
    """用户收件地址总数"""
    return await _count(db, Address, user_id=user_id)


async def _feat_addr_province_count(db: AsyncSession, user_id: str) -> float:
    """不同收件省份数"""
    stmt = select(func.count(func.distinct(Address.province))).select_from(
        Address
    ).where(Address.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_is_new(
    db: AsyncSession, user_id: str, address_id: str | None
) -> float:
    """是否新地址 (该地址使用次数 <= 1, 1/0)"""
    if not address_id:
        return 0.0
    row = (await db.execute(
        select(Address.use_count).where(
            Address.address_id == address_id,
            Address.user_id == user_id,
        )
    )).first()
    if not row:
        return 1.0
    return 1.0 if (row.use_count or 0) <= 1 else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个用户维度特征."""
    total = await _feat_user_shipment_count(db, user_id)

    independent = {
        "user_shipment_7d": _feat_user_shipment_7d,
        "user_shipment_30d": _feat_user_shipment_30d,
        "user_cod_count": _feat_user_cod_count,
        "user_cod_reject_rate": _feat_user_cod_reject_rate,
        "user_dangerous_count": _feat_user_dangerous_count,
        "user_undeclared_count": _feat_user_undeclared_count,
        "user_real_name_status": _feat_user_real_name_status,
        "user_account_age_days": _feat_user_account_age_days,
        "user_address_count": _feat_user_address_count,
        "user_cross_province_count": _feat_user_cross_province_count,
        "user_cancel_count": _feat_user_cancel_count,
    }
    features = {name: await fn(db, user_id) for name, fn in independent.items()}
    features["user_shipment_count"] = total
    # 派生特征复用 total, 避免重复查 SQL
    features["user_avg_declared_value"] = await _feat_user_avg_declared_value(db, user_id, total)
    features["user_avg_weight"] = await _feat_user_avg_weight(db, user_id, total)
    return features


async def compute_shipment_features(db: AsyncSession, shipment_id: str) -> dict[str, float]:
    """计算 8 个运单维度特征."""
    feat_funcs = {
        "shipment_weight_kg": _feat_shipment_weight_kg,
        "shipment_item_count": _feat_shipment_item_count,
        "shipment_dangerous_flag": _feat_shipment_dangerous_flag,
        "shipment_undeclared_flag": _feat_shipment_undeclared_flag,
        "shipment_declared_value": _feat_shipment_declared_value,
        "shipment_cod_amount": _feat_shipment_cod_amount,
        "shipment_is_cross_border": _feat_shipment_is_cross_border,
        "shipment_is_night": _feat_shipment_is_night,
    }
    return {name: await fn(db, shipment_id) for name, fn in feat_funcs.items()}


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    address_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个地址维度特征."""
    return {
        "addr_total_count": await _feat_addr_total_count(db, user_id),
        "addr_province_count": await _feat_addr_province_count(db, user_id),
        "addr_is_new": await _feat_addr_is_new(db, user_id, address_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    shipment_id: str | None = None,
    address_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部 25 维特征并合并返回."""
    features = await compute_user_features(db, user_id)
    if shipment_id:
        features.update(await compute_shipment_features(db, shipment_id))
    features.update(await compute_address_features(db, user_id, address_id))
    return features

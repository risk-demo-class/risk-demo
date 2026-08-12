"""
特征工程模块: 通过 ORM 查询物流业务数据, 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx   = 用户(寄件人)维度特征
  order_xxx  = 包裹(订单)维度特征
  addr_xxx   = 地址维度特征

【25 维构成】用户 10 + 包裹 8 + 地址 7, 顺序必须与 ml_model.py::FEATURE_COLUMNS 一一对应.
【对齐要求】requirements.md §7: compute_user_features → 寄件人特征, compute_order_features
  → 包裹特征, compute_address_features → 地址特征; 字段名与 FEATURE_COLUMNS (25 维) 对齐.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BlacklistExtra,
    CodTransaction,
    DangerousDeclaration,
    Parcel,
    ReceiverInfo,
    Region,
    RiskBlacklist,
    SenderInfo,
    UserInfo,
)


# ============================================================
# 通用 SQL 工具
# ============================================================

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
# 用户(寄件人)维度特征 (10 个)
# ============================================================

async def _feat_user_account_age_days(db: AsyncSession, user_id: str) -> float:
    """注册至今天数 (天). 无用户记录返回 0."""
    row = (await db.execute(
        select(UserInfo.register_at).where(UserInfo.user_id == user_id)
    )).first()
    if not row or not row.register_at:
        return 0.0
    return max(float((datetime.now() - row.register_at).total_seconds() / 86400.0), 0.0)


async def _feat_user_real_name_verified(db: AsyncSession, user_id: str) -> float:
    """是否实名认证 (0/1): real_name_status='已认证' → 1"""
    row = (await db.execute(
        select(UserInfo.real_name_status).where(UserInfo.user_id == user_id)
    )).first()
    return 1.0 if row and row.real_name_status == "已认证" else 0.0


async def _feat_user_is_enterprise(db: AsyncSession, user_id: str) -> float:
    """是否企业账号 (0/1): account_type='enterprise' → 1"""
    row = (await db.execute(
        select(UserInfo.account_type).where(UserInfo.user_id == user_id)
    )).first()
    return 1.0 if row and row.account_type == "enterprise" else 0.0


async def _feat_user_total_parcel_count(db: AsyncSession, user_id: str) -> float:
    """历史寄件总票数"""
    return await _count(Parcel, db, user_id=user_id)


async def _feat_user_total_parcel_count_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天寄件量"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(Parcel).where(
        Parcel.user_id == user_id,
        Parcel.created_at >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_parcel_count_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天寄件量"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(Parcel).where(
        Parcel.user_id == user_id,
        Parcel.created_at >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_declared_value(
    db: AsyncSession, user_id: str, total_parcels: float | None = None,
) -> float:
    """平均申报价值 (元) = SUM(declared_value) / 总票数. total_parcels 预传可省 1 次 SQL."""
    if total_parcels is None:
        total_parcels = await _feat_user_total_parcel_count(db, user_id)
    if total_parcels == 0:
        return 0.0
    total_value = await _sum(Parcel, "declared_value", db, user_id=user_id)
    return round(total_value / total_parcels, 2)


async def _feat_user_distinct_receiver_count(db: AsyncSession, user_id: str) -> float:
    """不同收件人数量 (DISTINCT receiver_id, 反映收货地址分散度)"""
    stmt = select(func.count(func.distinct(Parcel.receiver_id))).select_from(Parcel).where(
        Parcel.user_id == user_id,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cod_overdue_count(db: AsyncSession, user_id: str) -> float:
    """COD 逾期次数 (cod_status='overdue')"""
    stmt = select(func.count()).select_from(CodTransaction).join(
        Parcel, CodTransaction.parcel_id == Parcel.parcel_id,
    ).where(
        Parcel.user_id == user_id,
        CodTransaction.cod_status == "overdue",
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_blacklist_hit_count(db: AsyncSession, user_id: str) -> float:
    """关联黑名单命中次数.

    统计 2 类黑名单源:
      1. risk_blacklist 的"用户"类型 (value=user_id, 未软删)
      2. blacklist_extra 的 手机号/证件号 类型, 值等于寄件人实名信息
    """
    cnt = 0.0
    # 1. risk_blacklist 用户类型
    stmt = select(func.count()).select_from(RiskBlacklist).where(
        RiskBlacklist.blacklist_type == "用户",
        RiskBlacklist.blacklist_value == user_id,
        RiskBlacklist.deleted_at.is_(None),
    )
    cnt += float((await db.execute(stmt)).scalar() or 0)
    # 2. blacklist_extra: 手机号 + 证件号 (来自 sender_info, sender_id == user_id)
    sender = (await db.execute(
        select(SenderInfo.phone, SenderInfo.id_number).where(SenderInfo.sender_id == user_id)
    )).first()
    if sender:
        for val in (sender.phone, sender.id_number):
            if not val:
                continue
            sub = select(func.count()).select_from(BlacklistExtra).where(
                BlacklistExtra.type.in_(["phone", "id_number"]),
                BlacklistExtra.value == val,
            )
            cnt += float((await db.execute(sub)).scalar() or 0)
    return cnt


# ============================================================
# 包裹(订单)维度特征 (8 个)
# ============================================================

async def _feat_order_weight_kg(db: AsyncSession, parcel_id: str) -> float:
    """包裹重量 (kg)"""
    row = (await db.execute(
        select(Parcel.weight_kg).where(Parcel.parcel_id == parcel_id)
    )).first()
    return float(row.weight_kg) if row and row.weight_kg is not None else 0.0


async def _feat_order_declared_value(db: AsyncSession, parcel_id: str) -> float:
    """申报价值 (元)"""
    row = (await db.execute(
        select(Parcel.declared_value).where(Parcel.parcel_id == parcel_id)
    )).first()
    return float(row.declared_value) if row and row.declared_value is not None else 0.0


async def _feat_order_value_per_kg(
    db: AsyncSession, parcel_id: str, weight: float | None = None, value: float | None = None,
) -> float:
    """单位重量价值 (元/kg) = declared_value / weight_kg, 防 0 除"""
    if weight is None:
        weight = await _feat_order_weight_kg(db, parcel_id)
    if value is None:
        value = await _feat_order_declared_value(db, parcel_id)
    if weight <= 0:
        return 0.0
    return round(value / weight, 4)


async def _feat_order_piece_count(db: AsyncSession, parcel_id: str) -> float:
    """货物件数"""
    row = (await db.execute(
        select(Parcel.piece_count).where(Parcel.parcel_id == parcel_id)
    )).first()
    return float(row.piece_count) if row and row.piece_count is not None else 0.0


async def _feat_order_is_international(db: AsyncSession, parcel_id: str) -> float:
    """是否国际件 (0/1)"""
    row = (await db.execute(
        select(Parcel.is_international).where(Parcel.parcel_id == parcel_id)
    )).first()
    return 1.0 if row and row.is_international else 0.0


async def _feat_order_is_dangerous_declared(db: AsyncSession, parcel_id: str) -> float:
    """是否申报危险品 (0/1): 存在 dangerous_declaration 记录"""
    stmt = select(func.count()).select_from(DangerousDeclaration).where(
        DangerousDeclaration.parcel_id == parcel_id,
    )
    return 1.0 if (await db.execute(stmt)).scalar() else 0.0


async def _feat_order_has_cod(db: AsyncSession, parcel_id: str) -> float:
    """是否代收货款 (0/1): 存在 cod_transaction 记录"""
    stmt = select(func.count()).select_from(CodTransaction).where(
        CodTransaction.parcel_id == parcel_id,
    )
    return 1.0 if (await db.execute(stmt)).scalar() else 0.0


async def _feat_order_cod_amount(db: AsyncSession, parcel_id: str) -> float:
    """COD 金额 (元, 无则 0)"""
    return await _sum(CodTransaction, "amount", db, parcel_id=parcel_id)


# ============================================================
# 地址维度特征 (7 个)
# ============================================================

async def _feat_addr_sender_province_code(db: AsyncSession, parcel_id: str) -> float:
    """寄件省份编码 (region.province_code, 查不到返回 0)"""
    stmt = select(Region.province_code).select_from(Parcel).join(
        SenderInfo, Parcel.sender_id == SenderInfo.sender_id,
    ).join(
        Region, SenderInfo.sender_province == Region.province,
    ).where(Parcel.parcel_id == parcel_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_receiver_province_code(db: AsyncSession, parcel_id: str) -> float:
    """收件省份编码 (region.province_code, 查不到返回 0)"""
    stmt = select(Region.province_code).select_from(Parcel).join(
        ReceiverInfo, Parcel.receiver_id == ReceiverInfo.receiver_id,
    ).join(
        Region, ReceiverInfo.receiver_province == Region.province,
    ).where(Parcel.parcel_id == parcel_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_is_cross_province(db: AsyncSession, parcel_id: str) -> float:
    """是否跨省 (0/1): 寄件省份 != 收件省份"""
    stmt = select(SenderInfo.sender_province, ReceiverInfo.receiver_province).select_from(
        Parcel,
    ).join(
        SenderInfo, Parcel.sender_id == SenderInfo.sender_id,
    ).join(
        ReceiverInfo, Parcel.receiver_id == ReceiverInfo.receiver_id,
    ).where(Parcel.parcel_id == parcel_id)
    row = (await db.execute(stmt)).first()
    if not row or not row.sender_province or not row.receiver_province:
        return 0.0
    return 1.0 if row.sender_province != row.receiver_province else 0.0


async def _feat_addr_same_address_sender_count_24h(
    db: AsyncSession, user_id: str, receiver_id: str,
) -> float:
    """同一收件地址 24h 内不同寄件人数量 (DISTINCT user_id).

    高危信号: 同一收件地址短时间内涌入大量不同寄件人 → 疑似"二程改派 / 刷单 / 黑产收货".
    """
    since = datetime.now() - timedelta(hours=24)
    stmt = select(func.count(func.distinct(Parcel.user_id))).select_from(Parcel).where(
        Parcel.receiver_id == receiver_id,
        Parcel.created_at >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_addr_address_blacklist_hit(db: AsyncSession, address: str) -> float:
    """收件地址是否命中黑名单 (0/1): risk_blacklist(地址) 或 blacklist_extra(address)"""
    if not address:
        return 0.0
    rb = select(func.count()).select_from(RiskBlacklist).where(
        RiskBlacklist.blacklist_type == "地址",
        RiskBlacklist.blacklist_value == address,
        RiskBlacklist.deleted_at.is_(None),
    )
    if (await db.execute(rb)).scalar():
        return 1.0
    be = select(func.count()).select_from(BlacklistExtra).where(
        BlacklistExtra.type == "address",
        BlacklistExtra.value == address,
    )
    return 1.0 if (await db.execute(be)).scalar() else 0.0


async def _feat_addr_is_proxy_received(db: AsyncSession, receiver_id: str) -> float:
    """收件人是否代签收 (0/1)"""
    row = (await db.execute(
        select(ReceiverInfo.is_proxy_received).where(ReceiverInfo.receiver_id == receiver_id)
    )).first()
    return 1.0 if row and row.is_proxy_received else 0.0


async def _feat_addr_sender_is_blacklisted(db: AsyncSession, sender_id: str) -> float:
    """寄件人是否黑名单 (0/1, sender_info.is_blacklisted)"""
    row = (await db.execute(
        select(SenderInfo.is_blacklisted).where(SenderInfo.sender_id == sender_id)
    )).first()
    return 1.0 if row and row.is_blacklisted else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 10 个用户(寄件人)维度特征.

    【P5 优化】先 await 1 次 _feat_user_total_parcel_count, 传给 _feat_user_avg_declared_value
    复用, 避免各自重查 (2 次 SQL → 1 次).
    """
    total_parcels = await _feat_user_total_parcel_count(db, user_id)

    return {
        "user_account_age_days": await _feat_user_account_age_days(db, user_id),
        "user_real_name_verified": await _feat_user_real_name_verified(db, user_id),
        "user_is_enterprise": await _feat_user_is_enterprise(db, user_id),
        "user_total_parcel_count": total_parcels,
        "user_total_parcel_count_30d": await _feat_user_total_parcel_count_30d(db, user_id),
        "user_total_parcel_count_7d": await _feat_user_total_parcel_count_7d(db, user_id),
        "user_avg_declared_value": await _feat_user_avg_declared_value(db, user_id, total_parcels=total_parcels),
        "user_distinct_receiver_count": await _feat_user_distinct_receiver_count(db, user_id),
        "user_cod_overdue_count": await _feat_user_cod_overdue_count(db, user_id),
        "user_blacklist_hit_count": await _feat_user_blacklist_hit_count(db, user_id),
    }


async def compute_order_features(db: AsyncSession, parcel_id: str) -> dict[str, float]:
    """计算 8 个包裹(订单)维度特征."""
    weight = await _feat_order_weight_kg(db, parcel_id)
    value = await _feat_order_declared_value(db, parcel_id)

    return {
        "order_weight_kg": weight,
        "order_declared_value": value,
        "order_value_per_kg": await _feat_order_value_per_kg(db, parcel_id, weight=weight, value=value),
        "order_piece_count": await _feat_order_piece_count(db, parcel_id),
        "order_is_international": await _feat_order_is_international(db, parcel_id),
        "order_is_dangerous_declared": await _feat_order_is_dangerous_declared(db, parcel_id),
        "order_has_cod": await _feat_order_has_cod(db, parcel_id),
        "order_cod_amount": await _feat_order_cod_amount(db, parcel_id),
    }


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    parcel_id: str | None = None,
) -> dict[str, float]:
    """计算 7 个地址维度特征.

    parcel_id 为空 (只算用户维度, 如 agent 查画像) → 全部返回 0,
    保证 compute_all_features 永远产出完整 25 键.
    """
    zero = {
        "addr_sender_province": 0.0,
        "addr_receiver_province": 0.0,
        "addr_is_cross_province": 0.0,
        "addr_same_address_sender_count_24h": 0.0,
        "addr_address_blacklist_hit": 0.0,
        "addr_is_proxy_received": 0.0,
        "addr_sender_is_blacklisted": 0.0,
    }
    if not parcel_id:
        return zero

    # 包裹 → 收件人 (地址特征大多挂在收件人上)
    receiver_row = (await db.execute(
        select(Parcel.receiver_id, Parcel.sender_id).where(Parcel.parcel_id == parcel_id)
    )).first()
    if not receiver_row:
        return zero
    receiver_id = receiver_row.receiver_id
    sender_id = receiver_row.sender_id

    receiver = (await db.execute(
        select(ReceiverInfo.address, ReceiverInfo.receiver_id).where(
            ReceiverInfo.receiver_id == receiver_id,
        )
    )).first()

    return {
        "addr_sender_province": await _feat_addr_sender_province_code(db, parcel_id),
        "addr_receiver_province": await _feat_addr_receiver_province_code(db, parcel_id),
        "addr_is_cross_province": await _feat_addr_is_cross_province(db, parcel_id),
        "addr_same_address_sender_count_24h": await _feat_addr_same_address_sender_count_24h(db, user_id, receiver_id),
        "addr_address_blacklist_hit": await _feat_addr_address_blacklist_hit(db, receiver.address if receiver else None),
        "addr_is_proxy_received": await _feat_addr_is_proxy_received(db, receiver_id),
        "addr_sender_is_blacklisted": await _feat_addr_sender_is_blacklisted(db, sender_id),
    }


# 包裹维度零值 (parcel_id 为空时填 0, 保证 compute_all_features 恒为 25 键)
_ORDER_ZERO_FEATURES = {
    "order_weight_kg": 0.0,
    "order_declared_value": 0.0,
    "order_value_per_kg": 0.0,
    "order_piece_count": 0.0,
    "order_is_international": 0.0,
    "order_is_dangerous_declared": 0.0,
    "order_has_cod": 0.0,
    "order_cod_amount": 0.0,
}


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    parcel_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部 25 维特征并合并返回 (固定 25 键, 跟 FEATURE_COLUMNS 对齐).

    parcel_id 为空 → 包裹维度填 0, 地址维度也全 0, 保证 10+8+7=25 键不缺失.
    """
    features = await compute_user_features(db, user_id)
    if parcel_id:
        features.update(await compute_order_features(db, parcel_id))
    else:
        features.update(_ORDER_ZERO_FEATURES)
    features.update(await compute_address_features(db, user_id, parcel_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python -m app.engine.feature
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 — 25 维特征名 + 字典派发表")
    print("=" * 60)

    # 25 维特征按域分组 (跟 engine/feature.py 的 3 个 compute_* 函数对应)
    user_feats = [
        ("user_account_age_days",        "注册至今天数(天)"),
        ("user_real_name_verified",      "是否实名认证 (0/1)"),
        ("user_is_enterprise",           "是否企业账号 (0/1)"),
        ("user_total_parcel_count",      "历史寄件总票数"),
        ("user_total_parcel_count_30d",  "近 30 天寄件量"),
        ("user_total_parcel_count_7d",   "近 7 天寄件量"),
        ("user_avg_declared_value",      "平均申报价值(元)"),
        ("user_distinct_receiver_count", "不同收件人数"),
        ("user_cod_overdue_count",       "COD 逾期次数"),
        ("user_blacklist_hit_count",     "关联黑名单命中次数"),
    ]
    order_feats = [
        ("order_weight_kg",             "包裹重量(kg)"),
        ("order_declared_value",        "申报价值(元)"),
        ("order_value_per_kg",          "单位重量价值(元/kg)"),
        ("order_piece_count",           "货物件数"),
        ("order_is_international",      "是否国际件 (0/1)"),
        ("order_is_dangerous_declared", "是否申报危险品 (0/1)"),
        ("order_has_cod",               "是否代收货款 (0/1)"),
        ("order_cod_amount",            "COD 金额(元)"),
    ]
    addr_feats = [
        ("addr_sender_province",                "寄件省份编码(1-34)"),
        ("addr_receiver_province",              "收件省份编码(1-34)"),
        ("addr_is_cross_province",              "是否跨省 (0/1)"),
        ("addr_same_address_sender_count_24h",  "同一收件地址 24h 内不同寄件人数"),
        ("addr_address_blacklist_hit",          "收件地址是否命中黑名单 (0/1)"),
        ("addr_is_proxy_received",              "是否代签收 (0/1)"),
        ("addr_sender_is_blacklisted",          "寄件人是否黑名单 (0/1)"),
    ]
    all_groups = [("用户 (10)", user_feats), ("包裹 (8)", order_feats), ("地址 (7)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<38} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")

    # P5 优化示例: total_parcel_count 一次查询复用给 avg_declared_value
    print("\n" + "=" * 60)
    print("[P5 优化示例] 1 次 SQL 查 user_total_parcel_count, 复用给 avg_declared_value:")
    print("  compute_user_features(db, user_id) 内部")
    print("    _feat_user_total_parcel_count(db, user_id)               → 1 次 SQL")
    print("    _feat_user_avg_declared_value(...,total_parcels)         → 0 次 SQL (复用)")
    print("  原来 2 个特征 = 2 次 SQL → 现在 2 个 = 1 次 SQL (节省 50%)")

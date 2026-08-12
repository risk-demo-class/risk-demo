"""
电信风控特征工程: 通过 ORM 查询业务表, 计算 30 维风控特征.

【特征族命名规范】前缀对应业务表域, 给 ml_model.FEATURE_COLUMNS 锁定顺序
  card_*   = 号卡维度 (5)   开卡时长/物联网/国际/漫游/状态
  cust_*   = 客户维度 (5)   一证多卡/活体核验/风险标签/渠道数
  cdr_*    = 通信行为 (9)   短时高频/固定点位/短通话/国际来电/夜间/凌晨
  dev_*    = 设备维度 (3)   一机多卡/机卡异地/频繁换机
  channel_*= 渠道维度 (2)   批量开卡/代理商
  iot_*    = 物联网维度 (2) 流量突增/机卡分离
  bill_*   = 账单维度 (2)   高频充值/转出比例 (话费套现)
  grp_*    = 集团维度 (2)   子号数量/异常标记 (集团诈骗)

【对齐监管】
  cust_card_count   → 反诈法第10条 (开卡数量核验)
  cdr_intl_incoming → 反诈法第16条 (国际来电识别)
  iot_data_burst    → 反诈法第12条 (物联网卡监测)
  channel_open_count→ 反诈法第9条  (代理商管理)
  bill_outflow_ratio→ 反诈法第14条 (资金监测/反洗钱)
"""
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    TelecomBillingRecord, TelecomCard, TelecomCardDeviceBinding, TelecomCdr,
    TelecomCell, TelecomChannel, TelecomCustomer, TelecomDataUsage,
    TelecomGroupCustomer, TelecomIotCard, TelecomServiceOrder,
)

# 漫游状态 → 数值编码 (有序: 越严越大)
_ROAM_CODE = {"归属地": 0, "省内漫游": 1, "省间漫游": 2, "国际漫游": 3}


# ============================================================
# 号卡维度特征 (5 个)
# ============================================================

async def compute_card_features(db: AsyncSession, msisdn: str) -> dict[str, float]:
    """号卡本身属性. 新卡/物联网/国际/漫游/状态."""
    row = (await db.execute(
        select(
            TelecomCard.open_time, TelecomCard.is_iot, TelecomCard.intl_call_enabled,
            TelecomCard.roam_status, TelecomCard.card_status, TelecomCard.open_province,
            TelecomCard.current_imei, TelecomCard.customer_id, TelecomCard.open_channel_id,
        ).where(TelecomCard.msisdn == msisdn)
    )).first()
    if not row:
        return {k: 0.0 for k in (
            "card_age_days", "card_is_iot", "card_intl_enabled",
            "card_roam_type_code", "card_status_normal",
        )}
    now = datetime.now()
    age_days = max((now - row.open_time).total_seconds() / 86400.0, 0.0) if row.open_time else 0.0
    return {
        "card_age_days": round(age_days, 2),
        "card_is_iot": float(row.is_iot),
        "card_intl_enabled": float(row.intl_call_enabled),
        "card_roam_type_code": float(_ROAM_CODE.get(row.roam_status, 0)),
        "card_status_normal": 1.0 if row.card_status == "正常" else 0.0,
    }


# ============================================================
# 客户维度特征 (5 个) — 一证多卡核验 (反诈法第10条)
# ============================================================

async def compute_customer_features(db: AsyncSession, customer_id: str) -> dict[str, float]:
    """客户实名 + 一证多卡 + 活体核验 + 风险标签."""
    cust = (await db.execute(
        select(TelecomCustomer.face_verify_status, TelecomCustomer.risk_tag)
        .where(TelecomCustomer.customer_id == customer_id)
    )).first()

    card_count = float((await db.execute(
        select(func.count()).select_from(TelecomCard).where(TelecomCard.customer_id == customer_id)
    )).scalar() or 0)

    channel_count = float((await db.execute(
        select(func.count(func.distinct(TelecomCard.open_channel_id)))
        .where(TelecomCard.customer_id == customer_id)
    )).scalar() or 0)

    face_ok = 1.0 if (cust and cust.face_verify_status == "通过") else 0.0
    risk_high = 1.0 if (cust and cust.risk_tag == "高风险") else 0.0
    return {
        "cust_card_count": card_count,
        "cust_id_multi_card_flag": 1.0 if card_count >= 5 else 0.0,
        "cust_face_verify_passed": face_ok,
        "cust_risk_tag_high_flag": risk_high,
        "cust_open_channel_count": channel_count,
    }


# ============================================================
# 通信行为特征 (8 个) — GOIP/猫池/国际诈骗识别核心
# ============================================================

async def compute_cdr_features(db: AsyncSession, msisdn: str) -> dict[str, float]:
    """CDR 聚合: 短时高频主叫/固定点位/短通话/国际来电/夜间/平均时长."""
    now = datetime.now()
    h1 = now - timedelta(hours=1)
    h24 = now - timedelta(hours=24)

    # 主叫聚合 (近 1h / 24h) + 不同基站数 (近 1h)
    out_1h_row = (await db.execute(
        select(
            func.count().label("cnt"),
            func.count(func.distinct(TelecomCdr.cell_id)).label("cells"),
        ).where(TelecomCdr.calling_no == msisdn, TelecomCdr.start_time >= h1)
    )).first()
    out_1h = float(out_1h_row.cnt or 0) if out_1h_row else 0.0
    distinct_cell_1h = float(out_1h_row.cells or 0) if out_1h_row else 0.0

    out_24h = float((await db.execute(
        select(func.count()).where(
            TelecomCdr.calling_no == msisdn, TelecomCdr.start_time >= h24,
        )
    )).scalar() or 0)

    in_24h = float((await db.execute(
        select(func.count()).where(
            TelecomCdr.called_no == msisdn, TelecomCdr.start_time >= h24,
        )
    )).scalar() or 0)

    intl_in_24h = float((await db.execute(
        select(func.count()).where(
            TelecomCdr.called_no == msisdn, TelecomCdr.roam_type == "国际",
            TelecomCdr.start_time >= h24,
        )
    )).scalar() or 0)

    # 短通话占比 / 夜间占比 / 平均时长 / 凌晨1h呼叫数 (全量主叫)
    night_1h = now - timedelta(hours=1)
    agg = (await db.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(
                case((TelecomCdr.duration < 10, 1), else_=0)
            ), 0).label("short_cnt"),
            func.coalesce(func.sum(
                case((func.extract("hour", TelecomCdr.start_time) < 6, 1), else_=0)
            ), 0).label("night_cnt"),
            func.coalesce(func.avg(TelecomCdr.duration), 0).label("avg_dur"),
        ).where(TelecomCdr.calling_no == msisdn)
    )).first()

    # 凌晨 1h 内主叫次数 (R015: 凌晨密集呼叫)
    night_call_1h = float((await db.execute(
        select(func.count()).where(
            TelecomCdr.calling_no == msisdn,
            func.extract("hour", TelecomCdr.start_time) < 6,
            TelecomCdr.start_time >= night_1h,
        )
    )).scalar() or 0)
    total = float(agg.total or 0)
    short_ratio = float(agg.short_cnt or 0) / total if total > 0 else 0.0
    night_ratio = float(agg.night_cnt or 0) / total if total > 0 else 0.0
    avg_dur = float(agg.avg_dur or 0)

    return {
        "cdr_out_count_1h": out_1h,
        "cdr_out_count_24h": out_24h,
        "cdr_in_count_24h": in_24h,
        "cdr_distinct_cell_1h": distinct_cell_1h,
        "cdr_short_call_ratio": round(short_ratio, 4),
        "cdr_intl_incoming_24h": intl_in_24h,
        "cdr_night_call_ratio": round(night_ratio, 4),
        "cdr_avg_duration_sec": round(avg_dur, 2),
        "cdr_night_call_count": night_call_1h,
    }


# ============================================================
# 设备维度特征 (3 个) — 猫池/机卡异地/频繁换机
# ============================================================

async def compute_device_features(db: AsyncSession, msisdn: str) -> dict[str, float]:
    """设备指纹: 一机多卡/机卡异地/换机频率."""
    card = (await db.execute(
        select(TelecomCard.current_imei, TelecomCard.open_province)
        .where(TelecomCard.msisdn == msisdn)
    )).first()

    cards_on_imei = 0.0
    mismatch = 0.0
    if card and card.current_imei:
        cards_on_imei = float((await db.execute(
            select(func.count()).where(TelecomCard.current_imei == card.current_imei)
        )).scalar() or 0)
        # 机卡异地: 最近一次通话基站省 != 开卡省
        last_cdr = (await db.execute(
            select(TelecomCdr.cell_id).where(
                TelecomCdr.calling_no == msisdn
            ).order_by(TelecomCdr.start_time.desc()).limit(1)
        )).first()
        if last_cdr and last_cdr.cell_id:
            cell_prov = (await db.execute(
                select(TelecomCell.province).where(TelecomCell.cell_id == last_cdr.cell_id)
            )).first()
            if cell_prov and cell_prov.province and card.open_province \
                    and cell_prov.province != card.open_province:
                mismatch = 1.0

    since_30d = datetime.now() - timedelta(days=30)
    binding_changes = float((await db.execute(
        select(func.count()).where(
            TelecomCardDeviceBinding.msisdn == msisdn,
            TelecomCardDeviceBinding.bind_time >= since_30d,
        )
    )).scalar() or 0)

    return {
        "dev_cards_on_imei": cards_on_imei,
        "dev_card_imei_mismatch_flag": mismatch,
        "dev_binding_changes_30d": binding_changes,
    }


# ============================================================
# 渠道维度特征 (2 个) — 批量开卡/代理商 (反诈法第9条)
# ============================================================

async def compute_channel_features(db: AsyncSession, channel_id: str) -> dict[str, float]:
    """渠道: 近 1h 开卡量 + 是否代理商."""
    ch = (await db.execute(
        select(TelecomChannel.channel_type).where(TelecomChannel.channel_id == channel_id)
    )).first()
    is_agent = 1.0 if (ch and ch.channel_type == "代理商") else 0.0

    h1 = datetime.now() - timedelta(hours=1)
    open_1h = float((await db.execute(
        select(func.count()).where(
            TelecomServiceOrder.channel_id == channel_id,
            TelecomServiceOrder.order_type == "新开户",
            TelecomServiceOrder.order_time >= h1,
        )
    )).scalar() or 0)
    return {
        "channel_open_count_1h": open_1h,
        "channel_is_agent_flag": is_agent,
    }


# ============================================================
# 物联网维度特征 (2 个) — 流量突增/机卡分离 (反诈法第12条)
# ============================================================

async def compute_iot_features(db: AsyncSession, msisdn: str) -> dict[str, float]:
    """物联网卡: 流量突增倍数 + 机卡分离 (非 iot 卡返回 0)."""
    card = (await db.execute(
        select(TelecomCard.is_iot, TelecomCard.current_imei)
        .where(TelecomCard.msisdn == msisdn)
    )).first()
    if not card or not card.is_iot:
        return {"iot_data_burst_ratio": 0.0, "iot_card_device_unbound_flag": 0.0}

    iot = (await db.execute(
        select(TelecomIotCard.bound_device_imei).where(TelecomIotCard.msisdn == msisdn)
    )).first()
    # 机卡分离: 绑定 IMEI 为空 或 跟当前 IMEI 不一致
    unbound = 0.0
    if not iot or not iot.bound_device_imei:
        unbound = 1.0
    elif card.current_imei and iot.bound_device_imei != card.current_imei:
        unbound = 1.0

    # 流量突增: 当天流量 / 近 7 天均值
    rows = (await db.execute(
        select(TelecomDataUsage.data_volume_mb, TelecomDataUsage.usage_date)
        .where(TelecomDataUsage.msisdn == msisdn)
        .order_by(TelecomDataUsage.usage_date.desc()).limit(7)
    )).all()
    if not rows:
        return {"iot_data_burst_ratio": 0.0, "iot_card_device_unbound_flag": unbound}
    today_vol = float(rows[0].data_volume_mb or 0)
    hist = [float(r.data_volume_mb or 0) for r in rows[1:]] if len(rows) > 1 else [today_vol]
    hist_avg = sum(hist) / len(hist) if hist else 0.0
    burst = round(today_vol / hist_avg, 2) if hist_avg > 0 else 0.0
    return {
        "iot_data_burst_ratio": burst,
        "iot_card_device_unbound_flag": unbound,
    }


# ============================================================
# 账单维度特征 (2 个) — 话费套现 (反诈法第14条)
# ============================================================

async def compute_billing_features(db: AsyncSession, msisdn: str) -> dict[str, float]:
    """话费账单: 近 1h 充值次数 + 转出金额占比 (识别套现)."""
    now = datetime.now()
    h1 = now - timedelta(hours=1)

    recharge_1h = float((await db.execute(
        select(func.count()).where(
            TelecomBillingRecord.msisdn == msisdn,
            TelecomBillingRecord.bill_type == "充值",
            TelecomBillingRecord.create_time >= h1,
        )
    )).scalar() or 0)

    # 全量统计: 转出总额 / (消费总额 + 转出总额)
    outflow = float((await db.execute(
        select(func.coalesce(func.sum(TelecomBillingRecord.amount), 0)).where(
            TelecomBillingRecord.msisdn == msisdn,
            TelecomBillingRecord.bill_type == "转出",
        )
    )).scalar() or 0)

    consume = float((await db.execute(
        select(func.coalesce(func.sum(TelecomBillingRecord.amount), 0)).where(
            TelecomBillingRecord.msisdn == msisdn,
            TelecomBillingRecord.bill_type == "消费",
        )
    )).scalar() or 0)

    total_out = outflow + consume
    outflow_ratio = round(outflow / total_out, 4) if total_out > 0 else 0.0

    return {
        "bill_recharge_count_1h": recharge_1h,
        "bill_outflow_ratio": outflow_ratio,
    }


# ============================================================
# 集团维度特征 (2 个) — 集团子号异常
# ============================================================

async def compute_group_features(db: AsyncSession, customer_id: str) -> dict[str, float]:
    """集团客户: 子号数量 + 子号异常标记."""
    group = (await db.execute(
        select(TelecomGroupCustomer.group_id).where(
            TelecomGroupCustomer.customer_id == customer_id,
            TelecomGroupCustomer.group_status == "正常",
        )
    )).first()

    if not group:
        return {"grp_sub_count": 0.0, "grp_sub_abnormal_flag": 0.0}

    group_id = group.group_id
    # 子号数 = 该客户名下号卡数 (含主号)
    sub_count = float((await db.execute(
        select(func.count()).select_from(TelecomCard).where(
            TelecomCard.customer_id == customer_id,
        )
    )).scalar() or 0)

    # 子号异常: 子号数 >= 8 且客户有风险标签
    cust = (await db.execute(
        select(TelecomCustomer.risk_tag).where(TelecomCustomer.customer_id == customer_id)
    )).first()
    abnormal = 0.0
    if sub_count >= 8 and cust and cust.risk_tag in ("高风险", "中风险"):
        abnormal = 1.0

    return {
        "grp_sub_count": sub_count,
        "grp_sub_abnormal_flag": abnormal,
    }


# ============================================================
# 汇总: 一次性算全 30 维
# ============================================================

async def compute_all_features(db: AsyncSession, msisdn: str) -> dict[str, float]:
    """计算全部 30 维特征 (顺序跟 ml_model.FEATURE_COLUMNS 一致).

    号卡是核心枢纽: 从 card 取 customer_id / open_channel_id, 再派生其他族.
    """
    card = (await db.execute(
        select(TelecomCard.customer_id, TelecomCard.open_channel_id)
        .where(TelecomCard.msisdn == msisdn)
    )).first()
    if not card:
        return {}

    features: dict[str, float] = {}
    features.update(await compute_card_features(db, msisdn))
    features.update(await compute_customer_features(db, card.customer_id))
    features.update(await compute_cdr_features(db, msisdn))
    features.update(await compute_device_features(db, msisdn))
    features.update(await compute_channel_features(db, card.open_channel_id))
    features.update(await compute_iot_features(db, msisdn))
    features.update(await compute_billing_features(db, msisdn))
    features.update(await compute_group_features(db, card.customer_id))
    return features


# ============================================================
# Demo: 30 维特征清单 (无需 DB)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("电信风控特征工程 — 30 维特征 (7 族)")
    print("=" * 60)
    groups = [
        ("号卡 (5)", [
            ("card_age_days", "开卡至今天数 (新卡风险高)"),
            ("card_is_iot", "是否物联网卡"),
            ("card_intl_enabled", "是否开通国际来去电"),
            ("card_roam_type_code", "漫游状态编码 (0归属/1省内/2省间/3国际)"),
            ("card_status_normal", "号卡状态是否正常"),
        ]),
        ("客户 (5)", [
            ("cust_card_count", "名下号卡数 (一证多卡, 反诈法第10条)"),
            ("cust_id_multi_card_flag", "名下卡数>=5 (0/1)"),
            ("cust_face_verify_passed", "活体核验通过 (0/1)"),
            ("cust_risk_tag_high_flag", "客户风险标签高风险 (0/1)"),
            ("cust_open_channel_count", "开卡渠道数 (多渠道可疑)"),
        ]),
        ("通信行为 (9)", [
            ("cdr_out_count_1h", "近1h主叫次数 (GOIP短时高频)"),
            ("cdr_out_count_24h", "近24h主叫次数"),
            ("cdr_in_count_24h", "近24h被叫次数"),
            ("cdr_distinct_cell_1h", "近1h不同基站数 (固定点位)"),
            ("cdr_short_call_ratio", "短通话(<10s)占比 (诈骗引流)"),
            ("cdr_intl_incoming_24h", "近24h国际来电次数 (反诈法第16条)"),
            ("cdr_night_call_ratio", "夜间(0-6点)通话占比"),
            ("cdr_avg_duration_sec", "平均通话时长(秒)"),
            ("cdr_night_call_count", "凌晨1h内主叫次数 (R015)"),
        ]),
        ("设备 (3)", [
            ("dev_cards_on_imei", "该IMEI绑定号卡数 (猫池, 一机多卡)"),
            ("dev_card_imei_mismatch_flag", "机卡异地 (0/1)"),
            ("dev_binding_changes_30d", "近30天换机次数"),
        ]),
        ("渠道 (2)", [
            ("channel_open_count_1h", "渠道近1h开卡数 (批量开卡, 反诈法第9条)"),
            ("channel_is_agent_flag", "是否代理商 (0/1)"),
        ]),
        ("物联网 (2)", [
            ("iot_data_burst_ratio", "近7天流量突增倍数 (反诈法第12条)"),
            ("iot_card_device_unbound_flag", "机卡分离 (0/1)"),
        ]),
        ("账单 (2)", [
            ("bill_recharge_count_1h", "近1h充值次数 (高频充值, 反诈法第14条)"),
            ("bill_outflow_ratio", "转出金额占比 (话费套现)"),
        ]),
        ("集团 (2)", [
            ("grp_sub_count", "集团子号数量"),
            ("grp_sub_abnormal_flag", "集团子号异常标记 (0/1)"),
        ]),
    ]
    total = 0
    for sec, feats in groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<30} - {desc}")
            total += 1
    print(f"\n总计: {total} 维 (跟 ml_model.FEATURE_COLUMNS 顺序一一对应)")

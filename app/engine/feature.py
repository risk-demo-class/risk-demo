"""
特征工程模块: 通过 ORM 查询业务数据, 计算 25 个风控特征 (医疗版).

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx   = 用户维度特征 (17 个)
  order_xxx  = 业务单维度特征 (8 个, 按事件类型分派)

25 维 = 用户 17 + 业务单 8, 与 ml_model.py FEATURE_COLUMNS 一一对应 (顺序不能乱).
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    DrugOrder,
    Hospital,
    InsuranceClaim,
    Prescription,
    UserInfo,
)


# ============================================================
# 用户维度特征 (17 个)
# ============================================================

async def _feat_user_total_visits(db: AsyncSession, user_id: str) -> float:
    """历史就诊 (挂号) 总数"""
    stmt = select(func.count()).select_from(Appointment).where(Appointment.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visits_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天就诊数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(Appointment).where(
        Appointment.user_id == user_id,
        Appointment.appt_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visits_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天就诊数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(Appointment).where(
        Appointment.user_id == user_id,
        Appointment.appt_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_total_claim_amount(db: AsyncSession, user_id: str) -> float:
    """历史医保结算总金额"""
    stmt = select(func.coalesce(func.sum(InsuranceClaim.total_amount), 0)).where(
        InsuranceClaim.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_claim_count(db: AsyncSession, user_id: str) -> float:
    """医保结算次数"""
    stmt = select(func.count()).select_from(InsuranceClaim).where(InsuranceClaim.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_claim_amount(
    db: AsyncSession, user_id: str, claim_count: float | None = None,
) -> float:
    """平均单次结算金额 = 总金额 / 结算次数"""
    if claim_count is None:
        claim_count = await _feat_user_claim_count(db, user_id)
    if claim_count == 0:
        return 0
    total = await _feat_user_total_claim_amount(db, user_id)
    return round(total / claim_count, 2)


async def _feat_user_max_claim_amount(db: AsyncSession, user_id: str) -> float:
    """最大单笔结算金额"""
    stmt = select(func.coalesce(func.max(InsuranceClaim.total_amount), 0)).where(
        InsuranceClaim.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_claims_1h_hospitals(db: AsyncSession, user_id: str) -> float:
    """近 1 小时结算涉及的不同医院数 (R001 医保卡盗刷核心信号)"""
    since = datetime.now() - timedelta(hours=1)
    stmt = select(func.count(func.distinct(InsuranceClaim.hospital_id))).where(
        InsuranceClaim.user_id == user_id,
        InsuranceClaim.submit_at >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cancel_appt_count(db: AsyncSession, user_id: str) -> float:
    """取消挂号次数 (R003 挂号黄牛核心信号)"""
    stmt = select(func.count()).select_from(Appointment).where(
        Appointment.user_id == user_id,
        Appointment.appt_status == "已取消",
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cancel_appt_rate(
    db: AsyncSession, user_id: str, total_visits: float | None = None,
) -> float:
    """取消挂号率 = 取消次数 / 总就诊数"""
    if total_visits is None:
        total_visits = await _feat_user_total_visits(db, user_id)
    if total_visits == 0:
        return 0
    cancel = await _feat_user_cancel_appt_count(db, user_id)
    return round(cancel / total_visits, 4)


async def _feat_user_rx_count(db: AsyncSession, user_id: str) -> float:
    """处方总数"""
    stmt = select(func.count()).select_from(Prescription).where(Prescription.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_non_self_drug_count(db: AsyncSession, user_id: str) -> float:
    """非本人收药订单数 (收件人 != 患者姓名, R006 药品代购核心信号)"""
    stmt = select(func.count()).select_from(DrugOrder).join(
        UserInfo, DrugOrder.user_id == UserInfo.user_id
    ).where(
        DrugOrder.user_id == user_id,
        DrugOrder.receiver_name != UserInfo.name,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_insured_rate(db: AsyncSession, user_id: str) -> float:
    """医保报销率 = 医保支付总额 / 总费用"""
    row = (await db.execute(
        select(
            func.coalesce(func.sum(InsuranceClaim.insured_amount), 0),
            func.coalesce(func.sum(InsuranceClaim.total_amount), 0),
        ).where(InsuranceClaim.user_id == user_id)
    )).first()
    insured, total = (row or (0, 0))
    if not total:
        return 0
    return round(float(insured) / float(total), 4)


async def _feat_user_night_claim_count(db: AsyncSession, user_id: str) -> float:
    """夜间 (0-6 点) 结算次数 (R011 辅助信号)"""
    stmt = select(func.count()).select_from(InsuranceClaim).where(
        InsuranceClaim.user_id == user_id,
        func.hour(InsuranceClaim.submit_at) < 6,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cross_hospital_count(db: AsyncSession, user_id: str) -> float:
    """结算涉及的不同医院数 (跨机构行为)"""
    stmt = select(func.count(func.distinct(InsuranceClaim.hospital_id))).where(
        InsuranceClaim.user_id == user_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_out_region_count(db: AsyncSession, user_id: str) -> float:
    """异地结算次数 (就医省 != 参保省, R007 核心信号)"""
    stmt = select(func.count()).select_from(InsuranceClaim).join(
        Hospital, InsuranceClaim.hospital_id == Hospital.hospital_id
    ).join(
        UserInfo, InsuranceClaim.user_id == UserInfo.user_id
    ).where(
        InsuranceClaim.user_id == user_id,
        Hospital.province != UserInfo.insure_province,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_drug_order_count(db: AsyncSession, user_id: str) -> float:
    """药品订单总数"""
    stmt = select(func.count()).select_from(DrugOrder).where(DrugOrder.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


# ============================================================
# 业务单维度特征 (8 个, 按事件类型分派)
# ============================================================

async def _doctor_daily_rx_count(db: AsyncSession, doctor_id: str) -> float:
    """医生当日处方数 (R002 统方 / R005 虚假病历核心信号)"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.count()).select_from(Prescription).where(
        Prescription.doctor_id == doctor_id,
        Prescription.create_time >= today_start,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _doctor_cross_hospital_count(db: AsyncSession, doctor_id: str) -> float:
    """医生历史涉及的不同医院数 (R012 跨院高频核心信号)"""
    stmt = select(func.count(func.distinct(Prescription.hospital_id))).where(
        Prescription.doctor_id == doctor_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _order_features_from_rx(db: AsyncSession, rx_id: str) -> dict[str, float]:
    """处方审核事件: 基于 Prescription + DrugOrder 计算业务单特征"""
    rx = (await db.execute(
        select(Prescription).where(Prescription.rx_id == rx_id)
    )).scalar_one_or_none()
    if rx is None:
        return {k: 0.0 for k in _ORDER_KEYS}
    # 该处方的药品订单: 行数 + 总数量
    item_count = (await db.execute(
        select(func.count()).select_from(DrugOrder).where(DrugOrder.rx_id == rx_id)
    )).scalar() or 0
    drug_count = (await db.execute(
        select(func.coalesce(func.sum(DrugOrder.quantity), 0)).select_from(DrugOrder).where(DrugOrder.rx_id == rx_id)
    )).scalar() or 0
    return {
        "order_claim_amount": float(rx.total_amount or 0),
        "order_insured_rate": 0.0,   # 处方无结算金额, 报销率看医保结算事件
        "order_rx_item_count": float(item_count),
        "order_drug_count": float(drug_count),
        "order_dx_count": 1.0 if (rx.diagnosis_code or "").strip() else 0.0,  # R009 无诊断开药
        "order_doctor_daily_rx_count": await _doctor_daily_rx_count(db, rx.doctor_id),
        "order_doctor_cross_hospital_count": await _doctor_cross_hospital_count(db, rx.doctor_id),
        "order_is_night": 1.0 if rx.create_time.hour < 6 else 0.0,
    }


async def _order_features_from_claim(db: AsyncSession, claim_id: str) -> dict[str, float]:
    """医保结算事件: 基于 InsuranceClaim 计算业务单特征"""
    claim = (await db.execute(
        select(InsuranceClaim).where(InsuranceClaim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        return {k: 0.0 for k in _ORDER_KEYS}
    total = float(claim.total_amount or 0)
    insured = float(claim.insured_amount or 0)
    return {
        "order_claim_amount": total,
        "order_insured_rate": round(insured / total, 4) if total else 0.0,
        "order_rx_item_count": 0.0,
        "order_drug_count": 0.0,
        "order_dx_count": 0.0,
        "order_doctor_daily_rx_count": 0.0,
        "order_doctor_cross_hospital_count": 0.0,
        "order_is_night": 1.0 if claim.submit_at.hour < 6 else 0.0,
    }


async def _order_features_from_appt(db: AsyncSession, appt_id: str) -> dict[str, float]:
    """挂号事件: 基于 Appointment 计算业务单特征"""
    appt = (await db.execute(
        select(Appointment).where(Appointment.appt_id == appt_id)
    )).scalar_one_or_none()
    if appt is None:
        return {k: 0.0 for k in _ORDER_KEYS}
    return {
        "order_claim_amount": float(appt.pay_amount or 0),
        "order_insured_rate": 0.0,
        "order_rx_item_count": 0.0,
        "order_drug_count": 0.0,
        "order_dx_count": 0.0,
        "order_doctor_daily_rx_count": await _doctor_daily_rx_count(db, appt.doctor_id),
        "order_doctor_cross_hospital_count": await _doctor_cross_hospital_count(db, appt.doctor_id),
        "order_is_night": 1.0 if appt.appt_time.hour < 6 else 0.0,
    }


async def _order_features_from_drug(db: AsyncSession, drug_order_id: str) -> dict[str, float]:
    """药品代购事件: 基于 DrugOrder 计算业务单特征"""
    dg = (await db.execute(
        select(DrugOrder).where(DrugOrder.drug_order_id == drug_order_id)
    )).scalar_one_or_none()
    if dg is None:
        return {k: 0.0 for k in _ORDER_KEYS}
    return {
        "order_claim_amount": float(dg.total_amount or 0),
        "order_insured_rate": 0.0,
        "order_rx_item_count": 0.0,
        "order_drug_count": float(dg.quantity or 0),
        "order_dx_count": 0.0,
        "order_doctor_daily_rx_count": 0.0,
        "order_doctor_cross_hospital_count": 0.0,
        "order_is_night": 1.0 if dg.create_time.hour < 6 else 0.0,
    }


# 8 个业务单特征键 (顺序与 FEATURE_COLUMNS 一致)
_ORDER_KEYS = [
    "order_claim_amount",
    "order_insured_rate",
    "order_rx_item_count",
    "order_drug_count",
    "order_dx_count",
    "order_doctor_daily_rx_count",
    "order_doctor_cross_hospital_count",
    "order_is_night",
]


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 17 个用户维度特征."""
    total_visits = await _feat_user_total_visits(db, user_id)
    claim_count = await _feat_user_claim_count(db, user_id)

    independent_features = {
        "user_visits_30d": _feat_user_visits_30d,
        "user_visits_7d": _feat_user_visits_7d,
        "user_total_claim_amount": _feat_user_total_claim_amount,
        "user_max_claim_amount": _feat_user_max_claim_amount,
        "user_claims_1h_hospitals": _feat_user_claims_1h_hospitals,
        "user_cancel_appt_count": _feat_user_cancel_appt_count,
        "user_rx_count": _feat_user_rx_count,
        "user_non_self_drug_count": _feat_user_non_self_drug_count,
        "user_insured_rate": _feat_user_insured_rate,
        "user_night_claim_count": _feat_user_night_claim_count,
        "user_cross_hospital_count": _feat_user_cross_hospital_count,
        "user_out_region_count": _feat_user_out_region_count,
        "user_drug_order_count": _feat_user_drug_order_count,
    }
    features = {name: await fn(db, user_id) for name, fn in independent_features.items()}
    features["user_total_visits"] = total_visits
    features["user_claim_count"] = claim_count
    # 派生特征: 传预查值避免重复 SQL
    features["user_avg_claim_amount"] = await _feat_user_avg_claim_amount(db, user_id, claim_count=claim_count)
    features["user_cancel_appt_rate"] = await _feat_user_cancel_appt_rate(db, user_id, total_visits=total_visits)
    return features


async def compute_order_features(
    db: AsyncSession,
    order_id: str,
    event_type: str | None = None,
) -> dict[str, float]:
    """计算 8 个业务单维度特征. 按事件类型分派到对应业务表."""
    if not order_id:
        return {k: 0.0 for k in _ORDER_KEYS}
    if event_type == "医保结算":
        return await _order_features_from_claim(db, order_id)
    if event_type == "处方审核":
        return await _order_features_from_rx(db, order_id)
    if event_type == "挂号":
        return await _order_features_from_appt(db, order_id)
    if event_type == "药品代购":
        return await _order_features_from_drug(db, order_id)
    return {k: 0.0 for k in _ORDER_KEYS}


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    event_type: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部 25 维特征并合并返回."""
    features = await compute_user_features(db, user_id)
    features.update(await compute_order_features(db, order_id, event_type))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 — 25 维特征名 (医疗版)")
    print("=" * 60)

    user_feats = [
        ("user_total_visits",            "历史就诊(挂号)总数"),
        ("user_visits_30d",              "近 30 天就诊数"),
        ("user_visits_7d",               "近 7 天就诊数"),
        ("user_total_claim_amount",      "历史医保结算总金额"),
        ("user_avg_claim_amount",        "平均单次结算金额"),
        ("user_max_claim_amount",        "最大单笔结算金额"),
        ("user_claim_count",             "医保结算次数"),
        ("user_claims_1h_hospitals",     "近 1 小时跨院结算数(R001)"),
        ("user_cancel_appt_count",       "取消挂号次数(R003)"),
        ("user_cancel_appt_rate",        "取消挂号率"),
        ("user_rx_count",                "处方总数"),
        ("user_non_self_drug_count",     "非本人收药订单数(R006)"),
        ("user_insured_rate",            "医保报销率"),
        ("user_night_claim_count",       "夜间结算次数(R011)"),
        ("user_cross_hospital_count",    "结算涉及医院数"),
        ("user_out_region_count",        "异地结算次数(R007)"),
        ("user_drug_order_count",        "药品订单总数"),
    ]
    order_feats = [
        ("order_claim_amount",               "本次结算/挂号金额"),
        ("order_insured_rate",               "本次医保报销比例"),
        ("order_rx_item_count",              "处方药品订单行数"),
        ("order_drug_count",                 "药品总数量(R004)"),
        ("order_dx_count",                   "处方是否有诊断(R009)"),
        ("order_doctor_daily_rx_count",      "开方医生当日处方数(R002)"),
        ("order_doctor_cross_hospital_count","开方医生历史跨院数(R012)"),
        ("order_is_night",                   "本次是否夜间(R011)"),
    ]
    all_groups = [("用户 (17)", user_feats), ("业务单 (8)", order_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<38} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")
"""
特征工程模块 (医疗版): 通过 ORM 查询业务数据, 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_xxx   = 患者维度特征
  order_xxx  = 诊疗单据维度特征 (挂号/处方/结算/药品订单, 由 source_id 定位)
  addr_xxx   = 医疗机构维度特征 (hospital_id)

跟电商版的差异: 计算函数全部按医疗业务重写, 函数签名与 25 维规模保持不变,
engine/decision.py 与 ml_model.py::FEATURE_COLUMNS 无感知复用.
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
    RiskBlacklist,
    UserInfo,
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
# 患者维度特征 (14 个)
# ============================================================

async def _feat_user_total_visits(db: AsyncSession, user_id: str) -> float:
    """历史挂号总数"""
    return await _count(Appointment, db, user_id=user_id)


async def _feat_user_visits_7d(db: AsyncSession, user_id: str) -> float:
    """近 7 天挂号数"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(Appointment).where(
        Appointment.user_id == user_id,
        Appointment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_visits_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天挂号数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(Appointment).where(
        Appointment.user_id == user_id,
        Appointment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_cancel_count(db: AsyncSession, user_id: str) -> float:
    """取消挂号总次数 (appt_status='已取消')"""
    return await _count(Appointment, db, user_id=user_id, appt_status='已取消')


async def _feat_user_cancel_24h(db: AsyncSession, user_id: str) -> float:
    """近 24 小时同手机号取消挂号次数 (挂号黄牛: 反复抢号转卖).

    规则语义是"同一手机号", 先查患者手机号, 再按手机号统计所有取消记录
    (黄牛常用同一手机号给不同人抢号).
    """
    phone = (await db.execute(
        select(UserInfo.phone).where(UserInfo.user_id == user_id).limit(1)
    )).scalar_one_or_none()
    if not phone:
        return 0.0
    since = datetime.now() - timedelta(hours=24)
    stmt = select(func.count()).select_from(Appointment).where(
        Appointment.phone == phone,
        Appointment.appt_status == '已取消',
        Appointment.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_hospital_count(db: AsyncSession, user_id: str) -> float:
    """就诊不同医院数 (DISTINCT hospital_id)"""
    stmt = select(func.count(func.distinct(Appointment.hospital_id))).select_from(
        Appointment
    ).where(Appointment.user_id == user_id)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_claim_hospitals_1h(db: AsyncSession, user_id: str) -> float:
    """近 1 小时内结算的不同医院数 (医保卡盗刷: 短时间多家医院刷卡)"""
    since = datetime.now() - timedelta(hours=1)
    stmt = select(func.count(func.distinct(InsuranceClaim.hospital_id))).select_from(
        InsuranceClaim
    ).where(
        InsuranceClaim.user_id == user_id,
        InsuranceClaim.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_claim_count(db: AsyncSession, user_id: str) -> float:
    """医保结算总次数"""
    return await _count(InsuranceClaim, db, user_id=user_id)


async def _feat_user_claim_amount(db: AsyncSession, user_id: str) -> float:
    """医保结算总金额"""
    return await _sum(InsuranceClaim, "total_amount", db, user_id=user_id)


async def _feat_user_claim_30d_count(db: AsyncSession, user_id: str) -> float:
    """近 30 天结算次数 (异地集中结算规则条件之一)"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(InsuranceClaim).where(
        InsuranceClaim.user_id == user_id,
        InsuranceClaim.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_claim_30d_amount(db: AsyncSession, user_id: str) -> float:
    """近 30 天结算金额 (异地集中结算规则条件之一)"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.coalesce(func.sum(InsuranceClaim.total_amount), 0)).select_from(
        InsuranceClaim
    ).where(
        InsuranceClaim.user_id == user_id,
        InsuranceClaim.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_rx_count(db: AsyncSession, user_id: str) -> float:
    """历史处方总数"""
    return await _count(Prescription, db, user_id=user_id)


async def _feat_user_drug_amount(db: AsyncSession, user_id: str) -> float:
    """累计药品订单金额 (药品代购: 累计金额阈值)"""
    return await _sum(DrugOrder, "total_amount", db, user_id=user_id)


async def _feat_user_card_blacklist_hit(db: AsyncSession, user_id: str) -> float:
    """医保卡号/身份证号是否命中黑名单 (0/1).

    撞黑前置拦截之外的规则兜底: R030 黑医保卡规则用此特征触发一票否决.
    """
    row = (await db.execute(
        select(UserInfo.medical_card_no, UserInfo.id_card_hash)
        .where(UserInfo.user_id == user_id).limit(1)
    )).first()
    if not row:
        return 0.0
    values = [v for v in (row.medical_card_no, row.id_card_hash) if v]
    if not values:
        return 0.0
    stmt = select(func.count()).select_from(RiskBlacklist).where(
        RiskBlacklist.blacklist_type.in_(["医保卡号", "身份证号"]),
        RiskBlacklist.blacklist_value.in_(values),
        RiskBlacklist.deleted_at.is_(None),
    )
    hit = (await db.execute(stmt)).scalar() or 0
    return 1.0 if hit > 0 else 0.0


# ============================================================
# 诊疗单据维度特征 (8 个)
# source_id 依次按 挂号→处方→结算→药品订单 定位单据
# ============================================================

async def _locate_document(db: AsyncSession, source_id: str) -> dict:
    """按 source_id 定位诊疗单据, 返回统一上下文 dict.

    返回字段: kind / amount / item_count / drug_quantity / create_time /
              doctor_id / diagnosis_code / user_id / receiver_name
    找不到返回空 dict (特征全部 0 兜底).
    """
    row = (await db.execute(
        select(Appointment).where(Appointment.appt_id == source_id).limit(1)
    )).scalar_one_or_none()
    if row:
        return {
            "kind": "appointment", "amount": float(row.pay_amount or 0),
            "item_count": 1, "drug_quantity": 0,
            "create_time": row.create_time, "doctor_id": row.doctor_id,
            "diagnosis_code": None, "user_id": row.user_id, "receiver_name": None,
        }

    row = (await db.execute(
        select(Prescription).where(Prescription.rx_id == source_id).limit(1)
    )).scalar_one_or_none()
    if row:
        return {
            "kind": "prescription", "amount": float(row.total_amount or 0),
            "item_count": row.item_count or 0, "drug_quantity": row.total_quantity or 0,
            "create_time": row.create_time, "doctor_id": row.doctor_id,
            "diagnosis_code": row.diagnosis_code, "user_id": row.user_id,
            "receiver_name": None,
        }

    row = (await db.execute(
        select(InsuranceClaim).where(InsuranceClaim.claim_id == source_id).limit(1)
    )).scalar_one_or_none()
    if row:
        return {
            "kind": "claim", "amount": float(row.total_amount or 0),
            "item_count": 1, "drug_quantity": 0,
            "create_time": row.create_time, "doctor_id": None,
            "diagnosis_code": None, "user_id": row.user_id, "receiver_name": None,
        }

    row = (await db.execute(
        select(DrugOrder).where(DrugOrder.drug_order_id == source_id).limit(1)
    )).scalar_one_or_none()
    if row:
        return {
            "kind": "drug_order", "amount": float(row.total_amount or 0),
            "item_count": 1, "drug_quantity": row.quantity or 0,
            "create_time": row.create_time, "doctor_id": None,
            "diagnosis_code": None, "user_id": row.user_id,
            "receiver_name": row.receiver_name,
        }
    return {}


async def _feat_doc_total_amount(db: AsyncSession, source_id: str, doc: dict | None = None) -> float:
    """本次诊疗单据金额 (挂号费/处方金额/结算费用/购药金额)"""
    if doc is None:
        doc = await _locate_document(db, source_id)
    return float(doc.get("amount", 0))


async def _feat_doc_item_count(db: AsyncSession, source_id: str, doc: dict | None = None) -> float:
    """单据药品行数 (处方场景; 其他单据按 1 计)"""
    if doc is None:
        doc = await _locate_document(db, source_id)
    return float(doc.get("item_count", 0))


async def _feat_doc_drug_quantity(db: AsyncSession, source_id: str, doc: dict | None = None) -> float:
    """单据药品总数量 (处方超量规则: 如阿普唑仑 > 30 片)"""
    if doc is None:
        doc = await _locate_document(db, source_id)
    return float(doc.get("drug_quantity", 0))


async def _feat_doc_is_night(db: AsyncSession, source_id: str, doc: dict | None = None) -> float:
    """是否夜间单据 (0~6 点)"""
    if doc is None:
        doc = await _locate_document(db, source_id)
    ct = doc.get("create_time")
    if ct:
        return 1.0 if 0 <= ct.hour < 6 else 0.0
    return 0.0


async def _feat_doc_doctor_rx_1d(db: AsyncSession, source_id: str, doc: dict | None = None) -> float:
    """该医生当日开方数 (医生统方规则: 1 天 ≥ 50 张)"""
    if doc is None:
        doc = await _locate_document(db, source_id)
    doctor_id = doc.get("doctor_id")
    if not doctor_id:
        return 0.0
    since = datetime.now() - timedelta(days=1)
    stmt = select(func.count()).select_from(Prescription).where(
        Prescription.doctor_id == doctor_id,
        Prescription.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_doc_doctor_patient_1d(db: AsyncSession, source_id: str, doc: dict | None = None) -> float:
    """该医生当日接诊不同患者数 (医生统方规则: 涉及 ≥ 10 个患者)"""
    if doc is None:
        doc = await _locate_document(db, source_id)
    doctor_id = doc.get("doctor_id")
    if not doctor_id:
        return 0.0
    since = datetime.now() - timedelta(days=1)
    stmt = select(func.count(func.distinct(Prescription.user_id))).select_from(
        Prescription
    ).where(
        Prescription.doctor_id == doctor_id,
        Prescription.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_doc_diagnosis_same_7d(db: AsyncSession, source_id: str, doc: dict | None = None) -> float:
    """同医生同诊断编码 7 天内不同患者数 (虚假病历规则: ≥ 5 个).

    无诊断编码 (挂号/结算/药品订单) 时返回 0.
    """
    if doc is None:
        doc = await _locate_document(db, source_id)
    doctor_id, diagnosis_code = doc.get("doctor_id"), doc.get("diagnosis_code")
    if not doctor_id or not diagnosis_code:
        return 0.0
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count(func.distinct(Prescription.user_id))).select_from(
        Prescription
    ).where(
        Prescription.doctor_id == doctor_id,
        Prescription.diagnosis_code == diagnosis_code,
        Prescription.create_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_doc_receiver_not_self(db: AsyncSession, source_id: str, doc: dict | None = None) -> float:
    """药品订单收件人 ≠ 患者本人 (0/1, 药品代购识别)"""
    if doc is None:
        doc = await _locate_document(db, source_id)
    if doc.get("kind") != "drug_order":
        return 0.0
    receiver = doc.get("receiver_name")
    if not receiver:
        return 0.0
    name = (await db.execute(
        select(UserInfo.name).where(UserInfo.user_id == doc.get("user_id")).limit(1)
    )).scalar_one_or_none()
    return 1.0 if name and receiver != name else 0.0


# ============================================================
# 医疗机构维度特征 (3 个, hospital_id)
# ============================================================

async def _feat_hosp_visit_count(db: AsyncSession, user_id: str, hospital_id: str | None) -> float:
    """患者在该医院的就诊次数"""
    if not hospital_id:
        return 0.0
    return await _count(Appointment, db, user_id=user_id, hospital_id=hospital_id)


async def _feat_hosp_is_new(db: AsyncSession, user_id: str, hospital_id: str | None) -> float:
    """是否新医院 (该患者在该医院就诊次数 <= 1)"""
    if not hospital_id:
        return 0.0
    cnt = await _feat_hosp_visit_count(db, user_id, hospital_id)
    return 1.0 if cnt <= 1 else 0.0


async def _feat_hosp_cross_region(db: AsyncSession, user_id: str, hospital_id: str | None) -> float:
    """是否异地就医 (参保省份 ≠ 医院省份, 0/1, 异地集中结算规则条件之一)"""
    if not hospital_id:
        return 0.0
    row = (await db.execute(
        select(UserInfo.insured_province, Hospital.province)
        .select_from(UserInfo)
        .join(Hospital, Hospital.hospital_id == hospital_id)
        .where(UserInfo.user_id == user_id)
        .limit(1)
    )).first()
    if not row or not row.insured_province or not row.province:
        return 0.0
    return 1.0 if row.insured_province != row.province else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 14 个患者维度特征."""
    feat_funcs = {
        "user_total_visits": _feat_user_total_visits,
        "user_visits_7d": _feat_user_visits_7d,
        "user_visits_30d": _feat_user_visits_30d,
        "user_cancel_count": _feat_user_cancel_count,
        "user_cancel_24h": _feat_user_cancel_24h,
        "user_hospital_count": _feat_user_hospital_count,
        "user_claim_hospitals_1h": _feat_user_claim_hospitals_1h,
        "user_claim_count": _feat_user_claim_count,
        "user_claim_amount": _feat_user_claim_amount,
        "user_claim_30d_count": _feat_user_claim_30d_count,
        "user_claim_30d_amount": _feat_user_claim_30d_amount,
        "user_rx_count": _feat_user_rx_count,
        "user_drug_amount": _feat_user_drug_amount,
        "user_card_blacklist_hit": _feat_user_card_blacklist_hit,
    }
    return {name: await func(db, user_id) for name, func in feat_funcs.items()}


async def compute_doc_features(db: AsyncSession, source_id: str) -> dict[str, float]:
    """计算 8 个诊疗单据维度特征.

    【性能优化】先 await 1 次 _locate_document, 然后传给 8 个特征函数复用,
    避免每个特征各自重查单据 (9 次 SQL → 2 次).
    """
    doc = await _locate_document(db, source_id)
    feat_funcs = {
        "order_total_amount": _feat_doc_total_amount,
        "order_item_count": _feat_doc_item_count,
        "order_drug_quantity": _feat_doc_drug_quantity,
        "order_is_night": _feat_doc_is_night,
        "order_doctor_rx_1d": _feat_doc_doctor_rx_1d,
        "order_doctor_patient_1d": _feat_doc_doctor_patient_1d,
        "order_diagnosis_same_7d": _feat_doc_diagnosis_same_7d,
        "order_receiver_not_self": _feat_doc_receiver_not_self,
    }
    return {name: await func(db, source_id, doc) for name, func in feat_funcs.items()}


# 电商版 compute_order_features 的医疗对应: 单据维度
async def compute_order_features(db: AsyncSession, order_id: str) -> dict[str, float]:
    """兼容入口: order_id 即诊疗单据 source_id."""
    return await compute_doc_features(db, order_id)


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个医疗机构维度特征 (receive_id = hospital_id)."""
    return {
        "addr_visit_count": await _feat_hosp_visit_count(db, user_id, receive_id),
        "addr_is_new": await _feat_hosp_is_new(db, user_id, receive_id),
        "addr_cross_region": await _feat_hosp_cross_region(db, user_id, receive_id),
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回. 签名跟电商版一致 (decision.py 无感知)."""
    features = await compute_user_features(db, user_id)
    if order_id:
        features.update(await compute_order_features(db, order_id))
    features.update(await compute_address_features(db, user_id, receive_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 (医疗版) — 25 维特征名 + 字典派发表")
    print("=" * 60)

    user_feats = [
        ("user_total_visits",       "历史挂号总数"),
        ("user_visits_7d",          "近 7 天挂号数"),
        ("user_visits_30d",         "近 30 天挂号数"),
        ("user_cancel_count",       "取消挂号总次数"),
        ("user_cancel_24h",         "近 24h 同手机号取消次数 (黄牛)"),
        ("user_hospital_count",     "就诊不同医院数"),
        ("user_claim_hospitals_1h", "近 1h 结算不同医院数 (盗刷)"),
        ("user_claim_count",        "医保结算总次数"),
        ("user_claim_amount",       "医保结算总金额"),
        ("user_claim_30d_count",    "近 30 天结算次数"),
        ("user_claim_30d_amount",   "近 30 天结算金额"),
        ("user_rx_count",           "历史处方总数"),
        ("user_drug_amount",        "累计购药金额 (代购)"),
        ("user_card_blacklist_hit", "医保卡/身份证命中黑名单 (0/1)"),
    ]
    order_feats = [
        ("order_total_amount",       "本次单据金额"),
        ("order_item_count",         "处方药品行数"),
        ("order_drug_quantity",      "药品总数量 (超量)"),
        ("order_is_night",           "是否夜间单据 (0-6 点)"),
        ("order_doctor_rx_1d",       "医生当日开方数 (统方)"),
        ("order_doctor_patient_1d",  "医生当日接诊患者数"),
        ("order_diagnosis_same_7d",  "同医生同诊断 7 天患者数 (虚假病历)"),
        ("order_receiver_not_self",  "收件人≠患者本人 (0/1, 代购)"),
    ]
    addr_feats = [
        ("addr_visit_count",         "该医院就诊次数"),
        ("addr_is_new",              "是否新医院 (0/1)"),
        ("addr_cross_region",        "是否异地就医 (0/1)"),
    ]
    all_groups = [("患者 (14)", user_feats), ("诊疗单据 (8)", order_feats), ("医疗机构 (3)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<28} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")

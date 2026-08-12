"""医疗风控 25 维特征计算。"""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import (
    MedicalDoctor,
    MedicalHospital,
    MedicalInsuranceClaim,
    MedicalPatient,
    MedicalPatientDevice,
    MedicalPrescription,
    MedicalPrescriptionItem,
    MedicalRegistration,
)
from app.schemas import RiskCheckRequest


FEATURE_COLUMNS = [
    "patient_registration_count_7d", "patient_cancel_count_30d",
    "patient_cancel_rate_30d", "patient_hospital_count_7d",
    "patient_claim_count_24h", "patient_claim_amount_30d",
    "patient_cross_province_count_30d", "patient_same_drug_count_30d",
    "patient_device_count_30d", "patient_account_age_days",
    "event_total_amount", "prescription_drug_count",
    "prescription_total_quantity", "prescription_max_days_supply",
    "prescription_controlled_drug_count", "prescription_high_value_ratio",
    "claim_insurance_ratio", "event_is_night", "event_is_cross_province",
    "doctor_prescription_count_1d", "doctor_prescription_amount_1d",
    "doctor_avg_prescription_amount_30d", "hospital_claim_amount_1d",
    "device_patient_count_7d", "doctor_license_abnormal",
]


def _number(value) -> float:
    return float(value or 0)


async def _scalar(db: AsyncSession, statement):
    return (await db.execute(statement)).scalar_one_or_none()


async def compute_all_features(
    db: AsyncSession,
    request: RiskCheckRequest,
    now: datetime | None = None,
) -> dict[str, float]:
    now = now or datetime.now()
    patient_id = request.user_id
    patient = await db.get(MedicalPatient, patient_id)
    if patient is None:
        return {name: 0.0 for name in FEATURE_COLUMNS}

    reg_7d = _number(await _scalar(db, select(func.count()).select_from(MedicalRegistration).where(
        MedicalRegistration.patient_id == patient_id,
        MedicalRegistration.register_at >= now - timedelta(days=7),
    )))
    reg_30d = _number(await _scalar(db, select(func.count()).select_from(MedicalRegistration).where(
        MedicalRegistration.patient_id == patient_id,
        MedicalRegistration.register_at >= now - timedelta(days=30),
    )))
    cancel_30d = _number(await _scalar(db, select(func.count()).select_from(MedicalRegistration).where(
        MedicalRegistration.patient_id == patient_id,
        MedicalRegistration.register_at >= now - timedelta(days=30),
        MedicalRegistration.status == "已退号",
    )))
    hospital_7d = _number(await _scalar(db, select(func.count(func.distinct(MedicalInsuranceClaim.hospital_id))).where(
        MedicalInsuranceClaim.patient_id == patient_id,
        MedicalInsuranceClaim.claim_at >= now - timedelta(days=7),
    )))
    claim_24h = _number(await _scalar(db, select(func.count()).select_from(MedicalInsuranceClaim).where(
        MedicalInsuranceClaim.patient_id == patient_id,
        MedicalInsuranceClaim.claim_at >= now - timedelta(hours=24),
    )))
    claim_amount_30d = _number(await _scalar(db, select(func.sum(MedicalInsuranceClaim.total_amount)).where(
        MedicalInsuranceClaim.patient_id == patient_id,
        MedicalInsuranceClaim.claim_at >= now - timedelta(days=30),
    )))
    cross_province_30d = _number(await _scalar(db, select(func.count()).select_from(MedicalInsuranceClaim).where(
        MedicalInsuranceClaim.patient_id == patient_id,
        MedicalInsuranceClaim.claim_at >= now - timedelta(days=30),
        MedicalInsuranceClaim.visit_province != patient.insured_province,
    )))
    category_counts = (
        select(func.count(MedicalPrescriptionItem.item_id).label("category_count"))
        .select_from(MedicalPrescriptionItem)
        .join(MedicalPrescription, MedicalPrescription.prescription_id == MedicalPrescriptionItem.prescription_id)
        .where(
            MedicalPrescription.patient_id == patient_id,
            MedicalPrescription.issued_at >= now - timedelta(days=30),
        )
        .group_by(MedicalPrescriptionItem.drug_category)
        .subquery()
    )
    same_drug_30d = _number(await _scalar(db, select(func.max(category_counts.c.category_count))))
    device_count = _number(await _scalar(db, select(func.count(func.distinct(MedicalPatientDevice.device_id_hash))).where(
        MedicalPatientDevice.patient_id == patient_id,
        MedicalPatientDevice.last_seen_at >= now - timedelta(days=30),
    )))

    source = None
    if request.event_type in {"挂号申请", "挂号退号"}:
        source = await db.get(MedicalRegistration, request.source_id)
    elif request.event_type == "处方开立":
        source = await db.get(MedicalPrescription, request.source_id)
    elif request.event_type == "医保结算":
        source = await db.get(MedicalInsuranceClaim, request.source_id)

    prescription = source if isinstance(source, MedicalPrescription) else None
    if isinstance(source, MedicalInsuranceClaim) and source.prescription_id:
        prescription = await db.get(MedicalPrescription, source.prescription_id)

    total_amount = _number(getattr(source, "total_amount", 0))
    event_time = (
        getattr(source, "issued_at", None)
        or getattr(source, "claim_at", None)
        or getattr(source, "register_at", None)
        or now
    )
    doctor_id = getattr(prescription, "doctor_id", None) or getattr(source, "doctor_id", None)
    hospital_id = getattr(source, "hospital_id", None) or getattr(prescription, "hospital_id", None)
    device_hash = getattr(source, "device_id_hash", None)

    item_stats = (0, 0, 0, Decimal("0"), Decimal("0"))
    if prescription:
        item_stats = (await db.execute(select(
            func.coalesce(func.sum(MedicalPrescriptionItem.quantity), 0),
            func.coalesce(func.max(MedicalPrescriptionItem.days_supply), 0),
            func.coalesce(func.sum(case((MedicalPrescriptionItem.is_controlled.is_(True), 1), else_=0)), 0),
            func.coalesce(func.sum(MedicalPrescriptionItem.unit_price * MedicalPrescriptionItem.quantity), 0),
            func.coalesce(func.sum(case(
                (MedicalPrescriptionItem.is_high_value.is_(True), MedicalPrescriptionItem.unit_price * MedicalPrescriptionItem.quantity),
                else_=0,
            )), 0),
        ).where(MedicalPrescriptionItem.prescription_id == prescription.prescription_id))).one()
    quantity, max_days, controlled, item_total, high_value_total = item_stats
    item_total_f = _number(item_total)

    doctor_count_1d = doctor_amount_1d = doctor_avg_30d = 0.0
    doctor_abnormal = 0.0
    if doctor_id:
        day_start = event_time.replace(hour=0, minute=0, second=0, microsecond=0)
        doctor_count_1d = _number(await _scalar(db, select(func.count()).select_from(MedicalPrescription).where(
            MedicalPrescription.doctor_id == doctor_id,
            MedicalPrescription.issued_at >= day_start,
            MedicalPrescription.issued_at < day_start + timedelta(days=1),
        )))
        doctor_amount_1d = _number(await _scalar(db, select(func.sum(MedicalPrescription.total_amount)).where(
            MedicalPrescription.doctor_id == doctor_id,
            MedicalPrescription.issued_at >= day_start,
            MedicalPrescription.issued_at < day_start + timedelta(days=1),
        )))
        doctor_avg_30d = _number(await _scalar(db, select(func.avg(MedicalPrescription.total_amount)).where(
            MedicalPrescription.doctor_id == doctor_id,
            MedicalPrescription.issued_at >= now - timedelta(days=30),
        )))
        doctor = await db.get(MedicalDoctor, doctor_id)
        doctor_abnormal = float(bool(doctor and doctor.license_status != "有效"))

    hospital_claim_1d = 0.0
    if hospital_id:
        day_start = event_time.replace(hour=0, minute=0, second=0, microsecond=0)
        hospital_claim_1d = _number(await _scalar(db, select(func.sum(MedicalInsuranceClaim.total_amount)).where(
            MedicalInsuranceClaim.hospital_id == hospital_id,
            MedicalInsuranceClaim.claim_at >= day_start,
            MedicalInsuranceClaim.claim_at < day_start + timedelta(days=1),
        )))

    device_patient_count = 0.0
    if device_hash:
        device_patient_count = _number(await _scalar(db, select(func.count(func.distinct(MedicalPatientDevice.patient_id))).where(
            MedicalPatientDevice.device_id_hash == device_hash,
            MedicalPatientDevice.last_seen_at >= now - timedelta(days=7),
        )))

    is_cross = float(bool(
        isinstance(source, MedicalInsuranceClaim)
        and source.visit_province != patient.insured_province
    ))
    insurance_ratio = 0.0
    if isinstance(source, MedicalInsuranceClaim) and _number(source.total_amount) > 0:
        insurance_ratio = _number(source.insurance_amount) / _number(source.total_amount)

    features = {
        "patient_registration_count_7d": reg_7d,
        "patient_cancel_count_30d": cancel_30d,
        "patient_cancel_rate_30d": cancel_30d / reg_30d if reg_30d else 0.0,
        "patient_hospital_count_7d": hospital_7d,
        "patient_claim_count_24h": claim_24h,
        "patient_claim_amount_30d": claim_amount_30d,
        "patient_cross_province_count_30d": cross_province_30d,
        "patient_same_drug_count_30d": same_drug_30d,
        "patient_device_count_30d": device_count,
        "patient_account_age_days": max((now - patient.account_created_at).days, 0),
        "event_total_amount": total_amount,
        "prescription_drug_count": _number(getattr(prescription, "drug_count", 0)),
        "prescription_total_quantity": _number(quantity),
        "prescription_max_days_supply": _number(max_days),
        "prescription_controlled_drug_count": _number(controlled),
        "prescription_high_value_ratio": _number(high_value_total) / item_total_f if item_total_f else 0.0,
        "claim_insurance_ratio": insurance_ratio,
        "event_is_night": float(event_time.hour < 5),
        "event_is_cross_province": is_cross,
        "doctor_prescription_count_1d": doctor_count_1d,
        "doctor_prescription_amount_1d": doctor_amount_1d,
        "doctor_avg_prescription_amount_30d": doctor_avg_30d,
        "hospital_claim_amount_1d": hospital_claim_1d,
        "device_patient_count_7d": device_patient_count,
        "doctor_license_abnormal": doctor_abnormal,
    }
    assert list(features) == FEATURE_COLUMNS
    return features

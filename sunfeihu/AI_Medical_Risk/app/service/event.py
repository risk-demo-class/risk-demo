"""医疗风险事件入口：校验、黑名单检查、决策编排。"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.engine.rule import RuleHitResult
from app.engine.rule_definitions import BLACKLIST_RULE
from app.models_business import (
    MedicalInsuranceClaim,
    MedicalPatient,
    MedicalPrescription,
    MedicalRegistration,
)
from app.models_risk import RiskBlacklist
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.validator import validate_risk_check_request


async def _blacklist_candidates(db: AsyncSession, request: RiskCheckRequest) -> list[tuple[str, str]]:
    patient = await db.get(MedicalPatient, request.user_id)
    candidates = [("PATIENT_ID", request.user_id)]
    if patient:
        candidates.extend([
            ("ID_CARD_HASH", patient.id_card_hash),
            ("INSURANCE_CARD_HASH", patient.insurance_card_hash),
            ("PHONE_HASH", patient.phone_hash),
        ])
    source = None
    if request.event_type in {"挂号申请", "挂号退号"}:
        source = await db.get(MedicalRegistration, request.source_id)
    elif request.event_type == "处方开立":
        source = await db.get(MedicalPrescription, request.source_id)
    elif request.event_type == "医保结算":
        source = await db.get(MedicalInsuranceClaim, request.source_id)
    if source:
        if getattr(source, "hospital_id", None):
            candidates.append(("HOSPITAL_ID", source.hospital_id))
        if getattr(source, "doctor_id", None):
            candidates.append(("DOCTOR_ID", source.doctor_id))
        if getattr(source, "device_id_hash", None):
            candidates.append(("DEVICE_ID_HASH", source.device_id_hash))
    return candidates


async def find_blacklist_hit(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    candidates = await _blacklist_candidates(db, request)
    types = {item[0] for item in candidates}
    values = {item[1] for item in candidates}
    result = await db.execute(select(RiskBlacklist).where(
        RiskBlacklist.blacklist_type.in_(types),
        RiskBlacklist.blacklist_value.in_(values),
        RiskBlacklist.deleted_at.is_(None),
    ))
    candidate_set = set(candidates)
    now = datetime.now()
    for row in result.scalars().all():
        if (row.blacklist_type, row.blacklist_value) in candidate_set and (
            row.expire_time is None or row.expire_time > now
        ):
            return f"{row.blacklist_type}:{row.blacklist_value[:8]}***"
    return None


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    await validate_risk_check_request(db, request)
    blacklist_hit = await find_blacklist_hit(db, request)
    forced_hits = None
    if blacklist_hit:
        forced_hits = [RuleHitResult(**BLACKLIST_RULE)]
    response = await run_risk_check(db, request, forced_hits=forced_hits)
    if blacklist_hit:
        response.blocked_by = blacklist_hit
    return response

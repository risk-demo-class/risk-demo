"""医疗事件的业务存在性与归属校验。"""
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import (
    MedicalInsuranceClaim,
    MedicalPatient,
    MedicalPrescription,
    MedicalRegistration,
)
from app.schemas import RiskCheckRequest


@dataclass(frozen=True)
class EventSourceSpec:
    model: type
    id_attr: str
    label: str


EVENT_SOURCE_MAP: dict[str, EventSourceSpec] = {
    "挂号申请": EventSourceSpec(MedicalRegistration, "registration_id", "挂号记录"),
    "挂号退号": EventSourceSpec(MedicalRegistration, "registration_id", "挂号记录"),
    "处方开立": EventSourceSpec(MedicalPrescription, "prescription_id", "处方"),
    "医保结算": EventSourceSpec(MedicalInsuranceClaim, "claim_id", "医保结算"),
}


async def ensure_patient_exists(db: AsyncSession, patient_id: str) -> None:
    found = (await db.execute(
        select(MedicalPatient.patient_id).where(MedicalPatient.patient_id == patient_id)
    )).scalar_one_or_none()
    if found is None:
        raise HTTPException(status_code=404, detail=f"患者不存在: {patient_id}")


async def ensure_source_matches_event_type(
    db: AsyncSession,
    event_type: str,
    source_id: str,
    patient_id: str,
) -> None:
    """校验 source_id 属于事件对应表，且业务记录归属于请求患者。"""
    spec = EVENT_SOURCE_MAP.get(event_type)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"不支持的医疗事件类型: {event_type}")

    id_column = getattr(spec.model, spec.id_attr)
    row = (await db.execute(
        select(spec.model).where(id_column == source_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{spec.label}不存在: {source_id}")
    if row.patient_id != patient_id:
        raise HTTPException(
            status_code=400,
            detail=f"{spec.label} {source_id} 不属于患者 {patient_id}",
        )


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    """风险检查入口统一调用一次，避免重复数据库查询。"""
    await ensure_patient_exists(db, request.user_id)
    await ensure_source_matches_event_type(
        db,
        event_type=request.event_type,
        source_id=request.source_id,
        patient_id=request.user_id,
    )


__all__ = [
    "EVENT_SOURCE_MAP",
    "EventSourceSpec",
    "ensure_patient_exists",
    "ensure_source_matches_event_type",
    "validate_risk_check_request",
]

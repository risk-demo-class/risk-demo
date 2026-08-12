"""从合成医疗业务表采集训练样本，并生成教学型规则弱监督标签。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.feature import FEATURE_COLUMNS, compute_all_features
from app.engine.rule import evaluate_condition
from app.engine.rule_definitions import RULE_DEFINITIONS
from app.models_business import MedicalInsuranceClaim, MedicalPrescription, MedicalRegistration
from app.schemas import RiskCheckRequest


@dataclass(frozen=True)
class TrainingDataset:
    features: np.ndarray
    labels: np.ndarray
    sample_info: list[dict[str, str | int]]


def weak_supervision_label(event_type: str, features: dict[str, float]) -> tuple[int, list[str]]:
    """需人工审核/拒绝的规则作为正例；规则结果本身绝不进入特征矩阵。"""
    hit_ids: list[str] = []
    for rule_id, _name, _category, rule_event, condition, _level, score, action in RULE_DEFINITIONS:
        if rule_event not in (event_type, "通用"):
            continue
        if action in ("人工审核", "拒绝") and score >= 60 and evaluate_condition(condition, features):
            hit_ids.append(rule_id)
    return int(bool(hit_ids)), hit_ids


def _evenly_spaced(rows: list, limit: int) -> list:
    if len(rows) <= limit:
        return rows
    indices = np.linspace(0, len(rows) - 1, num=limit, dtype=int)
    return [rows[index] for index in indices]


async def collect_training_dataset(db: AsyncSession, limit: int = 1200) -> TrainingDataset:
    """按四类事件均匀采样，实时调用线上同一套 25 维特征计算。"""
    per_event = max(limit // 4, 1)
    registrations = list((await db.execute(
        select(MedicalRegistration).order_by(MedicalRegistration.registration_id)
    )).scalars().all())
    prescriptions = list((await db.execute(
        select(MedicalPrescription).order_by(MedicalPrescription.prescription_id)
    )).scalars().all())
    claims = list((await db.execute(
        select(MedicalInsuranceClaim).order_by(MedicalInsuranceClaim.claim_id)
    )).scalars().all())

    sources = [
        ("挂号申请", _evenly_spaced(registrations, per_event), "registration_id"),
        ("挂号退号", _evenly_spaced([row for row in registrations if row.status == "已退号"], per_event), "registration_id"),
        ("处方开立", _evenly_spaced(prescriptions, per_event), "prescription_id"),
        ("医保结算", _evenly_spaced(claims, per_event), "claim_id"),
    ]
    matrix: list[list[float]] = []
    labels: list[int] = []
    sample_info: list[dict[str, str | int]] = []
    for event_type, rows, id_attribute in sources:
        for row in rows:
            source_id = getattr(row, id_attribute)
            request = RiskCheckRequest(
                event_type=event_type,
                source_id=source_id,
                user_id=row.patient_id,
                event_data={},
            )
            features = await compute_all_features(db, request)
            label, hit_ids = weak_supervision_label(event_type, features)
            matrix.append([float(features[column]) for column in FEATURE_COLUMNS])
            labels.append(label)
            sample_info.append({
                "event_type": event_type,
                "source_id": source_id,
                "patient_id": row.patient_id,
                "label": label,
                "weak_rule_ids": ",".join(hit_ids),
            })
    return TrainingDataset(
        features=np.asarray(matrix, dtype=np.float32),
        labels=np.asarray(labels, dtype=np.int32),
        sample_info=sample_info,
    )

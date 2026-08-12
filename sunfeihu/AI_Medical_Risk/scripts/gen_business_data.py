"""生成可复现、完全合成的医疗业务数据。"""
import argparse
import asyncio
import hashlib
import json
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.models_business import (  # noqa: E402
    MedicalDoctor,
    MedicalHospital,
    MedicalInsuranceClaim,
    MedicalPatient,
    MedicalPatientDevice,
    MedicalPrescription,
    MedicalPrescriptionItem,
    MedicalRegistration,
)


PROVINCES = ["广东省", "浙江省", "江苏省", "四川省", "湖北省"]
DEPARTMENTS = ["内科", "外科", "儿科", "骨科", "皮肤科"]
DRUGS = [
    ("DRG001", "合成药品A", "镇痛药", Decimal("25.00"), False, False),
    ("DRG002", "合成药品B", "抗感染药", Decimal("58.00"), False, False),
    ("DRG003", "合成药品C", "慢病用药", Decimal("86.00"), False, False),
    ("DRG004", "合成药品D", "特殊管理药", Decimal("480.00"), True, True),
    ("DRG005", "合成药品E", "高值药", Decimal("1500.00"), False, True),
]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_dataset(seed: int = 20260811) -> dict[str, list[dict]]:
    """固定 seed 生成 PRD 默认规模，并嵌入 6 类可解释风险模式。"""
    rng = random.Random(seed)
    now = datetime(2026, 8, 11, 12, 0, 0)

    hospitals = [
        {
            "hospital_id": f"HOS{i:03d}",
            "hospital_name": f"合成示范医院{i}",
            "province": PROVINCES[i - 1],
            "city": f"示范城市{i}",
            "hospital_level": "三级" if i <= 3 else "二级",
            "hospital_type": "综合医院",
            "insurance_designated": True,
            "status": "正常",
        }
        for i in range(1, 6)
    ]

    doctors = []
    for i in range(1, 21):
        doctors.append({
            "doctor_id": f"DOC{i:04d}",
            "doctor_name_masked": f"医生{i}*",
            "hospital_id": f"HOS{((i - 1) % 5) + 1:03d}",
            "department": DEPARTMENTS[(i - 1) % len(DEPARTMENTS)],
            "professional_title": "主任医师" if i <= 5 else "主治医师",
            "license_status": "异常" if i == 20 else "有效",
            "practice_start_date": date(2010 + i % 10, 1, 1),
            "status": "异常" if i == 20 else "在职",
        })

    patients = []
    for i in range(1, 201):
        patients.append({
            "patient_id": f"PAT{i:06d}",
            "name_masked": f"患者{i:03d}*",
            "id_card_hash": _hash(f"synthetic-id-{seed}-{i}"),
            "insurance_card_hash": _hash(f"synthetic-insurance-{seed}-{i}"),
            "phone_hash": _hash(f"synthetic-phone-{seed}-{i}"),
            "gender": "男" if i % 2 else "女",
            "birth_year": 1945 + i % 55,
            "insured_province": PROVINCES[(i - 1) % 5],
            "account_created_at": now - timedelta(days=30 + i * 3),
            "real_name_status": "已实名",
        })

    shared_device = _hash(f"shared-device-{seed}")
    devices = []
    for i in range(1, 201):
        device_hash = shared_device if i <= 6 else _hash(f"device-{seed}-{i}")
        devices.append({
            "relation_id": f"DEVREL{i:06d}",
            "patient_id": f"PAT{i:06d}",
            "device_id_hash": device_hash,
            "first_seen_at": now - timedelta(days=60),
            "last_seen_at": now - timedelta(hours=i % 48),
            "use_count": 20 if i <= 6 else rng.randint(1, 8),
        })

    registrations = []
    for i in range(1, 501):
        # PAT000002 专门构造 10 次挂号/7 次退号，后续随机样本不再稀释退号率。
        patient_num = 2 if i <= 10 else rng.randint(3, 200)
        doctor_num = rng.randint(1, 20)
        hospital_num = ((doctor_num - 1) % 5) + 1
        cancelled = i <= 7 or (i > 10 and rng.random() < 0.12)
        register_at = (
            now - timedelta(days=i, hours=1)
            if i <= 10
            else now - timedelta(days=rng.randint(0, 45), hours=rng.randint(0, 20))
        )
        registrations.append({
            "registration_id": f"REG{i:07d}",
            "patient_id": f"PAT{patient_num:06d}",
            "hospital_id": f"HOS{hospital_num:03d}",
            "doctor_id": f"DOC{doctor_num:04d}",
            "department": DEPARTMENTS[(doctor_num - 1) % len(DEPARTMENTS)],
            "visit_date": register_at.date() + timedelta(days=rng.randint(0, 7)),
            "register_channel": rng.choice(["微信", "APP", "窗口", "自助机"]),
            "device_id_hash": shared_device if patient_num <= 6 else _hash(f"device-{seed}-{patient_num}"),
            "status": "已退号" if cancelled else rng.choice(["已挂号", "已完成"]),
            "register_at": register_at,
            "cancel_at": register_at + timedelta(hours=2) if cancelled else None,
        })

    prescriptions: list[dict] = []
    items: list[dict] = []
    for i in range(1, 501):
        if i <= 5:
            patient_num, doctor_num, drug_choices = 1, 1, [DRUGS[0], DRUGS[0]]
        elif i <= 20:
            patient_num, doctor_num, drug_choices = rng.randint(3, 30), 1, [DRUGS[4], DRUGS[4]]
        elif i == 500:
            patient_num, doctor_num, drug_choices = 50, 20, [DRUGS[1], DRUGS[2]]
        else:
            patient_num, doctor_num = rng.randint(1, 200), rng.randint(1, 19)
            drug_choices = rng.sample(DRUGS, 2)
        hospital_num = ((doctor_num - 1) % 5) + 1
        issued_at = now - timedelta(days=(i % 30), hours=(i % 10))
        if 6 <= i <= 20:
            issued_at = now.replace(hour=9) + timedelta(minutes=i)

        prescription_id = f"RX{i:07d}"
        total = Decimal("0.00")
        for j, drug in enumerate(drug_choices, 1):
            code, name, category, price, controlled, high_value = drug
            quantity = 3 if i <= 5 else (5 if 6 <= i <= 20 else rng.randint(1, 3))
            days_supply = 120 if i == 21 and j == 1 else rng.choice([7, 14, 30])
            total += price * quantity
            items.append({
                "item_id": f"ITEM{i:07d}-{j}",
                "prescription_id": prescription_id,
                "drug_code": code,
                "drug_name": name,
                "drug_category": category,
                "unit_price": price,
                "quantity": quantity,
                "days_supply": days_supply,
                "is_controlled": controlled,
                "is_high_value": high_value,
            })
        prescriptions.append({
            "prescription_id": prescription_id,
            "patient_id": f"PAT{patient_num:06d}",
            "doctor_id": f"DOC{doctor_num:04d}",
            "hospital_id": f"HOS{hospital_num:03d}",
            "registration_id": None,
            "prescription_type": "门诊",
            "total_amount": total,
            "drug_count": len(drug_choices),
            "issued_at": issued_at,
            "status": "有效",
        })

    claims = []
    for i in range(1, 501):
        patient_num = 1 if i <= 3 else rng.randint(1, 200)
        hospital_num = i if i <= 3 else rng.randint(1, 5)
        total = Decimal("25000.00") if i == 4 else Decimal(str(rng.randint(200, 8000)))
        insurance_ratio = Decimal("0.99") if i == 5 else Decimal("0.70")
        insurance = (total * insurance_ratio).quantize(Decimal("0.01"))
        claims.append({
            "claim_id": f"CLM{i:07d}",
            "patient_id": f"PAT{patient_num:06d}",
            "hospital_id": f"HOS{hospital_num:03d}",
            "prescription_id": f"RX{i:07d}",
            "total_amount": total,
            "insurance_amount": insurance,
            "self_pay_amount": total - insurance,
            "claim_type": "异地就医" if i <= 3 else "门诊",
            "visit_province": PROVINCES[(hospital_num - 1) % 5],
            "claim_at": now - timedelta(hours=i if i <= 3 else rng.randint(0, 720)),
            "status": "已结算",
        })

    return {
        "hospitals": hospitals,
        "doctors": doctors,
        "patients": patients,
        "devices": devices,
        "registrations": registrations,
        "prescriptions": prescriptions,
        "items": items,
        "claims": claims,
    }


def dataset_fingerprint(dataset: dict[str, list[dict]]) -> str:
    payload = json.dumps(dataset, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def persist_dataset(dataset: dict[str, list[dict]]) -> bool:
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(func.count(MedicalPatient.patient_id)))).scalar_one()
        if existing:
            print(f"检测到 {existing} 名患者，造数脚本幂等退出；如需重建请使用独立测试库。")
            return False
        try:
            # 模型刻意不声明 relationship，批量写入时显式按 FK 层级 flush。
            session.add_all([MedicalHospital(**row) for row in dataset["hospitals"]])
            session.add_all([MedicalPatient(**row) for row in dataset["patients"]])
            await session.flush()

            session.add_all([MedicalDoctor(**row) for row in dataset["doctors"]])
            await session.flush()

            session.add_all([MedicalPatientDevice(**row) for row in dataset["devices"]])
            session.add_all([MedicalRegistration(**row) for row in dataset["registrations"]])
            await session.flush()

            session.add_all([MedicalPrescription(**row) for row in dataset["prescriptions"]])
            await session.flush()

            session.add_all([MedicalPrescriptionItem(**row) for row in dataset["items"]])
            session.add_all([MedicalInsuranceClaim(**row) for row in dataset["claims"]])
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return True


async def persist_and_dispose(dataset: dict[str, list[dict]]) -> bool:
    try:
        return await persist_dataset(dataset)
    finally:
        await async_engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成合成医疗业务数据")
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--dry-run", action="store_true", help="只生成并输出摘要，不写数据库")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = build_dataset(args.seed)
    counts = {name: len(rows) for name, rows in dataset.items()}
    print("合成数据规模:", counts)
    print("fingerprint:", dataset_fingerprint(dataset))
    if args.dry_run:
        return 0
    created = asyncio.run(persist_and_dispose(dataset))
    print("写入完成" if created else "无需重复写入")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

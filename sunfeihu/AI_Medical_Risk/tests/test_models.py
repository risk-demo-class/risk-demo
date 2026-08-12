from decimal import Decimal

from app.database import Base
import app.models  # noqa: F401
from app.models_business import (
    MedicalInsuranceClaim,
    MedicalPrescription,
    MedicalPrescriptionItem,
)


BUSINESS_TABLES = {
    "medical_patient",
    "medical_doctor",
    "medical_hospital",
    "medical_registration",
    "medical_prescription",
    "medical_prescription_item",
    "medical_insurance_claim",
    "medical_patient_device",
}

RISK_TABLES = {
    "risk_rule", "risk_event", "risk_feature", "risk_assessment", "risk_case",
    "risk_blacklist", "risk_user_profile", "risk_action_log", "risk_alert",
}
AUTH_TABLES = {"app_user"}


def test_all_eighteen_tables_registered():
    assert set(Base.metadata.tables) == BUSINESS_TABLES | RISK_TABLES | AUTH_TABLES


def test_money_columns_use_decimal_python_type():
    assert MedicalPrescription.total_amount.property.columns[0].type.python_type is Decimal
    assert MedicalPrescriptionItem.unit_price.property.columns[0].type.python_type is Decimal
    for name in ("total_amount", "insurance_amount", "self_pay_amount"):
        assert getattr(MedicalInsuranceClaim, name).property.columns[0].type.python_type is Decimal


def test_expected_composite_indexes_exist():
    assert "idx_rx_patient_issued" in {idx.name for idx in MedicalPrescription.__table__.indexes}
    assert "idx_claim_patient_at" in {
        idx.name for idx in MedicalInsuranceClaim.__table__.indexes
    }

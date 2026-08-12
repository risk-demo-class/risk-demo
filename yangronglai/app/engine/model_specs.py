"""Feature contracts for the five scenario-specific XGBoost models."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelSpec:
    name: str
    scenario: str
    artifact: str
    features: tuple[str, ...]


MODEL_SPECS: dict[str, ModelSpec] = {
    "CARD": ModelSpec(
        name="CARD",
        scenario="CARD",
        artifact="card_fraud_xgb.json",
        features=("amount", "event_hour", "transactions_1h", "device_age_days", "device_user_count", "is_proxy", "credit_score"),
    ),
    "TRANSFER": ModelSpec(
        name="TRANSFER",
        scenario="TRANSFER",
        artifact="transfer_fraud_xgb.json",
        features=("amount", "event_hour", "transactions_1h", "distinct_from_cards_1h", "device_age_days", "device_user_count", "is_proxy", "beneficiary_blacklisted", "city_mismatch"),
    ),
    "LOAN_DEFAULT": ModelSpec(
        name="LOAN_DEFAULT",
        scenario="LOAN",
        artifact="loan_default_xgb.json",
        features=("amount", "term_months", "monthly_income", "debt_ratio", "credit_score", "loan_institution_count_month"),
    ),
    "LOAN_FRAUD": ModelSpec(
        name="LOAN_FRAUD",
        scenario="LOAN",
        artifact="loan_fraud_xgb.json",
        features=("amount", "loan_institution_count_month", "device_age_days", "device_user_count", "is_proxy", "credit_score"),
    ),
    "LOGIN": ModelSpec(
        name="LOGIN",
        scenario="LOGIN",
        artifact="login_ato_xgb.json",
        features=("event_hour", "device_age_days", "device_user_count", "is_proxy", "is_tor", "login_failed"),
    ),
}


SCENARIO_MODELS: dict[str, tuple[str, ...]] = {
    "CARD": ("CARD",),
    "TRANSFER": ("TRANSFER",),
    "LOAN": ("LOAN_DEFAULT", "LOAN_FRAUD"),
    "LOGIN": ("LOGIN",),
}


FEATURE_DEFAULTS = {
    "amount": 0.0,
    "event_hour": 12.0,
    "transactions_1h": 1.0,
    "distinct_from_cards_1h": 1.0,
    "device_age_days": 365.0,
    "device_user_count": 1.0,
    "is_proxy": 0.0,
    "is_tor": 0.0,
    "beneficiary_blacklisted": 0.0,
    "city_mismatch": 0.0,
    "credit_score": 650.0,
    "term_months": 12.0,
    "monthly_income": 10000.0,
    "debt_ratio": 0.3,
    "loan_institution_count_month": 1.0,
    "login_failed": 0.0,
}


def numeric_feature(name: str, features: dict[str, Any]) -> float:
    if name == "city_mismatch":
        current = features.get("current_city")
        usual = features.get("usual_city")
        return float(bool(current and usual and current != usual))
    if name == "login_failed":
        return float(features.get("success") is False)
    value = features.get(name, FEATURE_DEFAULTS[name])
    if value is None:
        value = FEATURE_DEFAULTS[name]
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(FEATURE_DEFAULTS[name])


def vectorize(spec: ModelSpec, features: dict[str, Any]) -> list[float]:
    return [numeric_feature(name, features) for name in spec.features]

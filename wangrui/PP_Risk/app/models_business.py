"""Forty PayPal-like business ORM models from one reviewed schema registry.

The registry keeps a large industry schema auditable while producing normal
SQLAlchemy mapped classes. Risk-engine code imports the generated classes by
their stable CamelCase names.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


BUSINESS_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "user_info": ("user_id", "user_type", "legal_name_hash", "birth_date", "nationality", "residence_country", "preferred_language", "register_time", "user_status"),
    "user_profile": ("user_id", "occupation", "annual_income", "income_currency", "source_of_funds", "expected_monthly_volume", "expected_countries", "risk_level"),
    "user_identity_document": ("document_id", "user_id", "document_type", "document_no_hash", "issuing_country", "expire_date", "verification_status"),
    "user_kyc_review": ("kyc_id", "user_id", "kyc_level", "face_score", "liveness_score", "name_match", "dob_match", "document_match", "review_status", "review_time"),
    "user_address": ("address_id", "user_id", "address_type", "country_code", "region", "city", "postal_code_hash", "address_hash", "verified"),
    "user_contact_point": ("contact_id", "user_id", "contact_type", "contact_hash", "country_code", "verified", "first_seen_time"),
    "user_consent": ("consent_id", "user_id", "consent_type", "policy_version", "country_code", "granted", "granted_time"),
    "merchant_info": ("merchant_id", "legal_name_hash", "trading_name", "registration_no_hash", "registration_country", "merchant_category_code", "industry", "channel", "merchant_status", "create_time"),
    "merchant_beneficial_owner": ("owner_id", "merchant_id", "owner_name_hash", "nationality", "ownership_percent", "control_type", "pep_flag"),
    "merchant_kyb_review": ("kyb_id", "merchant_id", "registration_verified", "license_verified", "address_verified", "owner_verified", "review_status", "review_time"),
    "merchant_store": ("store_id", "merchant_id", "store_name", "store_type", "country_code", "store_status"),
    "merchant_settlement_account": ("settlement_id", "merchant_id", "bank_account_id", "settlement_currency", "settlement_country", "reserve_rate", "account_status"),
    "merchant_risk_profile": ("merchant_id", "business_model", "prohibited_goods_flag", "expected_volume", "avg_ticket_amount", "chargeback_rate", "refund_rate", "risk_level"),
    "wallet_account": ("account_id", "owner_type", "owner_id", "base_currency", "account_status", "open_country", "open_time", "freeze_reason"),
    "wallet_balance": ("balance_id", "account_id", "asset_type", "asset_code", "available_balance", "frozen_balance", "pending_balance", "update_time"),
    "funding_instrument": ("instrument_id", "owner_id", "instrument_type", "provider", "fingerprint_hash", "country_code", "verified", "instrument_status"),
    "bank_account": ("bank_account_id", "instrument_id", "owner_id", "account_no_hash", "bank_code", "account_country", "holder_name_hash", "account_type"),
    "account_limit": ("limit_id", "account_id", "limit_type", "asset_code", "daily_limit", "monthly_limit", "used_amount", "effective_time"),
    "ledger_entry": ("entry_id", "transaction_id", "account_id", "asset_code", "direction", "amount", "balance_before", "balance_after", "entry_time"),
    "payment_transaction": ("transaction_id", "transaction_type", "payer_account_id", "payee_account_id", "amount", "asset_code", "transaction_status", "channel", "create_time", "complete_time"),
    "user_transfer": ("transfer_id", "transaction_id", "sender_user_id", "receiver_user_id", "payment_context", "relationship_type", "note"),
    "merchant_payment": ("payment_id", "transaction_id", "user_id", "merchant_id", "store_id", "payment_mode", "goods_category", "shipping_country"),
    "cross_border_transfer": ("cross_border_id", "transaction_id", "origin_country", "destination_country", "sender_asset", "receiver_asset", "intermediary_country", "transfer_purpose"),
    "transaction_party": ("party_id", "transaction_id", "party_role", "party_type", "party_reference", "country_code", "account_reference"),
    "transaction_status_history": ("history_id", "transaction_id", "old_status", "new_status", "reason_code", "operator_type", "change_time"),
    "fx_conversion": ("fx_id", "transaction_id", "source_asset", "target_asset", "source_amount", "target_amount", "exchange_rate", "spread_amount", "quote_time"),
    "refund": ("refund_id", "original_transaction_id", "refund_transaction_id", "requester_id", "refund_amount", "refund_reason", "refund_status", "request_time"),
    "chargeback": ("chargeback_id", "transaction_id", "instrument_id", "reason_code", "disputed_amount", "evidence_status", "chargeback_status", "create_time"),
    "cash_movement": ("movement_id", "transaction_id", "user_id", "movement_type", "instrument_id", "amount", "asset_code", "movement_status"),
    "device_info": ("device_id", "device_fingerprint_hash", "device_type", "os_version", "app_version", "is_emulator", "is_rooted", "first_seen_time"),
    "user_device": ("user_device_id", "user_id", "device_id", "trust_level", "first_bind_time", "last_active_time", "bind_status"),
    "login_event": ("login_id", "user_id", "device_id", "ip_hash", "login_method", "login_result", "failure_reason", "country_code", "login_time"),
    "network_observation": ("network_id", "ip_hash", "country_code", "asn", "isp", "proxy_flag", "vpn_flag", "tor_flag", "observed_time"),
    "interaction": ("interaction_id", "customer_type", "customer_id", "agent_id", "channel_family", "relationship_start_time", "last_contact_time", "interaction_status"),
    "conversation_segment": ("segment_id", "interaction_id", "channel", "subject", "start_time", "end_time", "segment_status", "language_code"),
    "message": ("message_id", "segment_id", "sender_type", "sender_id", "message_type", "message_text", "language_code", "sent_time", "delivery_status"),
    "email_envelope": ("email_id", "message_id", "from_address_hash", "to_address_hashes", "cc_address_hashes", "subject", "message_id_header_hash", "sent_time"),
    "message_attachment": ("attachment_id", "message_id", "file_name_hash", "file_type", "file_size", "file_hash", "scan_status", "extracted_text"),
    "screening_result": ("screening_id", "subject_type", "subject_id", "screening_type", "provider", "matched_name_hash", "match_score", "list_name", "match_status", "screened_time"),
    "country_risk_profile": ("country_code", "market_enabled", "p2p_enabled", "merchant_enabled", "balance_enabled", "crypto_enabled", "aml_risk_level", "sanctions_level", "fraud_risk_level", "effective_time"),
}

_BOOLEAN_FIELDS = {"verified", "granted", "pep_flag", "registration_verified", "license_verified", "address_verified", "owner_verified", "prohibited_goods_flag", "is_emulator", "is_rooted", "proxy_flag", "vpn_flag", "tor_flag", "market_enabled", "p2p_enabled", "merchant_enabled", "balance_enabled", "crypto_enabled", "name_match", "dob_match", "document_match"}
_NUMERIC_FIELDS = {
    "annual_income",
    "expected_monthly_volume",
    "face_score",
    "liveness_score",
    "ownership_percent",
    "reserve_rate",
    "expected_volume",
    "avg_ticket_amount",
    "chargeback_rate",
    "refund_rate",
    "available_balance",
    "frozen_balance",
    "pending_balance",
    "daily_limit",
    "monthly_limit",
    "used_amount",
    "amount",
    "balance_before",
    "balance_after",
    "source_amount",
    "target_amount",
    "exchange_rate",
    "spread_amount",
    "refund_amount",
    "disputed_amount",
    "match_score",
}
_TIME_MARKERS = ("_time", "_at")


def _class_name(table_name: str) -> str:
    return "".join(part.capitalize() for part in table_name.split("_"))


def _column(field: str, *, primary_key: bool) -> Mapped[Any]:
    if field in _BOOLEAN_FIELDS or field.endswith("_flag"):
        return mapped_column(Boolean, default=False, nullable=not primary_key, primary_key=primary_key)
    if field.endswith(_TIME_MARKERS):
        return mapped_column(DateTime(timezone=True), nullable=not primary_key, primary_key=primary_key)
    if field in _NUMERIC_FIELDS:
        return mapped_column(Numeric(20, 6), nullable=not primary_key, primary_key=primary_key)
    length = 1000 if field in {"message_text", "extracted_text", "note"} else 255
    return mapped_column(String(length), nullable=not primary_key, primary_key=primary_key)


BUSINESS_MODELS: dict[str, type[Base]] = {}
for _table_name, _fields in BUSINESS_TABLE_COLUMNS.items():
    _attributes: dict[str, Any] = {
        "__tablename__": _table_name,
        "__annotations__": {field: Mapped[Any] for field in _fields},
        "__table_args__": (Index(f"idx_{_table_name}_lookup", _fields[0]),),
    }
    for _position, _field in enumerate(_fields):
        _attributes[_field] = _column(_field, primary_key=_position == 0)
    _model = type(_class_name(_table_name), (Base,), _attributes)
    BUSINESS_MODELS[_table_name] = _model
    globals()[_model.__name__] = _model


assert len(BUSINESS_MODELS) == 40

__all__ = [model.__name__ for model in BUSINESS_MODELS.values()] + ["BUSINESS_MODELS", "BUSINESS_TABLE_COLUMNS"]

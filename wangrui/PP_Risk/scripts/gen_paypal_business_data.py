"""Generate a deterministic PayPal-like global payments dataset.

The generator writes 40 business-table CSV files plus auxiliary manifests,
simulation labels, and risk-rule seeds. It does not connect to MySQL and cannot
delete an existing output directory unless ``--overwrite`` is explicitly used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import secrets
import shutil
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any


TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
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

PRESETS: dict[str, tuple[int, int]] = {
    "dev": (100, 1_000),
    "demo": (10_000, 100_000),
    "load": (100_000, 5_000_000),
}

COUNTRIES = ("US", "GB", "DE", "FR", "SG", "AU", "CA", "BR", "MX", "JP", "IN", "HK")
CURRENCIES = {"US": "USD", "GB": "GBP", "DE": "EUR", "FR": "EUR", "SG": "SGD", "AU": "AUD", "CA": "CAD", "BR": "BRL", "MX": "MXN", "JP": "JPY", "IN": "INR", "HK": "HKD"}
LANGUAGES = {"US": "en", "GB": "en", "DE": "de", "FR": "fr", "SG": "en", "AU": "en", "CA": "en", "BR": "pt", "MX": "es", "JP": "ja", "IN": "en", "HK": "zh-Hant"}
RISK_SCENARIOS = ("NORMAL", "STRUCTURING", "RAPID_MOVEMENT", "FUNNEL_ACCOUNT", "ACCOUNT_TAKEOVER", "CARD_TESTING", "SANCTIONS_MATCH", "IDENTITY_FRAUD", "MERCHANT_FRAUD", "SOCIAL_ENGINEERING", "REFUND_ABUSE")


@dataclass(frozen=True)
class GeneratorConfig:
    users: int
    transactions: int
    seed: int = 20260811
    risk_ratio: float = 0.12
    merchants: int | None = None
    interactions: int | None = None
    segments: int | None = None
    messages: int | None = None
    email_ratio: float = 0.20
    attachment_ratio: float = 0.15

    def validate(self) -> None:
        if self.users < 10:
            raise ValueError("users must be at least 10")
        if self.transactions < self.users:
            raise ValueError("transactions must be greater than or equal to users")
        if not 0.0 <= self.risk_ratio <= 0.5:
            raise ValueError("risk_ratio must be between 0.0 and 0.5")
        for name in ("merchants", "interactions", "segments", "messages"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive")
        if self.segments is not None and self.interactions is not None and self.segments < self.interactions:
            raise ValueError("segments must be greater than or equal to interactions")
        if self.messages is not None and self.segments is not None and self.messages < self.segments * 2:
            raise ValueError("messages must be at least twice segments")
        if not 0 <= self.email_ratio <= 1 or not 0 <= self.attachment_ratio <= 1:
            raise ValueError("email and attachment ratios must be between 0 and 1")


def _hash(value: str) -> str:
    return hashlib.sha256(f"AI_RISK_SYNTHETIC::{value}".encode()).hexdigest()


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _money(value: float | Decimal) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"


def _identifier(prefix: str, index: int) -> str:
    return f"{prefix}{index:012d}"


class CsvDatasetWriter:
    def __init__(self, output_dir: Path, *, overwrite: bool = False) -> None:
        self.output_dir = output_dir.resolve()
        if self.output_dir.exists():
            if not overwrite:
                raise FileExistsError(f"output already exists: {self.output_dir}")
            if self.output_dir == self.output_dir.anchor or len(self.output_dir.parts) < 3:
                raise ValueError("refusing to remove an unsafe output directory")
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True)
        self.counts: dict[str, int] = {}

    def write(self, table: str, rows: Iterable[Mapping[str, Any]]) -> None:
        columns = TABLE_COLUMNS[table]
        path = self.output_dir / f"{table}.csv"
        count = 0
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in columns})
                count += 1
        self.counts[table] = count

    def write_auxiliary(self, filename: str, rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> int:
        count = 0
        with (self.output_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
                count += 1
        return count

    def write_bundle(
        self,
        tables: Sequence[str],
        chunks: Iterable[Mapping[str, Sequence[Mapping[str, Any]]]],
    ) -> None:
        """Stream related rows into multiple CSV tables in a single pass."""
        handles = {}
        writers = {}
        counts = {table: 0 for table in tables}
        try:
            for table in tables:
                handle = (self.output_dir / f"{table}.csv").open(
                    "w", encoding="utf-8", newline=""
                )
                handles[table] = handle
                csv_writer = csv.DictWriter(
                    handle, fieldnames=TABLE_COLUMNS[table], extrasaction="raise"
                )
                csv_writer.writeheader()
                writers[table] = csv_writer
            for chunk in chunks:
                for table in tables:
                    for row in chunk.get(table, ()):
                        writers[table].writerow(
                            {column: row.get(column, "") for column in TABLE_COLUMNS[table]}
                        )
                        counts[table] += 1
        finally:
            for handle in handles.values():
                handle.close()
        self.counts.update(counts)


class PayPalLikeGenerator:
    def __init__(self, config: GeneratorConfig) -> None:
        config.validate()
        self.config = config
        self.rng = random.Random(config.seed)
        self.now = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
        self.merchant_count = config.merchants or max(10, config.users // 10)
        self.interaction_count = config.interactions or config.users
        self.segment_count = config.segments or self.interaction_count * 3
        # Preserve the original compact default (two turns per segment), while
        # allowing callers to request realistic multi-turn conversations.
        self.message_count = config.messages or self.segment_count * 2
        self.user_ids = [_identifier("USR", i) for i in range(1, config.users + 1)]
        self.merchant_ids = [_identifier("MER", i) for i in range(1, self.merchant_count + 1)]
        self.interaction_ids = [_identifier("INT", i) for i in range(1, self.interaction_count + 1)]
        self.segment_ids = [_identifier("SEG", i) for i in range(1, self.segment_count + 1)]
        self.segment_channel = {sid: ("EMAIL" if self.rng.random() < config.email_ratio else "CHAT") for sid in self.segment_ids}
        self.user_country = {uid: self.rng.choice(COUNTRIES) for uid in self.user_ids}
        self.user_scenario = {uid: self._scenario() for uid in self.user_ids}
        self.merchant_country = {mid: self.rng.choice(COUNTRIES) for mid in self.merchant_ids}

    def _scenario(self) -> str:
        if self.rng.random() >= self.config.risk_ratio:
            return "NORMAL"
        return self.rng.choice(RISK_SCENARIOS[1:])

    def _time(self, days: int = 365) -> datetime:
        return self.now - timedelta(seconds=self.rng.randint(0, days * 86_400))

    def generate(self, writer: CsvDatasetWriter) -> None:
        generators = {
            "country_risk_profile": self._country_profiles,
            "user_info": self._users,
            "user_profile": self._user_profiles,
            "user_identity_document": self._documents,
            "user_kyc_review": self._kyc_reviews,
            "user_address": self._addresses,
            "user_contact_point": self._contacts,
            "user_consent": self._consents,
            "merchant_info": self._merchants,
            "merchant_beneficial_owner": self._merchant_owners,
            "merchant_kyb_review": self._kyb_reviews,
            "merchant_store": self._stores,
            "merchant_risk_profile": self._merchant_profiles,
            "wallet_account": self._wallets,
            "wallet_balance": self._balances,
            "funding_instrument": self._instruments,
            "bank_account": self._bank_accounts,
            "account_limit": self._limits,
            "device_info": self._devices,
            "user_device": self._user_devices,
            "login_event": self._logins,
            "network_observation": self._networks,
            "interaction": self._interactions,
            "conversation_segment": self._segments,
            "message": self._messages,
            "email_envelope": self._emails,
            "message_attachment": self._attachments,
            "screening_result": self._screenings,
        }
        transaction_tables = (
            "payment_transaction", "user_transfer", "merchant_payment", "cross_border_transfer",
            "transaction_party", "transaction_status_history", "fx_conversion", "refund",
            "chargeback", "cash_movement", "ledger_entry",
        )
        for table in TABLE_COLUMNS:
            if table in transaction_tables or table == "merchant_settlement_account":
                continue
            writer.write(table, generators[table]())
        writer.write("merchant_settlement_account", self._settlements())
        writer.write_bundle(transaction_tables, self._transaction_chunks())

        label_count = writer.write_auxiliary(
            "_simulation_labels.csv",
            ({"entity_type": "USER", "entity_id": uid, "scenario": self.user_scenario[uid]} for uid in self.user_ids),
            ("entity_type", "entity_id", "scenario"),
        )
        rules = build_rule_seeds()
        (writer.output_dir / "_risk_rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = {"seed": self.config.seed, "users": self.config.users, "merchants": self.merchant_count, "transactions": self.config.transactions, "interactions": self.interaction_count, "segments": self.segment_count, "messages": self.message_count, "email_ratio": self.config.email_ratio, "attachment_ratio": self.config.attachment_ratio, "risk_ratio": self.config.risk_ratio, "table_count": len(TABLE_COLUMNS), "row_counts": writer.counts, "label_count": label_count, "rule_count": len(rules), "generated_at": _iso(self.now)}
        (writer.output_dir / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _country_profiles(self) -> Iterator[dict[str, Any]]:
        for idx, country in enumerate(COUNTRIES):
            yield {"country_code": country, "market_enabled": 1, "p2p_enabled": int(country != "IN"), "merchant_enabled": 1, "balance_enabled": int(country not in {"IN"}), "crypto_enabled": int(country in {"US", "GB", "DE", "FR", "SG"}), "aml_risk_level": (idx % 4) + 1, "sanctions_level": 1 if idx < 9 else 2, "fraud_risk_level": (idx % 3) + 1, "effective_time": _iso(self.now)}

    def _users(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            country = self.user_country[uid]
            registered = self._time(900)
            yield {"user_id": uid, "user_type": "PERSONAL", "legal_name_hash": _hash(f"name-{uid}"), "birth_date": f"{self.rng.randint(1960, 2003)}-{self.rng.randint(1,12):02d}-{self.rng.randint(1,28):02d}", "nationality": country, "residence_country": country, "preferred_language": LANGUAGES[country], "register_time": _iso(registered), "user_status": "RESTRICTED" if self.user_scenario[uid] == "SANCTIONS_MATCH" else "ACTIVE"}

    def _user_profiles(self) -> Iterator[dict[str, Any]]:
        for uid in self.user_ids:
            country = self.user_country[uid]
            income = self.rng.randint(20_000, 180_000)
            yield {"user_id": uid, "occupation": self.rng.choice(("EMPLOYEE", "SELF_EMPLOYED", "STUDENT", "RETIRED")), "annual_income": income, "income_currency": CURRENCIES[country], "source_of_funds": self.rng.choice(("SALARY", "BUSINESS", "SAVINGS", "INVESTMENT")), "expected_monthly_volume": _money(income / 12 * self.rng.uniform(0.2, 1.2)), "expected_countries": country, "risk_level": "HIGH" if self.user_scenario[uid] != "NORMAL" else "LOW"}

    def _documents(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            country = self.user_country[uid]
            yield {"document_id": _identifier("DOC", idx), "user_id": uid, "document_type": "PASSPORT", "document_no_hash": _hash(f"passport-{uid}"), "issuing_country": country, "expire_date": f"{self.rng.randint(2027, 2036)}-12-31", "verification_status": "MISMATCH" if self.user_scenario[uid] == "IDENTITY_FRAUD" else "VERIFIED"}

    def _kyc_reviews(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            bad = self.user_scenario[uid] == "IDENTITY_FRAUD"
            yield {"kyc_id": _identifier("KYC", idx), "user_id": uid, "kyc_level": "ENHANCED" if self.user_scenario[uid] != "NORMAL" else "STANDARD", "face_score": 0.42 if bad else round(self.rng.uniform(0.88, 0.999), 4), "liveness_score": 0.51 if bad else round(self.rng.uniform(0.90, 0.999), 4), "name_match": int(not bad), "dob_match": int(not bad), "document_match": int(not bad), "review_status": "MANUAL_REVIEW" if bad else "APPROVED", "review_time": _iso(self._time(700))}

    def _addresses(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            country = self.user_country[uid]
            yield {"address_id": _identifier("ADR", idx), "user_id": uid, "address_type": "RESIDENTIAL", "country_code": country, "region": f"REGION-{country}", "city": f"CITY-{idx % 50:02d}", "postal_code_hash": _hash(f"postal-{uid}"), "address_hash": _hash(f"address-{uid}"), "verified": 1}

    def _contacts(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            for offset, contact_type in enumerate(("EMAIL", "PHONE")):
                yield {"contact_id": _identifier("CON", idx * 2 + offset), "user_id": uid, "contact_type": contact_type, "contact_hash": _hash(f"{contact_type}-{uid}"), "country_code": self.user_country[uid], "verified": 1, "first_seen_time": _iso(self._time(900))}

    def _consents(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            yield {"consent_id": _identifier("CNS", idx), "user_id": uid, "consent_type": "PRIVACY_AND_PAYMENT", "policy_version": "2026.08", "country_code": self.user_country[uid], "granted": 1, "granted_time": _iso(self._time(800))}

    def _merchants(self) -> Iterator[dict[str, Any]]:
        channels = ("ECOMMERCE", "POS", "QR", "SUBSCRIPTION")
        for idx, mid in enumerate(self.merchant_ids, 1):
            country = self.merchant_country[mid]
            yield {"merchant_id": mid, "legal_name_hash": _hash(f"merchant-legal-{mid}"), "trading_name": f"Synthetic Merchant {idx}", "registration_no_hash": _hash(f"registration-{mid}"), "registration_country": country, "merchant_category_code": self.rng.choice(("5411", "5732", "5812", "5999", "7399")), "industry": self.rng.choice(("RETAIL", "DIGITAL_GOODS", "SERVICES", "SUBSCRIPTION")), "channel": channels[idx % len(channels)], "merchant_status": "ACTIVE", "create_time": _iso(self._time(1000))}

    def _merchant_owners(self) -> Iterator[dict[str, Any]]:
        for idx, mid in enumerate(self.merchant_ids, 1):
            yield {"owner_id": _identifier("OWN", idx), "merchant_id": mid, "owner_name_hash": _hash(f"owner-{mid}"), "nationality": self.merchant_country[mid], "ownership_percent": "100.00", "control_type": "DIRECT", "pep_flag": int(idx % 97 == 0)}

    def _kyb_reviews(self) -> Iterator[dict[str, Any]]:
        for idx, mid in enumerate(self.merchant_ids, 1):
            yield {"kyb_id": _identifier("KYB", idx), "merchant_id": mid, "registration_verified": 1, "license_verified": 1, "address_verified": 1, "owner_verified": 1, "review_status": "APPROVED", "review_time": _iso(self._time(700))}

    def _stores(self) -> Iterator[dict[str, Any]]:
        for idx, mid in enumerate(self.merchant_ids, 1):
            yield {"store_id": _identifier("STR", idx), "merchant_id": mid, "store_name": f"Synthetic Store {idx}", "store_type": self.rng.choice(("ONLINE", "POS", "QR", "APP")), "country_code": self.merchant_country[mid], "store_status": "ACTIVE"}

    def _merchant_profiles(self) -> Iterator[dict[str, Any]]:
        for idx, mid in enumerate(self.merchant_ids, 1):
            risky = idx % 29 == 0
            yield {"merchant_id": mid, "business_model": self.rng.choice(("DIRECT", "MARKETPLACE", "SUBSCRIPTION")), "prohibited_goods_flag": int(risky), "expected_volume": _money(self.rng.randint(10_000, 2_000_000)), "avg_ticket_amount": _money(self.rng.randint(10, 500)), "chargeback_rate": "0.0800" if risky else "0.0050", "refund_rate": "0.1800" if risky else "0.0250", "risk_level": "HIGH" if risky else "LOW"}

    def _settlements(self) -> Iterator[dict[str, Any]]:
        for idx, mid in enumerate(self.merchant_ids, 1):
            yield {"settlement_id": _identifier("SET", idx), "merchant_id": mid, "bank_account_id": _identifier("BNK", (idx % self.config.users) + 1), "settlement_currency": CURRENCIES[self.merchant_country[mid]], "settlement_country": self.merchant_country[mid], "reserve_rate": "0.0500", "account_status": "ACTIVE"}

    def _wallets(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            country = self.user_country[uid]
            yield {"account_id": _identifier("ACC", idx), "owner_type": "USER", "owner_id": uid, "base_currency": CURRENCIES[country], "account_status": "ACTIVE", "open_country": country, "open_time": _iso(self._time(900)), "freeze_reason": ""}
        for idx, mid in enumerate(self.merchant_ids, 1):
            country = self.merchant_country[mid]
            yield {"account_id": _identifier("MAC", idx), "owner_type": "MERCHANT", "owner_id": mid, "base_currency": CURRENCIES[country], "account_status": "ACTIVE", "open_country": country, "open_time": _iso(self._time(1000)), "freeze_reason": ""}

    def _balances(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            country = self.user_country[uid]
            yield {"balance_id": _identifier("BAL", idx), "account_id": _identifier("ACC", idx), "asset_type": "FIAT", "asset_code": CURRENCIES[country], "available_balance": _money(self.rng.uniform(0, 20_000)), "frozen_balance": "0.00", "pending_balance": "0.00", "update_time": _iso(self.now)}
        for idx, mid in enumerate(self.merchant_ids, 1):
            country = self.merchant_country[mid]
            yield {"balance_id": _identifier("MBL", idx), "account_id": _identifier("MAC", idx), "asset_type": "FIAT", "asset_code": CURRENCIES[country], "available_balance": _money(self.rng.uniform(0, 200_000)), "frozen_balance": "0.00", "pending_balance": "0.00", "update_time": _iso(self.now)}

    def _instruments(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            yield {"instrument_id": _identifier("INS", idx), "owner_id": uid, "instrument_type": self.rng.choice(("BANK_ACCOUNT", "DEBIT_CARD", "CREDIT_CARD")), "provider": f"BANK-{idx % 20:02d}", "fingerprint_hash": _hash(f"instrument-{uid}"), "country_code": self.user_country[uid], "verified": 1, "instrument_status": "ACTIVE"}

    def _bank_accounts(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            yield {"bank_account_id": _identifier("BNK", idx), "instrument_id": _identifier("INS", idx), "owner_id": uid, "account_no_hash": _hash(f"bank-{uid}"), "bank_code": f"BANK-{idx % 20:02d}", "account_country": self.user_country[uid], "holder_name_hash": _hash(f"name-{uid}"), "account_type": "CHECKING"}

    def _limits(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            country = self.user_country[uid]
            yield {"limit_id": _identifier("LIM", idx), "account_id": _identifier("ACC", idx), "limit_type": "SEND", "asset_code": CURRENCIES[country], "daily_limit": "10000.00", "monthly_limit": "50000.00", "used_amount": _money(self.rng.uniform(0, 5000)), "effective_time": _iso(self.now)}

    def _devices(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            risky = self.user_scenario[uid] in {"ACCOUNT_TAKEOVER", "CARD_TESTING"}
            yield {"device_id": _identifier("DEV", idx), "device_fingerprint_hash": _hash(f"device-{idx if not risky else idx % 5}"), "device_type": self.rng.choice(("MOBILE", "WEB")), "os_version": self.rng.choice(("iOS-19", "Android-16", "Windows-11")), "app_version": "2026.8", "is_emulator": int(risky and idx % 2 == 0), "is_rooted": int(risky and idx % 3 == 0), "first_seen_time": _iso(self._time(600))}

    def _user_devices(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            yield {"user_device_id": _identifier("UDE", idx), "user_id": uid, "device_id": _identifier("DEV", idx), "trust_level": "NEW" if self.user_scenario[uid] == "ACCOUNT_TAKEOVER" else "TRUSTED", "first_bind_time": _iso(self._time(600)), "last_active_time": _iso(self._time(2)), "bind_status": "ACTIVE"}

    def _logins(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            scenario = self.user_scenario[uid]
            country = "US" if scenario == "ACCOUNT_TAKEOVER" and self.user_country[uid] != "US" else self.user_country[uid]
            yield {"login_id": _identifier("LGN", idx), "user_id": uid, "device_id": _identifier("DEV", idx), "ip_hash": _hash(f"ip-{idx % max(10, self.config.users // 5)}"), "login_method": "PASSWORD_MFA", "login_result": "SUCCESS", "failure_reason": "", "country_code": country, "login_time": _iso(self._time(30))}

    def _networks(self) -> Iterator[dict[str, Any]]:
        for idx in range(1, self.config.users + 1):
            uid = self.user_ids[idx - 1]
            risky = self.user_scenario[uid] == "ACCOUNT_TAKEOVER"
            yield {"network_id": _identifier("NET", idx), "ip_hash": _hash(f"ip-{idx % max(10, self.config.users // 5)}"), "country_code": self.user_country[uid], "asn": 64512 + idx % 100, "isp": f"SYNTHETIC-ISP-{idx % 20}", "proxy_flag": int(risky), "vpn_flag": int(risky), "tor_flag": 0, "observed_time": _iso(self._time(30))}

    def _interactions(self) -> Iterator[dict[str, Any]]:
        for idx, interaction_id in enumerate(self.interaction_ids, 1):
            uid = self.user_ids[(idx - 1) % len(self.user_ids)]
            yield {"interaction_id": interaction_id, "customer_type": "USER", "customer_id": uid, "agent_id": f"AGENT-{idx % 20:03d}", "channel_family": "OMNICHANNEL", "relationship_start_time": _iso(self._time(500)), "last_contact_time": _iso(self._time(10)), "interaction_status": self.rng.choice(("ACTIVE", "ACTIVE", "CLOSED"))}

    def _segments(self) -> Iterator[dict[str, Any]]:
        subjects = ("Account access", "Payment review", "Refund request", "Identity verification", "Cross-border transfer")
        for idx, segment_id in enumerate(self.segment_ids, 1):
            interaction_id = self.interaction_ids[(idx - 1) % len(self.interaction_ids)]
            uid = self.user_ids[(idx - 1) % len(self.user_ids)]
            start = self._time(60)
            yield {"segment_id": segment_id, "interaction_id": interaction_id, "channel": self.segment_channel[segment_id], "subject": self.rng.choice(subjects), "start_time": _iso(start), "end_time": _iso(start + timedelta(minutes=self.rng.randint(2, 90))), "segment_status": self.rng.choice(("CLOSED", "CLOSED", "OPEN")), "language_code": LANGUAGES[self.user_country[uid]]}

    def _messages(self) -> Iterator[dict[str, Any]]:
        normal = ("I need help reviewing a recent payment.", "I can help verify the transaction details.", "Can you confirm the amount and date?", "Thank you, that resolves my question.")
        risky_text = ("Someone asked me to share a verification code.", "Do not share codes or install remote access software.", "They asked me to transfer outside the platform.", "I am escalating this conversation for review.")
        for idx in range(1, self.message_count + 1):
            segment_idx = (idx - 1) % self.segment_count
            segment_id = self.segment_ids[segment_idx]
            interaction_idx = segment_idx % self.interaction_count
            user_idx = interaction_idx % self.config.users
            uid = self.user_ids[user_idx]
            is_user = idx % 2 == 1
            texts = risky_text if self.user_scenario[uid] == "SOCIAL_ENGINEERING" else normal
            yield {"message_id": _identifier("MSG", idx), "segment_id": segment_id, "sender_type": "USER" if is_user else "AGENT", "sender_id": uid if is_user else f"AGENT-{(interaction_idx + 1) % 20:03d}", "message_type": "TEXT", "message_text": self.rng.choice(texts), "language_code": LANGUAGES[self.user_country[uid]], "sent_time": _iso(self._time(60)), "delivery_status": self.rng.choice(("DELIVERED", "DELIVERED", "READ"))}

    def _emails(self) -> Iterator[dict[str, Any]]:
        for idx in range(1, self.message_count + 1):
            segment_id = self.segment_ids[(idx - 1) % self.segment_count]
            if self.segment_channel[segment_id] != "EMAIL": continue
            uid = self.user_ids[((idx - 1) % self.segment_count) % self.config.users]
            message_id = _identifier("MSG", idx)
            yield {"email_id": _identifier("EML", idx), "message_id": message_id, "from_address_hash": _hash(f"email-{uid}"), "to_address_hashes": _hash("support@example.invalid"), "cc_address_hashes": "", "subject": "Account and payment support", "message_id_header_hash": _hash(f"header-{message_id}"), "sent_time": _iso(self._time(60))}

    def _attachments(self) -> Iterator[dict[str, Any]]:
        for idx in range(1, self.message_count + 1):
            segment_id = self.segment_ids[(idx - 1) % self.segment_count]
            if self.segment_channel[segment_id] != "EMAIL" or self.rng.random() >= self.config.attachment_ratio: continue
            message_id = _identifier("MSG", idx)
            yield {"attachment_id": _identifier("ATT", idx), "message_id": message_id, "file_name_hash": _hash(f"attachment-{idx}.pdf"), "file_type": "application/pdf", "file_size": 2048 + idx, "file_hash": _hash(f"file-content-{idx}"), "scan_status": "CLEAN", "extracted_text": "Synthetic payment receipt"}

    def _screenings(self) -> Iterator[dict[str, Any]]:
        for idx, uid in enumerate(self.user_ids, 1):
            hit = self.user_scenario[uid] == "SANCTIONS_MATCH"
            yield {"screening_id": _identifier("SCR", idx), "subject_type": "USER", "subject_id": uid, "screening_type": "SANCTIONS_PEP", "provider": "SYNTHETIC_PROVIDER", "matched_name_hash": _hash(f"matched-{uid}") if hit else "", "match_score": "0.9900" if hit else "0.0500", "list_name": "SYNTHETIC_SANCTIONS" if hit else "NONE", "match_status": "MANUAL_REVIEW" if hit else "NO_MATCH", "screened_time": _iso(self._time(30))}

    def _transaction_chunks(self) -> Iterator[dict[str, list[dict[str, Any]]]]:
        transaction_tables = ("payment_transaction", "user_transfer", "merchant_payment", "cross_border_transfer", "transaction_party", "transaction_status_history", "fx_conversion", "refund", "chargeback", "cash_movement", "ledger_entry")
        for idx in range(1, self.config.transactions + 1):
            rows: dict[str, list[dict[str, Any]]] = {table: [] for table in transaction_tables}
            txid = _identifier("TXN", idx)
            payer_idx = self.rng.randint(1, self.config.users)
            payer = self.user_ids[payer_idx - 1]
            payer_account = _identifier("ACC", payer_idx)
            scenario = self.user_scenario[payer]
            tx_type = self.rng.choices(("USER_TRANSFER", "MERCHANT_PAYMENT", "CROSS_BORDER", "TOP_UP", "WITHDRAWAL"), weights=(35, 40, 10, 8, 7), k=1)[0]
            amount = self.rng.uniform(5, 1500)
            if scenario in {"STRUCTURING", "RAPID_MOVEMENT", "FUNNEL_ACCOUNT"}:
                amount = self.rng.uniform(8500, 9999)
            created = self._time(180)
            payee_account = payer_account
            receiver = payer
            merchant = ""
            if tx_type in {"USER_TRANSFER", "CROSS_BORDER"}:
                receiver_idx = self.rng.randint(1, self.config.users)
                receiver = self.user_ids[receiver_idx - 1]
                payee_account = _identifier("ACC", receiver_idx)
            elif tx_type == "MERCHANT_PAYMENT":
                merchant_idx = self.rng.randint(1, self.merchant_count)
                merchant = self.merchant_ids[merchant_idx - 1]
                payee_account = _identifier("MAC", merchant_idx)
            currency = CURRENCIES[self.user_country[payer]]
            rows["payment_transaction"].append({"transaction_id": txid, "transaction_type": tx_type, "payer_account_id": payer_account, "payee_account_id": payee_account, "amount": _money(amount), "asset_code": currency, "transaction_status": "COMPLETED", "channel": self.rng.choice(("WEB", "APP", "QR", "API")), "create_time": _iso(created), "complete_time": _iso(created + timedelta(seconds=self.rng.randint(1, 120)))})
            rows["transaction_status_history"].append({"history_id": _identifier("HIS", idx), "transaction_id": txid, "old_status": "CREATED", "new_status": "COMPLETED", "reason_code": "APPROVED", "operator_type": "SYSTEM", "change_time": _iso(created + timedelta(seconds=120))})
            rows["transaction_party"].extend((
                {"party_id": f"PTY{idx:012d}A", "transaction_id": txid, "party_role": "PAYER", "party_type": "USER", "party_reference": payer, "country_code": self.user_country[payer], "account_reference": payer_account},
                {"party_id": f"PTY{idx:012d}B", "transaction_id": txid, "party_role": "PAYEE", "party_type": "MERCHANT" if merchant else "USER", "party_reference": merchant or receiver, "country_code": self.merchant_country[merchant] if merchant else self.user_country[receiver], "account_reference": payee_account},
            ))
            rows["ledger_entry"].extend((
                {"entry_id": f"LED{idx:012d}D", "transaction_id": txid, "account_id": payer_account, "asset_code": currency, "direction": "DEBIT", "amount": _money(amount), "balance_before": _money(amount + 1000), "balance_after": "1000.00", "entry_time": _iso(created)},
                {"entry_id": f"LED{idx:012d}C", "transaction_id": txid, "account_id": payee_account, "asset_code": currency, "direction": "CREDIT", "amount": _money(amount), "balance_before": "1000.00", "balance_after": _money(amount + 1000), "entry_time": _iso(created)},
            ))
            if tx_type == "USER_TRANSFER":
                rows["user_transfer"].append({"transfer_id": _identifier("UTR", idx), "transaction_id": txid, "sender_user_id": payer, "receiver_user_id": receiver, "payment_context": self.rng.choice(("FRIENDS_FAMILY", "GOODS_SERVICES")), "relationship_type": "KNOWN" if idx % 3 else "NEW", "note": "Synthetic transfer"})
            elif tx_type == "MERCHANT_PAYMENT":
                merchant_idx = int(merchant[-12:])
                rows["merchant_payment"].append({"payment_id": _identifier("PAY", idx), "transaction_id": txid, "user_id": payer, "merchant_id": merchant, "store_id": _identifier("STR", merchant_idx), "payment_mode": self.rng.choice(("ONLINE", "POS", "QR", "SUBSCRIPTION")), "goods_category": "GENERAL", "shipping_country": self.user_country[payer]})
            elif tx_type == "CROSS_BORDER":
                destination = self.user_country[receiver]
                target_currency = CURRENCIES[destination]
                rows["cross_border_transfer"].append({"cross_border_id": _identifier("CBR", idx), "transaction_id": txid, "origin_country": self.user_country[payer], "destination_country": destination, "sender_asset": currency, "receiver_asset": target_currency, "intermediary_country": "", "transfer_purpose": "PERSONAL_REMITTANCE"})
                rows["fx_conversion"].append({"fx_id": _identifier("FXC", idx), "transaction_id": txid, "source_asset": currency, "target_asset": target_currency, "source_amount": _money(amount), "target_amount": _money(amount * 0.93), "exchange_rate": "0.930000", "spread_amount": _money(amount * 0.02), "quote_time": _iso(created)})
            else:
                rows["cash_movement"].append({"movement_id": _identifier("CSH", idx), "transaction_id": txid, "user_id": payer, "movement_type": tx_type, "instrument_id": _identifier("INS", payer_idx), "amount": _money(amount), "asset_code": currency, "movement_status": "COMPLETED"})
            if tx_type == "MERCHANT_PAYMENT" and idx % 50 == 0:
                rows["refund"].append({"refund_id": _identifier("REF", idx), "original_transaction_id": txid, "refund_transaction_id": "", "requester_id": payer, "refund_amount": _money(amount), "refund_reason": "CUSTOMER_REQUEST", "refund_status": "COMPLETED", "request_time": _iso(created + timedelta(days=1))})
            if tx_type == "MERCHANT_PAYMENT" and idx % 100 == 0:
                rows["chargeback"].append({"chargeback_id": _identifier("CHB", idx), "transaction_id": txid, "instrument_id": _identifier("INS", payer_idx), "reason_code": "UNAUTHORIZED", "disputed_amount": _money(amount), "evidence_status": "PENDING", "chargeback_status": "OPEN", "create_time": _iso(created + timedelta(days=7))})
            yield rows


def build_rule_seeds() -> list[dict[str, Any]]:
    category_counts = {"KYC_KYB": 16, "AML": 18, "PAYMENT_FRAUD": 12, "ACCOUNT_TAKEOVER": 8, "SANCTIONS_PEP": 6, "REFUND_CHARGEBACK": 6, "COMMUNICATION": 8}
    rules: list[dict[str, Any]] = []
    index = 0
    for category, count in category_counts.items():
        for category_index in range(1, count + 1):
            index += 1
            action = "REJECT" if category in {"SANCTIONS_PEP"} and category_index <= 2 else "MANUAL_REVIEW"
            rules.append({"rule_id": f"PAYPAL-RULE-{index:03d}", "rule_name": f"{category} synthetic control {category_index:02d}", "category": category, "business_event_type": "ALL", "condition": {"feature": f"{category.lower()}_signal_{category_index:02d}", "operator": ">=", "value": round(0.5 + category_index / (count * 2), 4)}, "risk_score": min(100, 55 + category_index * 3), "action": action, "enabled": True, "version": 1})
    return rules


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=PRESETS, default="dev")
    parser.add_argument("--users", type=int)
    parser.add_argument("--transactions", type=int)
    parser.add_argument("--merchants", type=int)
    parser.add_argument("--interactions", type=int)
    parser.add_argument("--segments", type=int)
    parser.add_argument("--messages", type=int)
    parser.add_argument("--email-ratio", type=float, default=0.20)
    parser.add_argument("--attachment-ratio", type=float, default=0.15)
    parser.add_argument("--risk-ratio", type=float, default=0.12)
    seed_group = parser.add_mutually_exclusive_group()
    seed_group.add_argument("--seed", type=int, default=20260811)
    seed_group.add_argument("--random-seed", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("generated/paypal_dev"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    preset_users, preset_transactions = PRESETS[args.preset]
    seed = secrets.randbits(63) if args.random_seed else args.seed
    config = GeneratorConfig(users=args.users or preset_users, transactions=args.transactions or preset_transactions, seed=seed, risk_ratio=args.risk_ratio, merchants=args.merchants, interactions=args.interactions, segments=args.segments, messages=args.messages, email_ratio=args.email_ratio, attachment_ratio=args.attachment_ratio)
    writer = CsvDatasetWriter(args.output, overwrite=args.overwrite)
    PayPalLikeGenerator(config).generate(writer)
    print(f"Generated {len(TABLE_COLUMNS)} tables in {writer.output_dir}")
    print(f"Rows: {sum(writer.counts.values()):,}; rules: {len(build_rule_seeds())}")
    print(f"Seed: {seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

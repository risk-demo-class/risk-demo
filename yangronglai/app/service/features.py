"""Hydrate business events and compute shared rule/model/graph features."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import (
    BankCard,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)
from app.schemas import RiskCheckRequest, Scenario


class RiskValidationError(ValueError):
    """Raised when a risk event cannot be safely evaluated."""


@dataclass(frozen=True, slots=True)
class EventContext:
    event_data: dict[str, Any]
    event_time: datetime
    features: dict[str, Any]


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _parse_datetime(value: Any, default: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return default or _utc_naive_now()
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class BankFeatureService:
    version = "bank-rule-v1"

    async def build(
        self,
        request: RiskCheckRequest,
        session: AsyncSession,
    ) -> EventContext:
        data = dict(request.event_data)
        source_loaded = False

        if request.scenario in {Scenario.CARD, Scenario.TRANSFER}:
            transaction = await session.get(Transaction, request.source_id)
            if transaction is not None:
                self._assert_owner(request, transaction.user_id)
                data.update(
                    {
                        "amount": float(transaction.amount),
                        "from_card": transaction.from_card,
                        "to_card": transaction.to_card,
                        "channel": transaction.channel,
                        "txn_type": transaction.txn_type,
                        "device_id": transaction.device_id,
                        "ip": transaction.ip,
                        "geo": transaction.geo,
                        "occurred_at": transaction.occurred_at.isoformat(),
                    }
                )
                source_loaded = True
        elif request.scenario is Scenario.LOAN:
            loan = await session.get(LoanApplication, request.source_id)
            if loan is not None:
                self._assert_owner(request, loan.user_id)
                data.update(
                    {
                        "amount": float(loan.amount),
                        "term_months": loan.term_months,
                        "purpose": loan.purpose,
                        "monthly_income": float(loan.monthly_income),
                        "debt_ratio": float(loan.debt_ratio),
                        "institution_code": loan.institution_code,
                        "device_id": loan.device_id,
                        "ip": loan.ip,
                        "applied_at": loan.applied_at.isoformat(),
                    }
                )
                source_loaded = True
        elif request.scenario is Scenario.LOGIN:
            login = await session.get(LoginLog, request.source_id)
            if login is not None:
                self._assert_owner(request, login.user_id)
                data.update(
                    {
                        "device_id": login.device_id,
                        "ip": login.ip,
                        "geo": login.geo,
                        "success": login.success,
                        "login_at": login.login_at.isoformat(),
                    }
                )
                source_loaded = True

        self._validate_required(request.scenario, data, source_loaded)
        event_time = _parse_datetime(
            data.get("event_time")
            or data.get("occurred_at")
            or data.get("applied_at")
            or data.get("login_at")
        )
        features = {key: _json_value(value) for key, value in data.items()}
        features.update(
            {
                "scenario": request.scenario.value,
                "source_id": request.source_id,
                "user_id": request.user_id,
                "event_hour": event_time.hour,
                "event_time": event_time.isoformat(),
            }
        )

        user = await session.get(UserInfo, request.user_id)
        if user is not None:
            features["credit_score"] = user.credit_score
            features["kyc_level"] = user.kyc_level

        await self._add_ip_features(features, session)
        await self._add_location_features(request.user_id, features, session)
        await self._add_device_features(features, event_time, session)
        if request.scenario in {Scenario.CARD, Scenario.TRANSFER}:
            await self._add_transaction_features(request, features, event_time, session)
        if request.scenario is Scenario.LOAN:
            await self._add_loan_features(request, features, event_time, session)
        if request.scenario is Scenario.TRANSFER:
            await self._add_blacklist_feature(features, event_time, session)

        return EventContext(event_data=data, event_time=event_time, features=features)

    @staticmethod
    def _assert_owner(request: RiskCheckRequest, actual_user_id: str) -> None:
        if request.user_id != actual_user_id:
            raise RiskValidationError("user_id 与业务数据所属用户不一致")

    @staticmethod
    def _validate_required(scenario: Scenario, data: dict[str, Any], source_loaded: bool) -> None:
        required = {
            Scenario.CARD: ("amount",),
            Scenario.TRANSFER: ("amount", "to_card"),
            Scenario.LOAN: ("amount", "institution_code"),
            Scenario.LOGIN: ("ip",),
        }[scenario]
        missing = [field for field in required if data.get(field) in (None, "")]
        if missing:
            hint = "业务表未找到 source_id，" if not source_loaded else ""
            raise RiskValidationError(f"{hint}event_data 缺少字段: {', '.join(missing)}")

    @staticmethod
    async def _add_ip_features(features: dict[str, Any], session: AsyncSession) -> None:
        ip = features.get("ip")
        ip_geo = await session.get(IpGeoLocation, ip) if ip else None
        if ip_geo is not None:
            features.update(
                {
                    "ip_country": ip_geo.country,
                    "ip_province": ip_geo.province,
                    "ip_city": ip_geo.city,
                    "is_proxy": ip_geo.is_proxy,
                    "is_tor": ip_geo.is_tor,
                }
            )
        else:
            features.setdefault("is_proxy", False)
            features.setdefault("is_tor", False)

    @staticmethod
    async def _add_location_features(
        user_id: str,
        features: dict[str, Any],
        session: AsyncSession,
    ) -> None:
        current_city = (
            features.get("current_city")
            or features.get("login_city")
            or features.get("ip_city")
            or features.get("geo")
        )
        features["current_city"] = current_city
        if features.get("usual_city"):
            return
        result = await session.scalars(
            select(LoginLog.geo)
            .where(LoginLog.user_id == user_id, LoginLog.success.is_(True), LoginLog.geo.is_not(None))
            .order_by(LoginLog.login_at.desc())
            .limit(100)
        )
        cities = [city for city in result.all() if city]
        features["usual_city"] = Counter(cities).most_common(1)[0][0] if cities else current_city

    @staticmethod
    async def _add_device_features(
        features: dict[str, Any],
        event_time: datetime,
        session: AsyncSession,
    ) -> None:
        device_id = features.get("device_id")
        if not device_id:
            features.setdefault("device_age_days", None)
            features.setdefault("device_user_count", 0)
            return
        records = (
            await session.scalars(
                select(DeviceFingerprint).where(DeviceFingerprint.device_id == device_id)
            )
        ).all()
        if records:
            first_seen = min(record.first_seen for record in records)
            features["device_age_days"] = max(0, (event_time - first_seen).days)
            features["device_user_count"] = len({record.user_id for record in records})
        else:
            features.setdefault("device_age_days", None)
            features.setdefault("device_user_count", 0)

    @staticmethod
    async def _add_transaction_features(
        request: RiskCheckRequest,
        features: dict[str, Any],
        event_time: datetime,
        session: AsyncSession,
    ) -> None:
        start_time = event_time - timedelta(hours=1)
        user_rows = (
            await session.scalars(
                select(Transaction).where(
                    Transaction.user_id == request.user_id,
                    Transaction.occurred_at >= start_time,
                    Transaction.occurred_at <= event_time,
                )
            )
        ).all()
        user_txn_ids = {row.txn_id for row in user_rows}
        features["transactions_1h"] = len(user_rows) + (0 if request.source_id in user_txn_ids else 1)

        to_card = features.get("to_card")
        if not to_card:
            features.setdefault("distinct_from_cards_1h", 0)
            return
        collection_rows = (
            await session.scalars(
                select(Transaction).where(
                    Transaction.to_card == to_card,
                    Transaction.occurred_at >= start_time,
                    Transaction.occurred_at <= event_time,
                )
            )
        ).all()
        source_cards = {row.from_card for row in collection_rows if row.from_card}
        if request.source_id not in {row.txn_id for row in collection_rows} and features.get("from_card"):
            source_cards.add(features["from_card"])
        features["distinct_from_cards_1h"] = len(source_cards)

    @staticmethod
    async def _add_loan_features(
        request: RiskCheckRequest,
        features: dict[str, Any],
        event_time: datetime,
        session: AsyncSession,
    ) -> None:
        month_start = event_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if event_time.month == 12:
            next_month = month_start.replace(year=event_time.year + 1, month=1)
        else:
            next_month = month_start.replace(month=event_time.month + 1)
        rows = (
            await session.scalars(
                select(LoanApplication).where(
                    LoanApplication.user_id == request.user_id,
                    LoanApplication.applied_at >= month_start,
                    LoanApplication.applied_at < next_month,
                )
            )
        ).all()
        institutions = {row.institution_code for row in rows}
        if request.source_id not in {row.loan_id for row in rows} and features.get("institution_code"):
            institutions.add(features["institution_code"])
        features["loan_institution_count_month"] = len(institutions)

    @staticmethod
    async def _add_blacklist_feature(
        features: dict[str, Any],
        event_time: datetime,
        session: AsyncSession,
    ) -> None:
        to_card = features.get("to_card")
        candidates = {to_card} if to_card else set()
        card = await session.get(BankCard, to_card) if to_card else None
        if card is not None:
            candidates.add(card.card_no_hash)
        if not candidates:
            features["beneficiary_blacklisted"] = False
            return
        hit = await session.scalar(
            select(BlacklistExtra.entry_id).where(
                BlacklistExtra.entry_type.in_(["BANK_CARD", "CARD"]),
                BlacklistExtra.value.in_(candidates),
                BlacklistExtra.is_enabled.is_(True),
                or_(BlacklistExtra.expire_at.is_(None), BlacklistExtra.expire_at > event_time),
            )
        )
        features["beneficiary_blacklisted"] = hit is not None


feature_service = BankFeatureService()

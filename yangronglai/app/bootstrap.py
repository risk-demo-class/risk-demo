"""Idempotent schema, mandatory-rule and demo-data initialization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  # register all mappings before create_all
from app.database import Base, get_engine, get_session_factory
from app.engine.rule_catalog import RULE_CATALOG
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
from app.models_risk import RiskActionLog, RiskLabel, RiskRule


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def create_schema() -> None:
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def drop_schema() -> None:
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


async def seed_mandatory_rules(session: AsyncSession) -> int:
    """Insert missing rules without overwriting operator changes to existing rows."""
    inserted = 0
    for definition in RULE_CATALOG:
        if await session.get(RiskRule, definition["rule_id"]) is None:
            session.add(RiskRule(**definition))
            session.add(
                RiskActionLog(
                    operator="system",
                    action_type="CREATE_RULE",
                    target_type="rule",
                    target_id=definition["rule_id"],
                    after_value=definition,
                    remark="阶段 3 初始化银行必备规则",
                )
            )
            inserted += 1
    await session.flush()
    return inserted


async def seed_demo_business_data(session: AsyncSession) -> bool:
    """Create a compact deterministic dataset with one case for every rule."""
    if await session.get(UserInfo, "U_SAFE") is not None:
        return False

    now = _now().replace(microsecond=0)
    night = now.replace(hour=2, minute=30, second=0)
    month_base = now.replace(day=min(now.day, 10), hour=10, minute=0, second=0)
    user_ids = [
        "U_SAFE",
        "U_R001",
        "U_R002",
        "U_R005",
        "U_R008_A",
        "U_R008_B",
        "U_R008_C",
        "U_R012",
        "U_R025",
        "U_R030",
        "U_SHARED_1",
        "U_SHARED_2",
        "U_SHARED_3",
        "U_SHARED_4",
        "U_SHARED_5",
    ]
    session.add_all(
        [
            UserInfo(
                user_id=user_id,
                name=f"演示客户-{user_id}",
                id_card_hash=f"IDHASH-{user_id}",
                credit_score=720 if user_id == "U_SAFE" else 610,
                register_at=now - timedelta(days=180),
                kyc_level="KYC3",
            )
            for user_id in user_ids
        ]
    )

    card_owners = {
        "CARD_SAFE": "U_SAFE",
        "CARD_TARGET_SAFE": "U_SAFE",
        "CARD_R001": "U_R001",
        "CARD_R001_TARGET": "U_SAFE",
        "CARD_R002": "U_R002",
        "CARD_R005": "U_R005",
        "CARD_R005_TARGET": "U_SAFE",
        "CARD_R008_A": "U_R008_A",
        "CARD_R008_B": "U_R008_B",
        "CARD_R008_C": "U_R008_C",
        "CARD_R008_TARGET": "U_SAFE",
        "CARD_R030": "U_R030",
        "CARD_BLACK": "U_SAFE",
    }
    session.add_all(
        [
            BankCard(
                card_id=card_id,
                user_id=user_id,
                card_no_hash=f"HASH-{card_id}",
                bank_code="DEMO_BANK",
                card_type="CREDIT" if "R002" in card_id else "DEBIT",
                credit_limit=Decimal("100000.00"),
                status="ACTIVE",
                opened_at=now - timedelta(days=160),
            )
            for card_id, user_id in card_owners.items()
        ]
    )

    session.add_all(
        [
            IpGeoLocation(ip="10.0.0.1", country="CN", province="北京", city="北京", isp="DEMO", is_proxy=False, is_tor=False),
            IpGeoLocation(ip="10.0.0.2", country="CN", province="上海", city="上海", isp="DEMO", is_proxy=False, is_tor=False),
            IpGeoLocation(ip="10.0.0.25", country="CN", province="广东", city="深圳", isp="PROXY", is_proxy=True, is_tor=False),
        ]
    )

    session.add_all(
        [
            LoginLog(login_id="LOGIN_R001_HOME_1", user_id="U_R001", device_id="DEV_R001", ip="10.0.0.1", geo="北京", success=True, login_at=now - timedelta(days=10)),
            LoginLog(login_id="LOGIN_R001_HOME_2", user_id="U_R001", device_id="DEV_R001", ip="10.0.0.1", geo="北京", success=True, login_at=now - timedelta(days=5)),
            LoginLog(login_id="LOGIN_R018", user_id="U_SHARED_1", device_id="DEV_SHARED", ip="10.0.0.1", geo="北京", success=True, login_at=now),
            LoginLog(login_id="LOGIN_R025", user_id="U_R025", device_id="DEV_R025", ip="10.0.0.25", geo="深圳", success=True, login_at=now),
        ]
    )

    device_rows = [
        DeviceFingerprint(device_id="DEV_R001", user_id="U_R001", fingerprint_hash="FP-R001", first_seen=now - timedelta(days=90), last_seen=now, os="Windows", browser="Edge"),
        DeviceFingerprint(device_id="DEV_R002", user_id="U_R002", fingerprint_hash="FP-R002", first_seen=now - timedelta(days=90), last_seen=now, os="Android", browser="App"),
        DeviceFingerprint(device_id="DEV_R005", user_id="U_R005", fingerprint_hash="FP-R005", first_seen=now - timedelta(days=2), last_seen=now, os="iOS", browser="App"),
        DeviceFingerprint(device_id="DEV_R025", user_id="U_R025", fingerprint_hash="FP-R025", first_seen=now - timedelta(days=60), last_seen=now, os="Linux", browser="Firefox"),
    ]
    device_rows.extend(
        DeviceFingerprint(
            device_id="DEV_SHARED",
            user_id=f"U_SHARED_{index}",
            fingerprint_hash="FP-SHARED",
            first_seen=now - timedelta(days=30),
            last_seen=now,
            os="Android",
            browser="App",
        )
        for index in range(1, 6)
    )
    session.add_all(device_rows)

    session.add_all(
        [
            Transaction(txn_id="TXN_SAFE", user_id="U_SAFE", from_card="CARD_SAFE", to_card="CARD_TARGET_SAFE", amount=Decimal("1000.00"), channel="MOBILE", txn_type="TRANSFER", device_id=None, ip="10.0.0.1", geo="北京", occurred_at=now),
            Transaction(txn_id="TXN_R001", user_id="U_R001", from_card="CARD_R001", to_card="CARD_R001_TARGET", amount=Decimal("60000.00"), channel="MOBILE", txn_type="TRANSFER", device_id="DEV_R001", ip="10.0.0.2", geo="上海", occurred_at=now),
            Transaction(txn_id="TXN_R002_1", user_id="U_R002", from_card="CARD_R002", to_card=None, amount=Decimal("200.00"), channel="POS", txn_type="CARD_PURCHASE", device_id="DEV_R002", ip="10.0.0.1", geo="北京", occurred_at=night - timedelta(minutes=30)),
            Transaction(txn_id="TXN_R002_2", user_id="U_R002", from_card="CARD_R002", to_card=None, amount=Decimal("220.00"), channel="POS", txn_type="CARD_PURCHASE", device_id="DEV_R002", ip="10.0.0.1", geo="北京", occurred_at=night - timedelta(minutes=15)),
            Transaction(txn_id="TXN_R002_3", user_id="U_R002", from_card="CARD_R002", to_card=None, amount=Decimal("260.00"), channel="POS", txn_type="CARD_PURCHASE", device_id="DEV_R002", ip="10.0.0.1", geo="北京", occurred_at=night),
            Transaction(txn_id="TXN_R005", user_id="U_R005", from_card="CARD_R005", to_card="CARD_R005_TARGET", amount=Decimal("40000.00"), channel="MOBILE", txn_type="TRANSFER", device_id="DEV_R005", ip="10.0.0.1", geo="北京", occurred_at=now),
            Transaction(txn_id="TXN_R008_1", user_id="U_R008_A", from_card="CARD_R008_A", to_card="CARD_R008_TARGET", amount=Decimal("8000.00"), channel="MOBILE", txn_type="TRANSFER", device_id=None, ip="10.0.0.1", geo="北京", occurred_at=now - timedelta(minutes=30)),
            Transaction(txn_id="TXN_R008_2", user_id="U_R008_B", from_card="CARD_R008_B", to_card="CARD_R008_TARGET", amount=Decimal("9000.00"), channel="MOBILE", txn_type="TRANSFER", device_id=None, ip="10.0.0.1", geo="北京", occurred_at=now - timedelta(minutes=15)),
            Transaction(txn_id="TXN_R008_3", user_id="U_R008_C", from_card="CARD_R008_C", to_card="CARD_R008_TARGET", amount=Decimal("10000.00"), channel="MOBILE", txn_type="TRANSFER", device_id=None, ip="10.0.0.1", geo="北京", occurred_at=now),
            Transaction(txn_id="TXN_R030", user_id="U_R030", from_card="CARD_R030", to_card="CARD_BLACK", amount=Decimal("500.00"), channel="MOBILE", txn_type="TRANSFER", device_id=None, ip="10.0.0.1", geo="北京", occurred_at=now),
        ]
    )

    session.add_all(
        [
            LoanApplication(loan_id="LOAN_R012_1", user_id="U_R012", amount=Decimal("30000.00"), term_months=12, purpose="经营", monthly_income=Decimal("15000.00"), debt_ratio=Decimal("0.25"), institution_code="BANK_A", status="PENDING", applied_at=month_base - timedelta(days=2)),
            LoanApplication(loan_id="LOAN_R012_2", user_id="U_R012", amount=Decimal("40000.00"), term_months=12, purpose="经营", monthly_income=Decimal("15000.00"), debt_ratio=Decimal("0.25"), institution_code="BANK_B", status="PENDING", applied_at=month_base - timedelta(days=1)),
            LoanApplication(loan_id="LOAN_R012_3", user_id="U_R012", amount=Decimal("50000.00"), term_months=24, purpose="经营", monthly_income=Decimal("15000.00"), debt_ratio=Decimal("0.25"), institution_code="BANK_C", status="PENDING", applied_at=month_base),
        ]
    )

    session.add(
        BlacklistExtra(
            entry_type="BANK_CARD",
            value="HASH-CARD_BLACK",
            reason="涉诈收款卡演示数据",
            is_enabled=True,
        )
    )
    labeled_events = [
        ("TRANSFER", "TXN_SAFE", "U_SAFE", "LEGIT"),
        ("TRANSFER", "TXN_R001", "U_R001", "FRAUD"),
        ("CARD", "TXN_R002_3", "U_R002", "FRAUD"),
        ("TRANSFER", "TXN_R005", "U_R005", "FRAUD"),
        ("TRANSFER", "TXN_R008_3", "U_R008_C", "FRAUD"),
        ("LOAN", "LOAN_R012_3", "U_R012", "FRAUD"),
        ("LOGIN", "LOGIN_R018", "U_SHARED_1", "FRAUD"),
        ("LOGIN", "LOGIN_R025", "U_R025", "FRAUD"),
        ("TRANSFER", "TXN_R030", "U_R030", "FRAUD"),
    ]
    session.add_all(
        RiskLabel(
            scenario=scenario,
            source_id=source_id,
            user_id=user_id,
            label=label,
            label_source="SIMULATION",
            confidence=Decimal("1.0000"),
            notes="演示数据人工预设真值，不由规则决策反推",
        )
        for scenario, source_id, user_id, label in labeled_events
    )
    await session.flush()
    return True


async def initialize_database(seed_demo: bool = True) -> dict[str, int | bool]:
    await create_schema()
    async with get_session_factory()() as session:
        try:
            rules_inserted = await seed_mandatory_rules(session)
            demo_inserted = await seed_demo_business_data(session) if seed_demo else False
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return {"rules_inserted": rules_inserted, "demo_inserted": demo_inserted}

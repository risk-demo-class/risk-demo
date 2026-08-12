"""Create the pingpong MySQL database and load deterministic synthetic data.

Examples:
  export PINGPONG_DB_PASSWORD='...'
  python seed_data.py --host 127.0.0.1 --port 9999 --reset

All identities, accounts and transactions are synthetic and unsuitable for production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

from faker import Faker
from sqlalchemy import URL, create_engine, func, select, text
from sqlalchemy.orm import Session

from models import (
    ALL_MODELS,
    AuthEvent,
    BankAccount,
    Base,
    CaseEntity,
    Counterparty,
    Customer,
    CustomerPersonRole,
    Device,
    EntityRelation,
    FxOrder,
    InboundAudit,
    InboundOrderAllocation,
    InboundPayment,
    LedgerAccount,
    LedgerEntry,
    Partner,
    Payout,
    Person,
    RiskCase,
    RiskBlacklist,
    RiskDecision,
    RiskEvent,
    RiskRule,
    Store,
    StoreVirtualAccountLink,
    TradeDocument,
    TradeOrder,
    VirtualAccount,
)


SEED = 20260811
NOW = datetime(2026, 8, 11, 8, 0, 0)
COUNTRIES = ["CN", "HK", "US", "GB", "DE", "FR", "SG", "JP", "AU", "CA", "AE", "BR"]
PAYMENT_COUNTRIES = ["US", "GB", "DE", "FR", "SG", "JP", "AU", "CA", "AE", "BR"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "SGD", "CNY"]
USD_RATES = {
    "USD": Decimal("1"),
    "EUR": Decimal("1.09"),
    "GBP": Decimal("1.28"),
    "JPY": Decimal("0.0068"),
    "SGD": Decimal("0.75"),
    "CNY": Decimal("0.139"),
}
PLATFORMS = ["AMAZON", "EBAY", "WISH", "SHOPEE", "WALMART", "SHOPIFY", "INDEPENDENT"]
BUSINESS_TYPES = ["ECOMMERCE_PLATFORM", "SELF_STATION", "B2B_COMMERCE", "SERVICE_TRADE"]
SERVICE_PURPOSES = ["05", "06", "07", "08", "09", "10", "11"]
PURPOSE_BY_BUSINESS = {
    "ECOMMERCE_PLATFORM": "01",
    "SELF_STATION": "01",
    "B2B_COMMERCE": "02",
    "SERVICE_TRADE": "06",
}
PURPOSE_DOMAIN = {
    "01": "ecommerce",
    "02": "general_trade",
    "03": "top_up",
    "04": "debit",
    "05": "service_trade",
    "06": "service_trade",
    "07": "service_trade",
    "08": "service_trade",
    "09": "service_trade",
    "10": "service_trade",
    "11": "service_trade",
}
INBOUND_STATUSES = ["APPROVED", "DECLINED", "REJECTED", "REFUNDED", "PROCESSING"]


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def rate(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)


def score(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def uid(prefix: str, index: int | None = None) -> str:
    tail = f"{index:08d}" if index is not None else uuid.uuid4().hex[:16]
    return f"{prefix}_{tail}"


def dt_days_ago(rng: random.Random, max_days: int = 180) -> datetime:
    return NOW - timedelta(
        days=rng.randint(0, max_days),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
        seconds=rng.randint(0, 59),
    )


def build_url(args: argparse.Namespace, database: str | None) -> URL:
    return URL.create(
        "mysql+pymysql",
        username=args.user,
        password=args.password,
        host=args.host,
        port=args.port,
        database=database,
        query={"charset": "utf8mb4"},
    )


def create_database(args: argparse.Namespace) -> None:
    engine = create_engine(build_url(args, None), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE DATABASE IF NOT EXISTS `pingpong` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
        )
    engine.dispose()


def add_ledger_entry(
    session: Session,
    balances: dict[int, Decimal],
    ledger: LedgerAccount,
    direction: str,
    amount: Decimal,
    business_type: str,
    business_ref_type: str,
    business_ref_id: str,
    booked_at: datetime,
    index: int,
    source_inbound_id: int | None = None,
    entry_group_id: str | None = None,
) -> LedgerEntry:
    signed = amount if direction == "CR" else -amount
    balances[ledger.id] = money(balances.get(ledger.id, Decimal("0")) + signed)
    entry = LedgerEntry(
        entry_id=uid("LE", index),
        entry_group_id=entry_group_id or uid("LEG", index),
        ledger_account_id=ledger.id,
        partner_id=ledger.partner_id,
        customer_id=ledger.customer_id,
        direction=direction,
        amount=amount,
        currency=ledger.currency,
        business_type=business_type,
        business_ref_type=business_ref_type,
        business_ref_id=business_ref_id,
        fund_source_transaction_id=source_inbound_id,
        booked_at=booked_at,
        balance_after=balances[ledger.id],
    )
    session.add(entry)
    return entry


def seed(args: argparse.Namespace) -> dict[str, int]:
    rng = random.Random(args.seed)
    Faker.seed(args.seed)
    fake = Faker(["zh_CN", "en_US"])

    create_database(args)
    engine = create_engine(build_url(args, "pingpong"), pool_pre_ping=True)
    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        existing = session.scalar(select(func.count()).select_from(Partner)) or 0
        if existing:
            raise SystemExit(
                "pingpong already contains seed data; rerun with --reset to rebuild it safely"
            )

        # 1. Partners
        partners = []
        for i, (ptype, country) in enumerate(
            [
                ("DIRECT", "CN"),
                ("OPEN_API", "CN"),
                ("LOGISTICS_PLATFORM", "SG"),
                ("SAAS", "HK"),
                ("FINTECH", "GB"),
                ("MARKETPLACE", "US"),
            ],
            1,
        ):
            partner = Partner(
                partner_code=f"P{i:03d}",
                partner_name=f"Synthetic {ptype.title()} Partner {i}",
                partner_type=ptype,
                country_code=country,
                risk_tier=rng.choices(["LOW", "MEDIUM", "HIGH"], [4, 5, 1])[0],
                status="ACTIVE",
                api_enabled=ptype != "DIRECT",
            )
            session.add(partner)
            partners.append(partner)
        session.flush()

        # 2. Customers, people, devices and auth events
        customers: list[Customer] = []
        customer_people: dict[int, list[Person]] = defaultdict(list)
        devices: list[Device] = []
        device_by_customer: dict[int, list[Device]] = defaultdict(list)
        shared_device_hashes = [sha(f"shared-device-{i}") for i in range(8)]
        for i in range(1, 81):
            partner = rng.choice(partners)
            business_type = rng.choices(BUSINESS_TYPES, [35, 20, 30, 15])[0]
            location = rng.choices(["CN", "HK"], [85, 15])[0]
            legal_name = fake.company() + f"-{i}"
            kyc_status = rng.choices(["APPROVED", "DECLINED", "PENDING"], [88, 7, 5])[0]
            approved_at = dt_days_ago(rng, 360) if kyc_status == "APPROVED" else None
            expected_currencies = rng.sample(CURRENCIES, k=rng.randint(1, 3))
            customer = Customer(
                client_id=f"PP{2026000000 + i}",
                partner_id=partner.id,
                customer_location=location,
                customer_type="ENTERPRISE",
                legal_name=legal_name,
                legal_name_en=f"Synthetic Global Trading {i} Ltd.",
                normalized_name=legal_name.upper().replace(" ", ""),
                registration_number_hash=sha(f"registration-{i}"),
                incorporation_date=date(2012 + rng.randint(0, 14), rng.randint(1, 12), rng.randint(1, 28)),
                company_url=f"https://merchant-{i}.example.test",
                declared_business_type=business_type,
                declared_industry_code=rng.choice(["3C", "APPAREL", "LOGISTICS", "ADS", "EDU", "GENERAL"]),
                export_country_list=rng.sample(PAYMENT_COUNTRIES, k=rng.randint(1, 5)),
                expected_currencies=expected_currencies,
                expected_monthly_volume_usd=money(rng.uniform(20_000, 2_000_000)),
                expected_monthly_count=rng.randint(5, 400),
                kyc_status=kyc_status,
                risk_tier=rng.choices(["LOW", "MEDIUM", "HIGH"], [45, 45, 10])[0],
                account_status="NORMAL" if kyc_status == "APPROVED" else "ABNORMAL",
                first_approved_at=approved_at,
                last_reviewed_at=approved_at,
            )
            session.add(customer)
            customers.append(customer)
        session.flush()

        person_index = 0
        role_index = 0
        device_index = 0
        auth_index = 0
        for customer in customers:
            role_specs = [("LEGAL_REPRESENTATIVE", True), ("UBO", False)]
            if rng.random() < 0.45:
                role_specs.append(("AUTHORIZED_OPERATOR", False))
            for role_type, primary in role_specs:
                person_index += 1
                # Intentionally share a few identity hashes to create graph-risk examples.
                id_seed = person_index if rng.random() > 0.05 else rng.randint(1, max(1, person_index - 1))
                person = Person(
                    person_ref=uid("PER", person_index),
                    full_name=fake.name(),
                    full_name_en=f"Synthetic Person {person_index}",
                    normalized_name=f"SYNTHETICPERSON{person_index}",
                    date_of_birth=date(rng.randint(1965, 2000), rng.randint(1, 12), rng.randint(1, 28)),
                    nationality=rng.choice(["CN", "CN", "CN", "HK", "SG"]),
                    residence_country=customer.customer_location,
                    id_type="CN_IDENTITY_CARD" if customer.customer_location == "CN" else "HK_ID_CARD",
                    id_country=customer.customer_location,
                    id_number_hash=sha(f"person-id-{id_seed}"),
                    phone_hash=sha(f"phone-{person_index}"),
                    email_hash=sha(f"person-{person_index}@example.test"),
                    pep_status="POSSIBLE_MATCH" if rng.random() < 0.02 else "CLEAR",
                    sanctions_status="POSSIBLE_MATCH" if rng.random() < 0.01 else "CLEAR",
                )
                session.add(person)
                session.flush()
                customer_people[customer.id].append(person)
                role_index += 1
                session.add(
                    CustomerPersonRole(
                        customer_id=customer.id,
                        person_id=person.id,
                        role_type=role_type,
                        ownership_percent=money(100 if role_type == "UBO" else 0),
                        control_type="OWNERSHIP" if role_type == "UBO" else "APPOINTMENT",
                        is_primary=primary,
                        valid_from=customer.incorporation_date,
                        source="DECLARED",
                    )
                )

            for _ in range(rng.randint(1, 2)):
                device_index += 1
                fingerprint = (
                    rng.choice(shared_device_hashes)
                    if rng.random() < 0.10
                    else sha(f"device-{device_index}")
                )
                first_seen = dt_days_ago(rng, 300)
                device = Device(
                    device_id=uid("DEV", device_index),
                    fingerprint_hash=fingerprint,
                    device_type=rng.choice(["WEB", "MOBILE"]),
                    os_name=rng.choice(["macOS", "Windows", "iOS", "Android"]),
                    browser_name=rng.choice(["Chrome", "Safari", "Edge"]),
                    is_emulator=rng.random() < 0.02,
                    is_rooted=rng.random() < 0.02,
                    first_seen_at=first_seen,
                    last_seen_at=NOW,
                    risk_score=score(rng.uniform(0, 95)),
                )
                session.add(device)
                session.flush()
                devices.append(device)
                device_by_customer[customer.id].append(device)

            for _ in range(rng.randint(4, 10)):
                auth_index += 1
                device = rng.choice(device_by_customer[customer.id])
                event_type = rng.choices(
                    ["LOGIN_SUCCEEDED", "LOGIN_FAILED", "MFA_RESET", "CONTACT_CHANGED"],
                    [76, 17, 4, 3],
                )[0]
                risky = event_type in {"MFA_RESET", "CONTACT_CHANGED"} or rng.random() < 0.05
                session.add(
                    AuthEvent(
                        event_id=uid("AUTH", auth_index),
                        partner_id=customer.partner_id,
                        customer_id=customer.id,
                        person_id=rng.choice(customer_people[customer.id]).id,
                        device_id=device.id,
                        event_type=event_type,
                        event_time=dt_days_ago(rng, 90),
                        result="SUCCESS" if event_type != "LOGIN_FAILED" else "FAILED",
                        session_id=uid("SES", auth_index),
                        ip_address=f"198.51.100.{rng.randint(1, 254)}",
                        ip_country=rng.choice(COUNTRIES),
                        asn=rng.randint(1000, 65000),
                        vpn_proxy_tor_flag=risky and rng.random() < 0.5,
                        is_new_device=rng.random() < 0.15,
                        risk_score=score(rng.uniform(60, 98) if risky else rng.uniform(0, 45)),
                        raw_payload={"synthetic": True},
                    )
                )
        session.flush()

        approved_customers = [c for c in customers if c.kyc_status == "APPROVED"]

        # 3. Stores, VAs and links
        stores: list[Store] = []
        stores_by_customer: dict[int, list[Store]] = defaultdict(list)
        vas: list[VirtualAccount] = []
        vas_by_customer: dict[int, list[VirtualAccount]] = defaultdict(list)
        store_index = va_index = link_index = 0
        for customer in approved_customers:
            if customer.declared_business_type in {"ECOMMERCE_PLATFORM", "SELF_STATION"}:
                for _ in range(rng.randint(1, 2)):
                    store_index += 1
                    platform = (
                        "INDEPENDENT"
                        if customer.declared_business_type == "SELF_STATION"
                        else rng.choice(PLATFORMS[:-1])
                    )
                    store = Store(
                        store_id=uid("STORE", store_index),
                        partner_id=customer.partner_id,
                        customer_id=customer.id,
                        platform=platform,
                        seller_id=f"SELLER-{platform}-{store_index}",
                        store_name=f"Synthetic {platform} Store {store_index}",
                        store_url=f"https://store-{store_index}.example.test",
                        category_code=customer.declared_industry_code,
                        auth_type="URL" if platform != "WALMART" else "KEY",
                        auth_status=rng.choices(["SUCCESS", "FAILED", "PROCESSING"], [92, 5, 3])[0],
                        auth_credential_fingerprint=sha(f"store-auth-{store_index}"),
                        authorized_at=dt_days_ago(rng, 250),
                        auth_expires_at=NOW + timedelta(days=rng.randint(30, 300)),
                        last_order_sync_at=NOW - timedelta(hours=rng.randint(0, 72)),
                        ownership_match_score=score(rng.uniform(65, 100)),
                        risk_tier=customer.risk_tier,
                    )
                    session.add(store)
                    session.flush()
                    stores.append(store)
                    stores_by_customer[customer.id].append(store)

            va_count = 2 if rng.random() < 0.35 else 1
            currencies = list(customer.expected_currencies or ["USD"])
            for n in range(va_count):
                va_index += 1
                currency = currencies[n % len(currencies)]
                purpose = PURPOSE_BY_BUSINESS[customer.declared_business_type]
                if customer.declared_business_type == "SERVICE_TRADE":
                    purpose = rng.choice(SERVICE_PURPOSES)
                va = VirtualAccount(
                    va_id=uid("VA", va_index),
                    partner_id=customer.partner_id,
                    customer_id=customer.id,
                    purpose_code=purpose,
                    purpose_domain=PURPOSE_DOMAIN[purpose],
                    currency=currency,
                    bank_country=rng.choice(["US", "GB", "DE", "SG", "JP"]),
                    rail=rng.choice(["LOCAL", "SWIFT", "SEPA", "FASTER_PAYMENTS"]),
                    account_holder_name=customer.legal_name_en or customer.legal_name,
                    account_number_token=uid("VATOK", va_index),
                    account_fingerprint=sha(f"va-account-{va_index}"),
                    status="NORMAL",
                    opened_at=dt_days_ago(rng, 280),
                    risk_tier=customer.risk_tier,
                )
                session.add(va)
                session.flush()
                vas.append(va)
                vas_by_customer[customer.id].append(va)
                for store in stores_by_customer.get(customer.id, [])[:1]:
                    link_index += 1
                    session.add(
                        StoreVirtualAccountLink(
                            store_id=store.id,
                            virtual_account_id=va.id,
                            linked_at=va.opened_at,
                            status="ACTIVE",
                        )
                    )

        # 4. Counterparties and bank accounts
        counterparties: list[Counterparty] = []
        counterparty_bank: dict[int, BankAccount] = {}
        for i in range(1, 301):
            country = rng.choice(PAYMENT_COUNTRIES)
            ctype = rng.choices(["BUYER", "PAYER", "SUPPLIER", "PLATFORM"], [45, 20, 25, 10])[0]
            cp = Counterparty(
                counterparty_ref=uid("CP", i),
                counterparty_type=ctype,
                legal_name=f"Synthetic {ctype.title()} {i} LLC",
                normalized_name=f"SYNTHETIC{ctype}{i}LLC",
                country_code=country,
                registration_or_id_hash=sha(f"counterparty-{i}"),
                industry_code=rng.choice(["GENERAL", "RETAIL", "LOGISTICS", "TECH", "ADS"]),
                sanctions_status="POSSIBLE_MATCH" if rng.random() < 0.01 else "CLEAR",
                external_risk_label=rng.choices([None, "MULE_SUSPECT", "FRAUD_COMPLAINT"], [94, 4, 2])[0],
                risk_score=score(rng.uniform(0, 98)),
            )
            session.add(cp)
            counterparties.append(cp)
        session.flush()

        bank_index = 0
        for cp in counterparties:
            bank_index += 1
            bank = BankAccount(
                account_ref=uid("BA", bank_index),
                owner_type="COUNTERPARTY",
                counterparty_id=cp.id,
                holder_name=cp.legal_name,
                normalized_holder_name=cp.normalized_name,
                holder_type="ENTERPRISE",
                bank_name=f"Synthetic Bank {cp.country_code}",
                bank_country=cp.country_code,
                currency=rng.choice(CURRENCIES),
                account_number_token=uid("BATOK", bank_index),
                account_fingerprint=sha(f"bank-account-{bank_index}"),
                ownership_check_result="MATCH",
                name_match_score=score(rng.uniform(85, 100)),
                status="APPROVED",
                first_used_at=dt_days_ago(rng, 200),
                risk_score=cp.risk_score,
            )
            session.add(bank)
            session.flush()
            counterparty_bank[cp.id] = bank

        customer_banks: dict[int, list[BankAccount]] = defaultdict(list)
        for customer in approved_customers:
            for n in range(1, 3):
                bank_index += 1
                bank = BankAccount(
                    account_ref=uid("BA", bank_index),
                    owner_type="CUSTOMER",
                    customer_id=customer.id,
                    holder_name=customer.legal_name,
                    normalized_holder_name=customer.normalized_name,
                    holder_type="ENTERPRISE",
                    bank_name=f"Synthetic Customer Bank {n}",
                    bank_country=customer.customer_location,
                    currency="CNY" if n == 1 else rng.choice(CURRENCIES),
                    account_number_token=uid("BATOK", bank_index),
                    account_fingerprint=sha(f"bank-account-{bank_index}"),
                    ownership_check_result="MATCH" if n == 1 else rng.choice(["MATCH", "CLOSE_MATCH"]),
                    name_match_score=score(rng.uniform(80, 100)),
                    status="APPROVED",
                    first_used_at=dt_days_ago(rng, 180),
                    risk_score=score(rng.uniform(0, 50)),
                )
                session.add(bank)
                session.flush()
                customer_banks[customer.id].append(bank)

        # 5. Ledger accounts for six currencies per approved customer.
        ledgers: dict[tuple[int, str, str], LedgerAccount] = {}
        balances: dict[int, Decimal] = {}
        ledger_index = 0
        for customer in approved_customers:
            for currency in CURRENCIES:
                for account_type in ["TEMP_ACCOUNT", "AVAIL_ACCOUNT"]:
                    ledger_index += 1
                    ledger = LedgerAccount(
                        ledger_account_no=uid("LA", ledger_index),
                        partner_id=customer.partner_id,
                        customer_id=customer.id,
                        account_type=account_type,
                        currency=currency,
                        available_balance=money(0),
                        frozen_balance=money(0),
                        status="NORMAL",
                    )
                    session.add(ledger)
                    session.flush()
                    ledgers[(customer.id, account_type, currency)] = ledger
                    balances[ledger.id] = Decimal("0")

        # 6. Trade orders and documents.
        trade_orders: list[TradeOrder] = []
        orders_by_customer_currency: dict[tuple[int, str], list[TradeOrder]] = defaultdict(list)
        document_hash_pool: list[str] = []
        for i in range(1, 601):
            customer = rng.choice(approved_customers)
            currency = rng.choice(CURRENCIES)
            buyer = rng.choice(counterparties)
            order_time = dt_days_ago(rng, 170)
            order_amount = money(rng.uniform(500, 100_000))
            store = rng.choice(stores_by_customer[customer.id]) if stores_by_customer.get(customer.id) else None
            order = TradeOrder(
                trade_order_no=f"TO-{customer.id}-{i:06d}",
                partner_id=customer.partner_id,
                customer_id=customer.id,
                store_id=store.id if store else None,
                buyer_counterparty_id=buyer.id,
                business_type="T_TRADE" if customer.declared_business_type == "B2B_COMMERCE" else "SELF_STATION",
                settlement_type=rng.choice(["SETTLEMENT", "NO_SETTLEMENT"]),
                trade_code=rng.choice(["121010", "122030"]),
                total_amount=order_amount,
                reserved_amount=money(0),
                approved_amount=money(0),
                currency=currency,
                order_time=order_time,
                payment_method=rng.choice(["FULL", "DEPOSIT_BALANCE"]),
                trading_terms=rng.choice(["FOB", "CIF", "EXW", "DAP"]),
                declaration_no=f"DEC-{i:09d}" if rng.random() < 0.72 else None,
                is_new_buyer=rng.random() < 0.28,
                category_code=customer.declared_industry_code,
                consignee_country_code=buyer.country_code,
                buyer_name_snapshot=buyer.legal_name,
                buyer_country_snapshot=buyer.country_code,
                status="APPROVED",
                risk_score=score(rng.uniform(0, 95)),
            )
            session.add(order)
            session.flush()
            trade_orders.append(order)
            orders_by_customer_currency[(customer.id, currency)].append(order)

            for doc_type in ["CONTRACT", rng.choice(["INVOICE", "CUSTOMS", "LOGISTICS"])]:
                doc_index = len(document_hash_pool) + 1
                # 3% duplicated hashes create deterministic fraud-feature examples.
                if document_hash_pool and rng.random() < 0.03:
                    file_hash = rng.choice(document_hash_pool)
                else:
                    file_hash = sha(f"trade-document-{i}-{doc_type}-{doc_index}")
                document_hash_pool.append(file_hash)
                session.add(
                    TradeDocument(
                        document_id=uid("DOC", doc_index),
                        partner_id=customer.partner_id,
                        customer_id=customer.id,
                        trade_order_id=order.id,
                        document_type=doc_type,
                        document_number=f"{doc_type}-{i:08d}",
                        file_hash=file_hash,
                        issued_at=order_time.date(),
                        issuer_name=customer.legal_name,
                        amount=order_amount,
                        currency=currency,
                        ocr_fields={"buyer": buyer.legal_name, "synthetic": True},
                        tamper_score=score(rng.uniform(55, 98) if rng.random() < 0.04 else rng.uniform(0, 25)),
                        verification_status=rng.choices(["VERIFIED", "PENDING", "FAILED"], [86, 10, 4])[0],
                    )
                )

        # 7. Inbound payments, allocations, audits and ledger movements.
        inbound_payments: list[InboundPayment] = []
        approved_inbounds: list[InboundPayment] = []
        ledger_entry_index = 0
        first_payer_seen: set[tuple[int, int]] = set()
        for i in range(1, 801):
            customer = rng.choice(approved_customers)
            va = rng.choice(vas_by_customer[customer.id])
            currency = va.currency
            payer = rng.choice(counterparties)
            orders = orders_by_customer_currency.get((customer.id, currency))
            if not orders:
                # Always available because orders cover all currencies, but keep a safe fallback.
                orders = [o for o in trade_orders if o.customer_id == customer.id]
            order = rng.choice(orders)
            max_native = min(Decimal(order.total_amount), Decimal("75000"))
            native_amount = money(rng.uniform(200, float(max_native)))
            received_at = dt_days_ago(rng, 150)
            first_payer_key = (customer.id, payer.id)
            is_first_payer = first_payer_key not in first_payer_seen
            first_payer_seen.add(first_payer_key)
            third_party = payer.id != order.buyer_counterparty_id and rng.random() < 0.25
            # Build a synthetic latent fraud propensity from facts that would be
            # available at inbound-audit time.  Statuses remain noisy, but are no
            # longer independent random labels; this makes the demo suitable for
            # testing a real train/validation pipeline without leaking status or
            # the precomputed risk score into model features.
            risk_value = min(
                100.0,
                max(
                    0.0,
                    0.24 * float(payer.risk_score)
                    + 0.16 * float(order.risk_score)
                    + (26.0 if third_party else 0.0)
                    + (9.0 if is_first_payer else 0.0)
                    + (28.0 if payer.sanctions_status == "POSSIBLE_MATCH" else 0.0)
                    + (18.0 if payer.external_risk_label else 0.0)
                    + rng.gauss(4.0, 9.0),
                ),
            )
            if risk_value >= 82:
                status_weights = [8, 10, 55, 17, 10]
            elif risk_value >= 65:
                status_weights = [25, 25, 25, 10, 15]
            elif risk_value >= 45:
                status_weights = [60, 15, 10, 5, 10]
            else:
                status_weights = [88, 5, 2, 1, 4]
            initial_status = rng.choices(INBOUND_STATUSES, status_weights)[0]
            available_at = received_at + timedelta(minutes=rng.randint(2, 1440)) if initial_status == "APPROVED" else None
            refunded_at = received_at + timedelta(days=rng.randint(1, 5)) if initial_status == "REFUNDED" else None
            inbound = InboundPayment(
                transaction_id=uid("IN", i),
                partner_reference=uid("PREF", i),
                partner_id=customer.partner_id,
                customer_id=customer.id,
                virtual_account_id=va.id,
                store_id=(rng.choice(stores_by_customer[customer.id]).id if stores_by_customer.get(customer.id) else None),
                payer_counterparty_id=payer.id,
                payer_bank_account_id=counterparty_bank[payer.id].id,
                business_type=customer.declared_business_type,
                purpose_code=va.purpose_code,
                amount=native_amount,
                currency=currency,
                amount_usd=money(native_amount * USD_RATES[currency]),
                received_at=received_at,
                value_date=received_at.date(),
                end_to_end_id=uid("E2E", i),
                uetr=str(uuid.UUID(int=i)),
                origin_country=payer.country_code,
                rail=va.rail,
                remittance_text=f"Synthetic payment for {order.trade_order_no}",
                is_third_party_payment=third_party,
                third_party_reason="GROUP_PAYMENT" if third_party else None,
                is_first_payer=is_first_payer,
                inbound_status=initial_status,
                temp_posted_at=received_at,
                available_at=available_at,
                refunded_at=refunded_at,
                risk_score=score(risk_value),
                risk_tier_snapshot="HIGH" if risk_value >= 75 else "MEDIUM" if risk_value >= 40 else "LOW",
                data_quality_flags=(
                    (["PAYER_BUYER_MISMATCH"] if third_party else [])
                    + (["PAYER_SANCTIONS_POSSIBLE"] if payer.sanctions_status == "POSSIBLE_MATCH" else [])
                    + (["PAYER_EXTERNAL_RISK"] if payer.external_risk_label else [])
                ),
            )
            session.add(inbound)
            session.flush()
            inbound_payments.append(inbound)

            allocation_status = "APPROVED" if initial_status == "APPROVED" else "RELEASED" if initial_status in {"REJECTED", "REFUNDED"} else "RESERVED"
            session.add(
                InboundOrderAllocation(
                    inbound_payment_id=inbound.id,
                    trade_order_id=order.id,
                    allocated_amount=native_amount,
                    currency=currency,
                    allocation_status=allocation_status,
                    reserved_at=received_at,
                    released_at=refunded_at if allocation_status == "RELEASED" else None,
                )
            )
            if allocation_status == "APPROVED":
                order.approved_amount = money(Decimal(order.approved_amount) + native_amount)
            elif allocation_status == "RESERVED":
                order.reserved_amount = money(Decimal(order.reserved_amount) + native_amount)

            audit_score = score(risk_value)
            session.add(
                InboundAudit(
                    audit_id=uid("AUD", i),
                    inbound_payment_id=inbound.id,
                    partner_id=customer.partner_id,
                    customer_id=customer.id,
                    attempt_no=1,
                    submitted_business_type=customer.declared_business_type,
                    status=initial_status if initial_status != "REFUNDED" else "REJECTED",
                    reason_code=("PAYER_MISMATCH" if third_party else "HIGH_RISK_SCORE" if risk_value > 80 else None),
                    fail_reason=("Synthetic evidence required" if initial_status in {"DECLINED", "REJECTED", "REFUNDED"} else None),
                    submitted_by_type="PARTNER" if customer.partner_id != partners[0].id else "CUSTOMER",
                    submitted_by_id=str(customer.partner_id),
                    submitted_at=received_at + timedelta(minutes=1),
                    completed_at=received_at + timedelta(minutes=rng.randint(2, 60)),
                    evidence_snapshot={"trade_order_no": order.trade_order_no, "synthetic": True},
                    rule_hits=["R_THIRD_PARTY"] if third_party else [],
                    decision_score=audit_score,
                )
            )

            temp_ledger = ledgers[(customer.id, "TEMP_ACCOUNT", currency)]
            ledger_entry_index += 1
            group = uid("LEG_IN", i)
            add_ledger_entry(
                session,
                balances,
                temp_ledger,
                "CR",
                native_amount,
                "INBOUND",
                "INBOUND_PAYMENT",
                inbound.transaction_id,
                received_at,
                ledger_entry_index,
                inbound.id,
                group,
            )
            if initial_status == "APPROVED":
                approved_inbounds.append(inbound)
                ledger_entry_index += 1
                add_ledger_entry(
                    session, balances, temp_ledger, "DR", native_amount, "INBOUND_APPROVAL",
                    "INBOUND_PAYMENT", inbound.transaction_id, available_at or received_at,
                    ledger_entry_index, inbound.id, group,
                )
                avail_ledger = ledgers[(customer.id, "AVAIL_ACCOUNT", currency)]
                ledger_entry_index += 1
                add_ledger_entry(
                    session, balances, avail_ledger, "CR", native_amount, "INBOUND_APPROVAL",
                    "INBOUND_PAYMENT", inbound.transaction_id, available_at or received_at,
                    ledger_entry_index, inbound.id, group,
                )
            elif initial_status == "REFUNDED":
                ledger_entry_index += 1
                add_ledger_entry(
                    session, balances, temp_ledger, "DR", native_amount, "INBOUND_REFUND",
                    "INBOUND_PAYMENT", inbound.transaction_id, refunded_at or received_at,
                    ledger_entry_index, inbound.id, group,
                )

            va.first_credit_at = min(va.first_credit_at or received_at, received_at)
            va.last_credit_at = max(va.last_credit_at or received_at, received_at)

        # 8. FX orders and ledger movements.
        fx_orders: list[FxOrder] = []
        for i in range(1, 251):
            inbound = rng.choice(approved_inbounds)
            customer = next(c for c in approved_customers if c.id == inbound.customer_id)
            sell_currency = inbound.currency
            buy_currency = "CNY" if sell_currency != "CNY" else "USD"
            source_ledger = ledgers[(customer.id, "AVAIL_ACCOUNT", sell_currency)]
            available = max(Decimal("0"), balances[source_ledger.id])
            if available < Decimal("10"):
                continue
            sell_amount = money(min(available * Decimal(str(rng.uniform(0.02, 0.12))), Decimal(inbound.amount) * Decimal("0.5")))
            if sell_amount <= 0:
                continue
            fx_rate_value = USD_RATES[sell_currency] / USD_RATES[buy_currency]
            buy_amount = money(sell_amount * fx_rate_value)
            requested_at = (inbound.available_at or inbound.received_at) + timedelta(seconds=rng.randint(60, 172800))
            fx = FxOrder(
                fx_order_id=uid("FX", i),
                partner_id=customer.partner_id,
                customer_id=customer.id,
                sell_currency=sell_currency,
                sell_amount=sell_amount,
                buy_currency=buy_currency,
                buy_amount=buy_amount,
                fx_rate=rate(fx_rate_value),
                quote_id=uid("QUOTE", i),
                source_inbound_payment_id=inbound.id,
                status="EXECUTED",
                requested_at=requested_at,
                executed_at=requested_at + timedelta(seconds=rng.randint(1, 20)),
                risk_score=score(rng.uniform(0, 85)),
            )
            session.add(fx)
            session.flush()
            fx_orders.append(fx)
            group = uid("LEG_FX", i)
            ledger_entry_index += 1
            add_ledger_entry(
                session, balances, source_ledger, "DR", sell_amount, "FX", "FX_ORDER",
                fx.fx_order_id, fx.executed_at or requested_at, ledger_entry_index, inbound.id, group,
            )
            target_ledger = ledgers[(customer.id, "AVAIL_ACCOUNT", buy_currency)]
            ledger_entry_index += 1
            add_ledger_entry(
                session, balances, target_ledger, "CR", buy_amount, "FX", "FX_ORDER",
                fx.fx_order_id, fx.executed_at or requested_at, ledger_entry_index, inbound.id, group,
            )

        # 9. Payouts and successful ledger debits.
        payouts: list[Payout] = []
        for i in range(1, 451):
            inbound = rng.choice(approved_inbounds)
            customer = next(c for c in approved_customers if c.id == inbound.customer_id)
            payout_type = rng.choices(["WITHDRAW", "PAY"], [62, 38])[0]
            if payout_type == "WITHDRAW":
                beneficiary = rng.choice(customer_banks[customer.id])
            else:
                beneficiary = counterparty_bank[rng.choice(counterparties).id]
            pay_currency = inbound.currency
            source_ledger = ledgers[(customer.id, "AVAIL_ACCOUNT", pay_currency)]
            available = max(Decimal("0"), balances[source_ledger.id])
            if available < Decimal("10"):
                continue
            pay_amount = money(min(available * Decimal(str(rng.uniform(0.01, 0.18))), Decimal(inbound.amount) * Decimal("0.7")))
            if pay_amount <= 0:
                continue
            requested_at = (inbound.available_at or inbound.received_at) + timedelta(seconds=rng.randint(30, 604800))
            security_flag = rng.random() < 0.06
            payout_risk = rng.uniform(70, 99) if security_flag else rng.uniform(0, 80)
            payout_status = rng.choices(["SUCCEEDED", "FAILED", "RISK_HOLD", "RETURNED"], [82, 7, 7, 4])[0]
            target_currency = "CNY" if payout_type == "WITHDRAW" and rng.random() < 0.75 else pay_currency
            payout_fx = USD_RATES[pay_currency] / USD_RATES[target_currency]
            payout = Payout(
                payout_id=uid("PO", i),
                partner_order_id=uid("PPO", i),
                partner_id=customer.partner_id,
                customer_id=customer.id,
                beneficiary_bank_account_id=beneficiary.id,
                source_inbound_payment_id=inbound.id,
                payout_type=payout_type,
                pay_currency=pay_currency,
                pay_amount=pay_amount,
                fee_amount=money(pay_amount * Decimal("0.002")),
                target_currency=target_currency,
                target_amount=money(pay_amount * payout_fx * Decimal("0.998")),
                fx_rate=rate(payout_fx) if target_currency != pay_currency else None,
                payer_name=customer.legal_name if payout_type == "PAY" else None,
                charges_indicator=rng.choice(["OUR", "SHA", "BEN"]),
                trade_code="121010" if payout_type == "PAY" else None,
                remark=f"Synthetic {payout_type.lower()} {i}",
                requested_at=requested_at,
                accepted_at=requested_at + timedelta(seconds=1),
                completed_at=requested_at + timedelta(minutes=rng.randint(1, 180)) if payout_status in {"SUCCEEDED", "FAILED", "RETURNED"} else None,
                status=payout_status,
                failure_reason="SYNTHETIC_CHANNEL_FAILURE" if payout_status == "FAILED" else None,
                is_new_beneficiary=rng.random() < 0.18,
                recent_security_event_flag=security_flag,
                seconds_since_inbound=int((requested_at - inbound.received_at).total_seconds()),
                balance_drain_ratio=score(min(1, float(pay_amount / max(available, Decimal("1"))))),
                risk_score=score(payout_risk),
            )
            session.add(payout)
            session.flush()
            payouts.append(payout)
            if payout_status == "SUCCEEDED":
                ledger_entry_index += 1
                add_ledger_entry(
                    session, balances, source_ledger, "DR", pay_amount, "PAYOUT", "PAYOUT",
                    payout.payout_id, payout.completed_at or requested_at, ledger_entry_index,
                    inbound.id, uid("LEG_PO", i),
                )

        # Persist current ledger balances after all movements.
        for ledger in ledgers.values():
            ledger.available_balance = money(balances[ledger.id])

        # 10. Generic risk events and decisions.
        risk_events: list[RiskEvent] = []
        event_types = [
            "inbound.audit.approved.v1",
            "inbound.audit.declined.v1",
            "inbound.audit.rejected.v1",
            "payout.requested.v1",
            "auth.mfa.reset.v1",
            "trade.document.duplicate_detected.v1",
            "partner.portfolio.anomaly_detected.v1",
        ]
        for i in range(1, 701):
            customer = rng.choice(approved_customers)
            event_type = rng.choice(event_types)
            if event_type.startswith("inbound"):
                subject = rng.choice(inbound_payments)
                subject_type, subject_id = "INBOUND_PAYMENT", subject.transaction_id
                event_time = subject.received_at
            elif event_type.startswith("payout") and payouts:
                subject = rng.choice(payouts)
                subject_type, subject_id = "PAYOUT", subject.payout_id
                event_time = subject.requested_at
            else:
                subject_type, subject_id = "CUSTOMER", customer.client_id
                event_time = dt_days_ago(rng, 120)
            event_score = rng.uniform(0, 100)
            risk_event = RiskEvent(
                event_id=uid("EVT", i),
                event_type=event_type,
                event_version=1,
                risk_domain=rng.choice(["FRAUD", "AML", "TRADE", "CYBER", "SANCTIONS"]),
                partner_id=customer.partner_id,
                customer_id=customer.id,
                subject_type=subject_type,
                subject_id=subject_id,
                actor_type="SYSTEM",
                actor_id="seed-generator",
                occurred_at=event_time,
                received_at=event_time + timedelta(milliseconds=rng.randint(1, 5000)),
                correlation_id=uid("CORR", i // 3),
                causation_id=None,
                idempotency_key=uid("IDEM", i),
                source_system="synthetic-seed",
                risk_score=score(event_score),
                labels=["HIGH_RISK"] if event_score >= 75 else [],
                payload={"synthetic": True, "feature_snapshot": {"score": round(event_score, 2)}},
            )
            session.add(risk_event)
            session.flush()
            risk_events.append(risk_event)
            if i <= 350:
                decision = "HOLD" if event_score >= 80 else "MANUAL_REVIEW" if event_score >= 60 else "ALLOW"
                session.add(
                    RiskDecision(
                        decision_id=uid("DECISION", i),
                        risk_event_id=risk_event.id,
                        partner_id=customer.partner_id,
                        customer_id=customer.id,
                        subject_type=subject_type,
                        subject_id=subject_id,
                        risk_domain=risk_event.risk_domain,
                        decision=decision,
                        risk_score=score(event_score),
                        rule_hits=["R_RAPID_PAYOUT"] if decision != "ALLOW" else [],
                        model_outputs={"model": "synthetic-v1", "score": round(event_score, 2)},
                        reason_codes=["SYNTHETIC_HIGH_SCORE"] if decision != "ALLOW" else [],
                        engine_version="demo-1.0.0",
                        decided_at=event_time + timedelta(milliseconds=20),
                        expires_at=event_time + timedelta(days=7) if decision == "HOLD" else None,
                        manual_override=False,
                    )
                )

        # 11. Cases and linked entities.
        cases: list[RiskCase] = []
        for i in range(1, 61):
            customer = rng.choice(approved_customers)
            opened_at = dt_days_ago(rng, 100)
            closed = rng.random() < 0.65
            case = RiskCase(
                case_id=uid("CASE", i),
                partner_id=customer.partner_id,
                customer_id=customer.id,
                case_type=rng.choice(["INBOUND_REVIEW", "ATO", "TBML", "MULE", "SANCTIONS"]),
                priority=rng.choice(["P0", "P1", "P2", "P3"]),
                status="CLOSED" if closed else "INVESTIGATING",
                title=f"Synthetic risk investigation {i}",
                opened_at=opened_at,
                due_at=opened_at + timedelta(days=3),
                closed_at=opened_at + timedelta(days=rng.randint(1, 10)) if closed else None,
                assignee=f"analyst-{rng.randint(1, 12)}",
                disposition=rng.choice(["CONFIRMED_FRAUD", "SUSPICIOUS", "FALSE_POSITIVE"]) if closed else None,
                label_confidence=score(rng.uniform(60, 100)) if closed else None,
                loss_amount_usd=money(rng.uniform(0, 20_000) if closed else 0),
                recovered_amount_usd=money(rng.uniform(0, 5_000) if closed else 0),
                summary="Synthetic case generated for schema and feature testing.",
            )
            session.add(case)
            session.flush()
            cases.append(case)
            inbound = rng.choice(inbound_payments)
            session.add_all(
                [
                    CaseEntity(
                        risk_case_id=case.id,
                        entity_type="CUSTOMER",
                        entity_id=customer.client_id,
                        relation_type="PRIMARY_SUBJECT",
                        added_at=opened_at,
                        evidence={"synthetic": True},
                    ),
                    CaseEntity(
                        risk_case_id=case.id,
                        entity_type="INBOUND_PAYMENT",
                        entity_id=inbound.transaction_id,
                        relation_type="RELATED_TRANSACTION",
                        added_at=opened_at,
                        evidence={"synthetic": True},
                    ),
                ]
            )

        # 12. Graph-friendly entity relations.
        relation_index = 0
        for customer in approved_customers:
            for person in customer_people[customer.id]:
                relation_index += 1
                session.add(
                    EntityRelation(
                        src_entity_type="CUSTOMER",
                        src_entity_id=customer.client_id,
                        dst_entity_type="PERSON",
                        dst_entity_id=person.person_ref,
                        relation_type="HAS_PERSON",
                        valid_from=customer.first_approved_at or NOW,
                        source="KYC",
                        confidence=score(100),
                        attributes={"synthetic": True},
                    )
                )
            for device in device_by_customer[customer.id]:
                relation_index += 1
                session.add(
                    EntityRelation(
                        src_entity_type="CUSTOMER",
                        src_entity_id=customer.client_id,
                        dst_entity_type="DEVICE",
                        dst_entity_id=device.device_id,
                        relation_type="USED_DEVICE",
                        valid_from=device.first_seen_at,
                        source="AUTH",
                        confidence=score(95),
                        attributes={"fingerprint_hash": device.fingerprint_hash},
                    )
                )
            for va in vas_by_customer[customer.id]:
                relation_index += 1
                session.add(
                    EntityRelation(
                        src_entity_type="CUSTOMER",
                        src_entity_id=customer.client_id,
                        dst_entity_type="VIRTUAL_ACCOUNT",
                        dst_entity_id=va.va_id,
                        relation_type="OWNS_VA",
                        valid_from=va.opened_at,
                        source="VA_SERVICE",
                        confidence=score(100),
                        attributes={"purpose_code": va.purpose_code},
                    )
                )

        # 13. Versioned business rules. JSON is an initialization artifact;
        # MySQL is the runtime source of truth and decisions keep hit ids.
        rule_path = Path(__file__).resolve().parent / "rules" / "pingpong_rules.json"
        source_refs = ["PingPong Open Platform", "FATF TBML", "FinCEN BEC", "FCA Money Mules", "OFAC"]
        for priority, item in enumerate(reversed(json.loads(rule_path.read_text(encoding="utf-8"))), 1):
            session.add(
                RiskRule(
                    rule_id=item["id"],
                    rule_name=item["name"],
                    stage=item["stage"],
                    category=item["category"],
                    fraud_scenario=item["fraud_scenario"],
                    rule_condition=item["condition"],
                    severity=item["severity"],
                    risk_score=item["score"],
                    action=item["action"],
                    is_veto=item["veto"],
                    priority=priority,
                    is_enabled=True,
                    version=1,
                    source_refs=source_refs,
                    effective_from=NOW,
                )
            )

        # 14. Cross-border entity blacklist. Values use business identifiers,
        # never raw account numbers or identity documents.
        blacklist_candidates: list[tuple[str, str, str, str]] = []
        for cp in sorted(counterparties, key=lambda item: item.risk_score, reverse=True)[:5]:
            blacklist_candidates.append(("COUNTERPARTY", cp.counterparty_ref, cp.legal_name, "MULE_OR_FRAUD_SIGNAL"))
            bank = counterparty_bank.get(cp.id)
            if bank and len(blacklist_candidates) < 8:
                blacklist_candidates.append(("BANK_ACCOUNT", bank.account_ref, bank.holder_name, "HIGH_RISK_BENEFICIARY"))
        for customer in sorted(approved_customers, key=lambda item: (item.risk_tier != "HIGH", item.id))[:3]:
            blacklist_candidates.append(("CUSTOMER", customer.client_id, customer.legal_name, "CASE_CONFIRMED_RISK"))
        for va in sorted(vas, key=lambda item: (item.risk_tier != "HIGH", item.id))[:3]:
            blacklist_candidates.append(("VIRTUAL_ACCOUNT", va.va_id, va.account_holder_name, "VA_MISUSE_SIGNAL"))
        for device in sorted(devices, key=lambda item: item.risk_score, reverse=True)[:3]:
            blacklist_candidates.append(("DEVICE", device.device_id, device.device_type, "DEVICE_FRAUD_CLUSTER"))

        for index, (entity_type, entity_value, display_name, reason_code) in enumerate(blacklist_candidates, 1):
            session.add(
                RiskBlacklist(
                    blacklist_id=f"BL-SEED-{index:04d}",
                    entity_type=entity_type,
                    entity_value=entity_value,
                    normalized_value="".join(entity_value.upper().split()),
                    display_name=display_name,
                    reason_code=reason_code,
                    reason_detail="Synthetic blacklist entry for workflow testing.",
                    severity="CRITICAL" if entity_type in {"COUNTERPARTY", "BANK_ACCOUNT"} else "HIGH",
                    source="CASE",
                    source_refs=["synthetic-case"],
                    is_active=True,
                    effective_from=NOW,
                    hit_count=0,
                    created_by="seed-data",
                )
            )

        session.commit()

        counts = {
            model.__tablename__: int(session.scalar(select(func.count()).select_from(model)) or 0)
            for model in ALL_MODELS
        }
    engine.dispose()
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("PINGPONG_DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PINGPONG_DB_PORT", "9999")))
    parser.add_argument("--user", default=os.getenv("PINGPONG_DB_USER", "root"))
    parser.add_argument("--password", default=os.getenv("PINGPONG_DB_PASSWORD"))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--reset", action="store_true", help="Drop only pingpong tables before seeding")
    args = parser.parse_args()
    if not args.password:
        parser.error("set PINGPONG_DB_PASSWORD or pass --password")
    return args


def main() -> None:
    args = parse_args()
    counts = seed(args)
    print("\nSynthetic seed completed (all data is fake):")
    for table, count in counts.items():
        print(f"  {table:32s} {count:6d}")
    print(f"  {'TOTAL':32s} {sum(counts.values()):6d}")


if __name__ == "__main__":
    main()

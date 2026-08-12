from __future__ import annotations

import argparse
import hashlib
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AuditLog,
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    BookingTour,
    OrderInfo,
    OrderPassenger,
    PassengerInfo,
    PaymentAccount,
    ReviewCase,
    RiskAssessment,
    RiskHit,
    RiskRule,
    UserInfo,
    VisaApplication,
)
from app.scoring import calculate_account_age_days, calculate_risk_score


ORDER_TYPES = ("FLIGHT", "HOTEL", "VISA", "TOUR")
DEFAULT_REVIEWER = "system_reviewer"
ENGINE_VERSION = "seed-evaluator-2.0"

RULE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "rule_code": "VISA_REJECT_90D_GTE3",
        "rule_group_code": "VISA_REJECT_HISTORY",
        "rule_name": "拒签历史拦截",
        "condition_json": {
            "metric": "visa_reject_count",
            "window_days": 90,
            "operator": "gte",
            "threshold": 3,
        },
        "risk_score": 90,
        "description": "用户 90 天内签证被拒次数不少于 3 次",
    },
    {
        "rule_code": "VISA_REJECT_90D_GTE1",
        "rule_group_code": "VISA_REJECT_HISTORY",
        "rule_name": "拒签历史拦截",
        "condition_json": {
            "metric": "visa_reject_count",
            "window_days": 90,
            "operator": "gte",
            "threshold": 1,
        },
        "risk_score": 70,
        "description": "用户 90 天内签证被拒次数不少于 1 次",
    },
    {
        "rule_code": "VISA_COUNTRY_30D_GTE3",
        "rule_group_code": "VISA_MULTI_COUNTRY",
        "rule_name": "短期多国签证",
        "condition_json": {
            "metric": "distinct_visa_countries",
            "window_days": 30,
            "operator": "gte",
            "threshold": 3,
        },
        "risk_score": 90,
        "description": "30 天内申请至少 3 个不同国家的签证",
    },
    {
        "rule_code": "VISA_COUNTRY_30D_GTE1",
        "rule_group_code": "VISA_MULTI_COUNTRY",
        "rule_name": "短期多国签证",
        "condition_json": {
            "metric": "distinct_visa_countries",
            "window_days": 30,
            "operator": "gte",
            "threshold": 1,
        },
        "risk_score": 70,
        "description": "30 天内申请至少 1 个国家的签证",
    },
    {
        "rule_code": "CROSS_BORDER_AMOUNT_GTE50000",
        "rule_group_code": "CROSS_BORDER_LARGE_AMOUNT",
        "rule_name": "大额跨境游",
        "condition_json": {
            "metric": "cross_border_order_amount",
            "currency": "CNY",
            "operator": "gte",
            "threshold": 50000,
        },
        "risk_score": 90,
        "description": "跨境旅游单笔订单金额不少于 50000 元",
    },
    {
        "rule_code": "CROSS_BORDER_AMOUNT_GTE30000",
        "rule_group_code": "CROSS_BORDER_LARGE_AMOUNT",
        "rule_name": "大额跨境游",
        "condition_json": {
            "metric": "cross_border_order_amount",
            "currency": "CNY",
            "operator": "gte",
            "threshold": 30000,
        },
        "risk_score": 70,
        "description": "跨境旅游单笔订单金额不少于 30000 元",
    },
    {
        "rule_code": "FLIGHT_HOARD_1H_GTE5",
        "rule_group_code": "FLIGHT_TICKET_HOARDING",
        "rule_name": "黄牛囤票",
        "condition_json": {
            "metric": "same_payment_same_flight_tickets",
            "window_hours": 1,
            "operator": "gte",
            "threshold": 5,
        },
        "risk_score": 95,
        "description": "同一支付账号 1 小时内预订同航班至少 5 张票",
    },
    {
        "rule_code": "FLIGHT_HOARD_1H_GTE2",
        "rule_group_code": "FLIGHT_TICKET_HOARDING",
        "rule_name": "黄牛囤票",
        "condition_json": {
            "metric": "same_payment_same_flight_tickets",
            "window_hours": 1,
            "operator": "gte",
            "threshold": 2,
        },
        "risk_score": 70,
        "description": "同一支付账号 1 小时内预订同航班至少 2 张票",
    },
    {
        "rule_code": "NIGHT_ORDER_DEPART_LE7",
        "rule_group_code": "NIGHT_RUSH_ORDER",
        "rule_name": "0 点突击下单",
        "condition_json": {
            "metric": "night_order_departure_interval",
            "hour_start": 1,
            "hour_end_exclusive": 5,
            "interval_days_lte": 7,
        },
        "risk_score": 50,
        "description": "凌晨 1 至 5 点下单且距离行程不超过 7 天",
    },
    {
        "rule_code": "NIGHT_ORDER_DEPART_LE3",
        "rule_group_code": "NIGHT_RUSH_ORDER",
        "rule_name": "0 点突击下单",
        "condition_json": {
            "metric": "night_order_departure_interval",
            "hour_start": 1,
            "hour_end_exclusive": 5,
            "interval_days_lte": 3,
        },
        "risk_score": 80,
        "description": "凌晨 1 至 5 点下单且距离行程不超过 3 天",
    },
    {
        "rule_code": "PASSENGER_HISTORY_MATCH_LTE30",
        "rule_group_code": "PASSENGER_INFO_MISMATCH",
        "rule_name": "乘客信息不一致",
        "condition_json": {
            "metric": "historical_passenger_match_rate",
            "operator": "lte",
            "threshold_percent": 30,
        },
        "risk_score": 50,
        "description": "订单乘客证件号与用户历史乘客匹配率不高于 30%",
    },
    {
        "rule_code": "NEW_USER_LARGE_ORDER",
        "rule_group_code": "NEW_USER_LARGE_ORDER",
        "rule_name": "新用户大单",
        "condition_json": {
            "metric": "account_age_and_order_amount",
            "account_age_days_lt": 7,
            "amount_gt": 10000,
            "currency": "CNY",
        },
        "risk_score": 60,
        "description": "注册不足 7 天且订单金额大于 10000 元",
    },
    {
        "rule_code": "PASSPORT_BLACKLIST",
        "rule_group_code": "PASSPORT_BLACKLIST",
        "rule_name": "黑护照拦截",
        "condition_json": {
            "metric": "passenger_document_blacklist",
            "entry_type": "PASSPORT",
            "operator": "exists",
        },
        "risk_score": 95,
        "description": "订单乘客证件号存在于有效黑名单",
    },
)

SURNAMES = tuple("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜")
GIVEN_NAMES = (
    "子涵",
    "宇轩",
    "梓萱",
    "浩然",
    "欣怡",
    "雨桐",
    "嘉豪",
    "思远",
    "佳宁",
    "晨曦",
    "俊杰",
    "梦瑶",
    "可欣",
    "博文",
    "诗涵",
    "明轩",
    "雅琪",
    "天佑",
    "若溪",
    "景行",
)
COUNTRIES = ("JP", "TH", "SG", "US", "FR", "GB", "AU", "KR", "DE", "IT")
DOMESTIC_CITIES = ("BJS", "SHA", "CAN", "SZX", "CTU", "HGH", "XIY", "CKG")
INTERNATIONAL_AIRPORTS = ("NRT", "BKK", "SIN", "LAX", "CDG", "LHR", "SYD", "ICN")
VISA_TYPES = ("TOURIST", "BUSINESS", "TRANSIT", "VISIT")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def mask_document(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def money_from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed OTA travel risk-control demo data")
    parser.add_argument("--orders", type=int, default=400, help="total number of orders")
    parser.add_argument("--seed", type=int, default=20260811, help="random seed")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        help="reference date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete all existing rows from the 15 project tables before seeding",
    )
    args = parser.parse_args()
    if args.orders < 40:
        parser.error("--orders must be at least 40")
    return args


def clear_existing_data(session: Session) -> None:
    deletion_order = (
        AuditLog,
        ReviewCase,
        RiskHit,
        RiskAssessment,
        VisaApplication,
        BookingFlight,
        BookingHotel,
        BookingTour,
        OrderPassenger,
        OrderInfo,
        BlacklistExtra,
        RiskRule,
        PaymentAccount,
        PassengerInfo,
        UserInfo,
    )
    for model in deletion_order:
        session.execute(delete(model))


def ensure_database_is_empty(session: Session) -> None:
    watched_models = (UserInfo, OrderInfo, RiskRule, BlacklistExtra, RiskAssessment)
    populated = []
    for model in watched_models:
        count = session.scalar(select(func.count()).select_from(model)) or 0
        if count:
            populated.append(f"{model.__tablename__}={count}")
    if populated:
        details = ", ".join(populated)
        raise RuntimeError(
            f"Database already contains project data ({details}). "
            "Use --reset only when replacing all existing demo data is intended."
        )


def create_rules(session: Session, as_of: datetime) -> list[RiskRule]:
    rules = [
        RiskRule(
            rule_code=item["rule_code"],
            rule_group_code=item["rule_group_code"],
            rule_name=item["rule_name"],
            applicable_order_types=list(ORDER_TYPES),
            condition_json=item["condition_json"],
            risk_score=item["risk_score"],
            is_enabled=True,
            rule_version=1,
            description=item["description"],
            created_at=as_of,
            updated_at=as_of,
        )
        for item in RULE_CATALOG
    ]
    session.add_all(rules)
    session.flush()
    return rules


def create_users(
    session: Session, rng: random.Random, as_of: datetime, count: int = 120
) -> list[UserInfo]:
    users: list[UserInfo] = []
    for index in range(count):
        if index < 6:
            account_age_days = rng.randint(240, 1200)
        elif index < 26:
            account_age_days = rng.randint(1, 6)
        else:
            account_age_days = rng.randint(15, 1500)
        users.append(
            UserInfo(
                name=f"{SURNAMES[index % len(SURNAMES)]}{GIVEN_NAMES[index % len(GIVEN_NAMES)]}",
                real_name_status=rng.random() < 0.88,
                vip_level=rng.choices(
                    ("NORMAL", "SILVER", "GOLD", "PLATINUM"),
                    weights=(58, 24, 14, 4),
                    k=1,
                )[0],
                registered_at=as_of - timedelta(days=account_age_days, hours=12),
                account_age_days=account_age_days,
                created_at=as_of,
                updated_at=as_of,
            )
        )
    session.add_all(users)
    session.flush()
    return users


def create_payment_accounts(
    session: Session, users: list[UserInfo]
) -> tuple[list[PaymentAccount], dict[int, list[PaymentAccount]]]:
    accounts: list[PaymentAccount] = []
    accounts_by_user: dict[int, list[PaymentAccount]] = defaultdict(list)
    for index, user in enumerate(users):
        account_count = 2 if index % 5 == 0 else 1
        for ordinal in range(account_count):
            account = PaymentAccount(
                user_id=user.user_id,
                account_type=("BANK_CARD", "ALIPAY", "WECHAT_PAY")[(index + ordinal) % 3],
                account_token_hash=sha256_text(f"PAY-{user.user_id}-{ordinal}"),
                status="ACTIVE",
            )
            accounts.append(account)
            accounts_by_user[user.user_id].append(account)
    session.add_all(accounts)
    session.flush()
    return accounts, accounts_by_user


def create_passengers(
    session: Session, rng: random.Random, users: list[UserInfo]
) -> tuple[list[PassengerInfo], dict[int, list[PassengerInfo]]]:
    passengers: list[PassengerInfo] = []
    family_by_user: dict[int, list[PassengerInfo]] = defaultdict(list)
    passenger_index = 0
    for user_index, user in enumerate(users):
        for family_index in range(3):
            document = f"P{(passenger_index + 10000000):08d}CN"
            passenger = PassengerInfo(
                name=(
                    f"{SURNAMES[(user_index + family_index) % len(SURNAMES)]}"
                    f"{GIVEN_NAMES[(passenger_index + family_index) % len(GIVEN_NAMES)]}"
                ),
                id_type="PASSPORT",
                id_number_hash=sha256_text(document),
                id_number_masked=mask_document(document),
                nationality="CN",
                birth_date=date(
                    rng.randint(1955, 2005), rng.randint(1, 12), rng.randint(1, 28)
                ),
                gender=("F", "M")[passenger_index % 2],
            )
            passengers.append(passenger)
            family_by_user[user.user_id].append(passenger)
            passenger_index += 1
    session.add_all(passengers)
    session.flush()
    return passengers, family_by_user


def distribute_order_counts(total: int) -> dict[str, int]:
    quotient, remainder = divmod(total, len(ORDER_TYPES))
    return {
        order_type: quotient + (1 if index < remainder else 0)
        for index, order_type in enumerate(ORDER_TYPES)
    }


def choose_amount(
    rng: random.Random, order_type: str, product_index: int, is_cross_border: bool
) -> Decimal:
    ranges = {
        "FLIGHT": (60_000, 1_200_000),
        "HOTEL": (80_000, 1_800_000),
        "VISA": (30_000, 450_000),
        "TOUR": (300_000, 8_000_000),
    }
    low, high = ranges[order_type]
    if is_cross_border and product_index % 23 == 5:
        return money_from_cents(rng.randint(5_000_000, 7_500_000))
    if is_cross_border and product_index % 19 == 7:
        return money_from_cents(rng.randint(3_000_000, 4_900_000))
    return money_from_cents(rng.randint(low, high))


def create_orders(
    session: Session,
    rng: random.Random,
    as_of: datetime,
    count: int,
    users: list[UserInfo],
    accounts_by_user: dict[int, list[PaymentAccount]],
) -> tuple[list[OrderInfo], dict[int, dict[str, Any]]]:
    orders: list[OrderInfo] = []
    metadata_by_object: dict[int, dict[str, Any]] = {}
    counts = distribute_order_counts(count)
    global_index = 0
    cluster_time = datetime.combine((as_of - timedelta(days=2)).date(), time(10, 0))

    for order_type in ORDER_TYPES:
        for product_index in range(counts[order_type]):
            special_kind: str | None = None
            if order_type == "FLIGHT" and product_index < 6:
                user = users[2]
                order_time = cluster_time + timedelta(minutes=product_index * 8)
                special_kind = "flight_hoard_cluster"
            elif order_type == "VISA" and product_index < 12:
                user = users[0]
                order_time = as_of - timedelta(days=85 - product_index * 6)
                special_kind = "visa_high_history"
            elif order_type == "VISA" and product_index < 18:
                user = users[1]
                order_time = as_of - timedelta(days=40 - (product_index - 12) * 5)
                special_kind = "visa_low_history"
            elif product_index % 17 == 4:
                user = users[6 + (product_index % 20)]
                current_age_days = calculate_account_age_days(user.registered_at, as_of=as_of)
                max_days_ago = max(0, min(3, current_age_days - 1))
                order_time = as_of - timedelta(
                    days=rng.randint(0, max_days_ago), hours=rng.randint(0, 10)
                )
                special_kind = "new_user_large_order"
            else:
                user = rng.choice(users)
                current_age_days = calculate_account_age_days(user.registered_at, as_of=as_of)
                max_days_ago = max(0, min(89, current_age_days - 1))
                order_time = as_of - timedelta(
                    days=rng.randint(0, max_days_ago),
                    hours=rng.randint(0, 22),
                    minutes=rng.randint(0, 59),
                )

            night_risk = None
            if special_kind not in {
                "flight_hoard_cluster",
                "visa_high_history",
                "visa_low_history",
            }:
                if product_index % 20 == 10:
                    order_time = datetime.combine(order_time.date(), time(2, 15))
                    night_risk = "high"
                elif product_index % 20 == 11:
                    order_time = datetime.combine(order_time.date(), time(3, 20))
                    night_risk = "low"

            if order_type == "VISA":
                is_cross_border = True
            elif order_type == "TOUR":
                is_cross_border = rng.random() < 0.82
            else:
                is_cross_border = rng.random() < 0.58

            dest_country = rng.choice(COUNTRIES) if is_cross_border else "CN"
            if special_kind == "visa_high_history":
                dest_country = COUNTRIES[product_index % 5]
            elif special_kind == "visa_low_history":
                dest_country = "JP"

            interval_days = rng.randint(8, 70)
            if night_risk == "high":
                interval_days = rng.randint(1, 3)
            elif night_risk == "low":
                interval_days = rng.randint(4, 7)
            depart_date = order_time.date() + timedelta(days=interval_days)
            return_date = depart_date + timedelta(days=rng.randint(2, 14))
            passenger_count = 1 if special_kind == "flight_hoard_cluster" else rng.randint(1, 3)
            amount = choose_amount(rng, order_type, product_index, is_cross_border)
            if special_kind == "new_user_large_order":
                amount = money_from_cents(rng.randint(1_200_000, 3_500_000))

            account = (
                accounts_by_user[user.user_id][0]
                if special_kind == "flight_hoard_cluster"
                else rng.choice(accounts_by_user[user.user_id])
            )
            order = OrderInfo(
                order_no=f"{order_type[:2]}{as_of:%Y%m%d}{global_index + 1:06d}",
                user_id=user.user_id,
                payment_account_id=account.payment_account_id,
                order_type=order_type,
                total_amount=amount,
                currency="CNY",
                dest_country=dest_country,
                is_cross_border=is_cross_border,
                order_time=order_time,
                depart_date=depart_date,
                return_date=return_date,
                passenger_count=passenger_count,
                order_status="CREATED",
                created_at=as_of,
                updated_at=as_of,
            )
            orders.append(order)
            metadata_by_object[id(order)] = {
                "global_index": global_index,
                "product_index": product_index,
                "special_kind": special_kind,
            }
            global_index += 1

    session.add_all(orders)
    session.flush()
    metadata_by_order = {
        order.order_id: metadata_by_object[id(order)] for order in orders
    }
    return orders, metadata_by_order


def create_order_passengers(
    session: Session,
    orders: list[OrderInfo],
    users: list[UserInfo],
    family_by_user: dict[int, list[PassengerInfo]],
    metadata_by_order: dict[int, dict[str, Any]],
) -> tuple[list[OrderPassenger], dict[int, list[PassengerInfo]]]:
    associations: list[OrderPassenger] = []
    passengers_by_order: dict[int, list[PassengerInfo]] = {}
    role_by_type = {
        "FLIGHT": "PASSENGER",
        "HOTEL": "GUEST",
        "VISA": "APPLICANT",
        "TOUR": "TRAVELER",
    }

    for order in orders:
        metadata = metadata_by_order[order.order_id]
        owner_family = family_by_user[order.user_id]
        if metadata["global_index"] % 13 == 7:
            other_user = users[(metadata["global_index"] + 31) % len(users)]
            if other_user.user_id == order.user_id:
                other_user = users[(metadata["global_index"] + 32) % len(users)]
            selected = family_by_user[other_user.user_id][: order.passenger_count]
        else:
            selected = owner_family[: order.passenger_count]

        passengers_by_order[order.order_id] = selected
        for position, passenger in enumerate(selected):
            associations.append(
                OrderPassenger(
                    order_id=order.order_id,
                    passenger_id=passenger.passenger_id,
                    passenger_role=role_by_type[order.order_type],
                    is_primary=position == 0,
                )
            )
    session.add_all(associations)
    session.flush()
    return associations, passengers_by_order


def create_product_details(
    session: Session,
    rng: random.Random,
    as_of: datetime,
    orders: list[OrderInfo],
    metadata_by_order: dict[int, dict[str, Any]],
    passengers_by_order: dict[int, list[PassengerInfo]],
) -> tuple[list[VisaApplication], dict[int, BookingFlight]]:
    visa_applications: list[VisaApplication] = []
    hotel_bookings: list[BookingHotel] = []
    flight_bookings: list[BookingFlight] = []
    tour_bookings: list[BookingTour] = []
    primary_flight_by_order: dict[int, BookingFlight] = {}

    for order in orders:
        metadata = metadata_by_order[order.order_id]
        product_index = metadata["product_index"]
        special_kind = metadata["special_kind"]

        if order.order_type == "VISA":
            for passenger in passengers_by_order[order.order_id]:
                if special_kind == "visa_high_history" and product_index < 3:
                    status = "REJECTED"
                elif special_kind == "visa_low_history" and product_index == 12:
                    status = "REJECTED"
                else:
                    status = rng.choices(
                        ("APPROVED", "REJECTED", "PENDING"),
                        weights=(72, 12, 16),
                        k=1,
                    )[0]
                decided_at = None
                if status != "PENDING":
                    candidate = order.order_time + timedelta(days=rng.randint(1, 4))
                    if candidate <= as_of:
                        decided_at = candidate
                    else:
                        status = "PENDING"
                visa_applications.append(
                    VisaApplication(
                        order_id=order.order_id,
                        user_id=order.user_id,
                        passenger_id=passenger.passenger_id,
                        dest_country=order.dest_country or "JP",
                        visa_type=rng.choice(VISA_TYPES),
                        application_status=status,
                        reject_history=0,
                        reject_reason=("材料真实性存疑" if status == "REJECTED" else None),
                        submit_time=order.order_time,
                        decided_at=decided_at,
                        created_at=as_of,
                        updated_at=as_of,
                    )
                )
        elif order.order_type == "HOTEL":
            hotel_bookings.append(
                BookingHotel(
                    order_id=order.order_id,
                    hotel_id=f"HTL{product_index + 1:05d}",
                    check_in=order.depart_date,
                    check_out=order.return_date,
                    room_count=max(1, (order.passenger_count + 1) // 2),
                    is_refundable=rng.random() < 0.68,
                    city_code=(
                        rng.choice(DOMESTIC_CITIES)
                        if not order.is_cross_border
                        else f"{order.dest_country}-CITY"
                    ),
                    created_at=as_of,
                    updated_at=as_of,
                )
            )
        elif order.order_type == "FLIGHT":
            if special_kind == "flight_hoard_cluster":
                flight_no = "CA8888"
                depart_airport = "PEK"
                arrive_airport = "NRT"
                flight_date = (as_of + timedelta(days=5)).date()
            else:
                flight_no = f"{rng.choice(('CA', 'MU', 'CZ', 'HU'))}{rng.randint(100, 9999):04d}"
                depart_airport = rng.choice(DOMESTIC_CITIES)
                arrive_airport = (
                    rng.choice(INTERNATIONAL_AIRPORTS)
                    if order.is_cross_border
                    else rng.choice(DOMESTIC_CITIES)
                )
                flight_date = order.depart_date
            primary = BookingFlight(
                order_id=order.order_id,
                flight_no=flight_no,
                flight_date=flight_date,
                depart_airport=depart_airport,
                arrive_airport=arrive_airport,
                cabin_class=rng.choice(("ECONOMY", "PREMIUM_ECONOMY", "BUSINESS")),
                ticket_count=order.passenger_count,
                segment_no=1,
                created_at=as_of,
                updated_at=as_of,
            )
            primary_flight_by_order[order.order_id] = primary
            flight_bookings.append(primary)
            if product_index % 4 == 0 and special_kind != "flight_hoard_cluster":
                flight_bookings.append(
                    BookingFlight(
                        order_id=order.order_id,
                        flight_no=f"{rng.choice(('CA', 'MU', 'CZ', 'HU'))}{rng.randint(100, 9999):04d}",
                        flight_date=order.return_date,
                        depart_airport=arrive_airport,
                        arrive_airport=depart_airport,
                        cabin_class=primary.cabin_class,
                        ticket_count=order.passenger_count,
                        segment_no=2,
                        created_at=as_of,
                        updated_at=as_of,
                    )
                )
        elif order.order_type == "TOUR":
            tour_bookings.append(
                BookingTour(
                    order_id=order.order_id,
                    tour_code=f"TOUR{product_index + 1:05d}",
                    tour_name=(
                        f"{order.dest_country} 精选跟团游"
                        if order.is_cross_border
                        else "国内精选跟团游"
                    ),
                    route_type="OUTBOUND" if order.is_cross_border else "DOMESTIC",
                    group_code=(f"G{as_of:%Y%m}{product_index + 1:04d}" if product_index % 3 else None),
                    departure_date=order.depart_date,
                    return_date=order.return_date,
                    traveler_count=order.passenger_count,
                    created_at=as_of,
                    updated_at=as_of,
                )
            )

    session.add_all(visa_applications)
    session.add_all(hotel_bookings)
    session.add_all(flight_bookings)
    session.add_all(tour_bookings)
    session.flush()

    rejection_events: dict[int, list[datetime]] = defaultdict(list)
    for application in sorted(visa_applications, key=lambda item: item.submit_time):
        prior_count = sum(
            1
            for decided_at in rejection_events[application.user_id]
            if decided_at >= application.submit_time - timedelta(days=90)
            and decided_at < application.submit_time
        )
        application.reject_history = prior_count
        if application.application_status == "REJECTED" and application.decided_at:
            rejection_events[application.user_id].append(application.decided_at)

    return visa_applications, primary_flight_by_order


def create_blacklist(
    session: Session,
    as_of: datetime,
    orders: list[OrderInfo],
    passengers_by_order: dict[int, list[PassengerInfo]],
) -> list[BlacklistExtra]:
    selected_hashes: list[tuple[str, str]] = []
    for index in range(7, len(orders), 37):
        passenger = passengers_by_order[orders[index].order_id][0]
        selected_hashes.append((passenger.id_number_hash, passenger.id_number_masked))
    unique_selected = list(dict.fromkeys(selected_hashes))

    blacklist: list[BlacklistExtra] = []
    for index, (value_hash, value_masked) in enumerate(unique_selected):
        blacklist.append(
            BlacklistExtra(
                entry_type="PASSPORT",
                value_hash=value_hash,
                value_masked=value_masked,
                reason="历史欺诈关联" if index % 2 == 0 else "风险名单命中",
                status="ACTIVE",
                effective_at=as_of - timedelta(days=180),
                expire_at=None if index % 3 else as_of + timedelta(days=365),
                created_by=DEFAULT_REVIEWER,
                created_at=as_of,
                updated_at=as_of,
            )
        )

    while len(blacklist) < 20:
        ordinal = len(blacklist) + 1
        document = f"BLACKLIST-{ordinal:04d}"
        blacklist.append(
            BlacklistExtra(
                entry_type="PASSPORT",
                value_hash=sha256_text(document),
                value_masked=mask_document(document),
                reason="外部名单导入",
                status="ACTIVE" if ordinal % 5 else "INACTIVE",
                effective_at=as_of - timedelta(days=90),
                expire_at=None,
                created_by=DEFAULT_REVIEWER,
                created_at=as_of,
                updated_at=as_of,
            )
        )
    session.add_all(blacklist)
    session.flush()
    return blacklist


def create_assessments(
    session: Session,
    rng: random.Random,
    as_of: datetime,
    orders: list[OrderInfo],
    users: list[UserInfo],
    rules: list[RiskRule],
    visa_applications: list[VisaApplication],
    primary_flight_by_order: dict[int, BookingFlight],
    passengers_by_order: dict[int, list[PassengerInfo]],
    blacklist: list[BlacklistExtra],
) -> tuple[list[RiskAssessment], list[RiskHit], list[ReviewCase], set[str]]:
    user_by_id = {user.user_id: user for user in users}
    rule_by_code = {rule.rule_code: rule for rule in rules}
    active_blacklist = {
        entry.value_hash
        for entry in blacklist
        if entry.status == "ACTIVE" and (entry.expire_at is None or entry.expire_at > as_of)
    }
    visa_by_user: dict[int, list[VisaApplication]] = defaultdict(list)
    for application in visa_applications:
        visa_by_user[application.user_id].append(application)

    orders_by_id = {order.order_id: order for order in orders}
    flight_events: dict[tuple[int, str, date], list[tuple[datetime, int]]] = defaultdict(list)
    passenger_history: dict[int, set[int]] = defaultdict(set)
    assessments: list[RiskAssessment] = []
    hits: list[RiskHit] = []
    cases: list[ReviewCase] = []
    hit_codes: set[str] = set()

    for order in sorted(orders, key=lambda item: (item.order_time, item.order_id)):
        order_hits: list[tuple[RiskRule, dict[str, Any]]] = []

        def register_hit(rule_code: str, evidence: dict[str, Any]) -> None:
            rule = rule_by_code[rule_code]
            order_hits.append((rule, evidence))
            hit_codes.add(rule_code)

        recent_rejections = [
            application
            for application in visa_by_user[order.user_id]
            if application.application_status == "REJECTED"
            and application.decided_at is not None
            and order.order_time - timedelta(days=90)
            <= application.decided_at
            < order.order_time
        ]
        rejection_count = len(recent_rejections)
        if rejection_count >= 3:
            register_hit(
                "VISA_REJECT_90D_GTE3",
                {"reject_count": rejection_count, "window_days": 90},
            )
        elif rejection_count >= 1:
            register_hit(
                "VISA_REJECT_90D_GTE1",
                {"reject_count": rejection_count, "window_days": 90},
            )

        recent_countries = {
            application.dest_country
            for application in visa_by_user[order.user_id]
            if order.order_time - timedelta(days=30)
            <= application.submit_time
            <= order.order_time
        }
        country_count = len(recent_countries)
        if country_count >= 3:
            register_hit(
                "VISA_COUNTRY_30D_GTE3",
                {"country_count": country_count, "countries": sorted(recent_countries)},
            )
        elif country_count >= 1:
            register_hit(
                "VISA_COUNTRY_30D_GTE1",
                {"country_count": country_count, "countries": sorted(recent_countries)},
            )

        amount = Decimal(order.total_amount)
        if order.is_cross_border and amount >= Decimal("50000"):
            register_hit(
                "CROSS_BORDER_AMOUNT_GTE50000",
                {"amount": str(amount), "currency": order.currency},
            )
        elif order.is_cross_border and amount >= Decimal("30000"):
            register_hit(
                "CROSS_BORDER_AMOUNT_GTE30000",
                {"amount": str(amount), "currency": order.currency},
            )

        flight = primary_flight_by_order.get(order.order_id)
        if flight is not None:
            flight_key = (order.payment_account_id, flight.flight_no, flight.flight_date)
            window_start = order.order_time - timedelta(hours=1)
            current_events = [
                event
                for event in flight_events[flight_key]
                if window_start <= event[0] <= order.order_time
            ]
            ticket_count = sum(event[1] for event in current_events) + flight.ticket_count
            if ticket_count >= 5:
                register_hit(
                    "FLIGHT_HOARD_1H_GTE5",
                    {
                        "payment_account_id": order.payment_account_id,
                        "flight_no": flight.flight_no,
                        "flight_date": flight.flight_date.isoformat(),
                        "ticket_count": ticket_count,
                    },
                )
            elif ticket_count >= 2:
                register_hit(
                    "FLIGHT_HOARD_1H_GTE2",
                    {
                        "payment_account_id": order.payment_account_id,
                        "flight_no": flight.flight_no,
                        "flight_date": flight.flight_date.isoformat(),
                        "ticket_count": ticket_count,
                    },
                )
            flight_events[flight_key].append((order.order_time, flight.ticket_count))

        if order.depart_date is not None and 1 <= order.order_time.hour < 5:
            interval_days = (order.depart_date - order.order_time.date()).days
            if interval_days <= 3:
                register_hit(
                    "NIGHT_ORDER_DEPART_LE3",
                    {"order_hour": order.order_time.hour, "interval_days": interval_days},
                )
            elif interval_days <= 7:
                register_hit(
                    "NIGHT_ORDER_DEPART_LE7",
                    {"order_hour": order.order_time.hour, "interval_days": interval_days},
                )

        current_passenger_ids = {
            passenger.passenger_id for passenger in passengers_by_order[order.order_id]
        }
        historical_ids = passenger_history[order.user_id]
        if historical_ids:
            match_count = len(current_passenger_ids & historical_ids)
            match_rate = round((match_count / len(current_passenger_ids)) * 100, 2)
            if match_rate <= 30:
                register_hit(
                    "PASSENGER_HISTORY_MATCH_LTE30",
                    {
                        "match_rate_percent": match_rate,
                        "matched_passengers": match_count,
                        "current_passengers": len(current_passenger_ids),
                    },
                )
        passenger_history[order.user_id].update(current_passenger_ids)

        user = user_by_id[order.user_id]
        account_age_days = calculate_account_age_days(
            user.registered_at, as_of=order.order_time
        )
        if account_age_days < 7 and amount > Decimal("10000"):
            register_hit(
                "NEW_USER_LARGE_ORDER",
                {"account_age_days": account_age_days, "amount": str(amount)},
            )

        blacklisted = [
            passenger.id_number_masked
            for passenger in passengers_by_order[order.order_id]
            if passenger.id_number_hash in active_blacklist
        ]
        if blacklisted:
            register_hit(
                "PASSPORT_BLACKLIST",
                {"matched_passports": blacklisted, "match_count": len(blacklisted)},
            )

        score_result = calculate_risk_score(rule.risk_score for rule, _ in order_hits)
        raw_score = score_result.raw_score
        risk_score = score_result.final_score
        decision = score_result.decision
        if decision == "REJECT":
            order.order_status = "RISK_REJECTED"
        elif decision == "REVIEW":
            order.order_status = "RISK_REVIEW"
        else:
            order.order_status = "CONFIRMED"

        reason = (
            "未命中风险规则"
            if not order_hits
            else "命中：" + "、".join(dict.fromkeys(rule.rule_name for rule, _ in order_hits))
        )
        assessment = RiskAssessment(
            order_id=order.order_id,
            raw_score=raw_score,
            risk_score=risk_score,
            decision=decision,
            decision_reason=reason[:500],
            evaluated_at=order.order_time,
            engine_version=ENGINE_VERSION,
            created_at=as_of,
        )
        session.add(assessment)
        session.flush()
        assessments.append(assessment)

        for rule, evidence in order_hits:
            hit = RiskHit(
                assessment_id=assessment.assessment_id,
                rule_id=rule.rule_id,
                rule_code_snapshot=rule.rule_code,
                rule_name_snapshot=rule.rule_name,
                score_snapshot=rule.risk_score,
                condition_snapshot=rule.condition_json,
                evidence_json=evidence,
                created_at=as_of,
            )
            session.add(hit)
            hits.append(hit)

        if decision == "REVIEW":
            case = ReviewCase(
                case_no=f"RC{as_of:%Y%m%d}{assessment.assessment_id:08d}",
                order_id=order.order_id,
                assessment_id=assessment.assessment_id,
                status="PENDING",
                reviewer=None,
                decision_reason=None,
                reviewed_at=None,
                lock_version=0,
                created_at=order.order_time,
                updated_at=order.order_time,
            )
            session.add(case)
            cases.append(case)

    session.flush()
    return assessments, hits, cases, hit_codes


def create_audit_logs(
    session: Session,
    as_of: datetime,
    rules: list[RiskRule],
    blacklist: list[BlacklistExtra],
    cases: list[ReviewCase],
) -> list[AuditLog]:
    logs: list[AuditLog] = []
    for rule in rules:
        logs.append(
            AuditLog(
                operator=DEFAULT_REVIEWER,
                action="RULE_CREATED",
                entity_type="risk_rule",
                entity_id=str(rule.rule_id),
                before_data=None,
                after_data={
                    "rule_code": rule.rule_code,
                    "risk_score": rule.risk_score,
                    "condition": rule.condition_json,
                    "is_enabled": rule.is_enabled,
                },
                request_id=f"SEED-RULE-{rule.rule_id}",
                created_at=as_of,
            )
        )
    for entry in blacklist:
        logs.append(
            AuditLog(
                operator=DEFAULT_REVIEWER,
                action="BLACKLIST_CREATED",
                entity_type="blacklist_extra",
                entity_id=str(entry.entry_id),
                before_data=None,
                after_data={
                    "entry_type": entry.entry_type,
                    "value_masked": entry.value_masked,
                    "status": entry.status,
                },
                request_id=f"SEED-BLACKLIST-{entry.entry_id}",
                created_at=as_of,
            )
        )
    for case in cases:
        if case.status == "PENDING":
            continue
        logs.append(
            AuditLog(
                operator=case.reviewer or DEFAULT_REVIEWER,
                action="REVIEW_DECIDED",
                entity_type="review_case",
                entity_id=str(case.case_id),
                before_data={"status": "PENDING"},
                after_data={
                    "status": case.status,
                    "decision_reason": case.decision_reason,
                },
                request_id=f"SEED-REVIEW-{case.case_id}",
                created_at=case.reviewed_at or as_of,
            )
        )
    session.add_all(logs)
    session.flush()
    return logs


def seed_database(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    as_of = datetime.combine(args.as_of, time(12, 0))

    with SessionLocal.begin() as session:
        if args.reset:
            clear_existing_data(session)
        else:
            ensure_database_is_empty(session)

        rules = create_rules(session, as_of)
        users = create_users(session, rng, as_of)
        _, accounts_by_user = create_payment_accounts(session, users)
        _, family_by_user = create_passengers(session, rng, users)
        orders, metadata_by_order = create_orders(
            session, rng, as_of, args.orders, users, accounts_by_user
        )
        _, passengers_by_order = create_order_passengers(
            session, orders, users, family_by_user, metadata_by_order
        )
        visa_applications, primary_flight_by_order = create_product_details(
            session,
            rng,
            as_of,
            orders,
            metadata_by_order,
            passengers_by_order,
        )
        blacklist = create_blacklist(session, as_of, orders, passengers_by_order)
        _, _, cases, hit_codes = create_assessments(
            session,
            rng,
            as_of,
            orders,
            users,
            rules,
            visa_applications,
            primary_flight_by_order,
            passengers_by_order,
            blacklist,
        )
        missing_rules = {item["rule_code"] for item in RULE_CATALOG} - hit_codes
        if missing_rules:
            raise RuntimeError(
                "Generated data did not cover every rule: " + ", ".join(sorted(missing_rules))
            )
        create_audit_logs(session, as_of, rules, blacklist, cases)


def print_summary() -> None:
    models = (
        UserInfo,
        PaymentAccount,
        OrderInfo,
        PassengerInfo,
        OrderPassenger,
        VisaApplication,
        BookingHotel,
        BookingFlight,
        BookingTour,
        BlacklistExtra,
        RiskRule,
        RiskAssessment,
        RiskHit,
        ReviewCase,
        AuditLog,
    )
    with SessionLocal() as session:
        print("Seeded row counts:")
        for model in models:
            count = session.scalar(select(func.count()).select_from(model)) or 0
            print(f"  {model.__tablename__}: {count}")
        print("Decision distribution:")
        rows = session.execute(
            select(RiskAssessment.decision, func.count())
            .group_by(RiskAssessment.decision)
            .order_by(RiskAssessment.decision)
        )
        for decision, count in rows:
            print(f"  {decision}: {count}")
        print("Rule coverage:")
        rows = session.execute(
            select(RiskHit.rule_code_snapshot, func.count())
            .group_by(RiskHit.rule_code_snapshot)
            .order_by(RiskHit.rule_code_snapshot)
        )
        for rule_code, count in rows:
            print(f"  {rule_code}: {count}")


def main() -> None:
    args = parse_arguments()
    seed_database(args)
    print_summary()


if __name__ == "__main__":
    main()

"""生成并幂等写入完全虚构的银行业务演示数据。"""

import argparse
import asyncio
import hashlib
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.models_business import (  # noqa: E402
    BankCard,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)

ALLOWED_DATABASES = {"bank_risk", "bank_risk_test"}
RISK_PATTERNS = (
    "异地大额",
    "凌晨密集",
    "新设备大额",
    "多卡归集",
    "多头借贷",
    "设备多人共用",
    "代理/Tor",
    "黑卡候选",
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event_counts(count: int) -> dict[str, int]:
    if count < 8:
        raise ValueError("--count 至少为 8，才能构造四类事件及有效卡关系")
    base, remainder = divmod(count, 4)
    names = ("绑卡", "转账", "贷款申请", "登录")
    return {
        name: base + (1 if index < remainder else 0) for index, name in enumerate(names)
    }


def build_business_data(count: int = 100, seed: int = 20260811) -> dict[str, Any]:
    """按 seed 构造可复现的数据；count 是四类 source 记录总数。"""
    event_counts = _event_counts(count)
    rng = random.Random(seed)
    prefix = f"DEMO_{seed}_"
    anchor = datetime(2026, 1, 1, 12, 0, 0) + timedelta(days=seed % 180)

    card_count = event_counts["绑卡"]
    transaction_count = event_counts["转账"]
    loan_count = event_counts["贷款申请"]
    login_count = event_counts["登录"]
    # 大批量训练数据保留足够多的独立用户，便于按用户分组切分训练/验证集。
    user_count = max(20, min(500, card_count))
    ip_count = max(8, min(20, (count + 7) // 8))

    users = []
    for index in range(user_count):
        users.append(
            {
                "user_id": f"{prefix}USR_{index:03d}",
                "name": f"教学虚构用户{index:03d}",
                "id_card_hash": _digest(f"{prefix}ID_CARD_{index}"),
                "credit_score": 430 + rng.randint(0, 350),
                "register_at": anchor - timedelta(days=30 + rng.randint(0, 720)),
                "kyc_level": ("基础", "标准", "增强")[index % 3],
            }
        )

    ips = []
    cities = (
        ("华东", "海州市"),
        ("华南", "岭南市"),
        ("华北", "北辰市"),
        ("西部", "云山市"),
    )
    for index in range(ip_count):
        province, city = cities[index % len(cities)]
        ips.append(
            {
                "ip": f"IP_DEMO_{seed}_{index:03d}",
                "country": "虚构国",
                "province": province,
                "city": city,
                "isp": f"教学网络{index % 3}",
                "is_proxy": index in (1, 2),
                "is_tor": index == 2,
                "updated_at": anchor,
            }
        )

    devices = []
    shared_device_id = f"{prefix}DEV_SHARED"
    for index, user in enumerate(users):
        device_id = shared_device_id if index < 5 else f"{prefix}DEV_{index:03d}"
        first_seen = anchor - timedelta(days=1 if index % 10 == 0 else 60 + index % 90)
        devices.append(
            {
                "device_id": device_id,
                "user_id": user["user_id"],
                "fingerprint_hash": _digest(device_id),
                "first_seen": first_seen,
                "last_seen": anchor + timedelta(hours=index),
                "os": ("教学Android", "教学iOS", "教学Windows")[index % 3],
                "browser": ("教学浏览器A", "教学浏览器B")[index % 2],
            }
        )

    cards = []
    for index in range(card_count):
        user = users[index % user_count]
        cards.append(
            {
                "card_id": f"{prefix}CARD_{index:03d}",
                "user_id": user["user_id"],
                "card_no_hash": _digest(f"{prefix}CARD_NUMBER_{index}"),
                "bank_code": f"DEMO_BANK_{index % 4}",
                "card_type": "信用卡" if index % 3 == 0 else "借记卡",
                "credit_limit": Decimal("50000.00")
                if index % 3 == 0
                else Decimal("0.00"),
                "bind_at": anchor - timedelta(days=index),
                "is_active": True,
            }
        )

    transactions = []
    user_device = {row["user_id"]: row["device_id"] for row in devices}
    for index in range(transaction_count):
        block_pos = index % 8
        block = index // 8
        target_index = (block * 8 + 7) % card_count
        if block_pos == 0:
            # 每组首笔使用明确的新设备客户和异地大额，形成可解释正例。
            from_index = (block * 10) % user_count
        else:
            from_index = (block * 8 + block_pos) % card_count
        to_index = target_index if block_pos < 5 else (from_index + 7) % card_count
        if to_index == from_index:
            to_index = (to_index + 1) % card_count
        high_amount = block_pos == 0
        hour = 2 if block_pos < 5 else 9 + index % 10
        ip_index = 2 if high_amount else 0
        owner_id = cards[from_index]["user_id"]
        transactions.append(
            {
                "txn_id": f"{prefix}TXN_{index:03d}",
                "from_card": cards[from_index]["card_id"],
                "to_card": cards[to_index]["card_id"],
                "amount": Decimal("88000.00")
                if high_amount
                else Decimal(str(200 + rng.randint(0, 8000))),
                "channel": ("手机银行", "网上银行", "ATM")[index % 3],
                "device_id": user_device[owner_id],
                "ip": ips[ip_index]["ip"],
                "geo": "异地-岭南市"
                if high_amount
                else f"常用地-{ips[ip_index]['city']}",
                "txn_at": anchor.replace(hour=hour) + timedelta(minutes=index % 60),
                "status": "成功",
            }
        )

    loans = []
    for index in range(loan_count):
        block_pos = index % 6
        block = index // 6
        # 每 6 笔中前 4 笔属于同一客户、机构各异；第 3/4 笔稳定命中多头借贷。
        user = users[(block * 7) % user_count] if block_pos < 4 else users[index % user_count]
        loans.append(
            {
                "loan_id": f"{prefix}LOAN_{index:03d}",
                "user_id": user["user_id"],
                "amount": Decimal("200000.00")
                if block_pos < 4
                else Decimal(str(10000 + rng.randint(0, 90000))),
                "term_months": (6, 12, 24, 36)[index % 4],
                "purpose": ("教学消费", "教学经营", "教学装修")[index % 3],
                "monthly_income": Decimal("8000.00")
                if block_pos < 4
                else Decimal(str(6000 + rng.randint(0, 20000))),
                "debt_ratio": Decimal("0.8500")
                if block_pos < 4
                else Decimal(f"0.{20 + index % 50:04d}"),
                "institution_code": f"DEMO_LENDER_{block_pos}",
                "apply_at": anchor + timedelta(days=block_pos, minutes=block % 60),
                "status": "待审核",
            }
        )

    logins = []
    for index in range(login_count):
        user = users[index % user_count]
        if index < 5:
            device_id = shared_device_id
            device_user = users[index]["user_id"]
        else:
            device_user = user["user_id"]
            device_id = devices[index % len(devices)]["device_id"]
            matching = next(
                (
                    row
                    for row in devices
                    if row["device_id"] == device_id and row["user_id"] == device_user
                ),
                None,
            )
            if matching is None:
                device_id = next(
                    row["device_id"] for row in devices if row["user_id"] == device_user
                )
        ip_index = (1 + index % 2) if index % 10 == 0 else 0
        logins.append(
            {
                "login_id": f"{prefix}LOGIN_{index:03d}",
                "user_id": device_user,
                "device_id": device_id,
                "ip": ips[ip_index]["ip"],
                "geo": f"登录地-{ips[ip_index]['city']}",
                "success": index % 9 != 0,
                "login_at": anchor - timedelta(days=2) + timedelta(minutes=index * 3),
            }
        )

    blacklist_extra = [
        {
            "type": "银行卡号",
            "value": cards[index]["card_no_hash"],
            "reason": "教学黑卡候选，不代表真实司法或欺诈结论",
            "expire_at": anchor + timedelta(days=180),
            "created_at": anchor,
        }
        for index in range(min(2, len(cards)))
    ]
    blacklist_extra.extend(
        [
            {
                "type": "设备指纹",
                "value": _digest(shared_device_id),
                "reason": "教学共享设备候选",
                "expire_at": anchor + timedelta(days=30),
                "created_at": anchor,
            },
            {
                "type": "IP",
                "value": ips[2]["ip"],
                "reason": "教学代理/Tor网络候选",
                "expire_at": anchor + timedelta(days=30),
                "created_at": anchor,
            },
        ]
    )

    device_first_seen = {row["device_id"]: row["first_seen"] for row in devices}
    incoming_cards: dict[str, set[str]] = defaultdict(set)
    for row in transactions:
        incoming_cards[row["to_card"]].add(row["from_card"])
    loan_institutions: dict[str, set[str]] = defaultdict(set)
    for row in loans:
        loan_institutions[row["user_id"]].add(row["institution_code"])
    device_users: dict[str, set[str]] = defaultdict(set)
    for row in devices:
        device_users[row["device_id"]].add(row["user_id"])
    risky_ips = {row["ip"] for row in ips if row["is_proxy"] or row["is_tor"]}
    risk_patterns = {
        "异地大额": sum(1 for row in transactions if row["amount"] > Decimal("50000") and row["geo"].startswith("异地")),
        "凌晨密集": sum(1 for row in transactions if 0 <= row["txn_at"].hour <= 5),
        "新设备大额": sum(1 for row in transactions if row["amount"] > Decimal("30000") and (row["txn_at"] - device_first_seen[row["device_id"]]).days < 7),
        "多卡归集": sum(1 for cards_for_payee in incoming_cards.values() if len(cards_for_payee) >= 3),
        "多头借贷": sum(1 for institutions in loan_institutions.values() if len(institutions) >= 3),
        "设备多人共用": sum(1 for users_for_device in device_users.values() if len(users_for_device) >= 5),
        "代理/Tor": sum(1 for row in logins if row["ip"] in risky_ips),
        "黑卡候选": min(2, len(cards)),
    }
    tables = {
        "user_info": users,
        "ip_geo_location": ips,
        "device_fingerprint": devices,
        "bank_card": cards,
        "bank_transaction": transactions,
        "loan_application": loans,
        "login_log": logins,
        "blacklist_extra": blacklist_extra,
    }
    return {
        **tables,
        "summary": {
            "tables": {name: len(rows) for name, rows in tables.items()},
            "events": event_counts,
        },
        "risk_patterns": risk_patterns,
    }


async def _upsert_rows(connection, model, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    statement = mysql_insert(model.__table__).values(rows)
    primary_keys = {column.name for column in model.__table__.primary_key.columns}
    update_values = {
        column.name: getattr(statement.inserted, column.name)
        for column in model.__table__.columns
        if column.name not in primary_keys and column.name in rows[0]
    }
    await connection.execute(statement.on_duplicate_key_update(**update_values))


async def write_business_data(data: dict[str, Any], db_name: str) -> None:
    if db_name not in ALLOWED_DATABASES:
        raise ValueError(
            f"数据库只允许为 {sorted(ALLOWED_DATABASES)}，实际为 {db_name}"
        )
    engine = create_async_engine(
        settings.get_database_url_async(db_name), pool_pre_ping=False
    )
    try:
        async with engine.begin() as connection:
            for model, key in (
                (UserInfo, "user_info"),
                (IpGeoLocation, "ip_geo_location"),
                (DeviceFingerprint, "device_fingerprint"),
                (BankCard, "bank_card"),
                (Transaction, "bank_transaction"),
                (LoanApplication, "loan_application"),
                (LoginLog, "login_log"),
                (BlacklistExtra, "blacklist_extra"),
            ):
                await _upsert_rows(connection, model, data[key])
    finally:
        await engine.dispose()


def _print_summary(data: dict[str, Any]) -> None:
    print("各表数量：")
    for name, count in data["summary"]["tables"].items():
        print(f"- {name}: {count}")
    print("四类事件数量：")
    for name, count in data["summary"]["events"].items():
        print(f"- {name}: {count}")
    print("高风险模式：")
    print(json.dumps(data["risk_patterns"], ensure_ascii=False, sort_keys=True))


async def main() -> int:
    parser = argparse.ArgumentParser(description="生成可重复、完全虚构的银行业务数据")
    parser.add_argument(
        "--count", type=int, default=100, help="四类 source 业务记录总数，默认 100"
    )
    parser.add_argument("--seed", type=int, default=20260811, help="随机种子")
    parser.add_argument(
        "--db",
        default=settings.DB_NAME,
        choices=sorted(ALLOWED_DATABASES),
        help="目标专用数据库",
    )
    args = parser.parse_args()

    try:
        data = build_business_data(count=args.count, seed=args.seed)
        await write_business_data(data, args.db)
    except (ValueError, OSError) as exc:
        print(f"生成失败: {exc}")
        return 1

    print(
        f"幂等写入完成: database={args.db}, seed={args.seed}, source_count={args.count}"
    )
    _print_summary(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

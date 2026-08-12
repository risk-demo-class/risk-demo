"""写入可复现的小规模银行演示数据，所有标识均为虚构或哈希值。"""

import asyncio
import hashlib
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.models_business import (  # noqa: E402
    AccountStatus,
    AccountType,
    BankAccount,
    BankCard,
    BankTransaction,
    CardStatus,
    CardType,
    CustomerInfo,
    CustomerStatus,
    DeviceFingerprint,
    IpGeoLocation,
    KycLevel,
    LoanApplication,
    LoanStatus,
    LoginLog,
    TransactionChannel,
    TransactionStatus,
    TransactionType,
)
from app.models_risk import BlacklistType, RiskBlacklist  # noqa: E402


def demo_hash(value: str) -> str:
    return hashlib.sha256(f"bank-risk-demo::{value}".encode()).hexdigest()


async def _merge_all(db: AsyncSession, rows: list[object]) -> None:
    for row in rows:
        await db.merge(row)
    await db.flush()


async def _upsert_device(db: AsyncSession, **values: object) -> None:
    result = await db.execute(
        select(DeviceFingerprint).where(
            DeviceFingerprint.device_id == values["device_id"],
            DeviceFingerprint.user_id == values["user_id"],
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        db.add(DeviceFingerprint(**values))
    else:
        for key, value in values.items():
            setattr(device, key, value)


async def seed_demo_data(db: AsyncSession) -> None:
    await _merge_all(
        db,
        [
            CustomerInfo(
                user_id="U10001", name_hash=demo_hash("normal-name"),
                id_card_hash=demo_hash("normal-id"), mobile_hash=demo_hash("normal-mobile"),
                credit_score=720, kyc_level=KycLevel.L2, monthly_income=Decimal("18000"),
                home_city="北京", register_at=datetime(2023, 1, 1), status=CustomerStatus.NORMAL,
            ),
            CustomerInfo(
                user_id="U90001", name_hash=demo_hash("risk-name"),
                id_card_hash=demo_hash("risk-id"), mobile_hash=demo_hash("risk-mobile"),
                credit_score=520, kyc_level=KycLevel.L1, monthly_income=Decimal("8000"),
                home_city="北京", register_at=datetime(2025, 12, 1), status=CustomerStatus.NORMAL,
            ),
        ],
    )
    await _merge_all(
        db,
        [
            IpGeoLocation(
                ip="10.0.0.1", country="中国", province="北京", city="北京", isp="演示运营商A",
                is_proxy=False, is_tor=False, risk_score=5, updated_at=datetime(2026, 8, 1),
            ),
            IpGeoLocation(
                ip="10.0.0.9", country="中国", province="上海", city="上海", isp="演示代理网络",
                is_proxy=True, is_tor=False, risk_score=90, updated_at=datetime(2026, 8, 1),
            ),
        ],
    )
    await _merge_all(
        db,
        [
            BankAccount(
                account_id="A10001", user_id="U10001", account_no_hash=demo_hash("account-normal"),
                account_type=AccountType.SAVING, balance=Decimal("100000"),
                available_balance=Decimal("100000"), home_branch="北京演示支行",
                open_at=datetime(2023, 1, 2), status=AccountStatus.NORMAL,
            ),
            BankAccount(
                account_id="A90001", user_id="U90001", account_no_hash=demo_hash("account-risk"),
                account_type=AccountType.SAVING, balance=Decimal("200000"),
                available_balance=Decimal("200000"), home_branch="北京演示支行",
                open_at=datetime(2025, 12, 2), status=AccountStatus.NORMAL,
            ),
        ],
    )
    await _merge_all(
        db,
        [
            BankCard(
                card_id="C10001", user_id="U10001", account_id="A10001",
                card_no_hash=demo_hash("card-normal"), card_type=CardType.CREDIT,
                credit_limit=Decimal("50000"), available_limit=Decimal("40000"),
                issue_at=datetime(2024, 1, 1), status=CardStatus.NORMAL,
            ),
            BankCard(
                card_id="C90001", user_id="U90001", account_id="A90001",
                card_no_hash=demo_hash("card-risk"), card_type=CardType.CREDIT,
                credit_limit=Decimal("50000"), available_limit=Decimal("2000"),
                issue_at=datetime(2026, 1, 1), status=CardStatus.NORMAL,
            ),
        ],
    )
    await _upsert_device(
        db, device_id="D10001", user_id="U10001", fingerprint_hash=demo_hash("device-normal"),
        first_seen=datetime(2025, 1, 1), last_seen=datetime(2026, 8, 12, 11),
        os="Windows", browser="Chrome", is_rooted=False, is_emulator=False,
    )
    await _upsert_device(
        db, device_id="D90000", user_id="U90001", fingerprint_hash=demo_hash("device-risk-old"),
        first_seen=datetime(2025, 12, 1), last_seen=datetime(2026, 8, 11, 23, 30),
        os="Android", browser="APP", is_rooted=False, is_emulator=False,
    )
    await _upsert_device(
        db, device_id="D90001", user_id="U90001", fingerprint_hash=demo_hash("device-risk-new"),
        first_seen=datetime(2026, 8, 11), last_seen=datetime(2026, 8, 12, 12),
        os="Android", browser="APP", is_rooted=True, is_emulator=False,
    )
    await db.flush()

    await _merge_all(
        db,
        [
            LoginLog(
                login_id="L10001", user_id="U10001", device_id="D10001", ip="10.0.0.1",
                geo="北京", success=True, fail_reason=None, login_at=datetime(2026, 8, 12, 9),
            ),
            LoginLog(
                login_id="L90000", user_id="U90001", device_id="D90000", ip="10.0.0.1",
                geo="北京", success=True, fail_reason=None, login_at=datetime(2026, 8, 11, 23, 30),
            ),
            LoginLog(
                login_id="L90001", user_id="U90001", device_id="D90001", ip="10.0.0.9",
                geo="上海", success=True, fail_reason=None, login_at=datetime(2026, 8, 12, 10),
            ),
        ],
    )
    beneficiary_normal = demo_hash("beneficiary-normal")
    beneficiary_risk = demo_hash("beneficiary-risk")
    beneficiary_black = demo_hash("beneficiary-blacklisted")
    await _merge_all(
        db,
        [
            BankTransaction(
                txn_id="T10000", user_id="U10001", from_account_id="A10001", from_card_id=None,
                beneficiary_account_hash=beneficiary_normal, amount=Decimal("900"), currency="CNY",
                txn_type=TransactionType.TRANSFER, channel=TransactionChannel.APP,
                device_id="D10001", ip="10.0.0.1", geo="北京",
                txn_time=datetime(2026, 8, 10, 10), status=TransactionStatus.SUCCESS,
            ),
            BankTransaction(
                txn_id="T10001", user_id="U10001", from_account_id="A10001", from_card_id=None,
                beneficiary_account_hash=beneficiary_normal, amount=Decimal("1000"), currency="CNY",
                txn_type=TransactionType.TRANSFER, channel=TransactionChannel.APP,
                device_id="D10001", ip="10.0.0.1", geo="北京",
                txn_time=datetime(2026, 8, 12, 10), status=TransactionStatus.PENDING,
            ),
            BankTransaction(
                txn_id="T10002", user_id="U10001", from_account_id="A10001", from_card_id="C10001",
                beneficiary_account_hash=demo_hash("merchant-normal"), amount=Decimal("200"), currency="CNY",
                txn_type=TransactionType.CARD_PAYMENT, channel=TransactionChannel.POS,
                device_id="D10001", ip="10.0.0.1", geo="北京",
                txn_time=datetime(2026, 8, 12, 11), status=TransactionStatus.PENDING,
            ),
            BankTransaction(
                txn_id="T10003", user_id="U10001", from_account_id="A10001", from_card_id=None,
                beneficiary_account_hash=beneficiary_black, amount=Decimal("500"), currency="CNY",
                txn_type=TransactionType.TRANSFER, channel=TransactionChannel.APP,
                device_id="D10001", ip="10.0.0.1", geo="北京",
                txn_time=datetime(2026, 8, 12, 11, 30), status=TransactionStatus.PENDING,
            ),
            BankTransaction(
                txn_id="T90002", user_id="U90001", from_account_id="A90001", from_card_id="C90001",
                beneficiary_account_hash=demo_hash("merchant-risk"), amount=Decimal("12000"), currency="CNY",
                txn_type=TransactionType.CARD_PAYMENT, channel=TransactionChannel.APP,
                device_id="D90001", ip="10.0.0.9", geo="上海",
                txn_time=datetime(2026, 8, 12, 1), status=TransactionStatus.PENDING,
            ),
            BankTransaction(
                txn_id="T90001", user_id="U90001", from_account_id="A90001", from_card_id=None,
                beneficiary_account_hash=beneficiary_risk, amount=Decimal("60000"), currency="CNY",
                txn_type=TransactionType.TRANSFER, channel=TransactionChannel.APP,
                device_id="D90001", ip="10.0.0.9", geo="上海",
                txn_time=datetime(2026, 8, 12, 10, 30), status=TransactionStatus.PENDING,
            ),
        ],
    )
    await _merge_all(
        db,
        [
            LoanApplication(
                loan_id="LN10001", user_id="U10001", institution_code="DEMO_BANK_A",
                amount=Decimal("20000"), term_months=12, purpose="演示消费贷",
                monthly_income=Decimal("18000"), debt_ratio=Decimal("0.20"),
                device_id="D10001", ip="10.0.0.1", apply_at=datetime(2026, 8, 12, 12),
                status=LoanStatus.SUBMITTED,
            ),
            LoanApplication(
                loan_id="LN90000A", user_id="U90001", institution_code="DEMO_BANK_A",
                amount=Decimal("10000"), term_months=12, purpose="演示历史申请",
                monthly_income=Decimal("8000"), debt_ratio=Decimal("0.50"),
                device_id="D90000", ip="10.0.0.1", apply_at=datetime(2026, 8, 1),
                status=LoanStatus.REJECTED,
            ),
            LoanApplication(
                loan_id="LN90000B", user_id="U90001", institution_code="DEMO_BANK_B",
                amount=Decimal("15000"), term_months=12, purpose="演示历史申请",
                monthly_income=Decimal("8000"), debt_ratio=Decimal("0.60"),
                device_id="D90000", ip="10.0.0.1", apply_at=datetime(2026, 8, 5),
                status=LoanStatus.REJECTED,
            ),
            LoanApplication(
                loan_id="LN90001", user_id="U90001", institution_code="DEMO_BANK_C",
                amount=Decimal("100000"), term_months=36, purpose="演示高风险贷款",
                monthly_income=Decimal("8000"), debt_ratio=Decimal("0.80"),
                device_id="D90001", ip="10.0.0.9", apply_at=datetime(2026, 8, 12, 12),
                status=LoanStatus.SUBMITTED,
            ),
        ],
    )

    result = await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == BlacklistType.BENEFICIARY_ACCOUNT,
            RiskBlacklist.blacklist_value == beneficiary_black,
        )
    )
    blacklist = result.scalar_one_or_none()
    if blacklist is None:
        db.add(
            RiskBlacklist(
                blacklist_type=BlacklistType.BENEFICIARY_ACCOUNT,
                blacklist_value=beneficiary_black,
                reason="教学演示：风险收款账户",
            )
        )


async def run() -> None:
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await seed_demo_data(db)
        print("演示数据初始化成功：正常/高风险登录、转账、信用卡交易、贷款申请")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())


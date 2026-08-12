"""可重复生成银行风控教学业务数据。"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

# Keep direct ``python scripts/...`` execution consistent with existing scripts.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import BankCard, BankTransaction, DeviceFingerprint, IpGeoLocation, LoanApplication, LoginLog, PayeeRelationship, UserInfo


async def _merge_device(db, device_id: str, user_id: str, now: datetime) -> None:
    exists = (await db.execute(select(DeviceFingerprint.record_id).where(DeviceFingerprint.device_id == device_id, DeviceFingerprint.user_id == user_id))).scalar_one_or_none()
    if not exists:
        db.add(DeviceFingerprint(device_id=device_id, user_id=user_id, fingerprint_hash=f"fp_{device_id}_{user_id}", first_seen=now, last_seen=now, os="Android", browser="Chrome"))


async def _merge_payee(db, user_id: str, payee_id: str, now: datetime) -> None:
    exists = (await db.execute(select(PayeeRelationship.relation_id).where(PayeeRelationship.user_id == user_id, PayeeRelationship.payee_id == payee_id))).scalar_one_or_none()
    if not exists:
        db.add(PayeeRelationship(user_id=user_id, payee_id=payee_id, payee_card_hash=f"payee_hash_{payee_id}", first_txn_at=now, last_txn_at=now, txn_count=1, total_amount=Decimal("1000")))


async def generate(count: int) -> tuple[int, int]:
    now = datetime.now().replace(microsecond=0)
    async with AsyncSessionLocal() as db:
        for ip, proxy, tor in (("10.0.0.1", False, False), ("10.0.0.99", True, False), ("10.0.0.66", False, True)):
            await db.merge(IpGeoLocation(ip=ip, country="中国", province="上海", city="上海", isp="demo", is_proxy=proxy, is_tor=tor))
        high_risk = 0
        for index in range(1, count + 1):
            user_id = f"BU{index:05d}"
            risky = index % 3 == 0
            high_risk += int(risky)
            home_geo = "上海" if risky else "北京"
            device_id = "DEV_SHARED" if risky else f"DEV{index:05d}"
            ip = "10.0.0.99" if risky else "10.0.0.1"
            txn_time = now - timedelta(minutes=index % 90)
            await db.merge(UserInfo(user_id=user_id, name=f"测试用户{index}", id_card_hash=f"id_hash_{index:05d}", credit_score=520 if risky else 720, register_at=now - timedelta(days=2 if risky else 600), kyc_level=2, monthly_income=Decimal("8000"), debt_ratio=Decimal("0.65") if risky else Decimal("0.18"), home_geo=home_geo, status="正常"))
            await db.merge(BankCard(card_id=f"BC{index:05d}", user_id=user_id, card_no_hash=f"card_hash_{index:05d}", bank_code="DEMO", card_type="信用卡", credit_limit=Decimal("50000"), open_at=now - timedelta(days=300)))
            await _merge_device(db, device_id, user_id, now - timedelta(days=1 if risky else 100))
            await _merge_payee(db, user_id, f"PAY{index:05d}", txn_time)
            await db.merge(BankTransaction(txn_id=f"TXN{index:06d}", user_id=user_id, from_card_id=f"BC{index:05d}", to_card_hash=f"target_hash_{index % 20:03d}", payee_id=f"PAY{index:05d}", amount=Decimal("65000") if risky else Decimal("800"), transaction_type="转账" if index % 2 else "信用卡交易", channel="web" if risky else "mobile", device_id=device_id, ip=ip, geo="北京" if risky else home_geo, txn_time=txn_time, status="成功"))
            await db.merge(LoanApplication(loan_id=f"LOAN{index:06d}", user_id=user_id, amount=Decimal("120000") if risky else Decimal("10000"), term_months=12, purpose="消费", monthly_income=Decimal("8000"), debt_ratio=Decimal("0.65") if risky else Decimal("0.18"), device_id=device_id, ip=ip, apply_at=txn_time, status="待审批"))
            await db.merge(LoginLog(login_id=f"LOGIN{index:06d}", user_id=user_id, device_id=device_id, ip=ip, geo="北京" if risky else home_geo, success=not risky, login_at=txn_time))
        await db.commit()
    return count, high_risk


def main() -> None:
    parser = argparse.ArgumentParser(description="生成银行风控教学业务数据")
    parser.add_argument("--count", type=int, default=150, help="生成用户/交易数量，默认150")
    args = parser.parse_args()
    total, high_risk = asyncio.run(generate(args.count))
    print(f"[OK] 生成或更新 {total} 位用户和对应银行业务数据")
    print(f"[OK] 高风险样本 {high_risk} 条，占比 {high_risk / total:.1%}")


if __name__ == "__main__":
    main()

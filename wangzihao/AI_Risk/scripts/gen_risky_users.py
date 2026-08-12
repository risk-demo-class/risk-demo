"""Generate deterministic manufacturing business data for Step 6.

The historical filename is retained as a CLI compatibility point.  It now creates
Dealer/Device/PurchaseOrder/WarrantyClaim/CrossRegionReport/BlacklistExtra rows only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


MANUFACTURING_MODES = (
    "normal_long",
    "normal_new",
    "risk_new_large",
    "risk_warranty",
    "risk_cross_region",
    "blacklisted",
)


def _mode_counts(count: int) -> dict[str, int]:
    if count < 20:
        raise ValueError("--count/--dealers must be at least 20")
    weights = (60, 20, 40, 40, 15, 5)
    raw = [count * weight / sum(weights) for weight in weights]
    counts = [int(value) for value in raw]
    for index in range(count - sum(counts)):
        counts[index % len(counts)] += 1
    return dict(zip(MANUFACTURING_MODES, counts))


def _items(index: int, quantity: int) -> str:
    return json.dumps(
        [
            {"model": f"MX-{index % 7 + 1:02d}", "quantity": quantity},
            {"model": f"MX-{(index + 3) % 7 + 1:02d}", "quantity": max(1, quantity // 2)},
        ],
        ensure_ascii=False,
    )


def _jitter(index: int, salt: int, modulo: int) -> int:
    """Deterministic non-monotonic variation; avoids encoding generation order."""
    return (index * 7919 + salt * 104729) % modulo


async def generate_manufacturing_business_data(
    *, db_name: str, dealer_count: int = 180, reset: bool = False
) -> dict[str, int]:
    mode_counts = _mode_counts(dealer_count)
    now = datetime.now().replace(microsecond=0)
    today = date.today()
    regions = ["华东", "华南", "华北", "西南", "华中"]

    dealers: list[dict] = []
    devices: list[dict] = []
    orders: list[dict] = []
    claims: list[dict] = []
    reports: list[dict] = []
    blacklist_extra: list[dict] = []
    core_blacklist: list[dict] = []

    mode_sequence: list[str] = []
    for mode in MANUFACTURING_MODES:
        mode_sequence.extend([mode] * mode_counts[mode])

    for index, mode in enumerate(mode_sequence, 1):
        dealer_id = f"MLD{index:04d}"
        region = regions[index % len(regions)]
        if mode in {"normal_new", "risk_new_large"}:
            authorized_at = today - timedelta(days=10 + index % 15)
        else:
            authorized_at = today - timedelta(days=900 + _jitter(index, 1, 1800))
        dealers.append({
            "dealer_id": dealer_id,
            "name": f"ML-{mode.upper()}-{index:04d}",
            "level": "核心" if mode == "normal_long" else "普通",
            "region": region,
            "authorized_at": authorized_at,
            "contract_end": today + timedelta(days=365 + index % 365),
        })

        device_total = 1 if mode in {"risk_warranty", "blacklisted"} else 2
        for device_no in range(1, device_total + 1):
            old_device = mode == "risk_warranty" and device_no == 1
            factory_at = today - timedelta(days=(2200 + index if old_device else 200 + index % 500))
            devices.append({
                "device_id": f"MLDEV{index:04d}_{device_no:02d}",
                "sn": f"SN-ML-{index:04d}-{device_no:02d}",
                "model": f"MX-{index % 7 + 1:02d}",
                "batch_no": f"B{(index % 12) + 1:02d}-{today.year}",
                "factory_at": factory_at,
                "warranty_end": factory_at + timedelta(days=1095),
                "dealer_id": dealer_id,
            })

        order_total = {
            "normal_long": 3,
            "normal_new": 3,
            "risk_new_large": 3,
            "risk_warranty": 2,
            "risk_cross_region": 2,
            "blacklisted": 2,
        }[mode]
        for order_no in range(1, order_total + 1):
            is_large = mode == "risk_new_large"
            amount = (
                Decimal("1050000") + Decimal(_jitter(index, order_no, 350000))
                if is_large
                else Decimal("90000") + Decimal(_jitter(index, order_no, 180000))
            )
            orders.append({
                "po_id": f"MLPO{index:04d}_{order_no:02d}",
                "dealer_id": dealer_id,
                "total_amount": amount,
                "items": _items(index + order_no, 2 + (index + order_no) % 6),
                "ship_to": f"{region}-仓库{index % 11 + 1}",
                "payment_term": ("预付", "账期30天", "账期60天")[order_no % 3],
                "create_time": now - timedelta(days=(index * 3 + order_no) % 85),
            })

        if mode == "normal_long":
            claims.append({
                "claim_id": f"MLCLM{index:04d}_01",
                "device_id": f"MLDEV{index:04d}_01",
                "dealer_id": dealer_id,
                "fault_desc": "常规传感器校准",
                "claim_amount": Decimal("5000") + Decimal(_jitter(index, 2, 15000)),
                "photos": json.dumps([f"normal-{index}.jpg"], ensure_ascii=False),
                "create_time": now - timedelta(days=index % 60),
            })
            reports.append({
                "report_id": f"MLCRR{index:04d}_01",
                "device_id": f"MLDEV{index:04d}_02",
                "expected_region": region,
                "actual_region": region,
                "reporter_id": f"REPORTER-{index:04d}",
                "create_time": now - timedelta(days=index % 45),
            })
        elif mode == "normal_new":
            reports.append({
                "report_id": f"MLCRR{index:04d}_01",
                "device_id": f"MLDEV{index:04d}_01",
                "expected_region": region,
                "actual_region": region,
                "reporter_id": f"REPORTER-{index:04d}",
                "create_time": now - timedelta(days=index % 20),
            })
        elif mode == "risk_warranty":
            # Ten claims on one physical device/SN: high-frequency and repeated-SN anomaly.
            for claim_no in range(1, 11):
                high_claim = claim_no == 10
                claims.append({
                    "claim_id": f"MLCLM{index:04d}_{claim_no:02d}",
                    "device_id": f"MLDEV{index:04d}_01",
                    "dealer_id": dealer_id,
                    "fault_desc": "同一设备重复故障申报",
                    "claim_amount": (
                        Decimal("120000") + Decimal(_jitter(index, claim_no, 120000))
                        if high_claim
                        else Decimal("15000") + Decimal(_jitter(index, claim_no, 30000))
                    ),
                    "photos": None if high_claim else json.dumps([f"claim-{index}-{claim_no}.jpg"]),
                    "create_time": now - timedelta(days=claim_no % 7, hours=index % 12),
                })
        elif mode == "risk_cross_region":
            for report_no in range(1, 3):
                actual = regions[(regions.index(region) + report_no) % len(regions)]
                reports.append({
                    "report_id": f"MLCRR{index:04d}_{report_no:02d}",
                    "device_id": f"MLDEV{index:04d}_{report_no:02d}",
                    "expected_region": region,
                    "actual_region": actual,
                    "reporter_id": f"REPORTER-{index:04d}-{report_no}",
                    "create_time": now - timedelta(days=report_no),
                })
        elif mode == "blacklisted":
            core_blacklist.append({
                "blacklist_type": "用户",
                "blacklist_value": dealer_id,
                "reason": "Step 6 黑经销商前置拦截验证",
            })
            blacklist_extra.append({
                "type": "银行账户",
                "value": f"ML-BANK-{index:04d}",
                "reason": f"经销商 {dealer_id} 扩展风险标识",
                "expire_at": None,
            })

    engine = create_async_engine(settings.get_database_url_async(db_name), pool_pre_ping=False)
    try:
        async with engine.begin() as conn:
            if reset:
                await conn.execute(text("DELETE FROM warranty_claim WHERE claim_id LIKE 'MLCLM%'"))
                await conn.execute(text("DELETE FROM cross_region_report WHERE report_id LIKE 'MLCRR%'"))
                await conn.execute(text("DELETE FROM purchase_order WHERE po_id LIKE 'ONLINE_%'"))
                await conn.execute(text("DELETE FROM purchase_order WHERE po_id LIKE 'MLPO%'"))
                await conn.execute(text("DELETE FROM device WHERE device_id LIKE 'MLDEV%'"))
                await conn.execute(text("DELETE FROM blacklist_extra WHERE value LIKE 'ML-%'"))
                await conn.execute(text("DELETE FROM risk_blacklist WHERE blacklist_type='用户' AND blacklist_value LIKE 'MLD%'"))
                await conn.execute(text("DELETE FROM dealer WHERE dealer_id LIKE 'MLD%'"))

            await conn.execute(text("""
                INSERT INTO dealer (dealer_id,name,level,region,authorized_at,contract_end)
                VALUES (:dealer_id,:name,:level,:region,:authorized_at,:contract_end)
            """), dealers)
            await conn.execute(text("""
                INSERT INTO device (device_id,sn,model,batch_no,factory_at,warranty_end,dealer_id)
                VALUES (:device_id,:sn,:model,:batch_no,:factory_at,:warranty_end,:dealer_id)
            """), devices)
            await conn.execute(text("""
                INSERT INTO purchase_order
                    (po_id,dealer_id,total_amount,items,ship_to,payment_term,create_time)
                VALUES (:po_id,:dealer_id,:total_amount,CAST(:items AS JSON),:ship_to,:payment_term,:create_time)
            """), orders)
            if claims:
                await conn.execute(text("""
                    INSERT INTO warranty_claim
                        (claim_id,device_id,dealer_id,fault_desc,claim_amount,photos,create_time)
                    VALUES (:claim_id,:device_id,:dealer_id,:fault_desc,:claim_amount,
                            CASE WHEN :photos IS NULL THEN NULL ELSE CAST(:photos AS JSON) END,:create_time)
                """), claims)
            if reports:
                await conn.execute(text("""
                    INSERT INTO cross_region_report
                        (report_id,device_id,expected_region,actual_region,reporter_id,create_time)
                    VALUES (:report_id,:device_id,:expected_region,:actual_region,:reporter_id,:create_time)
                """), reports)
            if blacklist_extra:
                await conn.execute(text("""
                    INSERT INTO blacklist_extra (type,value,reason,expire_at)
                    VALUES (:type,:value,:reason,:expire_at)
                """), blacklist_extra)
            if core_blacklist:
                await conn.execute(text("""
                    INSERT INTO risk_blacklist (blacklist_type,blacklist_value,reason,expire_time,deleted_at)
                    VALUES (:blacklist_type,:blacklist_value,:reason,NULL,NULL)
                """), core_blacklist)
    finally:
        await engine.dispose()

    counts = {
        "dealer": len(dealers),
        "device": len(devices),
        "purchase_order": len(orders),
        "warranty_claim": len(claims),
        "cross_region_report": len(reports),
        "blacklist_extra": len(blacklist_extra),
        "blacklisted_dealer": len(core_blacklist),
    }
    print("制造业模拟数据完成:", counts)
    print("场景分布:", mode_counts)
    return counts


# Historical callable name retained, but its semantics are now manufacturing-only.
gen_risky_users = generate_manufacturing_business_data


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Step 6 制造业经销商训练业务数据")
    parser.add_argument("--dealers", "--count", dest="dealer_count", type=int, default=180)
    parser.add_argument("--db", default=settings.DB_NAME)
    parser.add_argument("--reset", action="store_true", help="仅清理 ML* 前缀模拟业务数据后重建")
    args = parser.parse_args()
    asyncio.run(generate_manufacturing_business_data(
        db_name=args.db, dealer_count=args.dealer_count, reset=args.reset,
    ))


if __name__ == "__main__":
    main()

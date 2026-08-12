"""生成可重复的物流业务样本。

默认重建 80 用户、100 地址、300 运单和对应物品明细；固定随机种子确保
SQL 初始化、测试和模型训练使用同一分布。
"""
import argparse
import asyncio
import hashlib
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, insert  # noqa: E402

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.models import Address, BlacklistExtra, Shipment, ShipmentItem, UserInfo  # noqa: E402

SEED = 20260811
ANCHOR = datetime(2026, 8, 11, 12, 0, 0)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _q(value: Decimal, places: str) -> Decimal:
    """按数据库列精度量化，避免初始化时出现截断警告。"""
    return value.quantize(Decimal(places))


def build_rows(seed: int = SEED):
    rng = random.Random(seed)
    users = []
    special_status = {"U_RNAME": "信息不符"}
    user_ids = [f"U{i:03d}" for i in range(1, 75)] + [
        "U_RNAME", "U_DANGER", "U_CROSS", "U_COD", "U_FREQ", "U_ADDR",
    ]
    for idx, uid in enumerate(user_ids, 1):
        users.append({
            "user_id": uid,
            "user_role": "寄件人",
            "full_name": f"演示用户{idx:03d}",
            "phone": f"139{idx:08d}"[-11:],
            "id_type": "居民身份证",
            "id_no_hash": _sha(f"DEMO-ID-{uid}"),
            "id_no_masked": f"110101********{idx:04d}"[-18:],
            "real_name_status": special_status.get(uid, "已核验"),
            "device_fingerprint": f"DEV-{uid}",
            "last_ip": f"10.20.{idx // 250}.{idx % 250 + 1}",
            "account_status": "正常",
            "register_time": ANCHOR - timedelta(days=365 - idx),
        })

    regions = [
        ("北京市", "北京市", "朝阳区"), ("上海市", "上海市", "浦东新区"),
        ("广东省", "深圳市", "南山区"), ("浙江省", "杭州市", "余杭区"),
        ("四川省", "成都市", "武侯区"), ("新疆维吾尔自治区", "喀什地区", "塔什库尔干县"),
    ]
    addresses = []
    for idx in range(1, 101):
        province, city, district = regions[idx % len(regions)]
        is_shared = idx >= 95
        normalized = "共享临时仓地址" if is_shared else f"{province}{city}{district}演示路{idx}号"
        addresses.append({
            "address_id": f"ADDR{idx:03d}",
            "user_id": user_ids[(idx - 1) % len(user_ids)],
            "contact_name": f"收件人{idx:03d}",
            "contact_phone": f"138{idx:08d}"[-11:],
            "province": province,
            "city": city,
            "district": district,
            "detail_address": f"演示路{idx}号{idx % 9 + 1}室",
            "normalized_hash": _sha(normalized),
            "address_type": "临时" if is_shared else ("单位" if idx % 5 == 0 else "住宅"),
            "is_remote": 1 if province.startswith("新疆") else 0,
            "created_at": ANCHOR - timedelta(days=idx),
        })

    shipments, items = [], []
    normal_users = [f"U{i:03d}" for i in range(1, 75)]
    destinations = ["中国", "日本", "新加坡", "德国", "美国"]
    for idx in range(1, 301):
        bucket = idx % 20
        risk_pattern = None
        sender = normal_users[(idx * 7) % len(normal_users)]
        address_id = f"ADDR{(idx * 11) % 90 + 1:03d}"
        create_time = ANCHOR - timedelta(days=idx % 45, hours=idx % 12)
        payment_type, cod_status, cod_amount = "寄付", "无", Decimal("0")
        is_cross, destination, customs_status = 0, "中国", "不适用"
        declared_weight = Decimal(str(round(rng.uniform(0.2, 8.0), 3)))
        actual_weight = declared_weight + Decimal(str(round(rng.uniform(-0.08, 0.08), 3)))
        declared_value = Decimal(str(round(rng.uniform(30, 1800), 2)))
        assessed_value = declared_value
        real_name_verified, inspection_status = 1, "已通过"
        dangerous_type = None
        dangerous_declared, inspection_result = 0, "正常"
        shipment_status = "已签收"

        if bucket == 0:
            sender, risk_pattern, real_name_verified = "U_RNAME", "实名信息异常", 0
        elif bucket == 1:
            sender, risk_pattern = "U_DANGER", "危险品瞒报"
            inspection_status, shipment_status = "拒绝收寄", "安全拦截"
            dangerous_type, inspection_result = "锂电池", "禁寄"
        elif bucket == 2:
            sender, risk_pattern, is_cross = "U_CROSS", "跨境重量申报异常", 1
            destination, customs_status = destinations[idx % 4 + 1], "查验中"
            actual_weight = declared_weight * Decimal("1.85")
            assessed_value = declared_value * Decimal("2.4")
            shipment_status = "海关查验"
        elif bucket == 3:
            sender, risk_pattern = "U_COD", "代收货款高拒收"
            payment_type, cod_status = "代收货款", "拒收"
            cod_amount, shipment_status = Decimal(str(800 + idx * 11)), "拒收退回"
        elif bucket == 4:
            sender, risk_pattern = "U_FREQ", "高频凌晨寄件"
            create_time = ANCHOR - timedelta(days=idx % 6, hours=9 + idx % 5)
        elif bucket == 5:
            sender, risk_pattern, address_id = "U_ADDR", "共享临时偏远地址", f"ADDR{95 + idx % 6:03d}"

        shipment_id = f"SHP{idx:04d}"
        risk_label = 1 if risk_pattern else 0
        shipments.append({
            "shipment_id": shipment_id,
            "waybill_no": f"SF20260811{idx:06d}",
            "sender_id": sender,
            "receiver_id": None,
            "sender_address_id": None,
            "receiver_address_id": address_id,
            "create_time": create_time,
            "pickup_time": create_time + timedelta(minutes=10 + idx % 90),
            "delivered_time": None if shipment_status in ("安全拦截", "海关查验") else create_time + timedelta(days=2),
            "shipment_status": shipment_status,
            "channel": ["柜台", "上门取件", "直营网点", "合作平台"][idx % 4],
            "payment_type": payment_type,
            "cod_amount": cod_amount,
            "cod_status": cod_status,
            "is_cross_border": is_cross,
            "origin_country": "中国",
            "destination_country": destination,
            "customs_subject": "DEMO-CUSTOMS-RISK" if risk_pattern == "跨境重量申报异常" else None,
            "customs_status": customs_status,
            "declared_weight_kg": _q(max(declared_weight, Decimal("0.05")), "0.001"),
            "actual_weight_kg": _q(max(actual_weight, Decimal("0.05")), "0.001"),
            "declared_value": _q(declared_value, "0.01"),
            "customs_assessed_value": _q(assessed_value, "0.01"),
            "real_name_verified": real_name_verified,
            "inspection_status": inspection_status,
            "risk_label": risk_label,
            "risk_pattern": risk_pattern,
        })
        item_count = 2 if idx % 3 == 0 else 1
        for seq in range(1, item_count + 1):
            is_danger_line = dangerous_type is not None and seq == 1
            items.append({
                "item_id": f"ITM{idx:04d}_{seq}",
                "shipment_id": shipment_id,
                "item_name": "充电电池组" if is_danger_line else ["服装", "书籍", "日用品"][idx % 3],
                "declared_category": "日用品" if is_danger_line else ["服装", "书籍", "日用品"][idx % 3],
                "actual_category": "锂电池" if is_danger_line else ["服装", "书籍", "日用品"][idx % 3],
                "quantity": 1 + idx % 3,
                "unit_value": _q(declared_value / item_count, "0.01"),
                "dangerous_declared": dangerous_declared,
                "detected_dangerous_type": dangerous_type if is_danger_line else None,
                "inspection_result": inspection_result if is_danger_line else "正常",
            })

    extras = [{
        "entity_type": "设备指纹",
        "entity_value": "DEV-BLACKLIST-DEMO",
        "reason": "演示：关联多起危险品瞒报",
        "source": "风险运营",
        "status": "启用",
        "expire_time": None,
        "create_time": ANCHOR,
    }]
    return users, addresses, shipments, items, extras


def _sql_value(value):
    if value is None:
        return "NULL"
    if isinstance(value, datetime):
        return f"'{value:%Y-%m-%d %H:%M:%S}'"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def render_sql(path: Path, seed: int = SEED) -> None:
    users, addresses, shipments, items, extras = build_rows(seed)
    tables = [
        ("user_info", users),
        ("address", addresses),
        ("shipment", shipments),
        ("shipment_item", items),
        ("blacklist_extra", extras),
    ]
    lines = ["-- 由 scripts/gen_business_data.py 生成，请勿手工维护。", "SET FOREIGN_KEY_CHECKS = 0;"]
    for table, rows in reversed(tables):
        lines.append(f"DELETE FROM `{table}`;")
    for table, rows in tables:
        if not rows:
            continue
        cols = list(rows[0].keys())
        lines.append(f"INSERT INTO `{table}` (`" + "`,`".join(cols) + "`) VALUES")
        values = ["(" + ",".join(_sql_value(row[col]) for col in cols) + ")" for row in rows]
        lines.append(",\n".join(values) + ";")
    lines.append("SET FOREIGN_KEY_CHECKS = 1;")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def load_database(seed: int = SEED) -> None:
    users, addresses, shipments, items, extras = build_rows(seed)
    async with AsyncSessionLocal() as db:
        for model in (BlacklistExtra, ShipmentItem, Shipment, Address, UserInfo):
            await db.execute(delete(model))
        for model, rows in (
            (UserInfo, users), (Address, addresses), (Shipment, shipments),
            (ShipmentItem, items), (BlacklistExtra, extras),
        ):
            await db.execute(insert(model), rows)
        await db.commit()
    print(f"业务数据完成: 用户={len(users)}, 地址={len(addresses)}, 运单={len(shipments)}, 明细={len(items)}")


def main():
    parser = argparse.ArgumentParser(description="生成物流风控业务数据")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--emit-sql", type=Path, help="输出初始化 SQL")
    parser.add_argument("--emit-only", action="store_true", help="只生成 SQL，不写数据库")
    args = parser.parse_args()
    if args.emit_sql:
        render_sql(args.emit_sql, args.seed)
        print(f"SQL 已生成: {args.emit_sql}")
    if not args.emit_only:
        async def _load_and_close():
            try:
                await load_database(args.seed)
            finally:
                await async_engine.dispose()
        asyncio.run(_load_and_close())


if __name__ == "__main__":
    main()

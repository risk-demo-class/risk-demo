"""
物流风控系统 - 业务数据生成脚本 (可重复运行)

生成 5 张业务表数据:
  user_info (30 用户, 含 5 个 RISK 高风险寄件人)
  address   (~50 收件地址)
  shipment  (~120 运单: 普通/跨境/代收货款)
  shipment_item (~250 物品明细, 含危险品)
  blacklist_extra (4 条扩展黑名单: 身份证号/寄件网点)

用法:
  python scripts/gen_business_data.py                 # 直接写库
  python scripts/gen_business_data.py --emit-sql sql/init_business_data.sql  # 只导出静态 SQL

注意: 写库前需要先跑 init_db.py 建好 5 张业务表 (或本脚本前先建库).
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

# 项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import Address, BlacklistExtra, Shipment, ShipmentItem, UserInfo  # noqa: E402


PROVINCES = ["广东省", "浙江省", "江苏省", "上海市", "北京市", "四川省", "湖北省", "山东省"]
CITIES = {
    "广东省": ["广州市", "深圳市", "东莞市"],
    "浙江省": ["杭州市", "宁波市", "温州市"],
    "江苏省": ["南京市", "苏州市", "无锡市"],
    "上海市": ["上海市"],
    "北京市": ["北京市"],
    "四川省": ["成都市", "绵阳市"],
    "湖北省": ["武汉市", "宜昌市"],
    "山东省": ["济南市", "青岛市"],
}
DISTRICTS = ["A区", "B区", "C区", "D区"]
STREETS = ["人民路1号", "建设路88号", "科技园3栋", "工业大道66号", "解放路12号", "大学城9栋"]
ITEM_NAMES = {
    "普通": ["日用品", "服装", "书籍", "食品", "数码配件", "玩具"],
    "电池": ["锂电池", "充电宝", "电动工具电池"],
    "液体": ["香水", "洗面奶", "饮料", "消毒液"],
    "化学品": ["油漆", "清洁剂", "农药", "化学试剂"],
}
COUNTRIES = ["美国", "日本", "德国", "澳大利亚", "英国", "韩国"]


def _shipment_id(i: int) -> str:
    return f"SH{20260800 + i:04d}"


def build_dataset(seed: int = 42):
    """构造全部业务数据, 返回 (users, addresses, shipments, items, blacklists)."""
    rng = random.Random(seed)
    now = datetime.now()

    users: list[dict] = []
    addresses: list[dict] = []
    shipments: list[dict] = []
    items: list[dict] = []

    # ---------- 普通用户 U0001-U0025 ----------
    normal_users = []
    for i in range(1, 26):
        uid = f"U{i:04d}"
        age = rng.randint(30, 900)
        real = 1 if rng.random() > 0.12 else 0
        users.append({
            "user_id": uid,
            "user_name": f"用户{i}",
            "phone": f"13{rng.randint(100000000, 999999999):09d}",
            "id_number_hash": f"IDH{uid}",
            "real_name_status": real,
            "company_name": f"公司{i}" if rng.random() < 0.2 else None,
            "account_age_days": age,
            "create_time": now - timedelta(days=age),
        })
        normal_users.append(uid)
        # 每个用户 1-2 个收件地址
        for a in range(rng.randint(1, 2)):
            prov = rng.choice(PROVINCES)
            addr_id = f"AD{uid}_{a}"
            addresses.append({
                "address_id": addr_id,
                "user_id": uid,
                "receiver_name": f"收件人{i}_{a}",
                "receiver_phone": f"15{rng.randint(100000000, 999999999):09d}",
                "province": prov,
                "city": rng.choice(CITIES[prov]),
                "district": rng.choice(DISTRICTS),
                "street": rng.choice(STREETS),
                "is_temp": 1 if rng.random() < 0.15 else 0,
                "use_count": rng.randint(1, 12),
                "create_time": now - timedelta(days=rng.randint(5, 400)),
            })

    # ---------- 高风险用户 RISK001-RISK005 ----------
    risk_users = []
    risk_profiles = [
        # (uid, name, 说明, 地址数)
        ("RISK001", "危险品瞒报者", 2),
        ("RISK002", "高频寄件者", 1),
        ("RISK003", "代收拒收者", 2),
        ("RISK004", "多地址夜猫子", 5),
        ("RISK005", "跨境虚报者", 2),
    ]
    for uid, name, addr_count in risk_profiles:
        users.append({
            "user_id": uid,
            "user_name": name,
            "phone": f"18{rng.randint(100000000, 999999999):09d}",
            "id_number_hash": f"IDH{uid}",
            "real_name_status": 1 if uid != "RISK001" else 0,
            "company_name": None,
            "account_age_days": rng.randint(3, 60),
            "create_time": now - timedelta(days=rng.randint(3, 60)),
        })
        risk_users.append(uid)
        for a in range(addr_count):
            prov = rng.choice(PROVINCES)
            addresses.append({
                "address_id": f"AD{uid}_{a}",
                "user_id": uid,
                "receiver_name": f"{name}收件{a}",
                "receiver_phone": f"18{rng.randint(100000000, 999999999):09d}",
                "province": prov,
                "city": rng.choice(CITIES[prov]),
                "district": rng.choice(DISTRICTS),
                "street": rng.choice(STREETS),
                "is_temp": 1 if uid == "RISK004" and a >= 3 else 0,
                "use_count": 0 if uid == "RISK004" else rng.randint(1, 8),
                "create_time": now - timedelta(days=rng.randint(1, 30)),
            })

    def user_address_ids(uid: str) -> list[str]:
        return [a["address_id"] for a in addresses if a["user_id"] == uid]

    # ---------- 运单 + 物品 ----------
    idx = 0
    shipment_seq = 0

    def add_shipment(uid, stype, days_ago, hour, weight, declared, cod,
                     declared_dangerous, delivered, rejected, status,
                     dest_prov=None, dest_city=None, country=None,
                     dangerous_ratio=0.0, item_count=None):
        nonlocal idx, shipment_seq
        shipment_seq += 1
        sid = _shipment_id(shipment_seq)
        addr_ids = user_address_ids(uid)
        if not addr_ids:
            return None
        addr_id = rng.choice(addr_ids)
        addr = next(a for a in addresses if a["address_id"] == addr_id)
        origin = rng.choice(PROVINCES)
        dp = dest_prov or rng.choice(PROVINCES)
        dc = dest_city or rng.choice(CITIES[dp])
        create = now - timedelta(days=days_ago, hours=24 - hour)
        shipments.append({
            "shipment_id": sid,
            "user_id": uid,
            "shipment_type": stype,
            "receiver_name": addr["receiver_name"],
            "receiver_phone": addr["receiver_phone"],
            "address_id": addr_id,
            "origin_province": origin,
            "dest_province": dp,
            "dest_city": dc,
            "dest_country": country,
            "weight_kg": weight,
            "declared_value": declared,
            "cod_amount": cod,
            "is_dangerous_declared": 1 if declared_dangerous else 0,
            "is_delivered": 1 if delivered else 0,
            "is_rejected": 1 if rejected else 0,
            "status": status,
            "create_time": create,
        })
        # 物品明细
        cnt = item_count or rng.randint(1, 3)
        for k in range(cnt):
            if rng.random() < dangerous_ratio:
                cat = rng.choice(["电池", "液体", "化学品"])
            else:
                cat = "普通"
            items.append({
                "shipment_id": sid,
                "item_name": rng.choice(ITEM_NAMES[cat]),
                "item_category": cat,
                "quantity": rng.randint(1, 5),
                "unit_weight": round(rng.uniform(0.3, 4.0), 2),
                "unit_price": round(rng.uniform(20, 800), 2),
            })
        idx += 1
        return sid

    # 普通用户: 每人 2-4 单 (近 30 天)
    for uid in normal_users:
        for _ in range(rng.randint(2, 4)):
            stype = rng.choices(["普通", "普通", "代收货款"], weights=[0.6, 0.2, 0.2])[0]
            add_shipment(
                uid, stype, days_ago=rng.randint(0, 30), hour=rng.randint(8, 22),
                weight=round(rng.uniform(0.5, 8), 2),
                declared=round(rng.uniform(30, 3000), 2),
                cod=round(rng.uniform(50, 2000), 2) if stype == "代收货款" else 0,
                declared_dangerous=False, delivered=rng.random() < 0.7,
                rejected=False, status=rng.choice(["待揽收", "运输中", "已签收"]),
                dangerous_ratio=0.05,
            )

    # RISK001: 危险品瞒报 (8 单, 全部含危险品但未申报)
    for k in range(8):
        add_shipment(
            "RISK001", "普通", days_ago=rng.randint(0, 20), hour=rng.randint(10, 20),
            weight=round(rng.uniform(2, 15), 2),
            declared=round(rng.uniform(100, 1000), 2), cod=0,
            declared_dangerous=False, delivered=rng.random() < 0.6, rejected=False,
            status=rng.choice(["已签收", "运输中", "待揽收"]),
            dangerous_ratio=1.0, item_count=2,
        )

    # RISK002: 高频寄件 (近 7 天 14 单)
    for k in range(14):
        add_shipment(
            "RISK002", "普通", days_ago=rng.randint(0, 6), hour=rng.randint(9, 23),
            weight=round(rng.uniform(0.5, 3), 2),
            declared=round(rng.uniform(50, 400), 2), cod=0,
            declared_dangerous=False, delivered=True, rejected=False,
            status="已签收", dangerous_ratio=0.0,
        )

    # RISK003: 代收拒收 (10 单 COD, 6 单拒收)
    for k in range(10):
        rejected = k < 6
        add_shipment(
            "RISK003", "代收货款", days_ago=rng.randint(0, 25), hour=rng.randint(9, 20),
            weight=round(rng.uniform(1, 5), 2),
            declared=round(rng.uniform(100, 800), 2),
            cod=round(rng.uniform(200, 4000), 2),
            declared_dangerous=False, delivered=True, rejected=rejected,
            status="拒收" if rejected else "已签收", dangerous_ratio=0.0,
        )

    # RISK004: 多地址 + 凌晨寄件 + 跨省 (10 单, 7 单夜间 0-5 点)
    for k in range(10):
        night = k < 7
        add_shipment(
            "RISK004", "普通", days_ago=rng.randint(0, 15),
            hour=rng.randint(0, 5) if night else rng.randint(10, 20),
            weight=round(rng.uniform(0.3, 4), 2),
            declared=round(rng.uniform(50, 600), 2), cod=0,
            declared_dangerous=False, delivered=rng.random() < 0.5, rejected=False,
            status=rng.choice(["已签收", "运输中"]),
            dangerous_ratio=0.1,
        )

    # RISK005: 跨境价值虚报 (6 单, 申报 <= 100 但重量 >= 5kg)
    for k in range(6):
        add_shipment(
            "RISK005", "跨境", days_ago=rng.randint(0, 25), hour=rng.randint(8, 18),
            weight=round(rng.uniform(5, 12), 2),
            declared=round(rng.uniform(30, 95), 2), cod=0,
            declared_dangerous=False, delivered=rng.random() < 0.6, rejected=False,
            status=rng.choice(["运输中", "已签收"]),
            country=rng.choice(COUNTRIES), dangerous_ratio=0.0,
        )

    # ---------- 扩展黑名单 ----------
    # 故意用两个普通用户 (U0005/U0007) 的身份证号, 演示撞黑前置拦截,
    # 同时不把 RISK 高风险画像送进黑名单 (他们的欺诈模式要留给规则/模型去抓)
    blacklists = [
        {"blacklist_type": "身份证号", "blacklist_value": "IDHU0005",
         "reason": "涉假寄递关联", "expire_time": None},
        {"blacklist_type": "身份证号", "blacklist_value": "IDHU0007",
         "reason": "涉毒包裹关联", "expire_time": None},
        {"blacklist_type": "寄件网点", "blacklist_value": "STATION_888",
         "reason": "涉假网点", "expire_time": None},
        {"blacklist_type": "寄件网点", "blacklist_value": "STATION_666",
         "reason": "涉毒包裹关联", "expire_time": now + timedelta(days=30)},
    ]

    return users, addresses, shipments, items, blacklists


def _sql_str(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, datetime):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
    return "'" + str(v).replace("'", "''") + "'"


def emit_sql(users, addresses, shipments, items, blacklists, path: str) -> None:
    """把内存数据导出成静态 SQL 文件 (供 init_db / Docker 自动初始化用)."""
    lines = [
        "-- ============================================",
        "-- 物流风控系统 - 业务测试数据 (由 scripts/gen_business_data.py 生成)",
        f"-- 生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
        "-- ============================================",
        "",
        f"INSERT INTO `user_info` (`user_id`,`user_name`,`phone`,`id_number_hash`,`real_name_status`,`company_name`,`account_age_days`,`create_time`) VALUES",
    ]
    for u in users:
        lines.append(
            "(" + ",".join(_sql_str(u[k]) for k in
                           ["user_id", "user_name", "phone", "id_number_hash",
                            "real_name_status", "company_name", "account_age_days", "create_time"]) + "),"
        )
    lines[-1] = lines[-1][:-1] + ";"
    lines.append("")
    lines.append("INSERT INTO `address` (`address_id`,`user_id`,`receiver_name`,`receiver_phone`,`province`,`city`,`district`,`street`,`is_temp`,`use_count`,`create_time`) VALUES")
    for a in addresses:
        lines.append(
            "(" + ",".join(_sql_str(a[k]) for k in
                           ["address_id", "user_id", "receiver_name", "receiver_phone",
                            "province", "city", "district", "street", "is_temp", "use_count", "create_time"]) + "),"
        )
    lines[-1] = lines[-1][:-1] + ";"
    lines.append("")
    lines.append("INSERT INTO `shipment` (`shipment_id`,`user_id`,`shipment_type`,`receiver_name`,`receiver_phone`,`address_id`,`origin_province`,`dest_province`,`dest_city`,`dest_country`,`weight_kg`,`declared_value`,`cod_amount`,`is_dangerous_declared`,`is_delivered`,`is_rejected`,`status`,`create_time`) VALUES")
    for s in shipments:
        lines.append(
            "(" + ",".join(_sql_str(s[k]) for k in
                           ["shipment_id", "user_id", "shipment_type", "receiver_name",
                            "receiver_phone", "address_id", "origin_province", "dest_province",
                            "dest_city", "dest_country", "weight_kg", "declared_value",
                            "cod_amount", "is_dangerous_declared", "is_delivered", "is_rejected",
                            "status", "create_time"]) + "),"
        )
    lines[-1] = lines[-1][:-1] + ";"
    lines.append("")
    lines.append("INSERT INTO `shipment_item` (`shipment_id`,`item_name`,`item_category`,`quantity`,`unit_weight`,`unit_price`) VALUES")
    for it in items:
        lines.append(
            "(" + ",".join(_sql_str(it[k]) for k in
                           ["shipment_id", "item_name", "item_category", "quantity", "unit_weight", "unit_price"]) + "),"
        )
    lines[-1] = lines[-1][:-1] + ";"
    lines.append("")
    lines.append("INSERT INTO `blacklist_extra` (`blacklist_type`,`blacklist_value`,`reason`,`expire_time`) VALUES")
    for b in blacklists:
        lines.append(
            "(" + ",".join(_sql_str(b[k]) for k in
                           ["blacklist_type", "blacklist_value", "reason", "expire_time"]) + "),"
        )
    lines[-1] = lines[-1][:-1] + ";"

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"SQL 已导出: {path}")


async def insert_db(users, addresses, shipments, items, blacklists) -> None:
    """把数据写进 MySQL (幂等: 先清空 5 张业务表)."""
    from sqlalchemy import delete
    async with AsyncSessionLocal() as db:
        for model in (BlacklistExtra, ShipmentItem, Shipment, Address, UserInfo):
            await db.execute(delete(model))
        db.add_all([UserInfo(**u) for u in users])
        db.add_all([Address(**a) for a in addresses])
        db.add_all([Shipment(**s) for s in shipments])
        db.add_all([ShipmentItem(**it) for it in items])
        db.add_all([BlacklistExtra(**b) for b in blacklists])
        await db.commit()
    print(f"写库完成: 用户 {len(users)}, 地址 {len(addresses)}, 运单 {len(shipments)}, "
          f"物品 {len(items)}, 扩展黑名单 {len(blacklists)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="物流风控系统 - 业务数据生成")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42, 保证可复现)")
    parser.add_argument("--emit-sql", type=str, default=None,
                        help="只导出静态 SQL 文件路径 (不写库)")
    args = parser.parse_args()

    users, addresses, shipments, items, blacklists = build_dataset(args.seed)
    if args.emit_sql:
        emit_sql(users, addresses, shipments, items, blacklists, args.emit_sql)
        return
    asyncio.run(insert_db(users, addresses, shipments, items, blacklists))


if __name__ == "__main__":
    main()

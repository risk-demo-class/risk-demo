"""
二手交易平台物流侧风控系统 - 高风险卖家数据生成 (异步).
生成 RISK 前缀的高风险卖家及其高风险运单, 用于触发 L001-L030 规则造正例.

5 种风险模式轮换生成:
  模式 1: 空包/轻包高价值 (触发 L001/L002 → 人工审核)
  模式 2: 高保价运单 (触发 L030 → 标记, 可组合其他规则)
  模式 3: 高纠纷/高投诉卖家 (触发纠纷/投诉规则)
  模式 4: 序列号重复/一物多卖 (触发 L028 → 人工审核)
  模式 5: 高退货率买家 (触发 L017 → 拒绝)

例:
  python scripts/gen_risky_users.py                # 默认 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 × 5 模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成

配合训练:
  python scripts/gen_risk_data_with_dates.py --days 10 --per-day 200 --clean --force-pos-ratio 0.5
  python scripts/train_xgb_model.py
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


RISK_MODES = ["空包/轻包高价值", "高保价运单", "高纠纷卖家", "序列号重复", "高退货率买家"]

CATEGORIES_HV = ["手机", "电脑", "相机", "奢侈品", "平板"]


async def _gen_empty_pkg_shipper(conn, shipper_id: str):
    """模式 1: 空包/轻包高价值卖家. 造 5 个运单 cargo_weight∈[0.02,0.15], 触发 L001/L002."""
    now = datetime.now()
    for i in range(1, 6):
        wid = f"RISK{shipper_id[4:]}{i:03d}" if shipper_id.startswith("RISK") else f"RSK{shipper_id[3:]}{i:03d}"
        cat = random.choice(CATEGORIES_HV)
        weight = round(random.uniform(0.02, 0.15), 2)
        declared = round(random.uniform(2000, 8000), 2)
        ct = now - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
        await conn.execute(text("""
            INSERT IGNORE INTO waybill_info
            (waybill_id, create_time, pickup_time, delivered_time, complete_time, segment,
             shipper_id, consignee_id, carrier_id, waybill_status,
             cargo_category, cargo_weight, cargo_volume, cargo_quantity, declared_value,
             freight_amount, cod_amount, insurance_amount, insurance_premium,
             is_night_order, is_urgent, cargo_type, is_cross_border)
            VALUES (:wid, :ct, :pt, NULL, NULL, 'B',
                    :sid, :cid, 'CAR0001', '已签收',
                    :cat, :wt, 0.001, 1, :dv,
                    15, 0, 0, 0,
                    :night, 0, '普通', 0)
        """), {
            "wid": wid, "ct": ct, "pt": ct + timedelta(hours=random.randint(1, 6)),
            "sid": shipper_id, "cid": f"CG{random.randint(1, 8):04d}",
            "cat": cat, "wt": weight, "dv": declared, "night": 1 if ct.hour < 6 else 0,
        })


async def _gen_high_insurance_shipper(conn, shipper_id: str):
    """模式 2: 高保价运单卖家. 造 5 个运单 insurance_amount≥5000, 触发 L030."""
    now = datetime.now()
    for i in range(1, 6):
        wid = f"RISK{shipper_id[4:]}{i:03d}" if shipper_id.startswith("RISK") else f"RSK{shipper_id[3:]}{i:03d}"
        cat = random.choice(CATEGORIES_HV)
        declared = round(random.uniform(5000, 20000), 2)
        ins = round(declared * random.uniform(0.8, 1.0), 2)
        ct = now - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
        await conn.execute(text("""
            INSERT IGNORE INTO waybill_info
            (waybill_id, create_time, pickup_time, segment,
             shipper_id, consignee_id, carrier_id, waybill_status,
             cargo_category, cargo_weight, cargo_volume, cargo_quantity, declared_value,
             freight_amount, cod_amount, insurance_amount, insurance_premium,
             is_night_order, is_urgent, cargo_type, is_cross_border)
            VALUES (:wid, :ct, :pt, 'B',
                    :sid, :cid, 'CAR0001', '运输中',
                    :cat, 0.5, 0.003, 1, :dv,
                    20, 0, :ins, :prem,
                    0, 0, '普通', 0)
        """), {
            "wid": wid, "ct": ct, "pt": ct + timedelta(hours=random.randint(1, 6)),
            "sid": shipper_id, "cid": f"CG{random.randint(1, 8):04d}",
            "cat": cat, "dv": declared, "ins": ins, "prem": round(ins * 0.003, 2),
        })


async def _gen_high_dispute_shipper(conn, shipper_id: str):
    """模式 3: 高纠纷/高投诉卖家. shipper_info 标记高纠纷+造投诉记录."""
    now = datetime.now()
    # 更新卖家画像
    await conn.execute(text("""
        UPDATE shipper_info SET dispute_count = :dc, complaint_total = :cc
        WHERE shipper_id = :sid
    """), {"sid": shipper_id, "dc": random.randint(5, 15), "cc": random.randint(3, 10)})
    # 造 3 个正常运单 + 各配一条投诉
    for i in range(1, 4):
        wid = f"RISK{shipper_id[4:]}{i:03d}" if shipper_id.startswith("RISK") else f"RSK{shipper_id[3:]}{i:03d}"
        ct = now - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
        await conn.execute(text("""
            INSERT IGNORE INTO waybill_info
            (waybill_id, create_time, pickup_time, delivered_time, segment,
             shipper_id, consignee_id, carrier_id, waybill_status,
             cargo_category, cargo_weight, cargo_volume, cargo_quantity, declared_value,
             freight_amount, cod_amount, insurance_amount, insurance_premium,
             is_night_order, is_urgent, cargo_type, is_cross_border)
            VALUES (:wid, :ct, :pt, :dt, 'B',
                    :sid, :cid, 'CAR0001', '已签收',
                    :cat, 0.5, 0.003, 1, :dv,
                    15, 0, 0, 0, 0, 0, '普通', 0)
        """), {
            "wid": wid, "ct": ct, "pt": ct + timedelta(hours=2),
            "dt": ct + timedelta(days=random.randint(2, 5)),
            "sid": shipper_id, "cid": f"CG{random.randint(1, 8):04d}",
            "cat": random.choice(CATEGORIES_HV), "dv": round(random.uniform(1000, 5000), 2),
        })
        # 投诉
        await conn.execute(text("""
            INSERT IGNORE INTO complaint_claim
            (claim_id, waybill_id, claimant, claim_type, claim_amount, claim_reason, claim_status, create_time)
            VALUES (:clid, :wid, :clm, :cty, :amt, :rsn, '待处理', :ct)
        """), {
            "clid": f"CLM{wid[4:]}", "wid": wid, "clm": random.choice(["买家", "卖家"]),
            "cty": random.choice(["成色不符", "调包投诉", "未收到"]),
            "amt": round(random.uniform(500, 3000), 2),
            "rsn": "怀疑物流途中被调包",
            "ct": ct + timedelta(days=random.randint(5, 10)),
        })


async def _gen_imei_dup_shipper(conn, shipper_id: str):
    """模式 4: 序列号重复卖家. 同一 IMEI 出现在 3 个运单, 触发 L028."""
    now = datetime.now()
    shared_imei = "35" + f"{random.randint(10**12, 10**13 - 1)}"
    brand = random.choice(["Apple", "华为", "小米"])
    model = random.choice(["iPhone 14", "Mate 60 Pro", "14 Pro"])
    for i in range(1, 4):
        wid = f"RISK{shipper_id[4:]}{i:03d}" if shipper_id.startswith("RISK") else f"RSK{shipper_id[3:]}{i:03d}"
        ct = now - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
        await conn.execute(text("""
            INSERT IGNORE INTO waybill_info
            (waybill_id, create_time, pickup_time, segment,
             shipper_id, consignee_id, carrier_id, waybill_status,
             cargo_category, cargo_weight, cargo_volume, cargo_quantity, declared_value,
             freight_amount, cod_amount, insurance_amount, insurance_premium,
             is_night_order, is_urgent, cargo_type, is_cross_border)
            VALUES (:wid, :ct, :pt, 'B',
                    :sid, :cid, 'CAR0001', '已签收',
                    :cat, 0.4, 0.002, 1, :dv,
                    12, 0, 0, 0, 0, 0, '普通', 0)
        """), {
            "wid": wid, "ct": ct, "pt": ct + timedelta(hours=2),
            "sid": shipper_id, "cid": f"CG{random.randint(1, 8):04d}",
            "cat": "手机", "dv": round(random.uniform(2000, 5000), 2),
        })
        # 明细共用 IMEI
        await conn.execute(text("""
            INSERT IGNORE INTO waybill_detail
            (detail_id, waybill_id, item_imei, cargo_name, item_brand, item_model,
             item_grade, cargo_category, cargo_weight, cargo_volume, cargo_quantity, declared_value)
            VALUES (:did, :wid, :imei, :cn, :brd, :mdl,
                    '良', '手机', 0.4, 0.002, 1, :dv)
        """), {
            "did": f"DT{wid[4:]}{i:02d}", "wid": wid, "imei": shared_imei,
            "cn": f"{brand} {model}", "brd": brand, "mdl": model, "dv": round(random.uniform(2000, 5000), 2),
        })
        # 商品身份
        await conn.execute(text("""
            INSERT IGNORE INTO item_identity
            (item_id, item_imei, item_brand, item_model, cargo_category,
             declared_grade, inspected_grade, return_grade, waybill_id, status, create_time)
            VALUES (:iid, :imei, :brd, :mdl, '手机',
                    '优', '良', NULL, :wid, '在途', :ct)
        """), {
            "iid": f"II{wid[4:]}{i:02d}", "imei": shared_imei,
            "brd": brand, "mdl": model, "wid": wid, "ct": ct,
        })


async def _gen_high_return_buyer(conn, shipper_id: str):
    """模式 5: 高退货率买家. 更新买家 return_rate≥0.8 触发 L017 拒绝."""
    now = datetime.now()
    cid = f"CG{random.randint(9, 20):04d}"
    # 如果买家不存在就先创建
    await conn.execute(text("""
        INSERT IGNORE INTO consignee_info
        (consignee_id, consignee_name, consignee_phone, consignee_province,
         consignee_city, consignee_district, consignee_street)
        VALUES (:cid, '高风险买家', '13900009999', '广东', '广州市', '天河区', '珠江新城花城大道66号')
    """), {"cid": cid})
    # 更新退货率 (触发 L017: buyer_return_rate ≥ 0.8 → 拒绝)
    await conn.execute(text("""
        UPDATE consignee_info SET return_count = :rc, return_rate = :rr
        WHERE consignee_id = :cid
    """), {"cid": cid, "rc": random.randint(8, 20), "rr": round(random.uniform(0.8, 1.0), 4)})
    # 造 3 个运单关联该买家
    for i in range(1, 4):
        wid = f"RISK{shipper_id[4:]}{i:03d}" if shipper_id.startswith("RISK") else f"RSK{shipper_id[3:]}{i:03d}"
        ct = now - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
        await conn.execute(text("""
            INSERT IGNORE INTO waybill_info
            (waybill_id, create_time, pickup_time, delivered_time, segment,
             shipper_id, consignee_id, carrier_id, waybill_status,
             cargo_category, cargo_weight, cargo_volume, cargo_quantity, declared_value,
             freight_amount, cod_amount, insurance_amount, insurance_premium,
             is_night_order, is_urgent, cargo_type, is_cross_border)
            VALUES (:wid, :ct, :pt, :dt, 'B',
                    :sid, :cid, 'CAR0001', '已签收',
                    :cat, 0.5, 0.003, 1, :dv,
                    15, 0, 0, 0, 0, 0, '普通', 0)
        """), {
            "wid": wid, "ct": ct, "pt": ct + timedelta(hours=2),
            "dt": ct + timedelta(days=random.randint(2, 7)),
            "sid": shipper_id, "cid": cid,
            "cat": random.choice(CATEGORIES_HV), "dv": round(random.uniform(1000, 8000), 2),
        })


MODE_GENERATORS = [
    _gen_empty_pkg_shipper,      # 模式 0: 空包/轻包高价值
    _gen_high_insurance_shipper, # 模式 1: 高保价运单
    _gen_high_dispute_shipper,   # 模式 2: 高纠纷卖家
    _gen_imei_dup_shipper,       # 模式 3: 序列号重复
    _gen_high_return_buyer,      # 模式 4: 高退货率买家
]


async def gen_risky_users(count: int = 5, reset: bool = False):
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url, echo=False)

    print(f"生成 {count} 个高风险卖家 ({count//5 + (1 if count%5 else 0)} 套 × 5 模式)")
    print(f"模式: {', '.join(RISK_MODES)}")

    if reset:
        print("--reset 模式: 清理旧 RISK 数据...")
        async with engine.begin() as conn:
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            # 清空 RISK 卖家相关的运单/明细/商品身份
            await conn.execute(text("DELETE FROM complaint_claim WHERE waybill_id IN (SELECT waybill_id FROM waybill_info WHERE shipper_id LIKE 'RISK%')"))
            await conn.execute(text("DELETE FROM tracking_event WHERE waybill_id IN (SELECT waybill_id FROM waybill_info WHERE shipper_id LIKE 'RISK%')"))
            await conn.execute(text("DELETE FROM inspection_record WHERE waybill_id IN (SELECT waybill_id FROM waybill_info WHERE shipper_id LIKE 'RISK%')"))
            await conn.execute(text("DELETE FROM item_identity WHERE waybill_id IN (SELECT waybill_id FROM waybill_info WHERE shipper_id LIKE 'RISK%')"))
            await conn.execute(text("DELETE FROM waybill_detail WHERE waybill_id IN (SELECT waybill_id FROM waybill_info WHERE shipper_id LIKE 'RISK%')"))
            await conn.execute(text("DELETE FROM waybill_info WHERE shipper_id LIKE 'RISK%'"))
            await conn.execute(text("DELETE FROM shipper_info WHERE shipper_id LIKE 'RISK%'"))
            await conn.execute(text("UPDATE consignee_info SET return_count=0, return_rate=0, sign_count=0"))
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        print("  清空完成")

    now = datetime.now()
    for idx in range(count):
        mode_idx = idx % 5
        user_id = f"RISK{idx+1:04d}"
        async with engine.begin() as conn:
            # 创建卖家
            prov = random.choice(["北京", "上海", "广东", "浙江", "江苏", "四川"])
            _ADDR_MAP = {
                "北京": ("朝阳区", "建国路88号"), "上海": ("浦东新区", "张江路200号"),
                "广东": ("天河区", "体育西路100号"), "浙江": ("西湖区", "文三路500号"),
                "江苏": ("鼓楼区", "中山北路60号"), "四川": ("锦江区", "春熙路120号"),
            }
            _dist, _street = _ADDR_MAP.get(prov, ("海淀区", "中关村大街1号"))
            await conn.execute(text("""
                INSERT IGNORE INTO shipper_info
                (shipper_id, shipper_name, shipper_phone, shipper_id_card,
                 shipper_province, shipper_city, shipper_district, shipper_street, register_time)
                VALUES (:uid, :nm, :ph, :idc, :prov, :city, :dist, :street, :rt)
            """), {
                "uid": user_id, "nm": f"高风险卖家{idx+1}",
                "ph": f"138{idx+1:08d}",
                "idc": f"11010119900101{idx+1:04d}",
                "prov": prov, "city": prov + "市" if prov in ["北京","上海"] else prov + "州市",
                "dist": _dist, "street": _street,
                "rt": now - timedelta(days=random.randint(30, 365)),
            })
            # 生成对应模式的数据
            gen_func = MODE_GENERATORS[mode_idx]
            await gen_func(conn, user_id)
        print(f"  [{user_id}] 模式 {mode_idx+1}: {RISK_MODES[mode_idx]}")

    # 统计
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT COUNT(*) FROM shipper_info WHERE shipper_id LIKE 'RISK%'"))
        cnt = r.scalar() or 0
        r = await conn.execute(text("SELECT COUNT(*) FROM waybill_info WHERE shipper_id LIKE 'RISK%'"))
        wbc = r.scalar() or 0
    print(f"\n完成! RISK 卖家: {cnt} 个, RISK 运单: {wbc} 条")
    print(f"\n下一步: python scripts/gen_risk_data_with_dates.py --days 10 --per-day 200 --clean --force-pos-ratio 0.5")
    print(f"然后:   python scripts/train_xgb_model.py")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成高风险卖家测试数据 (RISK001-RISKn)")
    parser.add_argument("--count", type=int, default=5, help="生成卖家数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 数据再生成")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
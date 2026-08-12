"""
物流风控系统 - 生成 RISK 高风险寄件人样本 (异步)

5 种物流风险模式轮换生成:
  模式 1: 高频寄件 (55 票近 30 天, 含凌晨揽收)
  模式 2: 危险品瞒报 (电池/化学品, 低申报价值)
  模式 3: 跨境异常 (25 票跨境 + 报关, 高价值重量比)
  模式 4: 多地址/共用地址 (7 收件人 + 7 地址, 偏远/临时/共用)
  模式 5: COD拒收 + 实名异常 (未实名 + 高拒收)

用法:
  python scripts/gen_logistics_risky_senders.py                 # 默认 5 个
  python scripts/gen_logistics_risky_senders.py --count 30      # 30 个 (6 套 × 5 模式)
  python scripts/gen_logistics_risky_senders.py --reset         # 先删旧 RISK 数据再生成
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import async_engine

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


RISK_MODES = ["高频寄件", "危险品瞒报", "跨境异常", "多地址", "COD拒收"]


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def _insert_operator(conn) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_operator
        (operator_id, operator_name, phone, network_id, network_name, is_internal, status, create_time, update_time)
        VALUES ('OPR_RISK01', '风控测试快递员', '13800000001', 'NET_RISK', '风控测试网点', 1, '正常', NOW(), NOW())
    """))


async def _insert_sender(conn, sid: str, name: str, verified: int, fail_count: int) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_sender
        (sender_id, sender_name, sender_phone, is_real_name_verified, verify_time, verify_fail_count, create_time, update_time)
        VALUES (:sid, :name, :phone, :verified, :vt, :fc, NOW(), NOW())
    """), {
        "sid": sid, "name": name, "phone": f"138{sid[-3:]:0>8}",
        "verified": verified,
        "vt": _fmt(datetime.now() - timedelta(days=10)) if verified else None,
        "fc": fail_count,
    })


async def _insert_recipient(conn, rid: str, name: str, phone: str) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_recipient
        (recipient_id, recipient_name, recipient_phone, is_real_name_verified, verify_time, verify_fail_count, create_time, update_time)
        VALUES (:rid, :name, :phone, 1, NOW(), 0, NOW(), NOW())
    """), {"rid": rid, "name": name, "phone": phone})


async def _insert_address(conn, aid: str, rid: str, prov: str, city: str, dist: str,
                          street: str, remote: int = 0, temp: int = 0, use_count: int = 1) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_address
        (address_id, recipient_id, province, city, district, street_address, address_key, is_remote, is_temp, use_count, create_time, update_time)
        VALUES (:aid, :rid, :prov, :city, :dist, :street, :key, :remote, :temp, :use_count, NOW(), NOW())
    """), {
        "aid": aid, "rid": rid, "prov": prov, "city": city, "dist": dist,
        "street": street, "key": f"{prov}{city}{dist}{street}",
        "remote": remote, "temp": temp, "use_count": use_count,
    })


async def _insert_waybill(
    conn, wb: str, sid: str, rid: str, aid: str, item_name: str, category: str,
    value: float, weight: float, cod: float = 0, cross: int = 0,
    status: str = "已签收", create: datetime = None,
    pickup: datetime = None, sign: datetime = None,
) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_waybill
        (waybill_no, sender_id, recipient_id, address_id, operator_id, item_name, item_category,
         declared_value, weight_kg, volume_cm3, insured_amount, freight_amount, payment_method,
         cod_amount, is_cross_border, status, create_time, pickup_time, sign_time, update_time)
        VALUES (:wb, :sid, :rid, :aid, 'OPR_RISK01', :name, :cat, :value, :weight, 1000,
                :insured, :freight, '寄付', :cod, :cross, :status, :ct, :pt, :st, NOW())
    """), {
        "wb": wb, "sid": sid, "rid": rid, "aid": aid, "name": item_name, "cat": category,
        "value": round(value, 2), "weight": round(weight, 2),
        "insured": round(value * 0.2, 2), "freight": 20,
        "cod": round(cod, 2), "cross": cross, "status": status,
        "ct": _fmt(create) if create else _fmt(datetime.now()),
        "pt": _fmt(pickup) if pickup else None,
        "st": _fmt(sign) if sign else None,
    })


async def _insert_event(conn, eid: str, wb: str, sid: str, rid: str, event_type: str,
                        event_time: datetime, location: str) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_event_record
        (event_id, waybill_no, sender_id, recipient_id, operator_id, event_type, event_time, location, create_time)
        VALUES (:eid, :wb, :sid, :rid, 'OPR_RISK01', :et, :t, :loc, NOW())
    """), {
        "eid": eid, "wb": wb, "sid": sid, "rid": rid,
        "et": event_type, "t": _fmt(event_time), "loc": location,
    })


async def _insert_cod(conn, cod_id: str, wb: str, amount: float, status: str,
                      reject_time: datetime = None, collect_time: datetime = None) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_cod_settlement
        (cod_id, waybill_no, cod_amount, collect_status, collect_time, reject_time, create_time, update_time)
        VALUES (:cid, :wb, :amt, :status, :ct, :rt, NOW(), NOW())
    """), {
        "cid": cod_id, "wb": wb, "amt": round(amount, 2), "status": status,
        "ct": _fmt(collect_time) if collect_time else None,
        "rt": _fmt(reject_time) if reject_time else None,
    })


async def _insert_abnormal(conn, abn_id: str, wb: str, abn_type: str,
                           abn_time: datetime, desc: str) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_abnormal_record
        (abnormal_id, waybill_no, abnormal_type, abnormal_time, description, handle_status, create_time, update_time)
        VALUES (:aid, :wb, :at, :t, :desc, '已核实', NOW(), NOW())
    """), {"aid": abn_id, "wb": wb, "at": abn_type, "t": _fmt(abn_time), "desc": desc})


async def _insert_customs(conn, cus_id: str, wb: str, trade_mode: str, hs: str,
                          value: float, dest: str, status: str) -> None:
    await conn.execute(text("""
        INSERT IGNORE INTO logistics_customs_info
        (customs_id, waybill_no, order_no, payment_no, manifest_no, trade_mode, hs_code,
         declared_value, currency, origin_country, destination_country, customs_status, create_time, update_time)
        VALUES (:cid, :wb, :on, :pn, :mn, :tm, :hs, :val, 'CNY', '中国', :dest, :status, NOW(), NOW())
    """), {
        "cid": cus_id, "wb": wb, "on": f"ORD{wb}", "pn": f"PAY{wb}", "mn": f"MAN{cus_id}",
        "tm": trade_mode, "hs": hs, "val": round(value, 2), "dest": dest, "status": status,
    })


async def _gen_high_freq(conn, sid: str, rid: str, aid: str) -> None:
    """模式 1: 高频寄件, 55 票近 30 天, 含 6 次凌晨揽收."""
    base = datetime.now() - timedelta(days=29)
    for i in range(1, 56):
        ct = base + timedelta(days=i % 28, hours=(2 if i % 9 == 0 else random.randint(8, 20)),
                              minutes=random.randint(0, 59))
        pt = ct + timedelta(hours=1)
        st = pt + timedelta(days=2)
        wb = f"WB_RISK{sid[-3:]}_{i:03d}"
        await _insert_waybill(conn, wb, sid, rid, aid, "普通商品", "普通",
                              random.uniform(100, 800), random.uniform(1, 3),
                              status="已签收", create=ct, pickup=pt, sign=st)
        await _insert_event(conn, f"LEVT_{wb}_1", wb, sid, rid, "寄件下单", ct, "寄件网点")
        await _insert_event(conn, f"LEVT_{wb}_2", wb, sid, rid, "揽收", pt, "揽收网点")
        await _insert_event(conn, f"LEVT_{wb}_3", wb, sid, rid, "签收", st, "收件地址")


async def _gen_dangerous(conn, sid: str, rid: str, aid: str) -> None:
    """模式 2: 危险品瞒报, 12 票电池/化学品."""
    for i in range(1, 13):
        ct = datetime.now() - timedelta(days=random.randint(1, 20))
        pt = ct + timedelta(hours=1)
        wb = f"WB_RISK{sid[-3:]}_{i:03d}"
        cat = "电池" if i % 2 else "化学品"
        await _insert_waybill(conn, wb, sid, rid, aid, f"{cat}样品", cat,
                              random.uniform(50, 300), random.uniform(0.5, 2),
                              status="已签收", create=ct, pickup=pt,
                              sign=pt + timedelta(days=2))
        await _insert_event(conn, f"LEVT_{wb}_1", wb, sid, rid, "寄件下单", ct, "寄件网点")
        await _insert_event(conn, f"LEVT_{wb}_2", wb, sid, rid, "揽收", pt, "揽收网点")
        await _insert_abnormal(conn, f"ABN_{wb}", wb, "危险品瞒报",
                               ct + timedelta(hours=2), f"{cat}申报价值明显偏低")


async def _gen_cross_border(conn, sid: str, rid: str, aid: str) -> None:
    """模式 3: 跨境异常, 25 票跨境件 + 报关."""
    for i in range(1, 26):
        ct = datetime.now() - timedelta(days=random.randint(1, 30))
        pt = ct + timedelta(days=1)
        wb = f"WB_RISK{sid[-3:]}_{i:03d}"
        value = random.uniform(2000, 5000)
        weight = random.uniform(0.5, 1.5)
        status = random.choice(["已签收", "清关中"])
        await _insert_waybill(conn, wb, sid, rid, aid, "跨境商品", "电子产品",
                              value, weight, cross=1, status=status,
                              create=ct, pickup=pt,
                              sign=pt + timedelta(days=3) if status == "已签收" else None)
        await _insert_event(conn, f"LEVT_{wb}_1", wb, sid, rid, "寄件下单", ct, "寄件网点")
        await _insert_event(conn, f"LEVT_{wb}_2", wb, sid, rid, "揽收", pt, "揽收网点")
        await _insert_event(conn, f"LEVT_{wb}_3", wb, sid, rid, "报关清关",
                            pt + timedelta(days=1), "目的国清关")
        customs_status = random.choice(["已放行", "查验异常"])
        await _insert_customs(conn, f"CUS_{wb}", wb, random.choice(["9610", "9710", "1210"]),
                              random.choice(["85076000", "84713000"]), value,
                              random.choice(["美国", "德国", "日本"]), customs_status)
        if customs_status == "查验异常":
            await _insert_abnormal(conn, f"ABN_{wb}", wb, "清关异常",
                                   pt + timedelta(days=1), "目的国查验异常")
        elif i % 3 == 0:
            await _insert_abnormal(conn, f"ABN_{wb}", wb, "重量价值异常",
                                   ct, "跨境包裹价值/重量比异常")


async def _gen_multi_addr(conn, sid: str, rid: str, aid: str) -> None:
    """模式 4: 7 收件人 + 7 地址, 偏远/临时/共用."""
    provinces = ['广东', '上海', '北京', '浙江', '江苏', '四川', '湖北']
    cities = ['广州市', '上海市', '北京市', '杭州市', '南京市', '成都市', '武汉市']
    districts = ['天河区', '浦东新区', '朝阳区', '西湖区', '鼓楼区', '锦江区', '武昌区']
    rids = []
    aids = []
    for j in range(7):
        rid = f"RISKRCP{sid[-3:]}_{j}"
        aid = f"RISKADR{sid[-3:]}_{j}"
        rids.append(rid)
        aids.append(aid)
        await _insert_recipient(conn, rid, f"收件人{j}", f"139{int(sid[-3:]):06d}{j:02d}")
        # 前两个地址共用同一地址键, 制造"多人共用地址"
        street = "共用街道1号" if j < 2 else f"测试街道{j}号"
        remote = 1 if j in (5, 6) else 0
        temp = 1 if j in (2, 3, 4) else 0
        await _insert_address(conn, aid, rid, provinces[j], cities[j], districts[j],
                              street, remote=remote, temp=temp, use_count=random.randint(2, 10))
    for i in range(1, 21):
        j = i % 7
        ct = datetime.now() - timedelta(days=random.randint(1, 25))
        pt = ct + timedelta(hours=1)
        wb = f"WB_RISK{sid[-3:]}_{i:03d}"
        status = random.choice(["已签收", "拒收", "退回"])
        await _insert_waybill(conn, wb, sid, rids[j], aids[j], "普通商品", "普通",
                              random.uniform(100, 600), random.uniform(1, 3),
                              status=status, create=ct, pickup=pt,
                              sign=pt + timedelta(days=2) if status == "已签收" else None)
        await _insert_event(conn, f"LEVT_{wb}_1", wb, sid, rids[j], "寄件下单", ct, "寄件网点")
        await _insert_event(conn, f"LEVT_{wb}_2", wb, sid, rids[j], "揽收", pt, "揽收网点")
        if status == "拒收":
            await _insert_event(conn, f"LEVT_{wb}_3", wb, sid, rids[j], "拒收",
                                pt + timedelta(days=1), "收件地址")
        elif status == "退回":
            await _insert_event(conn, f"LEVT_{wb}_3", wb, sid, rids[j], "退回",
                                pt + timedelta(days=1), "寄件网点")
        if i % 4 == 0:
            await _insert_abnormal(conn, f"ABN_{wb}", wb, "地址异常", ct,
                                   "偏远/临时/共用地址组合异常")


async def _gen_cod_reject(conn, sid: str, rid: str, aid: str) -> None:
    """模式 5: COD 拒收 + 实名异常."""
    for i in range(1, 21):
        ct = datetime.now() - timedelta(days=random.randint(1, 20))
        pt = ct + timedelta(hours=1)
        wb = f"WB_RISK{sid[-3:]}_{i:03d}"
        cod = random.uniform(100, 500)
        await _insert_waybill(conn, wb, sid, rid, aid, "普通商品", "普通",
                              random.uniform(100, 300), random.uniform(1, 2),
                              cod=cod, status="拒收", create=ct, pickup=pt)
        await _insert_event(conn, f"LEVT_{wb}_1", wb, sid, rid, "寄件下单", ct, "寄件网点")
        await _insert_event(conn, f"LEVT_{wb}_2", wb, sid, rid, "揽收", pt, "揽收网点")
        await _insert_event(conn, f"LEVT_{wb}_3", wb, sid, rid, "拒收",
                            pt + timedelta(days=1), "收件地址")
        await _insert_cod(conn, f"COD_{wb}", wb, cod, "拒收", reject_time=pt + timedelta(days=1))
        await _insert_abnormal(conn, f"ABN_{wb}", wb, "COD拒收异常",
                               pt + timedelta(days=1), "代收货款拒收")


MODE_GENERATORS = [
    _gen_high_freq,
    _gen_dangerous,
    _gen_cross_border,
    _gen_multi_addr,
    _gen_cod_reject,
]


async def _reset_risk_data(conn) -> None:
    print("[reset] 删旧 RISK 寄件人 + 关联数据...")
    await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for tbl in ("logistics_abnormal_record", "logistics_complaint_record", "logistics_claim",
                "logistics_cod_settlement", "logistics_customs_info"):
        await conn.execute(text(f"DELETE FROM {tbl} WHERE waybill_no LIKE 'WB_RISK%'"))
    await conn.execute(text(
        "DELETE FROM logistics_event_record WHERE waybill_no LIKE 'WB_RISK%' OR sender_id LIKE 'RISK%'"
    ))
    await conn.execute(text("DELETE FROM logistics_waybill WHERE waybill_no LIKE 'WB_RISK%'"))
    await conn.execute(text("DELETE FROM logistics_address WHERE address_id LIKE 'RISKADR%'"))
    await conn.execute(text("DELETE FROM logistics_recipient WHERE recipient_id LIKE 'RISKRCP%'"))
    await conn.execute(text("DELETE FROM logistics_sender WHERE sender_id LIKE 'RISK%'"))
    await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


async def gen_logistics_risky_senders(count: int = 5, reset: bool = False) -> None:
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    async with async_engine.begin() as conn:
        if reset:
            await _reset_risk_data(conn)

        await _insert_operator(conn)

        print(f"[generate] 生成 {count} 个 RISK 高风险寄件人 (5 模式轮换)...")
        for idx in range(1, count + 1):
            sid = f"RISK{idx:03d}"
            mode_idx = (idx - 1) % 5
            mode_name = RISK_MODES[mode_idx]
            rid = f"RISKRCP{idx:03d}_0"
            aid = f"RISKADR{idx:03d}_0"
            verified = 0 if mode_idx == 4 else 1
            fail_count = 3 if mode_idx == 4 else 0
            await _insert_sender(conn, sid, f"风险寄件人{idx}", verified, fail_count)
            await _insert_recipient(conn, rid, f"收件人{idx}", f"137{idx:06d}00")
            await _insert_address(conn, aid, rid, "广东", "广州市", "天河区", "风险街道1号")
            print(f"  [{idx}/{count}] {sid} (模式 {mode_idx + 1}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, sid, rid, aid)

        # 统计
        stats = {}
        for label, sql in [
            ("RISK 寄件人", "SELECT COUNT(*) FROM logistics_sender WHERE sender_id LIKE 'RISK%'"),
            ("RISK 运单", "SELECT COUNT(*) FROM logistics_waybill WHERE sender_id LIKE 'RISK%'"),
            ("RISK COD", "SELECT COUNT(*) FROM logistics_cod_settlement WHERE waybill_no LIKE 'WB_RISK%'"),
            ("RISK 异常", "SELECT COUNT(*) FROM logistics_abnormal_record WHERE waybill_no LIKE 'WB_RISK%'"),
            ("RISK 地址", "SELECT COUNT(*) FROM logistics_address WHERE address_id LIKE 'RISKADR%'"),
        ]:
            stats[label] = (await conn.execute(text(sql))).scalar()

    print("\n[完成] 高风险寄件人数据生成完成!")
    for label, val in stats.items():
        print(f"  {label}: {val}")


def main() -> None:
    parser = argparse.ArgumentParser(description="造 RISK 高风险寄件人 + 运单/COD/异常")
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 寄件人数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 数据再生成")
    args = parser.parse_args()

    async def _runner() -> None:
        try:
            await gen_logistics_risky_senders(count=args.count, reset=args.reset)
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()

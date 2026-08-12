"""
二手交易平台物流侧风控系统 - 业务数据生成 (异步, 可重复运行)
================
默认生成约 300 条业务数据, 重复跑默认 INSERT IGNORE (幂等), 加 --reset 先清空:
  - 卖家 (shipper_info):          N_SHIPPER   (默认 10)
  - 买家 (consignee_info):        N_SHIPPER*3 (平均 3 个买家/卖家)
  - 快递员 (carrier_info):        N_CARRIER   (默认 8)
  - 运单 (waybill_info):          N_WAYBILL   (默认 50)
  - 运单明细 (waybill_detail):    50 条 (1 条/单)
  - 商品身份 (item_identity):    50 条 (IMEI 绑定)
  - 验货记录 (inspection_record): 100 条 (入仓+出仓/单)
  - 轨迹事件 (tracking_event):    ~300 条 (三段式)
  - 投诉纠纷 (complaint_claim):   ~7 条

三段式物流模型:
  链路 A (卖家→验货中心): 卖家下单寄件 → 揽收入仓
  验货中心:               验货完成 (入仓验货) → 出仓发货 (出仓复验)
  链路 B (验货中心→买家): 运输中 → 派送中 → 买家签收/拒收
  链路 C (退货逆向):      买家退回寄件 → 退货入仓验货

用法: python scripts/gen_logistics_data.py            # 幂等插入
      python scripts/gen_logistics_data.py --reset    # 先清空业务表再插入
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiomysql
from faker import Faker

from app.config import settings


# ============================================================
# 配置
# ============================================================
CHINESE_PROVINCES = [
    "北京", "上海", "天津", "重庆", "广东", "浙江", "江苏", "福建", "山东", "河北",
    "四川", "湖北", "湖南", "河南", "安徽", "江西", "陕西", "辽宁", "吉林", "黑龙江",
    "广西", "云南", "贵州", "山西", "甘肃", "青海", "内蒙古", "新疆", "宁夏", "西藏",
]
CHINESE_CITIES = {
    "北京": "北京市", "上海": "上海市", "天津": "天津市", "重庆": "重庆市",
    "广东": "广州市", "浙江": "杭州市", "江苏": "南京市", "福建": "福州市",
    "山东": "济南市", "河北": "石家庄市", "四川": "成都市", "湖北": "武汉市",
    "湖南": "长沙市", "河南": "郑州市", "安徽": "合肥市", "江西": "南昌市",
    "陕西": "西安市", "辽宁": "沈阳市", "吉林": "长春市", "黑龙江": "哈尔滨市",
    "广西": "南宁市", "云南": "昆明市", "贵州": "贵阳市", "山西": "太原市",
    "甘肃": "兰州市", "青海": "西宁市", "内蒙古": "呼和浩特市", "新疆": "乌鲁木齐市",
    "宁夏": "银川市", "西藏": "拉萨市",
}
CHINESE_DISTRICTS = [
    "朝阳区", "海淀区", "浦东新区", "黄浦区", "天河区", "越秀区", "西湖区", "拱墅区",
    "鼓楼区", "玄武区", "锦江区", "青羊区", "洪山区", "岳麓区", "雁塔区", "龙岗区",
]

SECOND_HAND_CATEGORIES = [
    ("手机", 1), ("电脑", 1), ("相机", 1), ("奢侈品", 1), ("平板", 1),
    ("手表", 0), ("耳机", 0), ("游戏机", 0), ("图书", 0), ("服装", 0),
    ("家居", 0), ("其他", 0),
]
CATEGORIES = [c[0] for c in SECOND_HAND_CATEGORIES]
HIGH_VALUE_CATEGORIES = {c[0] for c in SECOND_HAND_CATEGORIES if c[1] == 1}

CARGO_TYPES = ["普通", "电池", "化学品", "液体", "粉末", "刀具", "其他"]
WAYBILL_STATUSES = ["待揽收", "待验货", "已验货", "运输中", "派送中", "已签收", "已拒收", "已退回"]

TRACKING_EVENT_TYPES = [
    "卖家下单寄件", "揽收入仓", "验货完成", "出仓发货",
    "运输中", "派送中", "买家签收", "买家拒收",
    "买家退回寄件", "退货入仓验货",
]

COMPLAINT_REASONS = [
    "收到的物品与描述成色不符", "怀疑物流途中被调包", "收到假货/配件机",
    "未收到货但显示签收", "七天无理由退货", "保价理赔难",
]
CLAIM_TYPES = ["调包投诉", "成色不符", "退货争议", "未收到", "破损投诉", "遗失投诉", "费用争议", "其他"]
CLAIM_STATUSES = ["待处理", "处理中", "已赔付", "已驳回", "已关闭"]
CLAIMANTS = ["买家", "卖家"]

BRAND_MODELS = [
    ("Apple", "iPhone 13 Pro"), ("Apple", "iPhone 14"), ("Apple", "iPhone 15"),
    ("华为", "Mate 60 Pro"), ("华为", "P60"), ("小米", "14 Pro"), ("小米", "13 Ultra"),
    ("OPPO", "Find X7"), ("vivo", "X100"), ("三星", "Galaxy S24"),
    ("联想", "拯救者 Y9000P"), ("华硕", "ROG 幻16"), ("戴尔", "XPS 15"),
    ("索尼", "A7M4"), ("佳能", "EOS R6"), ("尼康", "Z6 II"),
    ("Apple", "MacBook Pro 14"), ("华为", "MateBook 16s"), ("Apple", "iPad Pro 11"),
    ("任天堂", "Switch OLED"), ("索尼", "PS5"),
]


def _risk_tier() -> str:
    """返回风险分层: normal / medium / high (概率 80/15/5)"""
    r = random.random()
    if r < 0.05:
        return "high"
    elif r < 0.20:
        return "medium"
    else:
        return "normal"


def _fake_imei() -> str:
    return f"35{random.randint(100000000000, 999999999999)}"


def _v(val):
    return "NULL" if val is None else f"'{val}'"


# ============================================================
# 主函数
# ============================================================
async def gen_logistics_data(
    n_shipper: int = 10,
    n_carrier: int = 8,
    n_waybill: int = 50,
    batch_size: int = 100,
    reset: bool = False,
):
    fake = Faker("zh_CN")
    conn = await aiomysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        db=settings.DB_NAME, charset="utf8mb4", autocommit=True,
    )

    print("=" * 60)
    print(f"开始生成二手物流业务数据 (卖家: {n_shipper}, 快递员: {n_carrier}, 运单: {n_waybill})")
    print(f"模式: {'[RESET] 先清空业务表' if reset else '[幂等] INSERT IGNORE'}")
    print("=" * 60)

    # 可选: 清空业务表 (按外键依赖倒序)
    if reset:
        print("\n[0/9] 清空业务表...")
        async with conn.cursor() as cur:
            await cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for t in ["complaint_claim", "tracking_event", "inspection_record", "item_identity",
                      "waybill_detail", "waybill_info", "carrier_info", "consignee_info",
                      "shipper_info", "complaint_reason", "dimension_waybill_status",
                      "dimension_cargo_category"]:
                await cur.execute(f"TRUNCATE TABLE `{t}`")
            await cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        print("  清空完成")

    now = datetime.now()

    # ---- 1. 维度表 ----
    print("\n[1/9] 灌维度表...")
    async with conn.cursor() as cur:
        for cat, hv in SECOND_HAND_CATEGORIES:
            await cur.execute(
                "INSERT IGNORE INTO dimension_cargo_category (cargo_category, is_high_value) VALUES (%s, %s)",
                (cat, hv))
        for st in WAYBILL_STATUSES:
            await cur.execute(
                "INSERT IGNORE INTO dimension_waybill_status (waybill_status) VALUES (%s)", (st,))
        for reason in COMPLAINT_REASONS:
            await cur.execute(
                "INSERT IGNORE INTO complaint_reason (complaint_reason) VALUES (%s)", (reason,))
    print(f"  → 品类 {len(CATEGORIES)} + 状态 {len(WAYBILL_STATUSES)} + 投诉原因 {len(COMPLAINT_REASONS)}")

    # ---- 2. 卖家 + 买家 ----
    print(f"\n[2/9] 灌卖家 ({n_shipper}) + 买家 (~{n_shipper*3})...")
    shipper_risk: dict[str, str] = {}
    shipper_ids: list[str] = []
    consignee_rows: list[dict] = []

    for i in range(1, n_shipper + 1):
        sid = f"SHP{i:04d}"
        shipper_ids.append(sid)
        risk = _risk_tier()
        shipper_risk[sid] = risk
        prov = random.choice(CHINESE_PROVINCES)
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT IGNORE INTO shipper_info "
                "(shipper_id, shipper_name, shipper_phone, shipper_id_card, "
                "shipper_province, shipper_city, shipper_district, shipper_street, register_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (sid, fake.name(), fake.phone_number()[:11],
                 f"{random.randint(110000, 659000)}{random.randint(19900101, 20051231)}{random.randint(1000, 9999)}",
                 prov, CHINESE_CITIES[prov], random.choice(CHINESE_DISTRICTS),
                 fake.street_address()[:50], now - timedelta(days=random.randint(30, 365 * 3))))
        for j in range(random.randint(2, 5)):
            cprov = random.choice(CHINESE_PROVINCES)
            consignee_rows.append({
                "consignee_id": f"CG{sid[3:]}{j+1:02d}",
                "consignee_name": fake.name(),
                "consignee_phone": fake.phone_number()[:11],
                "consignee_province": cprov,
                "consignee_city": CHINESE_CITIES[cprov],
                "consignee_district": random.choice(CHINESE_DISTRICTS),
                "consignee_street": fake.street_address()[:50],
            })

    async with conn.cursor() as cur:
        for r in consignee_rows:
            await cur.execute(
                "INSERT IGNORE INTO consignee_info "
                "(consignee_id, consignee_name, consignee_phone, "
                "consignee_province, consignee_city, consignee_district, consignee_street) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (r["consignee_id"], r["consignee_name"], r["consignee_phone"],
                 r["consignee_province"], r["consignee_city"],
                 r["consignee_district"], r["consignee_street"]))
    print(f"  → {n_shipper} 卖家 + {len(consignee_rows)} 买家")

    # ---- 3. 快递员 ----
    print(f"\n[3/9] 灌快递员 ({n_carrier})...")
    carrier_ids: list[str] = []
    vehicle_types = ["厢式货车", "平板货车", "冷链车", "危化品车", "快递三轮车"]
    for i in range(1, n_carrier + 1):
        cid = f"CAR{i:04d}"
        carrier_ids.append(cid)
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT IGNORE INTO carrier_info "
                "(carrier_id, carrier_name, carrier_phone, vehicle_plate, vehicle_type, "
                "vehicle_capacity, deposit_amount, is_verified, register_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (cid, fake.name(), fake.phone_number()[:11],
                 random.choice(["京A", "沪B", "粤C", "浙D", "苏E"]) + f"{random.randint(10000, 99999)}",
                 random.choice(vehicle_types), round(random.uniform(0.5, 30), 2),
                 round(random.uniform(0, 50000), 2), 1 if random.random() < 0.8 else 0,
                 now - timedelta(days=random.randint(30, 365 * 2))))
    print(f"  → {n_carrier} 快递员")

    # ---- 4. 运单 + 明细 + 商品身份 ----
    print(f"\n[4/9] 灌运单 ({n_waybill}) + 明细 + 商品身份...")
    waybill_rows: list[dict] = []
    detail_rows: list[dict] = []
    identity_rows: list[dict] = []
    shipper_consignees: dict[str, list[str]] = {}
    for r in consignee_rows:
        prefix = r["consignee_id"][2:6]
        sid = f"SHP{prefix}"
        shipper_consignees.setdefault(sid, []).append(r["consignee_id"])

    for i in range(1, n_waybill + 1):
        wid = f"WB{i:06d}"
        sid = random.choice(shipper_ids)
        risk = shipper_risk[sid]
        consignee_list = shipper_consignees.get(sid) or [r["consignee_id"] for r in consignee_rows]
        cid = random.choice(consignee_list)
        carid = random.choice(carrier_ids)

        create_time = now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23))
        is_night = 1 if create_time.hour < 6 else 0

        category = random.choice(CATEGORIES)
        if risk == "high" and random.random() < 0.7:
            category = random.choice(list(HIGH_VALUE_CATEGORIES))
        is_hv = 1 if category in HIGH_VALUE_CATEGORIES else 0

        weight = round(random.uniform(0.2, 5), 2)
        volume = round(random.uniform(0.001, 0.05), 4)
        qty = 1
        freight = round(random.uniform(8, 80), 2)
        declared = round(random.uniform(500, 15000), 2) if is_hv else round(random.uniform(50, 2000), 2)
        cod = round(declared * 0.8, 2) if random.random() < 0.3 else 0
        insurance_amt = round(declared * 0.8, 2) if random.random() < 0.4 else 0
        insurance_prem = round(insurance_amt * 0.003, 2)
        cargo_type = random.choices(CARGO_TYPES, weights=[70, 10, 5, 8, 3, 2, 2])[0]
        if risk == "high":
            cargo_type = random.choices(CARGO_TYPES, weights=[30, 25, 15, 15, 8, 5, 2])[0]
        is_cross = 1 if risk == "high" and random.random() < 0.4 else 0

        # 三段式状态流转
        r = random.random()
        if risk == "high":
            status = random.choice(["待揽收", "待验货", "已验货"])
            segment = "A"
        elif risk == "medium":
            status = random.choice(["待验货", "已验货", "运输中", "派送中"])
            segment = "B" if status in ("运输中", "派送中") else "A"
        else:
            status = random.choice(WAYBILL_STATUSES)
            if status in ("已拒收", "已退回"):
                segment = "C"
            elif status in ("运输中", "派送中", "已签收", "已验货"):
                segment = "B"
            else:
                segment = "A"

        pickup_time = create_time + timedelta(hours=random.randint(1, 24)) if status != "待揽收" else None
        delivered_time = create_time + timedelta(days=random.randint(1, 7)) if status == "已签收" else None
        complete_time = create_time + timedelta(days=random.randint(2, 10)) if status == "已签收" else None

        waybill_rows.append({
            "waybill_id": wid, "create_time": create_time,
            "pickup_time": pickup_time, "delivered_time": delivered_time, "complete_time": complete_time,
            "segment": segment, "shipper_id": sid, "consignee_id": cid, "carrier_id": carid,
            "waybill_status": status, "cargo_category": category,
            "cargo_weight": weight, "cargo_volume": volume, "cargo_quantity": qty,
            "declared_value": declared, "freight_amount": freight, "cod_amount": cod,
            "insurance_amount": insurance_amt, "insurance_premium": insurance_prem,
            "is_night_order": is_night, "is_urgent": random.choice([0, 1]),
            "cargo_type": cargo_type, "is_cross_border": is_cross,
        })

        brand, model = random.choice(BRAND_MODELS)
        imei = _fake_imei()
        declared_grade = random.choices(["优", "良", "差"], weights=[40, 45, 15])[0]
        if risk == "high":
            declared_grade = random.choices(["优", "良", "差"], weights=[80, 15, 5])[0]

        detail_rows.append({
            "detail_id": f"DT{wid[2:]}001", "waybill_id": wid, "item_imei": imei,
            "cargo_name": f"{brand} {model}", "item_brand": brand, "item_model": model,
            "item_grade": declared_grade, "cargo_category": category,
            "cargo_weight": weight, "cargo_volume": volume, "cargo_quantity": qty,
            "declared_value": declared,
        })
        inspected_grade = random.choices(["优", "良", "差"], weights=[5, 30, 65])[0] if risk == "high" else declared_grade
        identity_rows.append({
            "item_id": f"II{wid[2:]}001", "item_imei": imei, "item_brand": brand, "item_model": model,
            "cargo_category": category, "declared_grade": declared_grade, "inspected_grade": inspected_grade,
            "return_grade": None, "waybill_id": wid, "status": "在途", "create_time": create_time,
        })

    async with conn.cursor() as cur:
        for wb in waybill_rows:
            await cur.execute(
                "INSERT IGNORE INTO waybill_info "
                "(waybill_id, create_time, pickup_time, delivered_time, complete_time, "
                "segment, shipper_id, consignee_id, carrier_id, waybill_status, "
                "cargo_category, cargo_weight, cargo_volume, cargo_quantity, declared_value, "
                "freight_amount, cod_amount, insurance_amount, insurance_premium, "
                "is_night_order, is_urgent, cargo_type, is_cross_border) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (wb["waybill_id"], wb["create_time"], wb["pickup_time"], wb["delivered_time"], wb["complete_time"],
                 wb["segment"], wb["shipper_id"], wb["consignee_id"], wb["carrier_id"], wb["waybill_status"],
                 wb["cargo_category"], wb["cargo_weight"], wb["cargo_volume"], wb["cargo_quantity"], wb["declared_value"],
                 wb["freight_amount"], wb["cod_amount"], wb["insurance_amount"], wb["insurance_premium"],
                 wb["is_night_order"], wb["is_urgent"], wb["cargo_type"], wb["is_cross_border"]))
        for d in detail_rows:
            await cur.execute(
                "INSERT IGNORE INTO waybill_detail "
                "(detail_id, waybill_id, item_imei, cargo_name, item_brand, item_model, "
                "item_grade, cargo_category, cargo_weight, cargo_volume, cargo_quantity, declared_value) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (d["detail_id"], d["waybill_id"], d["item_imei"], d["cargo_name"], d["item_brand"], d["item_model"],
                 d["item_grade"], d["cargo_category"], d["cargo_weight"], d["cargo_volume"],
                 d["cargo_quantity"], d["declared_value"]))
        for it in identity_rows:
            await cur.execute(
                "INSERT IGNORE INTO item_identity "
                "(item_id, item_imei, item_brand, item_model, cargo_category, "
                "declared_grade, inspected_grade, return_grade, waybill_id, status, create_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (it["item_id"], it["item_imei"], it["item_brand"], it["item_model"], it["cargo_category"],
                 it["declared_grade"], it["inspected_grade"], it["return_grade"], it["waybill_id"],
                 it["status"], it["create_time"]))
    print(f"  → {len(waybill_rows)} 运单 + {len(detail_rows)} 明细 + {len(identity_rows)} 商品身份")

    # ---- 5. 验货记录 ----
    print(f"\n[5/9] 灌验货记录 (~{n_waybill*2})...")
    inspector_ids = [f"INSP{random.randint(1, 20):02d}" for _ in range(5)]
    ir_count = 0
    async with conn.cursor() as cur:
        for wb in waybill_rows:
            wid = wb["waybill_id"]
            base_time = wb["create_time"]
            for idx, (itype, grade, func_res) in enumerate([
                ("入仓验货", random.choices(["优", "良", "差"], weights=[40, 45, 15])[0],
                 random.choices(["正常", "异常"], weights=[85, 15])[0]),
                ("出仓复验", random.choices(["优", "良", "差"], weights=[40, 45, 15])[0], "正常"),
            ]):
                await cur.execute(
                    "INSERT IGNORE INTO inspection_record "
                    "(record_id, waybill_id, item_imei, inspector_id, inspect_type, "
                    "grade_result, functional_result, accessories_result, "
                    "photo_url, video_url, seal_id, duration_min, inspect_time) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (f"IR{wid[2:]}{idx+1:03d}", wid, _fake_imei(), random.choice(inspector_ids), itype,
                     grade, func_res, "齐全", f"/inspect/{wid}/{idx}.jpg", None,
                     f"SEAL{wid[2:]}", random.randint(2, 30),
                     base_time + timedelta(hours=random.randint(24, 120))))
                ir_count += 1
    print(f"  → {ir_count} 验货记录")

    # ---- 6. 轨迹事件 ----
    print(f"\n[6/9] 灌轨迹事件 (~{n_waybill*6})...")
    te_count = 0
    async with conn.cursor() as cur:
        for wb in waybill_rows:
            wid = wb["waybill_id"]
            base_time = wb["create_time"]
            status = wb["waybill_status"]
            if status == "待揽收":
                stages = ["卖家下单寄件"]
            elif status == "待验货":
                stages = ["卖家下单寄件", "揽收入仓"]
            elif status == "已验货":
                stages = ["卖家下单寄件", "揽收入仓", "验货完成"]
            elif status in ("运输中",):
                stages = ["卖家下单寄件", "揽收入仓", "验货完成", "出仓发货", "运输中"]
            elif status in ("派送中",):
                stages = ["卖家下单寄件", "揽收入仓", "验货完成", "出仓发货", "运输中", "派送中"]
            elif status == "已签收":
                stages = ["卖家下单寄件", "揽收入仓", "验货完成", "出仓发货", "运输中", "派送中", "买家签收"]
            elif status == "已拒收":
                stages = ["卖家下单寄件", "揽收入仓", "验货完成", "出仓发货", "运输中", "派送中", "买家拒收"]
            elif status == "已退回":
                stages = ["卖家下单寄件", "揽收入仓", "验货完成", "出仓发货", "运输中", "派送中",
                          "买家退回寄件", "退货入仓验货"]
            else:
                stages = ["卖家下单寄件", "揽收入仓"]
            for idx, evt in enumerate(stages):
                prov = random.choice(CHINESE_PROVINCES)
                await cur.execute(
                    "INSERT IGNORE INTO tracking_event "
                    "(waybill_id, event_type, event_time, "
                    "location_province, location_city, location_district, "
                    "location_lat, location_lng, node_weight, operator_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (wid, evt, base_time + timedelta(hours=idx * random.randint(2, 12)),
                     prov, CHINESE_CITIES[prov], random.choice(CHINESE_DISTRICTS),
                     round(random.uniform(20, 50), 6), round(random.uniform(100, 130), 6),
                     round(random.uniform(0.2, 5), 2), random.choice(carrier_ids)))
                te_count += 1
    print(f"  → {te_count} 轨迹事件")

    # ---- 7. 投诉纠纷 ----
    print(f"\n[7/9] 灌投诉纠纷 (~{int(n_waybill*0.15)})...")
    claim_count = 0
    async with conn.cursor() as cur:
        for wb in waybill_rows:
            risk = shipper_risk.get(wb["shipper_id"], "normal")
            prob = 0.50 if risk == "high" else (0.20 if risk == "medium" else 0.05)
            if random.random() < prob:
                await cur.execute(
                    "INSERT IGNORE INTO complaint_claim "
                    "(claim_id, waybill_id, claimant, claim_type, claim_amount, "
                    "claim_reason, claim_status, create_time, complete_time) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NULL)",
                    (f"CLM{wb['waybill_id'][2:]}", wb["waybill_id"], random.choice(CLAIMANTS),
                     random.choice(CLAIM_TYPES), round(random.uniform(50, wb["declared_value"] * 0.5), 2),
                     random.choice(COMPLAINT_REASONS), random.choice(CLAIM_STATUSES),
                     wb["create_time"] + timedelta(days=random.randint(1, 15))))
                claim_count += 1
    print(f"  → {claim_count} 投诉纠纷")

    # ---- 8. 汇总 ----
    total = (
        n_shipper + len(consignee_rows) + n_carrier
        + len(waybill_rows) + len(detail_rows) + len(identity_rows)
        + ir_count + te_count + claim_count
    )
    print(f"\n{'=' * 60}")
    print(f"完成! 总计生成 {total} 条物流业务数据")
    print(f"  - 卖家: {n_shipper} / 买家: {len(consignee_rows)} / 快递员: {n_carrier}")
    print(f"  - 运单: {len(waybill_rows)} / 明细: {len(detail_rows)} / 商品身份: {len(identity_rows)}")
    print(f"  - 验货记录: {ir_count} / 轨迹事件: {te_count} / 投诉纠纷: {claim_count}")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="二手交易平台物流侧业务数据生成 (可重复运行)")
    parser.add_argument("--shipper", type=int, default=10, help="卖家人数 (默认 10)")
    parser.add_argument("--carrier", type=int, default=8, help="快递员人数 (默认 8)")
    parser.add_argument("--waybill", type=int, default=50, help="运单数 (默认 50)")
    parser.add_argument("--batch", type=int, default=100, help="批次大小 (保留参数)")
    parser.add_argument("--reset", action="store_true", help="先清空业务表再插入")
    args = parser.parse_args()

    asyncio.run(gen_logistics_data(
        n_shipper=args.shipper,
        n_carrier=args.carrier,
        n_waybill=args.waybill,
        batch_size=args.batch,
        reset=args.reset,
    ))

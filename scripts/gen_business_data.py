"""
物流风控系统 - 业务模拟数据生成脚本 (异步)
生成物流行业业务数据：用户信息(UserInfo) / 地址(Address) /
  运单(Shipment) / 运单物品(ShipmentItem) /
  跨境申报(CustomsDeclaration) / 投诉记录(ComplaintRecord)

设计思路:
  * 50 个普通用户(U001~U050) + 5 个高风险用户(RISK001~RISK005)
  * 每个用户 2-4 个地址
  * 150+ 条运单，混合: 普通标快/到付/跨境月结/保价
  * 高风险用户特征命中:
    RISK001 - 高频+大额(30单+万级申报)
    RISK002 - 到付拒收率80%
    RISK003 - 危险品瞒报模式(大额+低保价)
    RISK004 - 跨境低申报+多地址
    RISK005 - 投诉滥用+被诉
  * 20 条跨境申报记录
  * 15 条投诉记录
"""
import argparse
import asyncio
import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.models import (
    Address, ComplaintRecord, CustomsDeclaration, Shipment, ShipmentItem, UserInfo,
)

SENDER_NAMES = [
    "张伟", "王芳", "李娜", "刘洋", "陈静", "杨帆", "赵磊", "黄敏",
    "周强", "吴丽", "徐峰", "孙燕", "朱浩", "马超", "胡雪", "林宇",
    "何涛", "郭芳", "高飞", "罗军", "梁婷", "宋鹏", "郑悦", "谢东",
    "韩冰", "唐倩", "冯雷", "于杰", "董梅", "曹阳",
]
RECEIVER_CITIES = [
    ("北京市", "朝阳区"), ("上海市", "浦东新区"), ("广东省", "深圳市"),
    ("广东省", "广州市"), ("浙江省", "杭州市"), ("江苏省", "南京市"),
    ("四川省", "成都市"), ("湖北省", "武汉市"), ("陕西省", "西安市"),
    ("浙江省", "义乌市"), ("福建省", "厦门市"), ("山东省", "青岛市"),
    ("辽宁省", "沈阳市"), ("河南省", "郑州市"), ("重庆市", "渝中区"),
    ("云南省", "昆明市"), ("湖南省", "长沙市"), ("安徽省", "合肥市"),
    ("新疆", "乌鲁木齐市"), ("西藏", "拉萨市"),
]
STREET_TEMPLATES = [
    "XX路{num}号", "XX大道{num}号XX大厦", "XX街{num}号XX小区",
    "XX路{num}号XX写字楼", "XX科技园XX栋{num}室",
]
CATEGORIES = [
    ("ELEC", 500, 8000), ("CLTH", 200, 2000), ("BOOK", 50, 500),
    ("HOME", 300, 3000), ("COSM", 200, 2500), ("FOOD", 100, 800),
    ("DOC", 2000, 20000), ("BAG", 500, 5000), ("TOY", 200, 1500),
    ("OUTD", 500, 4000), ("MED", 500, 3000), ("CHEM", 1000, 5000),
]
SHIPMENT_TYPES = ["普通标快", "生鲜冷链", "次日达", "隔日达", "国际快递"]
PAYMENT_METHODS = ["寄付现结", "到付", "月结", "寄付月结"]
CROSS_BORDER_COUNTRIES = [
    "美国", "日本", "韩国", "德国", "英国", "法国",
    "澳大利亚", "加拿大", "新加坡", "马来西亚",
]
COMPLAINT_TYPES = [
    "延误", "破损", "丢失", "服务态度差",
    "费用争议", "派送失败", "虚假签收",
]


def _random_phone() -> str:
    return f"1{random.choice(['3','5','7','8','9'])}{random.randint(100000000, 999999999)}"


def _hash_id_card(real_id: str) -> str:
    return hashlib.sha256(real_id.encode("utf-8")).hexdigest()


async def _gen_user(db, idx: int, is_risky: bool = False, risky_tag: str | None = None) -> UserInfo:
    if is_risky and risky_tag:
        user_id = risky_tag
        name = f"风险用户{risky_tag[-1]}"
        phone = f"160{random.randint(10000000, 99999999)}"
        id_card = f"510{random.randint(10000000000000, 99999999999999)}"
        real_status = "未实名"
        vip = 0
        reg_days = random.randint(5, 60)
        total = 0
    else:
        user_id = f"U{idx:03d}"
        name = random.choice(SENDER_NAMES)
        phone = _random_phone()
        id_card = f"110101{random.randint(1970, 2002):04d}{random.randint(101, 1231):04d}{random.randint(1000, 9999)}"
        real_status = random.choices(
            ["已实名", "未实名", "实名中", "实名失败"], weights=[0.85, 0.08, 0.05, 0.02],
        )[0]
        vip_map = {"普通": 0, "银卡": 1, "金卡": 2, "钻石": 3}
        vip = vip_map[random.choices(list(vip_map.keys()), weights=[0.7, 0.2, 0.08, 0.02])[0]]
        reg_days = random.randint(30, 500)
        total = 0

    from datetime import datetime, timedelta
    u = UserInfo(
        user_id=user_id,
        user_name=name,
        user_role="寄件人",
        phone=phone,
        id_card_hash=_hash_id_card(id_card),
        real_name_status=real_status,
        register_at=datetime.now() - timedelta(days=reg_days),
        vip_level=vip,
        total_shipments=total,
    )
    db.add(u)
    await db.flush()
    return u


async def _gen_addresses(db, user: UserInfo, count: int, force_remote: bool = False):
    addrs = []
    for i in range(count):
        prov_city = random.choice(RECEIVER_CITIES)
        # 偏远地区: 新疆/西藏
        is_remote = force_remote or prov_city[0] in ("新疆", "西藏")
        is_temporary = random.random() < 0.15
        a = Address(
            user_id=user.user_id,
            address_tag=random.choice(["家", "公司", "学校", "朋友", "代收点"]),
            contact_name=random.choice(SENDER_NAMES),
            contact_phone=_random_phone(),
            province=prov_city[0],
            city=prov_city[1],
            district=random.choice(["某某区", "开发区", "高新区", "主城区", "商圈"]),
            street_address=STREET_TEMPLATES[random.randint(0, 4)].format(num=random.randint(1, 999)),
            is_remote=is_remote,
            is_temporary=is_temporary,
        )
        db.add(a)
        addrs.append(a)
    await db.flush()
    return addrs


async def _gen_shipment(
    db, sender: UserInfo, sender_addrs: list,
    *, force_night=False, force_amount_high=False, force_reject=False,
    force_cancel=False, force_cross=False, force_cod=False, force_cod_amount_low=False,
) -> Shipment:
    from datetime import datetime, timedelta
    now = datetime.now()

    # 时间: 夜间寄件 (0-6点)
    if force_night:
        hour = random.randint(0, 5)
        minute = random.randint(0, 59)
    else:
        hour = random.choices(
            list(range(24)),
            weights=[0.01] * 6 + [0.05, 0.08, 0.1, 0.1, 0.09, 0.09, 0.08, 0.08, 0.07, 0.06, 0.04, 0.03, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01],
        )[0]
        minute = random.randint(0, 59)
    days_ago = random.randint(1, 80)
    create_time = (now - timedelta(days=days_ago)).replace(
        hour=hour, minute=minute, second=random.randint(0, 59),
    )

    # 发货/收件地址
    sender_addr = random.choice(sender_addrs)
    # 收件人独立一个用户
    receiver = (await db.execute(text("SELECT user_id FROM user_info WHERE user_id != :sid ORDER BY RAND() LIMIT 1"), {"sid": sender.user_id})).first()
    if receiver:
        receiver_uid = receiver.user_id
    else:
        receiver_uid = sender.user_id
    receiver_addr_rows = (await db.execute(text(
        "SELECT address_id FROM address WHERE user_id = :uid ORDER BY RAND() LIMIT 1"
    ), {"uid": receiver_uid})).fetchall()
    if receiver_addr_rows:
        receiver_addr_id = receiver_addr_rows[0].address_id
    else:
        receiver_addr_id = sender_addr.address_id

    # 运单类型
    shipment_type = random.choice(SHIPMENT_TYPES) if not force_cross else "国际快递"
    is_cross_border = force_cross or (shipment_type == "国际快递")

    # 支付方式: to 付 or 其他
    if force_cod:
        payment = "到付"
    elif force_cross:
        payment = random.choice(["月结", "寄付现结"])
    else:
        payment = random.choices(
            PAYMENT_METHODS, weights=[0.5, 0.15, 0.2, 0.15],
        )[0]

    # 金额
    if force_amount_high:
        total_amount = random.randint(8000, 60000)
    else:
        cat_code, _, _ = random.choice(CATEGORIES)
        if cat_code in ("DOC", "ELEC", "BAG"):
            total_amount = random.randint(2000, 15000)
        else:
            total_amount = random.randint(100, 5000)

    weight = round(random.uniform(0.5, 30), 2)
    freight = max(8, int(weight * 3 + total_amount * 0.002))
    cod_amount = freight + random.randint(0, int(total_amount * 0.3)) if payment == "到付" else 0
    # 保价: 危险品瞒报模式 = 大额但是0保价；普通 = 0-30% * 申报
    if force_amount_high and random.random() < 0.6:
        insurance = 0
    else:
        insurance = int(total_amount * random.choice([0, 0, 0, 0.01, 0.05, 0.1, 0.2, 0.5, 1.0]))

    # 状态
    if force_cancel:
        status = "CANCEL"
        pick_up_time = None
        delivered_time = None
        reject_count = 0
    elif force_reject:
        status = "REJECTED"
        pick_up_time = create_time + timedelta(hours=random.randint(1, 48))
        delivered_time = None
        reject_count = 1
    else:
        status = random.choices(
            ["CREATED", "PICKED", "INTRANS", "ARRIVED", "DELVRING", "DELIVERD", "REJECTED", "CANCEL"],
            weights=[0.05, 0.08, 0.1, 0.05, 0.07, 0.55, 0.05, 0.05],
        )[0]
        if status == "REJECTED":
            reject_count = 1
            pick_up_time = create_time + timedelta(hours=random.randint(1, 48))
            delivered_time = None
        elif status in ("DELIVERD",):
            reject_count = 0
            pick_up_time = create_time + timedelta(minutes=random.randint(15, 60 * 10))
            delivered_time = pick_up_time + timedelta(hours=random.randint(6, 96))
        elif status in ("PICKED", "INTRANS", "ARRIVED", "DELVRING"):
            reject_count = 0
            pick_up_time = create_time + timedelta(minutes=random.randint(5, 60 * 5))
            delivered_time = None
        else:  # CREATED or CANCEL
            reject_count = 0
            pick_up_time = None
            delivered_time = None

    waybill_no = f"SF{random.randint(10**11, 10**12 - 1)}"
    shipment_id = f"SHIP{random.randint(10**10, 10**11 - 1)}"

    s = Shipment(
        shipment_id=shipment_id,
        waybill_no=waybill_no,
        create_time=create_time,
        pick_up_time=pick_up_time,
        delivered_time=delivered_time,
        sender_user_id=sender.user_id,
        receiver_user_id=receiver_uid,
        sender_address_id=sender_addr.address_id,
        receiver_address_id=receiver_addr_id,
        shipment_type=shipment_type,
        payment_method=payment,
        total_weight_kg=weight,
        declared_value=total_amount,
        freight_amount=freight,
        cod_amount=cod_amount,
        insurance_amount=insurance,
        shipment_status=status,
        is_cross_border=is_cross_border,
        reject_count=reject_count,
        item_count=0,  # 后面生成 ShipmentItem 后回填
    )
    db.add(s)
    await db.flush()
    return s


async def _gen_items(db, s: Shipment, force_multi_category=False) -> int:
    """为一个运单生成物品明细, 返回行数量"""
    if force_multi_category:
        line_cnt = random.randint(6, 15)
    else:
        line_cnt = random.choices([1, 2, 3, 4, 5], weights=[0.5, 0.25, 0.1, 0.1, 0.05])[0]
    total_quantity = 0
    used_cats = set()
    for line_idx in range(line_cnt):
        cat_code, cat_min, cat_max = random.choice(CATEGORIES)
        used_cats.add(cat_code)
        quantity = random.randint(1, 8)
        unit_weight = round(random.uniform(0.05, 5), 2)
        declared = random.randint(cat_min, min(cat_max, max(cat_min + 1, s.declared_value // line_cnt)))
        item = ShipmentItem(
            item_id=f"ITEM{s.shipment_id[-6:]}{line_idx:03d}",
            shipment_id=s.shipment_id,
            item_name=f"{cat_code}商品{random.randint(100, 999)}",
            category_code=cat_code,
            quantity=quantity,
            unit_weight_kg=unit_weight,
            declared_value=declared,
            is_dangerous_declared=cat_code in ("MED", "CHEM"),
            hs_code=(
                f"{random.randint(1000, 9999)}.{random.randint(10, 99)}.{random.randint(10, 99)}"
                if s.is_cross_border else None
            ),
        )
        db.add(item)
        total_quantity += quantity
    # 回填 shipment item_count (用 item 行数, 符合 feature.order_item_count 语义)
    s.item_count = line_cnt
    await db.flush()
    return line_cnt


async def _gen_declaration(db, s: Shipment, force_low_value: bool = False) -> CustomsDeclaration | None:
    if not s.is_cross_border:
        return None
    from datetime import timedelta
    total_value = max(1, int(s.declared_value * (0.2 if force_low_value else random.uniform(0.8, 1.2))))
    d = CustomsDeclaration(
        declaration_id=f"DECL{s.shipment_id[-6:]}",
        shipment_id=s.shipment_id,
        declare_time=s.create_time + timedelta(minutes=random.randint(5, 180)),
        dest_country=random.choice(CROSS_BORDER_COUNTRIES),
        dest_customs_code=f"C{random.randint(100, 999)}",
        sender_id_card=_hash_id_card(f"SEND{random.randint(10**10, 10**11 - 1)}"),
        receiver_id_card=_hash_id_card(f"RECV{random.randint(10**10, 10**11 - 1)}"),
        total_declared_value=total_value,
        currency=random.choice(["CNY", "USD", "EUR", "JPY"]),
        declare_status=random.choices(
            ["待申报", "已申报", "审核中", "已放行", "被扣留"],
            weights=[0.05, 0.3, 0.1, 0.5, 0.05],
        )[0],
        is_value_mismatch=force_low_value or (total_value / max(1, s.declared_value) < 0.5),
    )
    db.add(d)
    await db.flush()
    return d


async def _gen_complaint(db, user: UserInfo, target_status_malicious: bool = False) -> ComplaintRecord | None:
    """生成投诉记录. 把投诉挂到 user 作为寄件人的某条运单上."""
    from datetime import datetime, timedelta
    rows = (await db.execute(text(
        "SELECT shipment_id FROM shipment WHERE sender_user_id = :uid LIMIT 20"
    ), {"uid": user.user_id})).fetchall()
    if not rows:
        return None
    shipment_id = random.choice(rows).shipment_id
    ctype = random.choice(COMPLAINT_TYPES)
    c = ComplaintRecord(
        shipment_id=shipment_id,
        user_id=user.user_id,
        complaint_type=ctype,
        complaint_content=f"投诉{ctype}：运单异常，需要赔偿。详细内容...",
        complaint_time=datetime.now() - timedelta(days=random.randint(1, 30)),
        claim_amount=random.randint(100, 5000) if target_status_malicious else random.randint(0, 1000),
        handle_status=random.choices(
            ["待处理", "处理中", "已结案", "已驳回"],
            weights=[0.15, 0.15, 0.5, 0.2],
        )[0],
        is_malicious=target_status_malicious or (ctype in ("费用争议", "虚假签收") and random.random() < 0.3),
    )
    db.add(c)
    await db.flush()
    return c


# ==================== 主流程: 先普通用户 -> 再高风险用户 ====================
async def generate_business_data():
    from datetime import datetime
    print(f"[{datetime.now()}] 开始生成物流业务数据 ...")
    async with AsyncSessionLocal() as db:
        # 1. 生成 50 个普通用户 + 地址
        print("  [1/6] 生成 50 个普通用户 ...")
        users = []
        for i in range(1, 51):
            u = await _gen_user(db, i)
            addrs = await _gen_addresses(db, u, random.randint(2, 4))
            users.append((u, addrs))
        await db.commit()

        # 2. 生成 5 个高风险用户 (各带一个特征标签)
        print("  [2/6] 生成 5 个高风险用户 ...")
        risky_defs = [
            ("RISK001", "高频大额寄件"),
            ("RISK002", "到付拒收高"),
            ("RISK003", "危险品瞒报"),
            ("RISK004", "跨境低申报"),
            ("RISK005", "投诉滥用"),
        ]
        risky_users = []
        for tag, _ in risky_defs:
            u = await _gen_user(db, 0, is_risky=True, risky_tag=tag)
            if tag == "RISK004":
                # 跨境低申报: 多地址 + 偏远
                addrs = await _gen_addresses(db, u, 6, force_remote=False)
            elif tag == "RISK002":
                # 到付拒收: 多地址 (换地址拒收)
                addrs = await _gen_addresses(db, u, 5)
            else:
                addrs = await _gen_addresses(db, u, 3)
            risky_users.append((u, addrs, tag))
        await db.commit()

        # 3. 普通用户: 110 条运单
        print("  [3/6] 普通用户生成 110 条运单 + 物品 ...")
        total_shipments = 0
        cross_shipments = []
        for u, addrs in users:
            # 每人 2-3 单
            for _ in range(random.randint(2, 3)):
                s = await _gen_shipment(db, u, addrs)
                multi = random.random() < 0.1
                await _gen_items(db, s, force_multi_category=multi)
                total_shipments += 1
                if s.is_cross_border:
                    cross_shipments.append((s, False))
        await db.commit()

        # 4. 高风险用户: 造对应特征
        print("  [4/6] 高风险用户造特征数据 ...")
        # RISK001: 高频(近7天10+ / 30天30+) + 大额 + 夜间
        u001, a001, _ = risky_users[0]
        from datetime import datetime, timedelta
        for _ in range(35):
            s = await _gen_shipment(
                db, u001, a001,
                force_night=random.random() < 0.4,
                force_amount_high=random.random() < 0.5,
            )
            await _gen_items(db, s)
            total_shipments += 1
            if s.is_cross_border:
                cross_shipments.append((s, False))

        # RISK002: 到付 + 拒收率 80% (8拒 / 10单) + 多地址 + 大额
        u002, a002, _ = risky_users[1]
        for i in range(12):
            force_reject = i < 10  # 10单拒收, 2单正常
            s = await _gen_shipment(
                db, u002, a002, force_cod=True,
                force_reject=force_reject,
                force_amount_high=random.random() < 0.6,
            )
            await _gen_items(db, s)
            total_shipments += 1

        # RISK003: 危险品瞒报: 大额 + 零保价 + 多分类
        u003, a003, _ = risky_users[2]
        for _ in range(18):
            s = await _gen_shipment(db, u003, a003, force_amount_high=True)
            s.insurance_amount = 0
            await _gen_items(db, s, force_multi_category=True)
            total_shipments += 1
            if s.is_cross_border:
                cross_shipments.append((s, False))

        # RISK004: 跨境 + 低申报 + 多省份地址
        u004, a004, _ = risky_users[3]
        for _ in range(15):
            s = await _gen_shipment(db, u004, a004, force_cross=True, force_amount_high=random.random() < 0.4)
            await _gen_items(db, s)
            total_shipments += 1
            cross_shipments.append((s, True))  # True = 低申报
        # 把 RISK004 的部分地址强行扩散到 3+ 省份(之前是随机 RECEIVER_CITIES 不一定多省, 不强制了, 概率会覆盖到)

        # RISK005: 投诉滥用 + 自己也有拒收 (综合场景)
        u005, a005, _ = risky_users[4]
        for _ in range(10):
            s = await _gen_shipment(
                db, u005, a005,
                force_reject=random.random() < 0.3,
                force_amount_high=random.random() < 0.3,
            )
            await _gen_items(db, s)
            total_shipments += 1
            if s.is_cross_border:
                cross_shipments.append((s, False))
        # 至少 7 条投诉
        for _ in range(7):
            await _gen_complaint(db, u005, target_status_malicious=True)
        await db.commit()

        # 5. 跨境申报: 对所有跨境运单生成申报单 (总数 ~ 40+)
        print(f"  [5/6] 生成 {len(cross_shipments)} 条跨境申报 ...")
        dec_cnt = 0
        for s, force_low in cross_shipments:
            d = await _gen_declaration(db, s, force_low_value=force_low)
            if d:
                dec_cnt += 1
        await db.commit()

        # 6. 投诉: 普通用户随机 8 条
        print("  [6/6] 生成 8 条普通用户投诉 ...")
        random.shuffle(users)
        comp_cnt = 0
        for u, _ in users[:8]:
            c = await _gen_complaint(db, u, target_status_malicious=False)
            if c:
                comp_cnt += 1
        await db.commit()

        # 回填每个用户 total_shipments
        print("  * 回填 user_info.total_shipments ...")
        await db.execute(text("""
            UPDATE user_info u
            SET total_shipments = (
                SELECT COUNT(*) FROM shipment s
                WHERE s.sender_user_id = u.user_id
            )
        """))
        await db.commit()

    total_users = len(users) + len(risky_users)
    print(f"[{datetime.now()}] 完成！生成 {total_users} 个用户, {total_shipments} 条运单, "
          f"{dec_cnt} 条跨境申报, {7 + comp_cnt} 条投诉.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成物流业务模拟数据")
    args = parser.parse_args()
    asyncio.run(generate_business_data())

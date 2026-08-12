"""
物流行业风控 - 业务数据生成脚本 (异步)

默认生成 120 张运单 + 关联的寄件人/收件人/地址/网点/事件/报关/COD/理赔/投诉/异常记录.
首次使用建议:
    python scripts/gen_logistics_data.py --init-tables --count 120
重复造数:
    python scripts/gen_logistics_data.py --count 200 --clean

说明:
  - --init-tables: 执行 sql/init_logistics_tables.sql 建表
  - --clean: 先清空 12 张物流表再插入 (按外键依赖逆序 TRUNCATE)
  - 生成数据会覆盖业务说明中的 6 类关键场景
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faker import Faker
from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from app.models_logistics import (
    LogisticsAbnormalRecord,
    LogisticsAddress,
    LogisticsClaim,
    LogisticsCodSettlement,
    LogisticsComplaint,
    LogisticsCustomerAccount,
    LogisticsCustomsInfo,
    LogisticsEventRecord,
    LogisticsOperator,
    LogisticsRecipient,
    LogisticsSender,
    LogisticsWaybill,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


PROVINCES = ["广东", "浙江", "江苏", "上海", "北京", "四川", "湖北", "福建", "山东", "河南"]
CITIES = {
    "广东": "广州市", "浙江": "杭州市", "江苏": "南京市", "上海": "上海市", "北京": "北京市",
    "四川": "成都市", "湖北": "武汉市", "福建": "厦门市", "山东": "济南市", "河南": "郑州市",
}
DISTRICTS = ["天河区", "西湖区", "鼓楼区", "浦东新区", "海淀区", "锦江区",
             "洪山区", "思明区", "历下区", "金水区"]
ITEM_CATEGORIES = ["普通", "电子产品", "电池", "化学品", "液体", "文件", "其他"]
HS_CODES = ["85076000", "90210000", "61102000", "95030021", "84713000", "33049900"]
DEST_COUNTRIES = ["美国", "德国", "日本", "新加坡", "澳大利亚", "英国"]
EVENT_TYPES = [
    "寄件下单", "揽收", "中转", "派送", "签收", "拒收", "退回", "投诉",
    "理赔申请", "异常上报", "报关清关", "海外仓", "结汇退税", "实名认证",
]

# 外键依赖逆序: 清空时从子表删到父表
TABLE_ORDER_REVERSE = [
    "logistics_abnormal_record", "logistics_complaint_record", "logistics_claim",
    "logistics_cod_settlement", "logistics_customs_info", "logistics_event_record",
    "logistics_waybill", "logistics_operator", "logistics_address",
    "logistics_recipient", "logistics_sender", "logistics_customer_account",
]


def _rand_time(days: int = 30) -> datetime:
    """最近 days 天内随机时间, 有 10% 概率落在 0-6 点 (凌晨寄件场景)."""
    base = datetime.now() - timedelta(days=random.uniform(0, days))
    if random.random() < 0.1:
        base = base.replace(hour=random.randint(0, 5), minute=random.randint(0, 59))
    return base


def _make_address_key(province: str, city: str, district: str, street: str) -> str:
    return f"{province}{city}{district}{street}"


async def _clean_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in TABLE_ORDER_REVERSE:
            await conn.execute(text(f"TRUNCATE TABLE `{table}`"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    print("[clean] 已清空 12 张物流表")


def _init_tables() -> None:
    """用 pymysql 执行 DDL 文件 (MULTI_STATEMENTS)."""
    import pymysql
    from pymysql.constants import CLIENT

    from app.config import settings

    sql_path = Path(__file__).resolve().parent.parent / "sql" / "init_logistics_tables.sql"
    conn = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        client_flag=CLIENT.MULTI_STATEMENTS,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"))
            while cur.nextset():
                pass
        conn.commit()
    finally:
        conn.close()
    print("[init-tables] 物流业务表 DDL 执行完成")


async def gen_logistics_data(count: int = 120, clean: bool = False) -> None:
    fake = Faker("zh_CN")
    if clean:
        await _clean_tables()

    accounts = [
        LogisticsCustomerAccount(
            account_id=f"ACC{i:03d}",
            customer_name=f"{fake.company()}",
            contact_phone=fake.phone_number(),
            settlement_account=fake.credit_card_number(card_type=None) if hasattr(fake, "credit_card_number") else f"BK{i:06d}",
            credit_level=random.choice(["普通", "良好", "优秀", "高风险"]),
            credit_limit=random.choice([10000, 50000, 100000, 500000]),
            settlement_method=random.choice(["月结", "预付", "现结"]),
            status=random.choice(["正常", "正常", "正常", "冻结"]),
            create_time=_rand_time(60),
            update_time=datetime.now(),
        )
        for i in range(1, 11)
    ]

    senders = []
    for i in range(1, 26):
        verified = random.random() > 0.12
        senders.append(LogisticsSender(
            sender_id=f"SND{i:03d}",
            account_id=f"ACC{random.randint(1, 10):03d}" if i % 5 == 0 else None,
            sender_name=fake.name(),
            sender_phone=fake.phone_number(),
            id_card_no=fake.ssn() if hasattr(fake, "ssn") else f"{random.randint(10**17, 10**18-1)}",
            company_name=fake.company() if i % 4 == 0 else None,
            province=random.choice(PROVINCES),
            city=CITIES[random.choice(PROVINCES)],
            district=random.choice(DISTRICTS),
            street_address=fake.street_address(),
            is_real_name_verified=1 if verified else 0,
            verify_time=_rand_time(60) if verified else None,
            verify_fail_count=random.randint(0, 3) if not verified else 0,
            create_time=_rand_time(60),
            update_time=datetime.now(),
        ))

    recipients = []
    for i in range(1, 31):
        verified = random.random() > 0.15
        recipients.append(LogisticsRecipient(
            recipient_id=f"RCP{i:03d}",
            recipient_name=fake.name(),
            recipient_phone=fake.phone_number(),
            is_real_name_verified=1 if verified else 0,
            verify_time=_rand_time(60) if verified else None,
            verify_fail_count=random.randint(1, 4) if not verified else 0,
            create_time=_rand_time(60),
            update_time=datetime.now(),
        ))

    addresses = []
    shared_streets = [fake.street_address() for _ in range(4)]  # 制造多人共用地址
    for i in range(1, 41):
        province = random.choice(PROVINCES)
        city = CITIES[province]
        district = random.choice(DISTRICTS)
        street = random.choice(shared_streets) if i % 5 == 0 else fake.street_address()
        addresses.append(LogisticsAddress(
            address_id=f"ADR{i:03d}",
            recipient_id=f"RCP{random.randint(1, 30):03d}",
            province=province,
            city=city,
            district=district,
            street_address=street,
            address_key=_make_address_key(province, city, district, street),
            is_remote=1 if random.random() < 0.08 else 0,
            is_temp=1 if random.random() < 0.10 else 0,
            use_count=random.randint(1, 15),
            create_time=_rand_time(60),
            update_time=datetime.now(),
        ))

    operators = [
        LogisticsOperator(
            operator_id=f"OPR{i:03d}",
            operator_name=fake.name(),
            phone=fake.phone_number(),
            network_id=f"NET{i:02d}",
            network_name=f"网点{i:02d}",
            is_internal=1,
            status="正常",
            create_time=_rand_time(90),
            update_time=datetime.now(),
        )
        for i in range(1, 16)
    ]

    waybills = []
    customs_list = []
    cod_list = []
    claims = []
    complaints = []
    abnormals = []
    events = []

    event_seq = 1
    customs_seq = 1
    cod_seq = 1
    claim_seq = 1
    complaint_seq = 1
    abnormal_seq = 1

    for i in range(1, count + 1):
        waybill_no = f"WB{datetime.now():%Y%m%d}{i:04d}"
        status = random.choices(
            ["已签收", "运输中", "派送中", "已揽收", "已下单", "拒收", "退回", "异常", "清关中", "已完结"],
            weights=[40, 15, 10, 8, 5, 5, 3, 2, 5, 7],
        )[0]
        is_cross = random.random() < 0.20
        if is_cross and status == "已下单":
            status = random.choice(["清关中", "运输中", "已签收"])
        item_category = random.choices(
            ["普通", "电子产品", "电池", "化学品", "液体", "文件", "其他"],
            weights=[40, 25, 10, 5, 10, 5, 5],
        )[0]
        declared_value = round(random.uniform(50, 5000), 2)
        if item_category in ("电池", "化学品"):
            declared_value = round(random.uniform(50, 800), 2)
        weight_kg = round(random.uniform(0.1, 20), 3)
        if is_cross:
            declared_value = round(random.uniform(100, 3000), 2)
        create_time = _rand_time(30)
        pickup_time = create_time + timedelta(hours=random.uniform(1, 12)) if status != "已下单" else None
        sign_time = (
            pickup_time + timedelta(days=random.uniform(1, 5))
            if status in ("已签收", "已完结") and pickup_time else None
        )
        cod_amount = round(random.uniform(50, 1000), 2) if random.random() < 0.15 else 0
        account_id = f"ACC{random.randint(1, 10):03d}" if random.random() < 0.3 else None

        waybills.append(LogisticsWaybill(
            waybill_no=waybill_no,
            sender_id=f"SND{random.randint(1, 25):03d}",
            recipient_id=f"RCP{random.randint(1, 30):03d}",
            address_id=f"ADR{random.randint(1, 40):03d}",
            operator_id=f"OPR{random.randint(1, 15):03d}",
            account_id=account_id,
            item_name=fake.word(),
            item_category=item_category,
            declared_value=declared_value,
            weight_kg=weight_kg,
            volume_cm3=round(random.uniform(100, 100000), 2),
            insured_amount=round(declared_value * random.uniform(0, 0.3), 2),
            freight_amount=round(random.uniform(10, 100), 2),
            payment_method=random.choices(["寄付", "到付", "月结"], weights=[50, 30, 20])[0],
            cod_amount=cod_amount,
            is_cross_border=1 if is_cross else 0,
            status=status,
            create_time=create_time,
            pickup_time=pickup_time,
            sign_time=sign_time,
            update_time=datetime.now(),
        ))

        # 事件流水: 核心轨迹 + 场景事件
        events.append(LogisticsEventRecord(
            event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
            sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
            event_type="寄件下单", event_time=create_time,
            location=f"{waybills[-1].sender_id}寄件网点", detail=None, create_time=datetime.now(),
        ))
        event_seq += 1

        if pickup_time:
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                operator_id=waybills[-1].operator_id,
                event_type="揽收", event_time=pickup_time,
                location=waybills[-1].operator_id, detail=None, create_time=datetime.now(),
            ))
            event_seq += 1

        if status in ("运输中", "清关中", "派送中", "已签收", "已完结", "拒收", "退回", "异常"):
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                event_type="中转", event_time=pickup_time + timedelta(hours=2),
                location="分拨中心", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1

        if is_cross:
            trade_mode = random.choice(["9610", "9710", "9810", "1210"])
            customs_status = random.choices(
                ["已放行", "查验中", "查验异常", "待申报"], weights=[70, 15, 10, 5],
            )[0]
            clear_time = create_time + timedelta(days=1) if customs_status == "已放行" else None
            customs_list.append(LogisticsCustomsInfo(
                customs_id=f"CUS{customs_seq:04d}",
                waybill_no=waybill_no,
                order_no=f"ORD{waybill_no}",
                payment_no=f"PAY{waybill_no}",
                manifest_no=f"MAN{customs_seq:04d}",
                trade_mode=trade_mode,
                hs_code=random.choice(HS_CODES),
                declared_value=declared_value,
                currency=random.choice(["CNY", "USD"]),
                origin_country="中国",
                destination_country=random.choice(DEST_COUNTRIES),
                customs_status=customs_status,
                clear_time=clear_time,
                create_time=create_time,
                update_time=datetime.now(),
            ))
            customs_seq += 1
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                event_type="报关清关", event_time=create_time + timedelta(days=1),
                location="目的国清关", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1

        if status in ("派送中", "已签收", "已完结", "拒收", "退回", "异常"):
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                operator_id=waybills[-1].operator_id,
                event_type="派送", event_time=pickup_time + timedelta(days=1),
                location="末端网点", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1

        if sign_time:
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                operator_id=waybills[-1].operator_id,
                event_type="签收", event_time=sign_time,
                location="收件地址", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1

        if status == "拒收":
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                event_type="拒收", event_time=pickup_time + timedelta(days=2),
                location="收件地址", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1
        elif status == "退回":
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                event_type="退回", event_time=pickup_time + timedelta(days=2),
                location="寄件网点", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1
        elif status == "异常":
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                event_type="异常上报", event_time=pickup_time + timedelta(days=1),
                location="分拨中心", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1

        # 代收货款
        if cod_amount > 0:
            collect_status = "待收款"
            collect_time = None
            reject_time = None
            settle_time = None
            if status in ("已签收", "已完结"):
                collect_status = "已收款"
                collect_time = sign_time or datetime.now()
                settle_time = collect_time + timedelta(days=2)
            elif status == "拒收":
                collect_status = "拒收"
                reject_time = pickup_time + timedelta(days=2)
            elif status == "退回":
                collect_status = "退款"
            cod_list.append(LogisticsCodSettlement(
                cod_id=f"COD{cod_seq:04d}",
                waybill_no=waybill_no,
                account_id=account_id,
                cod_amount=cod_amount,
                collect_status=collect_status,
                collect_time=collect_time,
                reject_time=reject_time,
                settle_time=settle_time,
                remark=None,
                create_time=create_time,
                update_time=datetime.now(),
            ))
            cod_seq += 1

        # 理赔 / 投诉 / 异常 按比例注入
        if random.random() < 0.08:
            claim_status = random.choice(["申请中", "定损中", "已赔付", "已驳回", "已关闭"])
            claims.append(LogisticsClaim(
                claim_id=f"CLM{claim_seq:04d}",
                waybill_no=waybill_no,
                claim_type=random.choice(["丢件", "破损", "延误", "其他"]),
                claim_amount=round(declared_value * random.uniform(0.3, 1), 2),
                claim_reason="客户反馈快件异常",
                claim_status=claim_status,
                apply_time=create_time + timedelta(days=2),
                settle_time=datetime.now() if claim_status == "已赔付" else None,
                create_time=create_time,
                update_time=datetime.now(),
            ))
            claim_seq += 1
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                event_type="理赔申请", event_time=create_time + timedelta(days=2),
                location="理赔中心", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1

        if random.random() < 0.08:
            complaints.append(LogisticsComplaint(
                complaint_id=f"CPT{complaint_seq:04d}",
                waybill_no=waybill_no,
                complaint_type=random.choice(["未收到", "时效", "服务", "代收货款", "其他"]),
                complaint_content="客户投诉",
                complaint_status=random.choice(["待处理", "处理中", "已解决", "已关闭"]),
                create_time=create_time + timedelta(days=3),
                resolve_time=datetime.now(),
                update_time=datetime.now(),
            ))
            complaint_seq += 1
            events.append(LogisticsEventRecord(
                event_id=f"LEVT{event_seq:06d}", waybill_no=waybill_no,
                sender_id=waybills[-1].sender_id, recipient_id=waybills[-1].recipient_id,
                event_type="投诉", event_time=create_time + timedelta(days=3),
                location="客服中心", detail=None, create_time=datetime.now(),
            ))
            event_seq += 1

        if random.random() < 0.12:
            abnormal_type = random.choice([
                "实名异常", "危险品瞒报", "重量价值异常", "地址异常",
                "COD拒收异常", "清关异常", "滞留异常", "其他",
            ])
            abnormals.append(LogisticsAbnormalRecord(
                abnormal_id=f"ABN{abnormal_seq:04d}",
                waybill_no=waybill_no,
                abnormal_type=abnormal_type,
                abnormal_time=create_time + timedelta(days=1),
                description=f"{abnormal_type}: {item_category}/{declared_value}元/{weight_kg}kg",
                handle_status=random.choice(["待处理", "已核实", "已处置", "已关闭"]),
                create_time=create_time,
                update_time=datetime.now(),
            ))
            abnormal_seq += 1

    # 少量独立实名认证事件 (无运单)
    for i in range(5):
        events.append(LogisticsEventRecord(
            event_id=f"LEVT{event_seq:06d}",
            waybill_no=None,
            sender_id=f"SND{random.randint(1, 25):03d}",
            event_type="实名认证",
            event_time=_rand_time(30),
            location="实名核验中心",
            detail=None,
            create_time=datetime.now(),
        ))
        event_seq += 1

    async with AsyncSessionLocal() as db:
        db.add_all(accounts)
        await db.flush()

        db.add_all(senders)
        db.add_all(recipients)
        db.add_all(operators)
        await db.flush()

        # 地址依赖收件人, 分开 flush 保证外键插入顺序
        db.add_all(addresses)
        await db.flush()

        db.add_all(waybills)
        await db.flush()

        db.add_all(events)
        db.add_all(customs_list)
        db.add_all(cod_list)
        db.add_all(claims)
        db.add_all(complaints)
        db.add_all(abnormals)
        await db.commit()

    print("=" * 60)
    print(f"物流业务数据生成完成: 运单 {len(waybills)} 条")
    print(f"  客户账户    : {len(accounts)}")
    print(f"  寄件人      : {len(senders)}")
    print(f"  收件人      : {len(recipients)}")
    print(f"  收件地址    : {len(addresses)}")
    print(f"  网点/快递员 : {len(operators)}")
    print(f"  事件流水    : {len(events)}")
    print(f"  跨境报关    : {len(customs_list)}")
    print(f"  COD 结算    : {len(cod_list)}")
    print(f"  理赔        : {len(claims)}")
    print(f"  投诉        : {len(complaints)}")
    print(f"  异常记录    : {len(abnormals)}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="物流风控业务数据生成")
    parser.add_argument("--count", type=int, default=120, help="运单数量 (默认 120)")
    parser.add_argument("--init-tables", action="store_true", help="先执行 DDL 建表")
    parser.add_argument("--clean", action="store_true", help="清空物流表后再生成")
    args = parser.parse_args()

    if args.count < 100:
        print(f"[WARN] --count={args.count} < 100, 业务数据量建议至少 100 条")
    if args.init_tables:
        _init_tables()

    async def _runner() -> None:
        try:
            await gen_logistics_data(count=args.count, clean=args.clean)
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()

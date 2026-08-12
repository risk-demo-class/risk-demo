"""
物流风控系统 - 10w 条随机业务数据生成 (异步, 一次性脚本)
================
生成规模 (默认 ≈ 8w 条, 可调):
  - 寄件用户 (user_info):        N_USER      (默认 10000)
  - 寄件人实名 (sender_info):     N_USER      (sender_id = user_id)
  - 收件人 (receiver_info):       N_USER * 2   (平均 2 个/人, 默认 20000)
  - 包裹 (parcel):               N_USER * 3   (平均 3 票/人, 默认 30000)
  - 危险品申报 (dangerous_declaration): 包裹 * 5%  (默认 1500)
  - COD 流水 (cod_transaction):          包裹 * 15% (默认 4500)
  - 总条目:                    ≈ 7.7w

风险画像 (自动注入, 供 gen_risk_data.py 采样时命中物流规则):
  - 80% 正常用户 (已实名, 普通包裹, 低申报价值)
  - 15% 中风险 (部分未实名 / 多收件人 / 少量 COD 逾期)
  - 5%  高风险 (大额低报 / 危险品锂电池 / 国际件 / COD 大额逾期)

性能: 默认 8w 条 ≈ 3-5 分钟 (aiomysql 批量 executemany)
数据源: faker 中文 + numpy 随机
幂等: 重复跑会因 UNIQUE 约束报错, 用 --drop 先清 (⚠ 危险, 清空业务数据)

用法:
  python scripts/gen_10w_data.py                       # 默认 10000 用户 ≈ 8w 条
  python scripts/gen_10w_data.py --users 5000          # 5000 用户 ≈ 4w 条
  python scripts/gen_10w_data.py --min-parcels 1 --max-parcels 8   # 每用户 1~8 票
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

# 把项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faker import Faker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

# ============================================================
# 配置
# ============================================================
# 必须是 region 表里真实存在的省名 (init_business_data.sql 灌了 34 个, 带编码)
CHINESE_PROVINCES = [
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西",
    "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏",
    "新疆",
]

# 必须是 item_category 表里真实存在的类目 (init_business_data.sql 灌了 7 个)
ITEM_CATEGORIES = ["电子产品", "服装", "食品", "化工品", "普通", "锂电池", "液体"]

# 危险品申报的物品类型
DANGEROUS_ITEM_TYPES = ["锂电池", "液体", "粉末", "气雾剂", "腐蚀品", "易燃固体"]

# 包裹状态 (parcel.status)
PARCEL_STATUSES = ["created", "in_transit", "delivered", "returned"]

# COD 状态
COD_STATUSES = ["pending", "paid", "returned", "overdue"]


# ============================================================
# 工具函数
# ============================================================
def _risk_tier() -> str:
    """返回风险分层: normal / medium / high (概率 80/15/5)"""
    r = random.random()
    if r < 0.05:
        return "high"
    elif r < 0.20:
        return "medium"
    else:
        return "normal"


def _user_id(idx: int) -> str:
    """用户 ID: U + 6位数字"""
    return f"U{idx:06d}"


def _now():
    """当前时间 (造 created_at 等字段用)"""
    return datetime.now()


# ============================================================
# 主函数
# ============================================================
async def gen_10w_data(
    n_user: int = 10_000,
    min_parcels: int = 1,
    max_parcels: int = 8,
    batch_size: int = 500,
):
    """
    生成 10w 条物流业务数据 (物流版: 用户/寄件人/收件人/包裹/危险品申报/COD).

    注意: sender_id == user_id (寄件人账号 = 风控主体, 关键约定).
    """
    fake = Faker("zh_CN")
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url, echo=False)

    print("=" * 60)
    print(f"开始生成 10w 条物流业务数据 (用户数: {n_user})")
    print(f"包裹范围: 每用户 {min_parcels}~{max_parcels} 票")
    print("=" * 60)

    now = _now()

    # 1. 风险分层
    print(f"\n[1/6] 分配风险分层 (80% 正常 / 15% 中风险 / 5% 高风险)...")
    user_ids = [_user_id(i) for i in range(1, n_user + 1)]
    user_risk = {uid: _risk_tier() for uid in user_ids}
    n_high = sum(1 for v in user_risk.values() if v == "high")
    n_medium = sum(1 for v in user_risk.values() if v == "medium")
    n_normal = n_user - n_high - n_medium
    print(f"  → 高风险 {n_high}, 中风险 {n_medium}, 正常 {n_normal}")

    # 2. 灌用户 + 寄件人实名 (sender_id = user_id)
    print(f"\n[2/6] 灌用户 + 寄件人 ({n_user} 条)...")
    user_rows = []
    sender_rows = []
    for uid in user_ids:
        risk = user_risk[uid]
        name = fake.name()
        # 高风险用户: 部分未实名 (触发 R001), 企业账号概率高 (大额低报 R025)
        if risk == "high":
            real_name_status = random.choices(
                ["已认证", "未认证", "认证失败"], weights=[0.5, 0.35, 0.15], k=1
            )[0]
            account_type = random.choices(
                ["personal", "enterprise"], weights=[0.6, 0.4], k=1
            )[0]
        elif risk == "medium":
            real_name_status = random.choices(
                ["已认证", "未认证"], weights=[0.8, 0.2], k=1
            )[0]
            account_type = "personal"
        else:
            real_name_status = "已认证"
            account_type = random.choices(
                ["personal", "enterprise"], weights=[0.9, 0.1], k=1
            )[0]
        register_at = now - timedelta(days=random.randint(30, 800))
        user_rows.append((uid, name, real_name_status, account_type, register_at))

        # 寄件人: 手机号/证件号唯一生成
        phone = f"13{random.randint(100000000, 999999999)}"
        id_number = f"{random.randint(110000000000000000, 999999999999999999)}"
        sender_prov = random.choice(CHINESE_PROVINCES)
        sender_rows.append((
            uid,  # sender_id
            name,
            random.choice(["身份证", "护照"]),
            id_number,
            phone,
            fake.address()[:80],
            sender_prov,
            0,  # is_blacklisted (黑名单单独灌, 高风险用户由黑名单规则触发)
        ))

    async with engine.begin() as conn:
        for i in range(0, len(user_rows), batch_size):
            batch = user_rows[i:i + batch_size]
            values = ", ".join([
                f"('{u[0]}', '{u[1]}', '{u[2]}', '{u[3]}', '{u[4]}')"
                for u in batch
            ])
            await conn.execute(text(
                f"INSERT IGNORE INTO user_info "
                f"(user_id, name, real_name_status, account_type, register_at) "
                f"VALUES {values}"
            ))
        for i in range(0, len(sender_rows), batch_size):
            batch = sender_rows[i:i + batch_size]
            values = ", ".join([
                f"('{s[0]}', '{s[1]}', '{s[2]}', '{s[3]}', '{s[4]}', "
                f"'{s[5]}', '{s[6]}', {s[7]})"
                for s in batch
            ])
            await conn.execute(text(
                f"INSERT IGNORE INTO sender_info "
                f"(sender_id, name, id_type, id_number, phone, address, sender_province, is_blacklisted) "
                f"VALUES {values}"
            ))
    print(f"  → {n_user} 用户 + {n_user} 寄件人 (sender_id=user_id)")

    # 3. 灌收件人 (用户数 * 2, 多收件人用户更多)
    print(f"\n[3/6] 灌收件人 (~{n_user * 2} 条)...")
    receiver_rows = []
    receiver_counter = 0
    user_receivers: dict[str, list[str]] = {}
    for uid in user_ids:
        risk = user_risk[uid]
        # 高风险用户 4-6 个收件人 (改派异常 R018 特征), 中风险 2-3, 正常 1-2
        if risk == "high":
            n_recv = random.randint(4, 6)
        elif risk == "medium":
            n_recv = random.randint(2, 3)
        else:
            n_recv = random.randint(1, 2)
        recv_ids = []
        for _ in range(n_recv):
            receiver_counter += 1
            recv_id = f"REC{receiver_counter:08d}"
            prov = random.choice(CHINESE_PROVINCES)
            # 高风险用户代签收概率高 (addr_is_proxy_received)
            is_proxy = 1 if (risk == "high" and random.random() < 0.3) else 0
            receiver_rows.append((
                recv_id,
                fake.name(),
                f"13{random.randint(100000000, 999999999)}",
                fake.address()[:80],
                prov,
                is_proxy,
            ))
            recv_ids.append(recv_id)
        user_receivers[uid] = recv_ids

    async with engine.begin() as conn:
        for i in range(0, len(receiver_rows), batch_size):
            batch = receiver_rows[i:i + batch_size]
            values = ", ".join([
                f"('{r[0]}', '{r[1]}', '{r[2]}', '{r[3]}', '{r[4]}', {r[5]})"
                for r in batch
            ])
            await conn.execute(text(
                f"INSERT IGNORE INTO receiver_info "
                f"(receiver_id, name, phone, address, receiver_province, is_proxy_received) "
                f"VALUES {values}"
            ))
    print(f"  → {len(receiver_rows)} 收件人")

    # 4. 灌包裹 (用户数 * 3, 高风险用户大额低报/国际件/危险品)
    print(f"\n[4/6] 灌包裹 (~{n_user * 3} 条)...")
    parcel_rows = []
    decl_rows = []
    cod_rows = []
    parcel_counter = 0
    for uid in user_ids:
        risk = user_risk[uid]
        n_parcels = random.randint(min_parcels, max_parcels)
        recv_ids = user_receivers[uid]

        for _ in range(n_parcels):
            parcel_counter += 1
            parcel_id = f"P{parcel_counter:09d}"
            receiver_id = random.choice(recv_ids)
            created_at = now - timedelta(days=random.randint(0, 60))

            # ---- 包裹属性按风险分层 ----
            if risk == "high":
                # 高风险: 50% 大额低报 (R025), 30% 国际件 (R005), 30% 危险品 (R002)
                weight_kg = round(random.uniform(15, 80), 2)          # 大重量
                declared_value = round(random.uniform(2000, 6000), 2) # 申报价值偏低 → 低报
                item_category = random.choice(["锂电池", "化工品", "电子产品", "液体"])
                is_international = 1 if random.random() < 0.3 else 0
                piece_count = random.randint(1, 8)
                status = random.choice(["in_transit", "delivered"])
            elif risk == "medium":
                # 中风险: 部分国际件, 申报价值中等
                weight_kg = round(random.uniform(1, 30), 2)
                declared_value = round(random.uniform(100, 3000), 2)
                item_category = random.choice(["电子产品", "服装", "食品", "普通"])
                is_international = 1 if random.random() < 0.1 else 0
                piece_count = random.randint(1, 4)
                status = random.choice(PARCEL_STATUSES)
            else:
                # 正常: 申报价值 = 合理 (价值密度正常)
                weight_kg = round(random.uniform(0.2, 10), 2)
                declared_value = round(random.uniform(20, 1000), 2)
                item_category = random.choice(["服装", "食品", "普通", "电子产品"])
                is_international = 0
                piece_count = random.randint(1, 3)
                status = random.choice(PARCEL_STATUSES)

            parcel_rows.append((
                parcel_id, uid, uid, receiver_id, weight_kg, declared_value,
                item_category, is_international, piece_count, status, created_at,
            ))

            # ---- 危险品申报 (关联 decl 表, 触发 order_is_dangerous_declared) ----
            # 高风险 30% / 中风险 3% / 正常 0.5%; 危险品类目(锂电池/化工品/液体)才申报
            decl_prob = {"high": 0.30, "medium": 0.03, "normal": 0.005}[risk]
            if random.random() < decl_prob and item_category in ("锂电池", "化工品", "液体"):
                decl_rows.append((
                    f"DCL{parcel_counter:09d}",
                    parcel_id,
                    random.choice(DANGEROUS_ITEM_TYPES),
                    1 if "液体" in item_category or random.random() < 0.3 else 0,
                    1 if item_category == "锂电池" else 0,
                    f"http://msds.example.com/{parcel_id}.pdf" if random.random() < 0.5 else None,
                    created_at,
                ))

            # ---- COD 流水 (关联 cod 表, 触发 order_has_cod) ----
            # 高风险 40% 且大额逾期 (R008), 中风险 10%, 正常 2%
            cod_prob = {"high": 0.40, "medium": 0.10, "normal": 0.02}[risk]
            if random.random() < cod_prob:
                amount = round(random.uniform(
                    1000 if risk == "high" else 100, 5000 if risk == "high" else 2000
                ), 2)
                if risk == "high":
                    # 高风险: COD 大额逾期 (R008 特征)
                    cod_status = random.choices(
                        ["overdue", "paid", "pending"], weights=[0.5, 0.3, 0.2], k=1
                    )[0]
                else:
                    cod_status = random.choices(
                        ["paid", "pending", "returned"], weights=[0.7, 0.2, 0.1], k=1
                    )[0]
                days_overdue = random.randint(3, 30) if cod_status == "overdue" else None
                paid_at = created_at + timedelta(days=random.randint(1, 10)) if cod_status == "paid" else None
                returned_at = created_at + timedelta(days=random.randint(1, 10)) if cod_status == "returned" else None
                cod_rows.append((
                    f"COD{parcel_counter:09d}",
                    parcel_id,
                    amount,
                    cod_status,
                    paid_at,
                    returned_at,
                    days_overdue,
                ))

    async with engine.begin() as conn:
        for i in range(0, len(parcel_rows), batch_size):
            batch = parcel_rows[i:i + batch_size]
            values = ", ".join([
                f"('{p[0]}', '{p[1]}', '{p[2]}', '{p[3]}', {p[4]}, {p[5]}, "
                f"'{p[6]}', {p[7]}, {p[8]}, '{p[9]}', '{p[10]}')"
                for p in batch
            ])
            await conn.execute(text(
                f"INSERT IGNORE INTO parcel "
                f"(parcel_id, user_id, sender_id, receiver_id, weight_kg, declared_value, "
                f"item_category, is_international, piece_count, status, created_at) "
                f"VALUES {values}"
            ))
    print(f"  → {len(parcel_rows)} 包裹")

    # 5. 灌危险品申报 + COD (依赖包裹已插入)
    print(f"\n[5/6] 灌危险品申报 (~{len(parcel_rows) * 5 // 100} 条) + COD (~{len(parcel_rows) * 15 // 100} 条)...")
    if decl_rows:
        async with engine.begin() as conn:
            for i in range(0, len(decl_rows), batch_size):
                batch = decl_rows[i:i + batch_size]
                values = ", ".join([
                    "('{0}', '{1}', '{2}', {3}, {4}, {5}, '{6}')".format(
                        d[0], d[1], d[2], d[3], d[4],
                        "'" + d[5] + "'" if d[5] else "NULL",
                        d[6],
                    )
                    for d in batch
                ])
                await conn.execute(text(
                    f"INSERT IGNORE INTO dangerous_declaration "
                    f"(decl_id, parcel_id, item_type, is_liquid, is_battery, msds_url, declared_at) "
                    f"VALUES {values}"
                ))
    print(f"  → {len(decl_rows)} 危险品申报")

    if cod_rows:
        async with engine.begin() as conn:
            for i in range(0, len(cod_rows), batch_size):
                batch = cod_rows[i:i + batch_size]
                values = ", ".join([
                    "('{0}', '{1}', {2}, '{3}', {4}, {5}, {6})".format(
                        c[0], c[1], c[2], c[3],
                        "'" + str(c[4]) + "'" if c[4] else "NULL",
                        "'" + str(c[5]) + "'" if c[5] else "NULL",
                        c[6] if c[6] is not None else "NULL",
                    )
                    for c in batch
                ])
                await conn.execute(text(
                    f"INSERT IGNORE INTO cod_transaction "
                    f"(cod_id, parcel_id, amount, cod_status, paid_at, returned_at, days_overdue) "
                    f"VALUES {values}"
                ))
    print(f"  → {len(cod_rows)} COD 流水")

    # 6. 汇总
    total = (
        len(user_rows)
        + len(sender_rows)
        + len(receiver_rows)
        + len(parcel_rows)
        + len(decl_rows)
        + len(cod_rows)
    )
    print(f"\n{'=' * 60}")
    print(f"完成! 总计生成 {total} 条物流业务数据")
    print(f"  - 寄件用户:       {len(user_rows)}")
    print(f"  - 寄件人实名:     {len(sender_rows)}")
    print(f"  - 收件人:         {len(receiver_rows)}")
    print(f"  - 包裹:           {len(parcel_rows)}")
    print(f"  - 危险品申报:     {len(decl_rows)}")
    print(f"  - COD 流水:       {len(cod_rows)}")
    print(f"\n下一步: 跑 gen_risk_data.py / gen_risk_data_with_dates.py 生成评估数据 + train_xgb_model.py 训练")
    print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="10w 条物流业务数据生成 (一次性, 跑完即结束)"
    )
    parser.add_argument("--users", type=int, default=10_000, help="用户数 (默认 10000, 决定总条数)")
    parser.add_argument("--min-parcels", type=int, default=1, help="每用户最少包裹数 (默认 1)")
    parser.add_argument("--max-parcels", type=int, default=8, help="每用户最多包裹数 (默认 8)")
    parser.add_argument("--batch", type=int, default=500, help="批量 insert 批次大小 (默认 500)")
    args = parser.parse_args()

    asyncio.run(gen_10w_data(
        n_user=args.users,
        min_parcels=args.min_parcels,
        max_parcels=args.max_parcels,
        batch_size=args.batch,
    ))

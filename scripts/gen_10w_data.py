"""
医疗风控系统 - 10w 条随机业务数据生成 (异步, 一次性脚本)
================
生成规模 (默认约 10w 条, 可调):
  - 患者 (user_info):            N_USER        (默认 10000)
  - 挂号 (appointment):          N_USER * 3    (平均 3 次/人, 默认 30000)
  - 处方 (prescription):         挂号 * 60%    (默认 18000)
  - 医保结算 (insurance_claim):   挂号 * 50%    (默认 15000)
  - 药品订单 (drug_order):        处方 * 40%    (默认 7200)
  - 总条目:                     ≈ 10w (含医院/医生档案)

风险画像 (自动注入):
  - 80% 正常患者 (少量就诊, 小额结算, 本人收件)
  - 15% 中风险 (高频就诊 10-20 次 / 异地就医 / 取消率偏高)
  - 5%  高风险 (大额结算 / 深夜就诊 / 1 小时多院结算 / 收件人非本人 / 处方超量)

性能: 默认 10w 条 ≈ 3-5 分钟 (aiomysql 批量 executemany)
数据源: faker 中文 + numpy 随机
幂等: 重复跑会因主键冲突报错, 用 --drop 先清 (⚠ 危险, 清空业务数据)
"""
import argparse
import asyncio
import hashlib
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
PROVINCE_CITIES = [
    ("江苏省", ["南京市", "苏州市", "无锡市"]),
    ("上海市", ["上海市"]),
    ("浙江省", ["杭州市", "宁波市", "温州市"]),
    ("安徽省", ["合肥市", "芜湖市"]),
    ("山东省", ["济南市", "青岛市"]),
    ("广东省", ["广州市", "深圳市"]),
]
HOSPITAL_LEVELS = ["三甲", "三乙", "二甲", "二乙", "社区"]
DEPARTMENTS = ["心内科", "呼吸科", "消化科", "神经内科", "内分泌科", "骨科", "普内科", "精神科", "中医科", "全科"]
DOCTOR_TITLES = ["主任医师", "副主任医师", "主治医师", "住院医师"]
INSURANCE_TYPES = ["职工医保", "居民医保", "新农合", "自费"]
DIAGNOSIS_CODES = ["I10", "E11.9", "J06.9", "K29.5", "G43.9", "F41.1", "M54.5", "N39.0"]
DRUGS = [
    ("苯磺酸氨氯地平片", "处方药", 6.5),
    ("二甲双胍片", "处方药", 4.2),
    ("奥美拉唑肠溶胶囊", "处方药", 6.0),
    ("阿普唑仑片", "精神药品", 3.0),
    ("佐米曲普坦片", "处方药", 50.0),
    ("感冒灵颗粒", "OTC", 9.3),
    ("维生素C片", "OTC", 9.9),
    ("布洛芬缓释胶囊", "OTC", 12.5),
]


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


def _rand_time_in_days(days: int = 180) -> datetime:
    """近 N 天内的随机时间"""
    return datetime.now() - timedelta(
        days=random.randint(0, days),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )


# ============================================================
# 主函数
# ============================================================
async def gen_10w_data(
    n_user: int = 10_000,
    n_hospital: int = 30,
    doctor_per_hospital: int = 6,
    batch_size: int = 500,
    drop: bool = False,
):
    """生成约 10w 条随机医疗业务数据."""
    fake = Faker("zh_CN")
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url, echo=False)

    print("=" * 60)
    print(f"开始生成医疗业务数据 (患者数: {n_user})")
    print(f"医院: {n_hospital} 家, 每院医生 {doctor_per_hospital} 名")
    print("=" * 60)

    async with engine.begin() as conn:
        # 0. (可选) 清空业务表
        if drop:
            print("\n[0] --drop: 清空业务表...")
            for tbl in ["drug_order", "insurance_claim", "prescription",
                        "appointment", "doctor", "hospital", "user_info", "blacklist_extra"]:
                await conn.execute(text(f"DELETE FROM {tbl}"))
            print("  清空完成")

        # 1. 医院档案 (不覆盖 init 种子的 H001-H006)
        print(f"\n[1] 生成 {n_hospital} 家医院...")
        hospitals = []
        for i in range(1, n_hospital + 1):
            hid = f"HG{i:04d}"
            prov, cities = random.choice(PROVINCE_CITIES)
            hospitals.append((
                hid,
                f"{prov[:2]}第{i}人民医院",
                random.choice(HOSPITAL_LEVELS),
                prov,
                random.choice(cities),
                1 if random.random() < 0.9 else 0,
            ))
        for i in range(0, len(hospitals), batch_size):
            await conn.execute(text("""
                INSERT IGNORE INTO hospital (hospital_id, name, level, province, city, is_insured)
                VALUES (:hid, :name, :level, :prov, :city, :ins)
            """), [
                {"hid": h[0], "name": h[1], "level": h[2], "prov": h[3], "city": h[4], "ins": h[5]}
                for h in hospitals[i:i + batch_size]
            ])
        all_hospital_ids = [h[0] for h in hospitals] + ["H001", "H002", "H003", "H004", "H005"]

        # 2. 医生档案
        n_doctor = n_hospital * doctor_per_hospital
        print(f"\n[2] 生成 {n_doctor} 名医生...")
        doctors = []
        for i in range(1, n_doctor + 1):
            did = f"DG{i:05d}"
            doctors.append((
                did, fake.name(),
                random.choice(all_hospital_ids),
                random.choice(DEPARTMENTS),
                random.choice(DOCTOR_TITLES),
                f"LIC2{i:07d}",
            ))
        for i in range(0, len(doctors), batch_size):
            await conn.execute(text("""
                INSERT IGNORE INTO doctor (doctor_id, name, hospital_id, department, title, license_no)
                VALUES (:did, :name, :hid, :dept, :title, :lic)
            """), [
                {"did": d[0], "name": d[1], "hid": d[2], "dept": d[3], "title": d[4], "lic": d[5]}
                for d in doctors[i:i + batch_size]
            ])
        all_doctor_ids = [d[0] for d in doctors]

        # 3. 患者档案 (带风险分层)
        print(f"\n[3] 生成 {n_user} 名患者...")
        users = []       # (user_id, name, tier, province)
        user_rows = []
        for i in range(1, n_user + 1):
            uid = f"PU{i:06d}"
            name = fake.name()
            tier = _risk_tier()
            prov = random.choice(PROVINCE_CITIES)[0]
            users.append((uid, name, tier, prov))
            id_hash = hashlib.sha256(f"idcard_{uid}".encode()).hexdigest()
            user_rows.append({
                "uid": uid, "name": name, "idh": id_hash,
                "mc": f"MC7{i:08d}", "phone": f"136{i:08d}",
                "itype": random.choice(INSURANCE_TYPES), "prov": prov,
                "reg": (_rand_time_in_days(365)).strftime("%Y-%m-%d %H:%M:%S"),
            })
        for i in range(0, len(user_rows), batch_size):
            await conn.execute(text("""
                INSERT IGNORE INTO user_info
                (user_id, name, id_card_hash, medical_card_no, phone, insurance_type, insured_province, register_at)
                VALUES (:uid, :name, :idh, :mc, :phone, :itype, :prov, :reg)
            """), user_rows[i:i + batch_size])

        # 4. 挂号 + 处方 + 结算 + 药品订单 (按风险分层造行为)
        print("\n[4] 生成诊疗流水 (挂号/处方/结算/药品订单)...")
        appt_rows, rx_rows, claim_rows, do_rows = [], [], [], []
        appt_seq = rx_seq = clm_seq = do_seq = 0

        for uid, name, tier, prov in users:
            # 每层就诊次数: 正常 1-4, 中风险 6-15, 高风险 8-20
            if tier == "normal":
                n_visits = random.randint(1, 4)
            elif tier == "medium":
                n_visits = random.randint(6, 15)
            else:
                n_visits = random.randint(8, 20)
            # 高风险 30% 概率走"1 小时多院结算"盗刷模式
            fraud_burst = (tier == "high" and random.random() < 0.3)
            # 高风险 40% 概率异地就医
            cross_region = (tier == "high" and random.random() < 0.4) or (tier == "medium" and random.random() < 0.15)

            for v in range(n_visits):
                if fraud_burst:
                    # 盗刷: 全部集中在"最近 1 小时", 且每次换医院
                    ct = datetime.now() - timedelta(minutes=random.randint(0, 55))
                    hid = random.choice(all_hospital_ids)
                else:
                    ct = _rand_time_in_days(180)
                    # 正常患者固定 1-2 家医院, 高风险多院
                    hid = random.choice(all_hospital_ids) if tier != "normal" else \
                        all_hospital_ids[hash(uid) % 3]

                # 夜间单据: 高风险 30% 概率
                if tier == "high" and random.random() < 0.3:
                    ct = ct.replace(hour=random.randint(0, 5))

                # --- 挂号 ---
                appt_seq += 1
                status = "已就诊"
                if tier in ("medium", "high") and random.random() < 0.25:
                    status = "已取消"
                appt_rows.append({
                    "aid": f"APG{appt_seq:08d}", "uid": uid, "hid": hid,
                    "dept": random.choice(DEPARTMENTS),
                    "did": random.choice(all_doctor_ids) if random.random() < 0.8 else None,
                    "phone": f"136{int(uid[2:]):08d}",
                    "at": (ct + timedelta(days=random.randint(0, 3))).strftime("%Y-%m-%d %H:%M:%S"),
                    "amt": random.choice([10, 25, 35, 50, 100]),
                    "status": status,
                    "ct": ct.strftime("%Y-%m-%d %H:%M:%S"),
                })

                # --- 处方 (60%) ---
                doctor_id = random.choice(all_doctor_ids)
                rx_id = None
                if random.random() < 0.6:
                    rx_seq += 1
                    rx_id = f"RXG{rx_seq:08d}"
                    drug_name, category, price = random.choice(DRUGS)
                    # 处方超量: 高风险 25% 概率数量 > 30
                    qty = random.randint(35, 80) if (tier == "high" and random.random() < 0.25) \
                        else random.randint(3, 14)
                    amount = round(price * qty, 2)
                    rx_rows.append({
                        "rx": rx_id, "did": doctor_id, "uid": uid, "hid": hid,
                        "diag": random.choice(DIAGNOSIS_CODES),
                        "items": f'[{{"drug": "{drug_name}", "quantity": {qty}}}]',
                        "icnt": 1, "qty": qty, "amt": amount,
                        "ins": 1 if random.random() < 0.85 else 0,
                        "ct": (ct + timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S"),
                    })

                # --- 医保结算 (50%) ---
                if random.random() < 0.5:
                    clm_seq += 1
                    # 大额结算: 高风险 30% 概率 > 2 万
                    if tier == "high" and random.random() < 0.3:
                        total = round(random.uniform(20000, 80000), 2)
                    elif tier == "medium":
                        total = round(random.uniform(1000, 12000), 2)
                    else:
                        total = round(random.uniform(100, 3000), 2)
                    claim_rows.append({
                        "cid": f"CLG{clm_seq:08d}", "uid": uid, "hid": hid,
                        "amt": total, "iamt": round(total * random.uniform(0.5, 0.85), 2),
                        "status": random.choice(["已结算", "已结算", "待审核"]),
                        "ct": (ct + timedelta(minutes=40)).strftime("%Y-%m-%d %H:%M:%S"),
                    })

                # --- 药品订单 (处方的 40%) ---
                if rx_id and random.random() < 0.4:
                    do_seq += 1
                    drug_name, category, price = random.choice(DRUGS)
                    qty = random.randint(1, 5)
                    # 代购: 高风险 50% 概率收件人非本人 + 金额放大
                    receiver = name
                    if tier == "high" and random.random() < 0.5:
                        receiver = fake.name()
                        qty = random.randint(8, 25)
                    do_rows.append({
                        "doid": f"DOG{do_seq:08d}", "rx": rx_id, "uid": uid,
                        "drug": drug_name, "qty": qty, "cat": category,
                        "otc": 1 if category == "OTC" else 0,
                        "recv": receiver,
                        "amt": round(price * qty, 2),
                        "ct": (ct + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
                    })

        # 批量写库
        print(f"  挂号 {len(appt_rows)}, 处方 {len(rx_rows)}, 结算 {len(claim_rows)}, 药品订单 {len(do_rows)}")
        for i in range(0, len(appt_rows), batch_size):
            await conn.execute(text("""
                INSERT IGNORE INTO appointment
                (appt_id, user_id, hospital_id, department, doctor_id, phone, appt_time, pay_amount, appt_status, create_time)
                VALUES (:aid, :uid, :hid, :dept, :did, :phone, :at, :amt, :status, :ct)
            """), appt_rows[i:i + batch_size])
        for i in range(0, len(rx_rows), batch_size):
            await conn.execute(text("""
                INSERT IGNORE INTO prescription
                (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, items, item_count, total_quantity, total_amount, is_insured, create_time)
                VALUES (:rx, :did, :uid, :hid, :diag, :items, :icnt, :qty, :amt, :ins, :ct)
            """), rx_rows[i:i + batch_size])
        for i in range(0, len(claim_rows), batch_size):
            await conn.execute(text("""
                INSERT IGNORE INTO insurance_claim
                (claim_id, user_id, hospital_id, total_amount, insured_amount, claim_status, submit_at, create_time)
                VALUES (:cid, :uid, :hid, :amt, :iamt, :status, :ct, :ct)
            """), claim_rows[i:i + batch_size])
        for i in range(0, len(do_rows), batch_size):
            await conn.execute(text("""
                INSERT IGNORE INTO drug_order
                (drug_order_id, rx_id, user_id, drug_name, quantity, drug_category, is_otc, receiver_name, total_amount, create_time)
                VALUES (:doid, :rx, :uid, :drug, :qty, :cat, :otc, :recv, :amt, :ct)
            """), do_rows[i:i + batch_size])

        # 5. 汇总
        print("\n[5] 汇总:")
        for label, tbl in [
            ("医院", "hospital"), ("医生", "doctor"), ("患者", "user_info"),
            ("挂号", "appointment"), ("处方", "prescription"),
            ("医保结算", "insurance_claim"), ("药品订单", "drug_order"),
        ]:
            cnt = (await conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))).scalar()
            print(f"  {label:<6} {cnt} 条")

    await engine.dispose()
    print("\n完成! 下一步: python scripts/gen_risk_data.py 跑风控评估")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造约 10w 条医疗业务数据 (患者/挂号/处方/结算/药品订单, 含风险分层)"
    )
    parser.add_argument("--n-user", type=int, default=10_000, help="患者数 (默认 10000)")
    parser.add_argument("--n-hospital", type=int, default=30, help="医院数 (默认 30)")
    parser.add_argument("--doctor-per-hospital", type=int, default=6, help="每院医生数 (默认 6)")
    parser.add_argument("--batch-size", type=int, default=500, help="批量插入大小 (默认 500)")
    parser.add_argument("--drop", action="store_true", help="⚠ 危险: 先清空业务表再生成")
    args = parser.parse_args()
    asyncio.run(gen_10w_data(
        n_user=args.n_user,
        n_hospital=args.n_hospital,
        doctor_per_hospital=args.doctor_per_hospital,
        batch_size=args.batch_size,
        drop=args.drop,
    ))

"""
生成有风险行为的患者测试数据 (医疗版, 异步).
支持 --count 指定生成用户数 (默认 5).

5 种风险模式轮换生成 (对应 4 大医疗风控场景):
  模式 1: 医保卡盗刷 (1 小时内在 3 家不同医院结算, 触发 R001)
  模式 2: 医生统方关联患者 (D005 医生 1 天内开 ≥50 张处方 ≥10 患者, 触发 R002)
  模式 3: 挂号黄牛 (同一手机号 24h 内取消挂号 ≥5 次, 触发 R005)
  模式 4: 处方超量 (单张处方药品数量 36 > 上限 30, 触发 R008)
  模式 5: 药品代购 (收件人 ≠ 本人 + 累计金额 > 5000, 触发 R018)

例:
  python scripts/gen_risky_users.py                # 默认 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 × 5 模式)
  python scripts/gen_risky_users.py --count 1      # 只 1 个 (RISK001, 医保卡盗刷模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 用户再生成

风险模式轮换逻辑: idx % 5, 所以 count=30 → 6 套各 5 个 = 30 个; count=7 → 模式 1-5 + 模式 1-2 = 7 个

依赖: 先跑 python scripts/init_db.py (医院 H001-H006 / 医生 D001-D012 种子数据)
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# 5 种风险模式
RISK_MODES = ["医保卡盗刷", "医生统方", "挂号黄牛", "处方超量", "药品代购"]

# 统方演示医生 (init_business_data.sql 种子数据)
TONGFANG_DOCTOR = "D005"
TONGFANG_HOSPITAL = "H002"

# 模式 2 共享计数: 第 1 个统方模式用户负责把 D005 的处方量堆到阈值
_tongfang_initialized = False


async def _insert_user(conn, user_id: str, name: str, phone: str, province: str = "江苏省"):
    """插一条 RISK 患者档案"""
    suffix = user_id[4:]
    await conn.execute(text("""
        INSERT IGNORE INTO user_info
        (user_id, name, id_card_hash, medical_card_no, phone, insurance_type, insured_province, register_at)
        VALUES (:uid, :name, :idh, :mc, :phone, '居民医保', :prov, DATE_SUB(NOW(), INTERVAL 30 DAY))
    """), {
        "uid": user_id, "name": name,
        "idh": f"riskhash{suffix}" + "0" * (64 - len(f"riskhash{suffix}")),
        "mc": f"MC98{suffix}00", "phone": phone, "prov": province,
    })


async def _gen_card_fraud_user(conn, user_id: str):
    """模式 1: 医保卡盗刷 (1 小时内在 H001/H002/H003 各结算 1 笔, 触发 R001)"""
    await _insert_user(conn, user_id, f"盗刷患者{user_id[4:]}", f"1371111{user_id[4:]}")
    for i, (hid, amount) in enumerate([("H001", 860), ("H002", 1200), ("H003", 950)], 1):
        # create_time 在最近 30 分钟内 (feature 按 create_time 统计 1 小时窗口)
        await conn.execute(text("""
            INSERT IGNORE INTO insurance_claim
            (claim_id, user_id, hospital_id, total_amount, insured_amount, claim_status, submit_at, create_time)
            VALUES (:cid, :uid, :hid, :amt, :iamt, '待审核',
                    DATE_SUB(NOW(), INTERVAL :m MINUTE), DATE_SUB(NOW(), INTERVAL :m MINUTE))
        """), {
            "cid": f"CLM_{user_id[4:]}_{i:02d}", "uid": user_id, "hid": hid,
            "amt": amount, "iamt": round(amount * 0.7, 2), "m": i * 8,
        })


async def _gen_tongfang_user(conn, user_id: str):
    """模式 2: 医生统方关联患者.

    第 1 个统方模式用户负责堆量: D005 1 天内开 44 张处方给 11 个 EXTRA 患者,
    之后每个统方模式用户再拿 2 张 → D005 当日处方 ≥50 且患者 ≥10 (触发 R002).
    """
    global _tongfang_initialized
    await _insert_user(conn, user_id, f"统方患者{user_id[4:]}", f"1372222{user_id[4:]}")

    if not _tongfang_initialized:
        _tongfang_initialized = True
        # 11 个 EXTRA 患者 × 4 张处方 = 44 张 (全部今天开)
        for p in range(1, 12):
            extra_id = f"EXTF{p:03d}"
            await _insert_user(conn, extra_id, f"统方关联{p}", f"137333300{p:02d}")
            for r in range(1, 5):
                await conn.execute(text("""
                    INSERT IGNORE INTO prescription
                    (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, items,
                     item_count, total_quantity, total_amount, is_insured, create_time)
                    VALUES (:rx, :doc, :uid, :hid, 'K29.5',
                            '[{"drug": "奥美拉唑肠溶胶囊", "quantity": 7}]',
                            1, 7, 42.00, 1, DATE_SUB(NOW(), INTERVAL :h HOUR))
                """), {
                    "rx": f"RX_EXTF{p:03d}_{r}", "doc": TONGFANG_DOCTOR,
                    "uid": extra_id, "hid": TONGFANG_HOSPITAL, "h": r,
                })

    # 本用户拿 2 张 D005 的处方 (今天)
    for r in range(1, 3):
        await conn.execute(text("""
            INSERT IGNORE INTO prescription
            (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, items,
             item_count, total_quantity, total_amount, is_insured, create_time)
            VALUES (:rx, :doc, :uid, :hid, 'K29.5',
                    '[{"drug": "奥美拉唑肠溶胶囊", "quantity": 7}]',
                    1, 7, 42.00, 1, DATE_SUB(NOW(), INTERVAL :h HOUR))
        """), {
            "rx": f"RX_{user_id[4:]}_{r:02d}", "doc": TONGFANG_DOCTOR,
            "uid": user_id, "hid": TONGFANG_HOSPITAL, "h": r,
        })


async def _gen_scalper_user(conn, user_id: str):
    """模式 3: 挂号黄牛 (同一手机号 24h 内取消挂号 6 次, 触发 R005)"""
    phone = f"1390000{user_id[4:]}"
    await _insert_user(conn, user_id, f"黄牛患者{user_id[4:]}", phone)
    # 6 次取消 + 1 次正常预约, 全用同一手机号 (黄牛给不同人抢号也用这个号)
    for i, status in enumerate(["已取消"] * 6 + ["已预约"], 1):
        await conn.execute(text("""
            INSERT IGNORE INTO appointment
            (appt_id, user_id, hospital_id, department, doctor_id, phone,
             appt_time, pay_amount, appt_status, create_time)
            VALUES (:aid, :uid, 'H001', '心内科', 'D001', :phone,
                    DATE_ADD(NOW(), INTERVAL :h HOUR), 50.00, :status,
                    DATE_SUB(NOW(), INTERVAL :h2 HOUR))
        """), {
            "aid": f"APPT_{user_id[4:]}_{i:02d}", "uid": user_id,
            "phone": phone, "h": i * 2, "status": status, "h2": i,
        })


async def _gen_overdose_user(conn, user_id: str):
    """模式 4: 处方超量 (单张处方 36 片 > 上限 30, 触发 R008)"""
    await _insert_user(conn, user_id, f"超量患者{user_id[4:]}", f"1374444{user_id[4:]}")
    await conn.execute(text("""
        INSERT IGNORE INTO prescription
        (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, items,
         item_count, total_quantity, total_amount, is_insured, create_time)
        VALUES (:rx, 'D007', :uid, 'H003', 'F41.1',
                '[{"drug": "阿普唑仑片", "quantity": 36}]',
                1, 36, 108.00, 1, DATE_SUB(NOW(), INTERVAL 2 HOUR))
    """), {"rx": f"RX_{user_id[4:]}_01", "uid": user_id})


async def _gen_proxy_buyer(conn, user_id: str):
    """模式 5: 药品代购 (收件人 ≠ 本人 + 5 单累计 6000 > 5000, 触发 R018)"""
    await _insert_user(conn, user_id, f"代购患者{user_id[4:]}", f"1375555{user_id[4:]}")
    # 先开 1 张普通处方作为药品订单来源
    await conn.execute(text("""
        INSERT IGNORE INTO prescription
        (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, items,
         item_count, total_quantity, total_amount, is_insured, create_time)
        VALUES (:rx, 'D006', :uid, 'H003', 'G43.9',
                '[{"drug": "佐米曲普坦片", "quantity": 6}]',
                1, 6, 300.00, 1, DATE_SUB(NOW(), INTERVAL 1 DAY))
    """), {"rx": f"RX_{user_id[4:]}_01", "uid": user_id})
    # 5 笔药品订单: 收件人是别人, 每单 1200 元 → 累计 6000
    for i in range(1, 6):
        await conn.execute(text("""
            INSERT IGNORE INTO drug_order
            (drug_order_id, rx_id, user_id, drug_name, quantity, drug_category,
             is_otc, receiver_name, total_amount, create_time)
            VALUES (:doid, :rx, :uid, '佐米曲普坦片', 6, '处方药',
                    0, '代购收货人', 1200.00, DATE_SUB(NOW(), INTERVAL :d DAY))
        """), {
            "doid": f"DO_{user_id[4:]}_{i:02d}", "rx": f"RX_{user_id[4:]}_01",
            "uid": user_id, "d": i,
        })


# 5 种模式生成器
MODE_GENERATORS = [
    _gen_card_fraud_user,   # 模式 0: 医保卡盗刷
    _gen_tongfang_user,     # 模式 1: 医生统方
    _gen_scalper_user,      # 模式 2: 挂号黄牛
    _gen_overdose_user,     # 模式 3: 处方超量
    _gen_proxy_buyer,       # 模式 4: 药品代购
]


async def gen_risky_users(count: int = 5, reset: bool = False):
    """生成 N 个 RISK 高风险患者 (5 种模式轮换).

    Args:
        count: 生成用户数 (默认 5). 例: count=30 → RISK001-RISK030 (6 套 × 5 模式).
        reset: 是否先删旧 RISK 用户 + 相关数据 (默认 False, 用 INSERT IGNORE 增量插入).
    """
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 删旧 RISK/EXTF 用户 + 关联数据...")
            # 先删从表 (子表), 再删主表
            for tbl, col in (
                ("drug_order", "user_id"), ("insurance_claim", "user_id"),
                ("prescription", "user_id"), ("appointment", "user_id"),
            ):
                await conn.execute(text(
                    f"DELETE FROM {tbl} WHERE {col} LIKE 'RISK%' OR {col} LIKE 'EXTF%'"
                ))
            await conn.execute(text(
                "DELETE FROM user_info WHERE user_id LIKE 'RISK%' OR user_id LIKE 'EXTF%'"
            ))
            print("  清理完成")

        # 批量生成 N 个 RISK 患者 (5 种模式轮换)
        print(f"[generate] 生成 {count} 个 RISK 高风险患者 (5 模式轮换)...")
        for idx in range(count):
            user_id = f"RISK{idx + 1:03d}"
            mode_idx = idx % 5
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx + 1}/{count}] {user_id} (模式 {mode_idx + 1}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, user_id)

        await conn.commit()

        # 统计
        total_users = (await conn.execute(text(
            "SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'"
        ))).scalar()
        total_appt = (await conn.execute(text(
            "SELECT COUNT(*) FROM appointment WHERE user_id LIKE 'RISK%'"
        ))).scalar()
        total_rx = (await conn.execute(text(
            "SELECT COUNT(*) FROM prescription WHERE user_id LIKE 'RISK%' OR user_id LIKE 'EXTF%'"
        ))).scalar()
        total_claim = (await conn.execute(text(
            "SELECT COUNT(*) FROM insurance_claim WHERE user_id LIKE 'RISK%'"
        ))).scalar()
        total_do = (await conn.execute(text(
            "SELECT COUNT(*) FROM drug_order WHERE user_id LIKE 'RISK%'"
        ))).scalar()

        print("\n[完成] 高风险患者数据生成完成!")
        print(f"  RISK 患者:     {total_users} 个")
        print(f"  RISK 挂号:     {total_appt} 条")
        print(f"  RISK 处方:     {total_rx} 张 (含统方关联 EXTF)")
        print(f"  RISK 结算:     {total_claim} 条")
        print(f"  RISK 药品订单: {total_do} 条")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造 RISK 高风险患者 + 诊疗流水. 默认 5 个, --count 指定数量.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python scripts/gen_risky_users.py                # 5 个 (RISK001-005, 一套)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 × 5 模式)
  python scripts/gen_risky_users.py --count 1      # 1 个 (RISK001, 医保卡盗刷模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
        """,
    )
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 用户数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 用户 + 关联数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))

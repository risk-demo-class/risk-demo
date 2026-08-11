"""
生成有风险行为的参保人测试数据 (医疗版, 异步).
【8 种医疗风险模式】轮换生成 (对应 12 条规则):
  模式 1: 医保卡盗刷   (近 1 小时 3 家医院结算  → R001)
  模式 2: 医生统方     (医生当日 50+ 处方      → R002)
  模式 3: 挂号黄牛     (24h 取消挂号 ≥5 次    → R003)
  模式 4: 处方超量     (单方 40 片             → R004)
  模式 5: 虚假病历     (医生集中开方 + 高频就诊 → R005)
  模式 6: 药品代购     (收件人≠患者 + 累计>5000 → R006)
  模式 7: 异地集中结算 (参保地≠就医地 + 大额    → R007)
  模式 8: 黑医保卡     (黑名单 MC-BLACK-001   → R008 撞黑)

例:
  python scripts/gen_risky_users.py                # 默认 8 个 (RISK001-008)
  python scripts/gen_risky_users.py --count 100    # 100 个 (13 轮 × 8 模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 用户再生成
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

RISK_MODES = ["医保卡盗刷", "医生统方", "挂号黄牛", "处方超量", "虚假病历", "药品代购", "异地集中结算", "黑医保卡"]
MODE_COUNT = len(RISK_MODES)


async def _insert_user(conn, user_id: str, mode_idx: int, card_no: str = None):
    """插入参保人基础档案 (参保地轮换, 黑卡模式用黑名单卡号)"""
    if card_no is None:
        card_no = f"MC-RISK-{user_id}"
    province = ["北京", "上海", "广东", "四川", "浙江"][mode_idx % 5]
    await conn.execute(text("""
        INSERT IGNORE INTO user_info
        (user_id, name, id_card_hash, medical_card_no, phone_no, insurance_type, insure_province, insure_city, register_at)
        VALUES (:uid, :name, :idh, :card, :phone, '城镇职工', :prov, :prov, DATE_SUB(NOW(), INTERVAL 200 DAY))
    """), {
        "uid": user_id, "name": f"风险用户{user_id}", "idh": f"HASH-RISK-{user_id}",
        "card": card_no, "phone": f"139{user_id}0000", "prov": province,
    })


async def _gen_card_theft(conn, user_id: str, mode_idx: int):
    """模式 1: 医保卡盗刷 — 近 1 小时 3 家医院各 1 次结算"""
    await _insert_user(conn, user_id, mode_idx)
    for i, hid in enumerate(["H001", "H003", "H004"], 1):
        await conn.execute(text("""
            INSERT IGNORE INTO insurance_claim
            (claim_id, user_id, hospital_id, total_amount, insured_amount, self_amount, claim_status, submit_at)
            VALUES (:cid, :uid, :hid, 800, 640, 160, '已结算', DATE_SUB(NOW(), INTERVAL :min MINUTE))
        """), {"cid": f"CLM_{user_id}_{i:02d}", "uid": user_id, "hid": hid, "min": i * 15})


async def _gen_doctor_tongfang(conn, user_id: str, mode_idx: int):
    """模式 2: 医生统方 — D001 当日 50 张处方 (轮换 5 个患者)"""
    await _insert_user(conn, user_id, mode_idx)
    patients = ["1001", "1002", "1003", "1004", "1005"]
    for i in range(1, 51):
        pid = patients[i % 5]
        await conn.execute(text("""
            INSERT IGNORE INTO prescription
            (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, diagnosis_name, items, total_amount, is_insured, create_time)
            VALUES (:rx, 'D001', :pid, 'H001', 'I10', '原发性高血压',
                    '[{"drug":"氨氯地平","qty":14}]', 120, 1, DATE_SUB(NOW(), INTERVAL :h HOUR))
        """), {"rx": f"RX_{user_id}_{i:03d}", "pid": pid, "h": (50 - i) // 12})


async def _gen_appt_scalper(conn, user_id: str, mode_idx: int):
    """模式 3: 挂号黄牛 — 24 小时内 6 次挂号全取消"""
    await _insert_user(conn, user_id, mode_idx)
    for i in range(1, 7):
        await conn.execute(text("""
            INSERT IGNORE INTO appointment
            (appt_id, user_id, hospital_id, department, doctor_id, appt_time, pay_amount, appt_status, cancel_time)
            VALUES (:aid, :uid, 'H002', '呼吸内科', 'D003', DATE_SUB(NOW(), INTERVAL :h HOUR), 20, '已取消', DATE_SUB(NOW(), INTERVAL :h2 HOUR))
        """), {"aid": f"APT_{user_id}_{i:02d}", "uid": user_id, "h": 24 - i * 3, "h2": 23 - i * 3})


async def _gen_rx_overdose(conn, user_id: str, mode_idx: int):
    """模式 4: 处方超量 — 单方 40 片 (常规上限 30)"""
    await _insert_user(conn, user_id, mode_idx)
    await conn.execute(text("""
        INSERT IGNORE INTO prescription
        (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, diagnosis_name, items, total_amount, is_insured, create_time)
        VALUES (:rx, 'D002', :uid, 'H001', 'F41', '焦虑状态',
                '[{"drug":"阿普唑仑","qty":40}]', 260, 1, NOW())
    """), {"rx": f"RX_{user_id}_001", "uid": user_id})
    await conn.execute(text("""
        INSERT IGNORE INTO drug_order
        (drug_order_id, rx_id, user_id, drug_name, quantity, drug_category, is_otc, receiver_name, total_amount, create_time)
        VALUES (:dg, :rx, :uid, '阿普唑仑', 40, '处方药', 0, :name, 260, NOW())
    """), {"dg": f"DG_{user_id}_001", "rx": f"RX_{user_id}_001", "uid": user_id, "name": f"风险用户{user_id}"})


async def _gen_fake_record(conn, user_id: str, mode_idx: int):
    """模式 5: 虚假病历 — D003 当日 5 张处方 + 用户近 7 天 3 次就诊"""
    await _insert_user(conn, user_id, mode_idx)
    for i in range(1, 6):
        await conn.execute(text("""
            INSERT IGNORE INTO prescription
            (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, diagnosis_name, items, total_amount, is_insured, create_time)
            VALUES (:rx, 'D003', :uid, 'H002', 'J45', '支气管哮喘',
                    '[{"drug":"沙丁胺醇","qty":7}]', 90, 1, NOW())
        """), {"rx": f"RX_{user_id}_{i:03d}", "uid": user_id})
    for i in range(1, 4):
        await conn.execute(text("""
            INSERT IGNORE INTO appointment
            (appt_id, user_id, hospital_id, department, doctor_id, appt_time, pay_amount, appt_status, cancel_time)
            VALUES (:aid, :uid, 'H002', '呼吸内科', 'D003', DATE_SUB(NOW(), INTERVAL :d DAY), 20, '已就诊', NULL)
        """), {"aid": f"APT_{user_id}_{i:02d}", "uid": user_id, "d": i})


async def _gen_drug_resale(conn, user_id: str, mode_idx: int):
    """模式 6: 药品代购 — 收件人≠患者 + 累计结算 >5000"""
    await _insert_user(conn, user_id, mode_idx)
    # 累计结算 >5000
    for i in range(1, 4):
        await conn.execute(text("""
            INSERT IGNORE INTO insurance_claim
            (claim_id, user_id, hospital_id, total_amount, insured_amount, self_amount, claim_status, submit_at)
            VALUES (:cid, :uid, 'H001', 2000, 1600, 400, '已结算', DATE_SUB(NOW(), INTERVAL :d DAY))
        """), {"cid": f"CLM_{user_id}_{i:02d}", "uid": user_id, "d": i * 5})
    await conn.execute(text("""
        INSERT IGNORE INTO prescription
        (rx_id, doctor_id, user_id, hospital_id, diagnosis_code, diagnosis_name, items, total_amount, is_insured, create_time)
        VALUES (:rx, 'D001', :uid, 'H001', 'I10', '原发性高血压',
                '[{"drug":"氨氯地平","qty":28}]', 240, 1, NOW())
    """), {"rx": f"RX_{user_id}_001", "uid": user_id})
    await conn.execute(text("""
        INSERT IGNORE INTO drug_order
        (drug_order_id, rx_id, user_id, drug_name, quantity, drug_category, is_otc, receiver_name, total_amount, create_time)
        VALUES (:dg, :rx, :uid, '氨氯地平', 28, '处方药', 0, '代购黄牛', 240, NOW())
    """), {"dg": f"DG_{user_id}_001", "rx": f"RX_{user_id}_001", "uid": user_id})


async def _gen_out_region(conn, user_id: str, mode_idx: int):
    """模式 7: 异地集中结算 — 参保地北京, 广州 H004 3 次结算累计 >1 万"""
    await _insert_user(conn, user_id, mode_idx)  # 参保地按轮换, H004 广州保证跨省
    for i in range(1, 4):
        await conn.execute(text("""
            INSERT IGNORE INTO insurance_claim
            (claim_id, user_id, hospital_id, total_amount, insured_amount, self_amount, claim_status, submit_at)
            VALUES (:cid, :uid, 'H004', 4000, 3200, 800, '已结算', DATE_SUB(NOW(), INTERVAL :d DAY))
        """), {"cid": f"CLM_{user_id}_{i:02d}", "uid": user_id, "d": i})


async def _gen_black_card(conn, user_id: str, mode_idx: int):
    """模式 8: 黑医保卡 — 卡号进 risk_blacklist, 撞黑即拒"""
    await _insert_user(conn, user_id, mode_idx, card_no="MC-BLACK-001")
    await conn.execute(text("""
        INSERT IGNORE INTO risk_blacklist (blacklist_type, blacklist_value, reason)
        VALUES ('医保卡', 'MC-BLACK-001', '黑医保卡演示 (R008)')
    """))


_GEN_FUNCS = [
    _gen_card_theft, _gen_doctor_tongfang, _gen_appt_scalper, _gen_rx_overdose,
    _gen_fake_record, _gen_drug_resale, _gen_out_region, _gen_black_card,
]


async def gen_risky_users(count: int = 8, reset: bool = False):
    """生成 count 个高风险参保人 (8 模式轮换)."""
    engine = create_async_engine(settings.DB_URL)
    async with engine.begin() as conn:
        if reset:
            await conn.execute(text("""
                DELETE FROM drug_order WHERE user_id LIKE 'RISK%';
                DELETE FROM insurance_claim WHERE user_id LIKE 'RISK%';
                DELETE FROM prescription WHERE user_id LIKE 'RISK%';
                DELETE FROM appointment WHERE user_id LIKE 'RISK%';
                DELETE FROM user_info WHERE user_id LIKE 'RISK%';
            """))
        for i in range(1, count + 1):
            user_id = f"RISK{i:03d}"
            mode = (i - 1) % MODE_COUNT
            await _GEN_FUNCS[mode](conn, user_id, mode)
    await engine.dispose()
    print(f"✔ 已生成 {count} 个高风险参保人 (RISK001-RISK{count:03d}), 模式轮换: {' / '.join(RISK_MODES)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成医疗风控高风险参保人")
    parser.add_argument("--count", type=int, default=8, help="生成用户数 (默认 8)")
    parser.add_argument("--reset", action="store_true", help="先删除旧 RISK 用户再生成")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
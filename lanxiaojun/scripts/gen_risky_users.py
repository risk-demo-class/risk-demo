"""
教育风控系统 - 生成高风险用户测试数据 (异步)
[P4-L3 2026-08-08] 支持 --count 指定数量 (默认 5).

7 种教育风控模式轮换生成:
  模式 1: 高退费率 (RISK001)       → ER016/ER017(标记/人工审核)
  模式 2: 多设备刷课 (RISK002)     → ER015(人工审核)
  模式 3: 凌晨刷课 (RISK003)       → ER012(标记)
  模式 4: 只报名不学习 (RISK004)   → ER007(标记)
  模式 5: 多投诉 (RISK005)         → ER006(标记)
  模式 6: 深夜高价 (RISK006)       → ER022/ER023(拒绝)
  模式 7: 低评分高价投诉 (RISK007) → ER030/ER024(拒绝/人工审核)
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# 5 种教育风险模式
RISK_MODES = ["高退费率", "多设备刷课", "凌晨刷课", "只报名不学习", "多投诉", "深夜高价", "低评分高价投诉"]


# 课程池 (被引用的课程需存在)
RISK_COURSES = [f"C{i:04d}" for i in range(1, 21)]


async def _ensure_base_data(conn):
    """确保基础词典数据存在 (教师/课程/订单状态)"""
    # 教师 (含 T0006 低评分教师)
    for i in range(1, 7):
        await conn.execute(text("""
            INSERT IGNORE INTO teacher_info (teacher_id, user_id, name, cert_no, teach_years, avg_rating, course_count)
            VALUES (:tid, :uid, :name, :cert, :years, :rating, :cnt)
        """), {
            "tid": f"T{i:04d}", "uid": f"RISK{i:03d}" if i <= 5 else "RISK006",
            "name": f"风险教师{i}", "cert": f"CERT_RISK_{i}",
            "years": 5, "rating": round(4.5 - i * 0.5, 2), "cnt": 10,
        })
    # 课程 (含高价课程 C0021+ 关联低评分教师)
    for cat_idx, cat in enumerate(["考研", "公考", "职业", "语言", "素质"]):
        for i in range(4):
            idx = cat_idx * 4 + i + 1
            await conn.execute(text("""
                INSERT IGNORE INTO course (course_id, name, category, price, total_hours, teacher_id, publish_date, status)
                VALUES (:cid, :name, :cat, :price, :hours, :tid, NOW(), '上架')
            """), {
                "cid": f"C{idx:04d}", "name": f"{cat}课程{idx}",
                "cat": cat, "price": 99 + idx * 500,
                "hours": 40 + idx * 10,
                "tid": f"T{(idx % 5) + 1:04d}",
            })
    # 额外高价课程 (关联低评分教师 T0006, 用于模式 6/7)
    extra_courses = [
        ("C0021", "深夜冲刺班", "职业", 15000, 200, "T0006"),
        ("C0022", "高端一对一", "素质", 12000, 180, "T0006"),
        ("C0023", "名师特训营", "考研", 8000, 160, "T0006"),
        ("C0024", "保过协议班", "公考", 6000, 200, "T0006"),
    ]
    for cid, name, cat, price, hours, tid in extra_courses:
        await conn.execute(text("""
            INSERT IGNORE INTO course (course_id, name, category, price, total_hours, teacher_id, publish_date, status)
            VALUES (:cid, :name, :cat, :price, :hours, :tid, NOW(), '上架')
        """), {
            "cid": cid, "name": name, "cat": cat,
            "price": price, "hours": hours, "tid": tid,
        })


async def _gen_user(conn, user_id: str, name: str, phone: str, role: str = "学生",
                    real_name: int = 1, age_days: int = 30):
    """插入基础用户"""
    register_at = datetime.now() - timedelta(days=age_days)
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name, role, phone, real_name_status, account_age_days, register_at)
        VALUES (:uid, :name, :role, :phone, :real_name, :age, :reg_at)
    """), {
        "uid": user_id, "name": name, "role": role, "phone": phone,
        "real_name": real_name, "age": age_days,
        "reg_at": register_at.strftime("%Y-%m-%d %H:%M:%S"),
    })


async def _gen_order(conn, order_id: str, user_id: str, course_id: str,
                     amount: float, pay_time: datetime, status: str = "已支付"):
    """插入订单"""
    await conn.execute(text("""
        INSERT IGNORE INTO order_info (order_id, user_id, course_id, amount, pay_time, order_status)
        VALUES (:oid, :uid, :cid, :amount, :pay, :status)
    """), {
        "oid": order_id, "uid": user_id, "cid": course_id,
        "amount": amount, "pay": pay_time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
    })


async def _gen_progress(conn, progress_id: str, user_id: str, course_id: str,
                        minutes: int, rate: float, last_active: datetime):
    """插入学习进度"""
    await conn.execute(text("""
        INSERT IGNORE INTO learning_progress (progress_id, user_id, course_id, total_minutes, completion_rate, last_active_at)
        VALUES (:pid, :uid, :cid, :min, :rate, :last)
    """), {
        "pid": progress_id, "uid": user_id, "cid": course_id,
        "min": minutes, "rate": rate,
        "last": last_active.strftime("%Y-%m-%d %H:%M:%S"),
    })


async def _gen_refund(conn, refund_id: str, order_id: str, user_id: str,
                      reason: str, minutes: int, amount: float, apply_time: datetime):
    """插入退费申请"""
    await conn.execute(text("""
        INSERT IGNORE INTO refund_request (refund_id, order_id, user_id, reason, study_minutes_before_refund, refund_amount, status, apply_time)
        VALUES (:rid, :oid, :uid, :reason, :min, :amount, '待审核', :at)
    """), {
        "rid": refund_id, "oid": order_id, "uid": user_id,
        "reason": reason, "min": minutes, "amount": amount,
        "at": apply_time.strftime("%Y-%m-%d %H:%M:%S"),
    })


async def _gen_complaint(conn, complaint_id: str, user_id: str, course_id: str,
                         ctype: str, content: str, create_time: datetime):
    """插入投诉"""
    await conn.execute(text("""
        INSERT IGNORE INTO complaint (complaint_id, user_id, course_id, complaint_type, content, status, create_time)
        VALUES (:cid, :uid, :coid, :ctype, :content, '待处理', :ctime)
    """), {
        "cid": complaint_id, "uid": user_id, "coid": course_id,
        "ctype": ctype, "content": content,
        "ctime": create_time.strftime("%Y-%m-%d %H:%M:%S"),
    })


async def _gen_device(conn, device_id: str, user_id: str, ip: str, os_name: str, browser: str):
    """插入设备指纹"""
    now = datetime.now()
    await conn.execute(text("""
        INSERT IGNORE INTO device_fingerprint (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser, ip)
        VALUES (:did, :uid, :hash, :first, :last, :os, :browser, :ip)
    """), {
        "did": device_id, "uid": user_id,
        "hash": f"fp_{device_id}",
        "first": (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
        "last": now.strftime("%Y-%m-%d %H:%M:%S"),
        "os": os_name, "browser": browser, "ip": ip,
    })


# ============================
# 7 种风险模式
# ============================

async def mode_high_refund_rate(conn, user_id: str):
    """模式 1: 偏高退费率 — 10 门报名 + 3~4 门退费 (退费 ~30%, 不再极端)"""
    await _gen_user(conn, user_id, "偏高退费用户", "13800000001", age_days=60)
    refund_count = random.randint(4, 5)  # 退费率 ≈ 40-50% (稳定触发 ER016/ER017)
    now = datetime.now()
    for i in range(1, 11):
        cid = RISK_COURSES[(i - 1) % len(RISK_COURSES)]
        oid = f"ORD_HR_{user_id[4:]}_{i:02d}"
        pay_time = now - timedelta(days=60 - i * 3)
        await _gen_order(conn, oid, user_id, cid, 2999.00, pay_time)
        # 部分申请退费, 学了一段时间后退
        if i <= refund_count:
            await _gen_refund(conn, f"RF_HR_{user_id[4:]}_{i:02d}", oid, user_id,
                              "课程不符合预期", random.randint(60, 300), 2999.00,
                              pay_time + timedelta(days=random.randint(3, 10)))
        # 学习进度: 中等偏低完成率
        await _gen_progress(conn, f"LP_HR_{user_id[4:]}_{i:02d}", user_id, cid,
                            random.randint(60, 200), round(random.uniform(10, 30), 2),
                            pay_time + timedelta(hours=random.randint(2, 12)))
    # 多设备
    for j in range(3):
        await _gen_device(conn, f"DEV_HR_{user_id[4:]}_{j}", user_id,
                          f"10.0.0.{j+1}", "Windows 10", "Chrome 120")


async def mode_multi_device(conn, user_id: str):
    """模式 2: 多设备刷课 — 3 门课, 3~4 个设备, 偶尔凌晨"""
    await _gen_user(conn, user_id, "多设备用户", "13800000002", age_days=90)
    now = datetime.now()
    for i in range(1, 4):
        cid = RISK_COURSES[i]
        oid = f"ORD_MD_{user_id[4:]}_{i:02d}"
        await _gen_order(conn, oid, user_id, cid, 1999.00, now - timedelta(days=30))
        # 完成率正常偏快, 不在凌晨 (非刷课特征)
        await _gen_progress(conn, f"LP_MD_{user_id[4:]}_{i:02d}", user_id, cid,
                            random.randint(200, 400), round(random.uniform(50, 80), 2),
                            now - timedelta(hours=random.randint(8, 22)))
    # 3~4 个设备 (略多但不算极端)
    device_count = random.randint(3, 4)
    for j in range(device_count):
        os_name = random.choice(["Windows 11", "Android 13", "iOS 17", "macOS 14"])
        browser = random.choice(["Chrome 121", "Safari 17", "Firefox 120", "Chrome Mobile"])
        await _gen_device(conn, f"DEV_MD_{user_id[4:]}_{j}", user_id,
                          f"10.0.1.{j+1}", os_name, browser)


async def mode_night_session(conn, user_id: str):
    """模式 3: 凌晨学习 — 凌晨时段短时间学习"""
    await _gen_user(conn, user_id, "凌晨学习", "13800000003", age_days=15)
    now = datetime.now()
    for i in range(1, 6):
        cid = RISK_COURSES[(i * 3) % len(RISK_COURSES)]
        oid = f"ORD_NS_{user_id[4:]}_{i:02d}"
        pay_time = now - timedelta(days=10)
        await _gen_order(conn, oid, user_id, cid, 3999.00, pay_time)
        # 凌晨 0-5 点学习, 完成率中等 (刷课时长)
        night_time = now.replace(hour=random.randint(0, 5), minute=random.randint(0, 59))
        await _gen_progress(conn, f"LP_NS_{user_id[4:]}_{i:02d}", user_id, cid,
                            random.randint(30, 80), round(random.uniform(30, 60), 2),
                            night_time)


async def mode_enroll_no_study(conn, user_id: str):
    """模式 4: 低学习投入 — 大量报名, 学习进度很低"""
    await _gen_user(conn, user_id, "低学习投入", "13800000004", age_days=7)
    now = datetime.now()
    for i in range(1, 7):  # 少报几门 (6 门)
        cid = RISK_COURSES[(i * 2) % len(RISK_COURSES)]
        oid = f"ORD_ES_{user_id[4:]}_{i:02d}"
        await _gen_order(conn, oid, user_id, cid, 4999.00,
                         now - timedelta(days=random.randint(1, 5)))
        # 学了一点但不深入
        await _gen_progress(conn, f"LP_ES_{user_id[4:]}_{i:02d}", user_id, cid,
                            random.randint(10, 60), round(random.uniform(5, 15), 2),
                            now - timedelta(days=random.randint(0, 2)))


async def mode_high_complaint(conn, user_id: str):
    """模式 5: 偏高投诉 — 报名 4 门 + 2~3 条投诉"""
    await _gen_user(conn, user_id, "偏高投诉用户", "13800000005", age_days=120)
    now = datetime.now()
    for i in range(1, 5):
        cid = RISK_COURSES[(i + 10) % len(RISK_COURSES)]
        oid = f"ORD_HC_{user_id[4:]}_{i:02d}"
        pay_time = now - timedelta(days=30)
        await _gen_order(conn, oid, user_id, cid, 5999.00, pay_time)
        await _gen_progress(conn, f"LP_HC_{user_id[4:]}_{i:02d}", user_id, cid,
                            random.randint(100, 200), round(random.uniform(20, 40), 2),
                            pay_time + timedelta(hours=2))
        # 只投诉部分订单
        if i <= random.randint(2, 3):
            await _gen_complaint(conn, f"CMP_HC_{user_id[4:]}_{i:02d}", user_id, cid,
                                 random.choice(["虚假宣传", "师资不符", "侵权盗版"]),
                                 f"课程{i}存在质量问题",
                                 pay_time + timedelta(days=random.randint(1, 5)))


async def mode_night_high_price(conn, user_id: str):
    """模式 6: 深夜高价课 — 新用户 + 高价课程 + 凌晨下单
    触发规则: ER022(95/拒绝) course_price>=10000 AND order_pay_hour>=23
             ER023(90/拒绝) order_amount>=3000 AND account_age<=3 AND order_pay_hour>=22
             ER008(70/人工审核) account_age<=1 AND course_price>=3000
    """
    await _gen_user(conn, user_id, "深夜高价用户", "13800000006", age_days=1)
    now = datetime.now()
    # 2 门高价课程, 凌晨下单
    for i in range(1, 3):
        cid = f"C002{i}"  # C0021=15000, C0022=12000
        oid = f"ORD_NH_{user_id[4:]}_{i:02d}"
        pay_time = now.replace(hour=23, minute=random.randint(0, 59))
        await _gen_order(conn, oid, user_id, cid, 15000 if i == 1 else 12000, pay_time)
        # 看完少量内容
        await _gen_progress(conn, f"LP_NH_{user_id[4:]}_{i:02d}", user_id, cid,
                            random.randint(10, 60), round(random.uniform(5, 20), 2),
                            pay_time + timedelta(minutes=random.randint(5, 30)))
    # 新用户特征: 无设备关联(行为特征计0), 新注册
    # 支付账号: 绑定 1 个
    await conn.execute(text("""
        INSERT IGNORE INTO payment_account (account_id, user_id, payment_type, account_hash, bind_time)
        VALUES (:aid, :uid, :type, :hash, NOW())
    """), {"aid": f"PA_NH_{user_id[4:]}", "uid": user_id, "type": "微信",
           "hash": f"hash_nh_{user_id[4:]}"})


async def mode_low_rating_complaint(conn, user_id: str):
    """模式 7: 低评分高价 + 投诉 — 低评分教师课程 + 高价 + 多次投诉
    触发规则: ER030(88/拒绝) teacher_rating<2.0 AND course_price>=3000 AND complaint_count>=2
             ER024(60/人工审核) complaint_count>=3
             ER028(60/人工审核) teacher_rating<3.5 AND course_price>=5000
             ER019(60/人工审核) refund_rate>=0.25 AND course_price>=3000
    """
    await _gen_user(conn, user_id, "低评分投诉用户", "13800000007", age_days=30)
    now = datetime.now()
    # 4 门低评分教师的高价课
    for i in range(1, 5):
        cid = RISK_COURSES[(i + 15) % len(RISK_COURSES)]
        if i <= 2:
            cid = f"C002{i + 2}"  # C0023=8000, C0024=6000 (低评分教师)
        oid = f"ORD_LR_{user_id[4:]}_{i:02d}"
        price = 8000 if i <= 2 else 5000
        pay_time = now - timedelta(days=30)
        await _gen_order(conn, oid, user_id, cid, float(price), pay_time)
        # 看了一些内容
        await _gen_progress(conn, f"LP_LR_{user_id[4:]}_{i:02d}", user_id, cid,
                            random.randint(100, 200), round(random.uniform(30, 60), 2),
                            pay_time + timedelta(hours=2))
        # 投诉 (4 条投诉, 触发 ER024 complaint_count >= 3)
        await _gen_complaint(conn, f"CMP_LR_{user_id[4:]}_{i:02d}", user_id, cid,
                             random.choice(["师资不符", "虚假宣传"]),
                             f"教师水平与宣传严重不符",
                             pay_time + timedelta(days=random.randint(1, 5)))
    # 退 1 门课 (凑 refund_rate 高)
    await _gen_refund(conn, f"RF_LR_{user_id[4:]}_01", f"ORD_LR_{user_id[4:]}_01", user_id,
                      "教师水平差", random.randint(100, 200), 8000.00,
                      now - timedelta(days=15))
    # 多设备 (触发行为特征)
    await _gen_device(conn, f"DEV_LR_{user_id[4:]}_0", user_id, "10.0.3.1", "Windows 10", "Chrome")


# 7 种模式生成器 (两种新模式生成"拒绝"级数据)
MODE_GENERATORS = [
    mode_high_refund_rate,   # 模式 0: 高退费率 — 触发 ER016(标记)/ER017(人工审核)
    mode_multi_device,       # 模式 1: 多设备刷课 — 触发 ER015(人工审核)
    mode_night_session,      # 模式 2: 凌晨刷课 — 触发 ER012(标记)
    mode_enroll_no_study,    # 模式 3: 只报名不学习 — 触发 ER007(标记)
    mode_high_complaint,     # 模式 4: 多投诉 — 触发 ER006(标记)
    mode_night_high_price,   # 模式 5: 深夜高价 — 触发 ER022(拒绝)/ER023(拒绝)
    mode_low_rating_complaint,  # 模式 6: 低评分投诉 — 触发 ER030(拒绝)
]


async def gen_risky_users(count: int = 5, reset: bool = False):
    """生成 N 个 RISK 高风险用户 (7 种教育风控模式轮换)."""
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    engine = create_async_engine(settings.get_database_url_async(), poolclass=NullPool)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 删旧 RISK 用户 + 关联数据...")
            # 按外键依赖顺序删除 (7 种模式涉及 teacher/course)
            tables = [
                "learning_progress", "refund_request", "complaint",
                "order_info", "device_fingerprint", "payment_account",
            ]
            for tbl in tables:
                if tbl in ("course", "teacher_info", "user_info"):
                    continue  # course 无 user_id 列, 单独处理
                await conn.execute(text(f"DELETE FROM {tbl} WHERE user_id LIKE 'RISK%'"))
            # 删课程 (通过 teacher_id 关联到 RISK 教师)
            await conn.execute(text("DELETE FROM course WHERE teacher_id IN (SELECT teacher_id FROM teacher_info WHERE user_id LIKE 'RISK%')"))
            # 删教师
            await conn.execute(text("DELETE FROM teacher_info WHERE user_id LIKE 'RISK%'"))
            # 删用户
            await conn.execute(text("DELETE FROM user_info WHERE user_id LIKE 'RISK%'"))
            print("  清理完成")

        print("[setup] 基础数据 (教师/课程)...")
        await _ensure_base_data(conn)

        print(f"[generate] 生成 {count} 个 RISK 高风险用户 (5 种教育模式轮换)...")
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]

        # 批量插 user_info
        from sqlalchemy.ext.asyncio import AsyncConnection
        await conn.execute(
            text("INSERT IGNORE INTO user_info (user_id, name, role, phone, real_name_status, account_age_days, register_at) VALUES "
                 + ",".join(f"('{u}', 'RISK用户{u[4:]}', '学生', '1380000{int(u[4:]):04d}', 1, 30, NOW())" for u in user_ids))
        )

        for idx, uid in enumerate(user_ids):
            mode_idx = idx % 7
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx+1}/{count}] {uid} (模式 {mode_idx+1}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, uid)

        await conn.commit()

        # 统计
        from sqlalchemy import text as _text
        r = await conn.execute(_text("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'"))
        total_users = r.scalar()
        r = await conn.execute(_text("SELECT COUNT(*) FROM order_info WHERE user_id LIKE 'RISK%'"))
        total_orders = r.scalar()
        r = await conn.execute(_text("SELECT COUNT(*) FROM refund_request WHERE user_id LIKE 'RISK%'"))
        total_refunds = r.scalar()
        r = await conn.execute(_text("SELECT COUNT(*) FROM complaint WHERE user_id LIKE 'RISK%'"))
        total_complaints = r.scalar()

        print(f"\n[完成] 高风险用户数据生成完成!")
        print(f"  RISK 用户:     {total_users} 个")
        print(f"  RISK 订单:     {total_orders} 个")
        print(f"  RISK 退费:     {total_refunds} 条")
        print(f"  RISK 投诉:     {total_complaints} 条")

    await engine.dispose()


if __name__ == "__main__":
    # Windows asyncio 兼容: 避免 Event loop is closed
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    parser = argparse.ArgumentParser(
        description="造 RISK 高风险用户 + 订单/行为数据. 默认 5 个, --count 指定数量.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
例:
  python scripts/gen_risky_users.py                # 5 个 (RISK001-005, 一套)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 x 5 模式)
  python scripts/gen_risky_users.py --count 1      # 1 个 (RISK001, 高退费率模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
        """,
    )
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 用户数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 用户 + 关联数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
"""
生成有风险行为的用户测试数据 (教育行业).
5 种风险模式轮换生成:

  模式 1: 高退费率 (10 报名 + 9 退费, 退费率 90%)
  模式 2: 高频报名 (35 门课, 30 天内)
  模式 3: 高退费金额 (3 门课 + 2 退费大额)
  模式 4: 多设备 (7 个设备指纹)
  模式 5: 0 学时退费 (报名后几分钟就退费)

例:
  python scripts/gen_risky_users.py                # 默认 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030)
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


RISK_MODES = ["高退费率", "高频报名", "高退费金额", "多设备", "0学时退费"]


async def _gen_high_refund_user(conn, user_id: str):
    """模式 1: 高退费率用户 (10 报名 + 9 退费, 退费率 90%)"""
    for i in range(1, 11):
        day_offset = max(1, 30 - i * 3)
        oid = f"ORD_{user_id[4:]}_{i:02d}"
        await conn.execute(text("""
            INSERT IGNORE INTO order_info (order_id, user_id, course_id, total_amount, study_goal, expected_finish_days, status, create_time, payment_time)
            VALUES (:oid, :uid, :cid, :amt, :goal, :exp, :status, DATE_SUB(NOW(), INTERVAL :d1 DAY), DATE_SUB(NOW(), INTERVAL :d2 DAY))
        """), {
            "oid": oid, "uid": user_id, "cid": f"C00{randint(1, 9)}",
            "amt": choice([999, 1599, 1999, 2599, 2999]),
            "goal": "测试学习目标", "exp": 90,
            "status": "已退费" if i <= 9 else "学习中",
            "d1": day_offset, "d2": max(1, day_offset - 1),
        })
    for i in range(1, 10):
        day_offset = max(1, 28 - i * 3)
        await conn.execute(text("""
            INSERT IGNORE INTO refund_request (refund_id, order_id, user_id, reason, study_minutes_before_refund, refund_amount, status, create_time)
            VALUES (:rid, :oid, :uid, :reason, :sm, :amt, '已通过', DATE_SUB(NOW(), INTERVAL :d DAY))
        """), {
            "rid": f"REF_{user_id[4:]}_{i:02d}",
            "oid": f"ORD_{user_id[4:]}_{i:02d}",
            "uid": user_id, "reason": "测试退费原因",
            "sm": randint(100, 500), "amt": choice([999, 1599, 1999, 2599, 2999]),
            "d": day_offset,
        })


async def _gen_high_freq_user(conn, user_id: str):
    """模式 2: 高频报名用户 (35 门课, 30 天内)"""
    base_date = datetime.now() - timedelta(days=25)
    for i in range(35):
        order_date = base_date + timedelta(days=i % 25)
        order_dt = order_date.strftime("%Y-%m-%d %H:%M:%S")
        pay_dt = (order_date + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        await conn.execute(text("""
            INSERT IGNORE INTO order_info (order_id, user_id, course_id, total_amount, study_goal, expected_finish_days, status, create_time, payment_time)
            VALUES (:oid, :uid, :cid, :amt, :goal, :exp, '已支付', :d1, :d2)
        """), {
            "oid": f"ORD_{user_id[4:]}_{i:02d}", "uid": user_id,
            "cid": f"C{randint(1, 20):03d}", "amt": choice([899, 1599, 1999, 2599]),
            "goal": "", "exp": 60, "d1": order_dt, "d2": pay_dt,
        })


async def _gen_high_amount_user(conn, user_id: str):
    """模式 3: 高退费金额用户 (3 门课 + 2 退费大额)"""
    for i, day in enumerate([15, 10, 5], 1):
        await conn.execute(text("""
            INSERT IGNORE INTO order_info (order_id, user_id, course_id, total_amount, study_goal, expected_finish_days, status, create_time, payment_time)
            VALUES (:oid, :uid, :cid, :amt, :goal, :exp, :status, DATE_SUB(NOW(), INTERVAL :d1 DAY), DATE_SUB(NOW(), INTERVAL :d2 DAY))
        """), {
            "oid": f"ORD_{user_id[4:]}_{i:02d}", "uid": user_id,
            "cid": "C013", "amt": 5999, "goal": "转行学习",
            "exp": 180, "status": "已退费" if i <= 2 else "学习中",
            "d1": day, "d2": day - 1,
        })
    for i, day in enumerate([12, 7], 1):
        await conn.execute(text("""
            INSERT IGNORE INTO refund_request (refund_id, order_id, user_id, reason, study_minutes_before_refund, refund_amount, status, create_time)
            VALUES (:rid, :oid, :uid, :reason, :sm, 5999, '待审核', DATE_SUB(NOW(), INTERVAL :d DAY))
        """), {
            "rid": f"REF_{user_id[4:]}_{i:02d}",
            "oid": f"ORD_{user_id[4:]}_{i:02d}",
            "uid": user_id, "reason": "大额退费测试",
            "sm": randint(50, 200), "d": day,
        })


async def _gen_multi_device_user(conn, user_id: str):
    """模式 4: 多设备用户 (7 个设备指纹)"""
    ips = ['10.0.0.1', '10.0.1.1', '172.16.0.1', '172.16.1.1', '192.168.1.1', '192.168.2.1', '192.168.3.1']
    for i in range(7):
        await conn.execute(text("""
            INSERT IGNORE INTO device_fingerprint (device_id, user_id, fingerprint, ip, create_at)
            VALUES (:did, :uid, :fp, :ip, DATE_SUB(NOW(), INTERVAL :d DAY))
        """), {
            "did": f"DEV_{user_id[4:]}_{i:02d}",
            "uid": user_id,
            "fp": f"fp_multi_{user_id[4:]}_{i:02d}",
            "ip": ips[i], "d": (7 - i) * 5,
        })


async def _gen_zero_study_refund_user(conn, user_id: str):
    """模式 5: 0 学时退费用户 (报名后几分钟就退费)"""
    # 3 门课, 都是 0 学时退费
    for i, day in enumerate([3, 2, 1], 1):
        await conn.execute(text("""
            INSERT IGNORE INTO order_info (order_id, user_id, course_id, total_amount, study_goal, expected_finish_days, status, create_time, payment_time)
            VALUES (:oid, :uid, :cid, :amt, :goal, :exp, '已退费', DATE_SUB(NOW(), INTERVAL :d1 DAY), DATE_SUB(NOW(), INTERVAL :d2 DAY))
        """), {
            "oid": f"ORD_{user_id[4:]}_{i:02d}", "uid": user_id,
            "cid": f"C0{randint(1, 9):02d}", "amt": choice([1999, 2599, 3499]),
            "goal": "", "exp": 90, "d1": day, "d2": max(1, day - 1),
        })
        await conn.execute(text("""
            INSERT IGNORE INTO learning_progress (progress_id, user_id, course_id, order_id, total_minutes, last_active_at, completion_rate)
            VALUES (:pid, :uid, :cid, :oid, 0, DATE_SUB(NOW(), INTERVAL :d DAY), 0.0000)
        """), {
            "pid": f"LP_{user_id[4:]}_{i:02d}",
            "uid": user_id, "cid": f"C0{randint(1, 9):02d}",
            "oid": f"ORD_{user_id[4:]}_{i:02d}", "d": day,
        })
        await conn.execute(text("""
            INSERT IGNORE INTO refund_request (refund_id, order_id, user_id, reason, study_minutes_before_refund, refund_amount, status, create_time)
            VALUES (:rid, :oid, :uid, :reason, 0, :amt, '待审核', DATE_SUB(NOW(), INTERVAL :d DAY))
        """), {
            "rid": f"REF_{user_id[4:]}_{i:02d}",
            "oid": f"ORD_{user_id[4:]}_{i:02d}",
            "uid": user_id, "reason": "0学时退费测试",
            "amt": choice([1999, 2599, 3499]), "d": day,
        })


MODE_GENERATORS = [
    _gen_high_refund_user,
    _gen_high_freq_user,
    _gen_high_amount_user,
    _gen_multi_device_user,
    _gen_zero_study_refund_user,
]


# Add random/choice for use in generators
from random import choice, randint


async def gen_risky_users(count: int = 5, reset: bool = False):
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 删旧 RISK 用户 + 关联数据...")
            for tbl in ("refund_request", "learning_progress", "order_info",
                        "device_fingerprint", "user_info"):
                await conn.execute(text(f"DELETE FROM {tbl} WHERE user_id LIKE 'RISK%'"))
            await conn.commit()
            print("  清理完成")

        # 确保基础数据存在
        print("[setup] 确保课程基础数据...")
        for i in range(1, 21):
            await conn.execute(text("""
                INSERT IGNORE INTO course (course_id, name, category, price, teacher_id, total_hours)
                VALUES (:cid, :name, :cat, :price, 'U006', :hours)
            """), {
                "cid": f"C{i:03d}",
                "name": f"测试课程{i}",
                "cat": ['学科辅导','兴趣培养','职业技能','语言学习','考级考证'][i % 5],
                "price": [899, 1599, 1999, 2599, 2999, 3499, 3999, 4999, 5999, 6999][i % 10],
                "hours": [600, 900, 1200, 1500, 1800, 2000, 2400, 3000, 3600, 4800][i % 10],
            })

        # 批量生成 RISK 用户
        print(f"[generate] 生成 {count} 个 RISK 高风险用户 (5 模式轮换)...")
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]

        # 批量插 user_info
        values_str = ",".join(f"('{u}', '{u}号', '学生', 'STU_FAKE_{u[4:]}', '未认证', NOW())" for u in user_ids)
        await conn.execute(
            text(f"INSERT IGNORE INTO user_info (user_id, name, role, student_id, real_name_status, register_at) VALUES {values_str}")
        )

        for idx, user_id in enumerate(user_ids):
            mode_idx = idx % 5
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx+1}/{count}] {user_id} (模式 {mode_idx+1}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, user_id)

        await conn.commit()

        # 统计
        r = await conn.execute(text("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'"))
        total_users = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM order_info WHERE user_id LIKE 'RISK%'"))
        total_orders = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM refund_request WHERE user_id LIKE 'RISK%'"))
        total_refund = r.scalar()

        print(f"\n[完成] 高风险用户数据生成完成!")
        print(f"  RISK 用户:   {total_users} 个")
        print(f"  RISK 报名:   {total_orders} 个")
        print(f"  RISK 退费:   {total_refund} 条")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造 RISK 高风险用户 + 报名/退费. 默认 5 个, --count 指定数量.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python scripts/gen_risky_users.py                # 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个
  python scripts/gen_risky_users.py --reset        # 先删旧数据再生成
        """,
    )
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 用户数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 用户 + 关联数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))

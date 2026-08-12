"""
教育风控系统 - 业务数据生成脚本 (可重复运行)
至少 100 条业务数据: 用户 + 课程 + 报名订单 + 学习进度 + 退费 + 设备指纹
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from random import choice, randint, random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


COURSE_CATEGORIES = ['学科辅导', '兴趣培养', '职业技能', '语言学习', '考级考证', '其他']
ROLES = ['学生', '学生', '学生', '学生', '家长', '老师']
REAL_NAME_STATUSES = ['已认证', '已认证', '已认证', '已认证', '未认证']
ORDER_STATUSES = ['待支付', '已支付', '学习中', '已完成', '已取消', '已退费']
REFUND_REASONS = [
    '时间冲突无法继续', '课程难度不适合', '个人原因退课',
    '经济困难', '找到更合适课程', '不想学了', '内容太简单',
    '工作变动无法学习', '暂时不学了', '课程质量不满意',
]
STUDY_GOALS = [
    '提高成绩到优秀水平', '为升学做准备', '培养兴趣爱好',
    '转行需要技能储备', '为了出国留学', '考证需求',
    '拓展知识面', '工作需要', '考研准备', '',
]
COURSE_NAMES = [
    '高中数学强化班', '初中英语冲刺', 'Python编程入门', '钢琴零基础入门',
    '日语N3备考', '小学奥数思维', 'UI设计实战', '吉他弹唱入门',
    '高考物理冲刺', '雅思口语特训', '会计从业资格', '水彩画基础',
    '网络安全基础', '小学语文阅读', '法语入门A1', '教师资格证',
    '声乐基础训练', '初三化学专题', '数据分析SQL', '素描速成班',
]


async def gen_business_data(count: int = 100, reset: bool = False):
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 清空旧业务数据...")
            for tbl in ("refund_request", "learning_progress", "order_info",
                        "device_fingerprint", "course", "user_info"):
                await conn.execute(text(f"DELETE FROM {tbl}"))
            await conn.commit()
            print("  清理完成")

        # 1. 生成课程 (20 门)
        print("[1/6] 生成课程...")
        for i in range(1, 21):
            cat = COURSE_CATEGORIES[i % 6]
            price = [899, 999, 1299, 1599, 1999, 2199, 2599, 2999, 3299, 3499, 3999, 4999, 5999, 6999][i % 14]
            hours = [600, 800, 900, 1000, 1200, 1500, 1600, 1800, 2000, 2400, 2800, 3000, 3600, 4000, 4500, 4800][i % 16]
            await conn.execute(text("""
                INSERT IGNORE INTO course (course_id, name, category, price, teacher_id, total_hours)
                VALUES (:cid, :name, :cat, :price, :tid, :hours)
            """), {
                "cid": f"C{i:03d}", "name": COURSE_NAMES[i-1],
                "cat": cat, "price": price,
                "tid": f"U{randint(6, 30):03d}", "hours": hours,
            })
        print(f"  20 门课程 OK")

        # 2. 生成用户 (50 个)
        print("[2/6] 生成用户...")
        for i in range(1, 51):
            uid = f"U{i:03d}"
            role = ROLES[i % 6]
            sid = f"STU{2024000 + i:04d}" if role == '学生' else None
            rns = REAL_NAME_STATUSES[i % 5]
            days_ago = randint(1, 600)
            reg_at = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            await conn.execute(text("""
                INSERT IGNORE INTO user_info (user_id, name, role, student_id, real_name_status, register_at)
                VALUES (:uid, :name, :role, :sid, :rns, :reg_at)
            """), {
                "uid": uid, "name": f"用户{uid[1:]}号",
                "role": role, "sid": sid, "rns": rns, "reg_at": reg_at,
            })
        print(f"  50 个用户 OK")

        # 3. 生成订单 (100 条)
        print("[3/6] 生成报名订单...")
        for i in range(1, count + 1):
            oid = f"ORD{i:04d}"
            uid = f"U{randint(1, 50):03d}"
            cid = f"C{randint(1, 20):03d}"
            # 价格随机在课程价基础上小幅浮动
            base_price = [899, 999, 1299, 1599, 1999, 2199, 2599, 2999, 3299, 3499, 3999, 4999, 5999, 6999][(int(cid[1:]) - 1) % 14]
            amount = base_price + randint(-200, 200)
            days_ago = randint(1, 500)
            create_t = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            pay_t = (datetime.now() - timedelta(days=days_ago, hours=-randint(1, 24))).strftime("%Y-%m-%d %H:%M:%S") if random() > 0.1 else None
            status = choice(ORDER_STATUSES)
            goal = choice(STUDY_GOALS)
            exp_days = choice([30, 60, 90, 120, 150, 180])
            await conn.execute(text("""
                INSERT IGNORE INTO order_info (order_id, user_id, course_id, total_amount, study_goal, expected_finish_days, status, create_time, payment_time)
                VALUES (:oid, :uid, :cid, :amount, :goal, :exp_d, :status, :ct, :pt)
            """), {
                "oid": oid, "uid": uid, "cid": cid, "amount": amount,
                "goal": goal, "exp_d": exp_days, "status": status,
                "ct": create_t, "pt": pay_t,
            })
        print(f"  {count} 条订单 OK")

        # 4. 生成学习进度 (80 条)
        print("[4/6] 生成学习进度...")
        for i in range(1, 81):
            pid = f"LP{i:04d}"
            uid = f"U{randint(1, 50):03d}"
            cid = f"C{randint(1, 20):03d}"
            oid = f"ORD{randint(1, count):04d}"
            minutes = randint(0, 4000)
            days_ago = randint(1, 400)
            last_active = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            comp = round(min(minutes / 4800.0, 1.0), 4)
            await conn.execute(text("""
                INSERT IGNORE INTO learning_progress (progress_id, user_id, course_id, order_id, total_minutes, last_active_at, completion_rate)
                VALUES (:pid, :uid, :cid, :oid, :min, :la, :cr)
            """), {
                "pid": pid, "uid": uid, "cid": cid, "oid": oid,
                "min": minutes, "la": last_active, "cr": comp,
            })
        print(f"  80 条学习进度 OK")

        # 5. 生成退费申请 (30 条)
        print("[5/6] 生成退费申请...")
        for i in range(1, 31):
            rid = f"REF{i:04d}"
            oid = f"ORD{randint(1, count):04d}"
            uid = f"U{randint(1, 50):03d}"
            reason = choice(REFUND_REASONS)
            study_min = randint(0, 500)
            amount = randint(500, 7000)
            status = choice(['待审核', '待审核', '待审核', '已通过', '已拒绝'])
            days_ago = randint(1, 200)
            create_t = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            await conn.execute(text("""
                INSERT IGNORE INTO refund_request (refund_id, order_id, user_id, reason, study_minutes_before_refund, refund_amount, status, create_time)
                VALUES (:rid, :oid, :uid, :reason, :sm, :amount, :status, :ct)
            """), {
                "rid": rid, "oid": oid, "uid": uid, "reason": reason,
                "sm": study_min, "amount": amount, "status": status, "ct": create_t,
            })
        print(f"  30 条退费申请 OK")

        # 6. 生成设备指纹 (50 条)
        print("[6/6] 生成设备指纹...")
        for i in range(1, 51):
            did = f"DEV{i:04d}"
            uid = f"U{randint(1, 50):03d}"
            fp = f"fp_{randint(100000, 999999):06d}"
            ip = f"192.168.{randint(1, 255)}.{randint(1, 255)}"
            days_ago = randint(1, 500)
            create_at = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            await conn.execute(text("""
                INSERT IGNORE INTO device_fingerprint (device_id, user_id, fingerprint, ip, create_at)
                VALUES (:did, :uid, :fp, :ip, :ca)
            """), {"did": did, "uid": uid, "fp": fp, "ip": ip, "ca": create_at})

        # 额外: 造 5 个共享设备指纹的"假学员" (DEV_SHARED 关联 5 个不同学员)
        shared_fp = "fp_shared_agent_001"
        shared_ip = "172.16.0.99"
        for uid_suffix in ['U101', 'U102', 'U103', 'U104', 'U105']:
            # 确保这些用户在 user_info 里
            await conn.execute(text("""
                INSERT IGNORE INTO user_info (user_id, name, role, student_id, real_name_status, register_at)
                VALUES (:uid, :name, '学生', :sid, '未认证', NOW())
            """), {"uid": uid_suffix, "name": f"可疑学员{uid_suffix}", "sid": f"FAKE{uid_suffix}"})
            await conn.execute(text("""
                INSERT IGNORE INTO device_fingerprint (device_id, user_id, fingerprint, ip, create_at)
                VALUES (:did, :uid, :fp, :ip, NOW())
            """), {"did": f"DEV_SHARED_{uid_suffix}", "uid": uid_suffix, "fp": shared_fp, "ip": shared_ip})

        print(f"  50+5 条设备指纹 OK (含 5 个共享设备假学员)")

        await conn.commit()

        # 统计
        tables = ["user_info", "course", "order_info", "learning_progress", "refund_request", "device_fingerprint"]
        print("\n[完成] 教育业务数据生成完成!")
        for tbl in tables:
            r = await conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            print(f"  {tbl:<22} = {r.scalar()} 条")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="造教育业务数据")
    parser.add_argument("--count", type=int, default=100, help="订单数 (默认 100)")
    parser.add_argument("--reset", action="store_true", help="先清空旧数据")
    args = parser.parse_args()
    asyncio.run(gen_business_data(count=args.count, reset=args.reset))

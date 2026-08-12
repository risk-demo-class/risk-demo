"""
教育风控系统 - 业务数据生成器
生成教育业务测试数据: 用户/课程/订单/学习进度/退费/打赏
用法: python scripts/gen_edu_data.py [--users 50] [--courses 20]
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

# Windows: fix aiomysql "Event loop is closed" on ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 项目根路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiomysql
from faker import Faker

fake = Faker("zh_CN")

# 默认配置
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3306
DEFAULT_USER = "root"
DEFAULT_PASSWORD = "279169"
DEFAULT_DB = "ecs"

N_USERS = 50
N_COURSES = 20
N_ORDERS = 150
N_PROGRESS = 100
N_REFUNDS = 20
N_DONATIONS = 30

COURSE_CATEGORIES = ["学科辅导", "兴趣特长", "职业技能", "语言学习", "考试考证", "其他"]
ORDER_STATUSES = ["待支付", "已支付", "学习中", "已完成", "已取消"]
ROLES = ["学生"] * 80 + ["老师"] * 15 + ["管理员"] * 5  # 80% student, 15% teacher, 5% admin


def gen_id(prefix="", length=12):
    """生成随机ID"""
    import uuid
    return f"{prefix}{uuid.uuid4().hex[:length]}"


async def generate(host, port, user, password, db, n_users, n_courses, n_orders,
                   n_progress, n_refunds, n_donations):
    conn = await aiomysql.connect(host=host, port=port, user=user, password=password,
                                  db=db, charset="utf8mb4", autocommit=True)
    cur = await conn.cursor()

    now = datetime.now()

    # Clear existing generated data (keep seed data structure intact)
    # Use TRUNCATE in correct FK order to avoid constraint errors
    truncate_order = [
        "donation_record", "refund_request", "learning_progress",
        "order_info", "blacklist_extra", "course", "user_info",
    ]
    for tbl in truncate_order:
        try:
            await cur.execute(f"DELETE FROM {tbl}")
        except Exception:
            pass
    print("  Cleared existing data")

    # ---- 1. Users ----
    print(f"[1/7] Generating {n_users} users...")
    users = []
    for i in range(n_users):
        uid = f"U{i+1:04d}"
        role = random.choice(ROLES)
        sid = f"STU{20240000 + i + 1}" if role == "学生" else None
        id_num = f"{random.randint(110000, 659999)}{random.randint(1900, 2024)}{random.randint(1,12):02d}{random.randint(1,28):02d}{random.randint(1000,9999)}"
        reg_days = random.randint(1, 365)
        reg_time = now - timedelta(days=reg_days, hours=random.randint(0, 23))
        real_name = random.choice(["已认证"] * 7 + ["未认证"] * 2 + ["认证失败"] * 1)
        users.append((uid, fake.name(), role, sid, id_num, real_name, reg_time))

    await cur.executemany(
        "INSERT INTO user_info (user_id, name, role, student_id, id_number, real_name_status, register_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        users,
    )
    user_ids = [u[0] for u in users]
    print(f"  Done: {len(users)} users")

    # ---- 2. Courses ----
    print(f"[2/7] Generating {n_courses} courses...")
    teacher_ids = [u[0] for u in users if u[2] == "老师"]
    if not teacher_ids:
        teacher_ids = user_ids[:3]
    courses = []
    for i in range(n_courses):
        cid = f"C{i+1:03d}"
        cat = random.choice(COURSE_CATEGORIES)
        price = round(random.uniform(100, 20000), 2)
        tid = random.choice(teacher_ids)
        hours = round(random.uniform(1, 200), 1)
        audience = random.choice(["学生"] * 6 + ["通用"] * 4)
        is_live = 1 if random.random() < 0.3 else 0
        courses.append((cid, fake.sentence(nb_words=4)[:50], cat, price, tid, hours, audience, is_live, now))

    await cur.executemany(
        "INSERT INTO course (course_id, name, category, price, teacher_id, total_hours, target_audience, is_live, create_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        courses,
    )
    course_ids = [c[0] for c in courses]
    print(f"  Done: {len(courses)} courses")

    # ---- 3. Orders ----
    print(f"[3/7] Generating {n_orders} orders...")
    orders = []
    for i in range(n_orders):
        oid = gen_id("ORD")
        uid = random.choice(user_ids)
        cid = random.choice(course_ids)
        course_price = next((c[3] for c in courses if c[0] == cid), 1000)
        amount = round(course_price * random.uniform(0.8, 1.2), 2)
        dev = f"DEV_{random.choice(user_ids[:10])}" if random.random() < 0.2 else f"DEV_{uid}"
        study_goal = fake.sentence(nb_words=6)[:50] if random.random() < 0.6 else None
        finish_days = random.choice([7, 14, 30, 60, 90]) if random.random() < 0.6 else None
        status = random.choice(ORDER_STATUSES)
        order_days_ago = random.randint(0, 90)
        create_t = now - timedelta(days=order_days_ago, hours=random.randint(0, 23))
        pay_t = create_t + timedelta(minutes=random.randint(1, 60)) if status != "待支付" else None
        orders.append((oid, uid, cid, amount, dev, study_goal, finish_days, status, create_t, pay_t))

    await cur.executemany(
        "INSERT INTO order_info (order_id, user_id, course_id, total_amount, device_fingerprint, study_goal, expected_finish_days, order_status, create_time, payment_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        orders,
    )
    order_ids = [o[0] for o in orders]
    print(f"  Done: {len(orders)} orders")

    # ---- 4. Learning Progress ----
    print(f"[4/7] Generating {n_progress} learning progress records...")
    progress_records = []
    for i in range(n_progress):
        pid = gen_id("PROG")
        o = random.choice(orders)
        uid = o[1]
        cid = o[2]
        oid = o[0]
        total_mins = random.randint(0, 5000)
        last_active = now - timedelta(days=random.randint(0, 30))
        completion = round(random.uniform(0, 100), 2)
        progress_records.append((pid, uid, cid, oid, total_mins, last_active, completion, now))

    await cur.executemany(
        "INSERT INTO learning_progress (progress_id, user_id, course_id, order_id, total_minutes, last_active_at, completion_rate, create_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        progress_records,
    )
    print(f"  Done: {len(progress_records)} progress records")

    # ---- 5. Refund Requests ----
    print(f"[5/7] Generating {n_refunds} refund requests...")
    refunds = []
    for i in range(n_refunds):
        rid = gen_id("REF")
        o = random.choice(orders)
        oid = o[0]
        uid = o[1]
        reason = random.choice(["不想学了", "课程太简单", "课程太难", "时间冲突", "老师不负责", "找到更好的课程"])
        study_mins = random.randint(0, 1000)
        refund_amt = round(o[3] * random.uniform(0.5, 1.0), 2)
        status = random.choice(["待审核"] * 5 + ["已同意"] * 3 + ["已拒绝"] * 2)
        days_ago = random.randint(0, 30)
        create_t = now - timedelta(days=days_ago, hours=random.randint(0, 23))
        refunds.append((rid, oid, uid, reason, study_mins, refund_amt, status, create_t))

    await cur.executemany(
        "INSERT INTO refund_request (refund_id, order_id, user_id, reason, study_minutes_before_refund, refund_amount, refund_status, create_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        refunds,
    )
    print(f"  Done: {len(refunds)} refunds")

    # ---- 6. Donation Records ----
    print(f"[6/7] Generating {n_donations} donation records...")
    live_courses = [c[0] for c in courses if c[7] == 1]
    if not live_courses:
        live_courses = course_ids[:5]
    donations = []
    for i in range(n_donations):
        did = gen_id("DON")
        uid = random.choice(user_ids)
        cid = random.choice(live_courses)
        amount = round(random.uniform(10, 10000), 2)
        days_ago = random.randint(0, 7)
        create_t = now - timedelta(days=days_ago, hours=random.randint(0, 23))
        donations.append((did, uid, cid, amount, create_t))

    await cur.executemany(
        "INSERT INTO donation_record (donation_id, user_id, course_id, amount, create_time) "
        "VALUES (%s, %s, %s, %s, %s)",
        donations,
    )
    print(f"  Done: {len(donations)} donations")

    # ---- 7. Blacklist Extra ----
    print(f"[7/7] Generating blacklist entries...")
    blacklist_entries = [
        ("BL001", "学号", "STU20240099", "历史欺诈账号 - 多次刷单", None),
        ("BL002", "身份证号", "330102199909090009", "虚假实名认证", None),
        ("BL003", "设备指纹", "DEV_BLOCKED_001", "关联多个欺诈账号", (now + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")),
    ]
    for entry in blacklist_entries:
        try:
            await cur.execute(
                "INSERT INTO blacklist_extra (entry_id, type, value, reason, expire_at) VALUES (%s, %s, %s, %s, %s)",
                entry,
            )
        except Exception:
            pass
    print(f"  Done: {len(blacklist_entries)} blacklist entries")

    await cur.close()
    await conn.ensure_closed()

    print(f"\n{'='*60}")
    print(f"Data generation complete!")
    print(f"  Users: {n_users} | Courses: {n_courses} | Orders: {n_orders}")
    print(f"  Progress: {n_progress} | Refunds: {n_refunds} | Donations: {n_donations}")
    print(f"{'='*60}")


async def main():
    parser = argparse.ArgumentParser(description="Education risk control data generator")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--users", type=int, default=N_USERS)
    parser.add_argument("--courses", type=int, default=N_COURSES)
    parser.add_argument("--orders", type=int, default=N_ORDERS)
    parser.add_argument("--progress", type=int, default=N_PROGRESS)
    parser.add_argument("--refunds", type=int, default=N_REFUNDS)
    parser.add_argument("--donations", type=int, default=N_DONATIONS)
    args = parser.parse_args()

    await generate(
        args.host, args.port, args.user, args.password, args.db,
        args.users, args.courses, args.orders, args.progress, args.refunds, args.donations,
    )


if __name__ == "__main__":
    asyncio.run(main())

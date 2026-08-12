"""
教育风控系统 - 10w 条随机业务数据生成 (异步, 一次性脚本)
============================================================
生成规模 (默认 ≈ 10w 条, 可调):
  - 用户 (user_info):                N_USER        (默认 10000)
  - 学籍档案 (student_profile):       N_USER * 60%  (默认 6000)
  - 教师 (teacher_info):              N_USER * 10%  (默认 1000)
  - 课程 (course):                    N_COURSE      (默认 200)
  - 订单 (order_info):                N_USER * 3    (默认 30000)
  - 学习进度 (learning_progress):     N_USER * 2    (默认 20000)
  - 退费申请 (refund_request):        N_ORDER * 10% (默认 3000)
  - 投诉 (complaint):                 N_ORDER * 2%  (默认 600)
  - 支付账户 (payment_account):       N_USER * 1.5  (默认 15000)
  - 设备指纹 (device_fingerprint):    N_USER * 1.2  (默认 12000)
  - 总条目:                          ≈ 10w

风险画像 (80/15/5):
  - 80% 正常用户 (合理报名, 正常学习)
  - 15% 中风险 (退费率 30-50% / 多设备 / 凌晨学习)
  - 5%  高风险 (极高退费率 / 刷课 / 批量注册)

数据源: faker 中文 + random
幂等: INSERT IGNORE, 重复跑安全
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faker import Faker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# ============================================================
# 配置
# ============================================================
CHINESE_SCHOOLS = [
    "北京大学", "清华大学", "复旦大学", "上海交通大学", "浙江大学",
    "南京大学", "武汉大学", "华中科技大学", "中山大学", "四川大学",
    "哈尔滨工业大学", "西安交通大学", "中国科学技术大学", "南开大学", "天津大学",
    "厦门大学", "山东大学", "吉林大学", "同济大学", "北京师范大学",
]

COURSE_CATEGORIES = ["考研", "公考", "职业", "语言", "素质"]
COURSE_NAMES = {
    "考研": ["2026考研数学全程班", "考研英语强化班", "考研政治冲刺班", "408计算机考研", "考研专业课一对一"],
    "公考": ["公务员行测精讲", "申论高分班", "面试实战班", "公考真题解析", "事业单位笔试班"],
    "职业": ["Python数据分析实战", "Java企业级开发", "产品经理入门", "全栈Web开发", "AI机器学习"],
    "语言": ["雅思7分冲刺班", "托福110分班", "日语N2通关", "商务英语高级", "德语A1-A2"],
    "素质": ["少儿编程启蒙", "书法基础班", "摄影后期处理", "吉他入门", "瑜伽塑形"],
}
COURSE_TEACHER_ID_POOL = [f"T{i:04d}" for i in range(1, 1001)]


# ============================================================
# 工具函数
# ============================================================
def _ulid() -> str:
    import ulid
    return ulid.new().str.lower()


def _chinese_user_id(idx: int) -> str:
    return f"U{idx:06d}"


def _risk_tier() -> str:
    r = random.random()
    if r < 0.05:
        return "high"
    elif r < 0.20:
        return "medium"
    else:
        return "normal"


# ============================================================
# 主函数
# ============================================================
async def gen_edu_data(
    n_user: int = 10_000,
    n_course: int = 200,
    min_orders: int = 1,
    max_orders: int = 8,
    batch_size: int = 500,
):
    """生成教育业务测试数据"""
    fake = Faker("zh_CN")
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url, echo=False)

    print("=" * 60)
    print(f"开始生成 10w 条教育业务数据 (用户数: {n_user})")
    print(f"订单范围: 每用户 {min_orders}~{max_orders} 单")
    print("=" * 60)

    # --- 用户 ID 池 + 风险分层 ---
    user_ids = [_chinese_user_id(i) for i in range(1, n_user + 1)]
    user_risk = {uid: _risk_tier() for uid in user_ids}
    high_users = [uid for uid, v in user_risk.items() if v == "high"]
    med_users = [uid for uid, v in user_risk.items() if v == "medium"]

    # ======== 1. 灌用户 (带角色/手机号/实名/注册时间) ========
    print(f"\n[1/8] 灌用户 ({n_user} 条)...")
    roles = ["学生", "学生", "学生", "学生", "学生", "老师", "家长", "家长"]  # 6:1:1
    async with engine.begin() as conn:
        for i in range(0, n_user, batch_size):
            batch = user_ids[i:i + batch_size]
            values = ", ".join([f"('{uid}', '{fake.name()}', '{random.choice(roles)}', "
                                f"'{fake.phone_number()[:11]}', {1 if random.random() > 0.15 else 0}, "
                                f"{random.randint(0, 730)}, "
                                f"'{datetime.now() - timedelta(days=random.randint(0, 730)):%Y-%m-%d %H:%M:%S}')"
                                for uid in batch])
            await conn.execute(text(f"INSERT IGNORE INTO user_info (user_id, name, role, phone, real_name_status, account_age_days, register_at) VALUES {values}"))
    print(f"  → {n_user} 用户 (高风险 {len(high_users)}, 中风险 {len(med_users)})")

    # ======== 2. 灌学籍档案 (60% 用户, 仅学生) ========
    print(f"\n[2/8] 灌学籍档案 (~{int(n_user * 0.6)} 条)...")
    student_pool = [uid for uid in user_ids if user_risk[uid] != "high" or random.random() < 0.5]
    student_sample = random.sample(student_pool, min(int(n_user * 0.6), len(student_pool)))
    async with engine.begin() as conn:
        for i in range(0, len(student_sample), batch_size):
            batch = student_sample[i:i + batch_size]
            values = ", ".join([f"('SP{uid[1:]}', '{uid}', 'STU{random.randint(2024001, 2024999)}', "
                                f"'{random.choice(CHINESE_SCHOOLS)}', '{random.choice(['大一','大二','大三','大四','研一','研二','研三'])}', "
                                f"'{fake.sha256()[:64]}', '{fake.phone_number()[:11]}')"
                                for uid in batch])
            await conn.execute(text(f"INSERT IGNORE INTO student_profile (profile_id, user_id, student_id, school_name, grade, id_card_hash, parent_phone) VALUES {values}"))
    print(f"  → {len(student_sample)} 学籍档案")

    # ======== 3. 灌教师信息 (10% 用户) ========
    print(f"\n[3/8] 灌教师信息 (~{int(n_user * 0.1)} 条)...")
    teacher_pool = random.sample(user_ids, min(int(n_user * 0.1), n_user))
    async with engine.begin() as conn:
        for i, uid in enumerate(teacher_pool):
            tid = f"T{i+1:04d}"
            await conn.execute(text(
                "INSERT IGNORE INTO teacher_info (teacher_id, user_id, name, cert_no, teach_years, avg_rating, course_count) "
                "VALUES (:tid, :uid, :name, :cert, :years, :rating, :cnt)"
            ), {
                "tid": tid, "uid": uid, "name": fake.name(),
                "cert": f"CERT{random.randint(2015000, 2026000)}",
                "years": random.randint(1, 30),
                "rating": round(random.uniform(1.0, 5.0), 2),
                "cnt": random.randint(1, 20),
            })
    print(f"  → {len(teacher_pool)} 教师")

    # ======== 4. 灌课程 ========
    print(f"\n[4/8] 灌课程 ({n_course} 条)...")
    async with engine.begin() as conn:
        for i in range(1, n_course + 1):
            cat = random.choice(COURSE_CATEGORIES)
            await conn.execute(text(
                "INSERT IGNORE INTO course (course_id, name, category, price, total_hours, teacher_id, publish_date, status) "
                f"VALUES ('C{i:04d}', :name, :cat, :price, :hours, :tid, '{datetime.now() - timedelta(days=random.randint(30, 365)):%Y-%m-%d %H:%M:%S}', '上架')"
            ), {
                "name": random.choice(COURSE_NAMES[cat]),
                "cat": cat,
                "price": round(random.uniform(99, 9999), 2),
                "hours": random.randint(20, 300),
                "tid": random.choice(COURSE_TEACHER_ID_POOL),
            })
    print(f"  → {n_course} 课程")

    # ======== 5. 灌订单/报名 ========
    print(f"\n[5/8] 灌订单 (~{n_user * 3} 条)...")
    order_rows = []
    order_id_counter = 0
    now = datetime.now()
    for uid in user_ids:
        risk = user_risk[uid]
        n_orders = random.randint(min_orders, max_orders)
        for _ in range(n_orders):
            order_id_counter += 1
            cid = f"C{random.randint(1, n_course):04d}"
            days_ago = random.randint(0, 90)
            pay_hour = random.randint(6, 23)  # 高风险用户可能凌晨
            if risk == "high":
                pay_hour = random.choice([0, 1, 2, 3, 22, 23])
            order_time = now - timedelta(days=days_ago, hours=random.randint(0, 23))
            pay_time = order_time + timedelta(minutes=random.randint(1, 120))

            amount = round(random.uniform(99, 3000), 2)
            if risk == "high":
                amount = round(random.uniform(3000, 10000), 2)

            status_r = random.random()
            if status_r < 0.70:
                status = "已支付"
            elif status_r < 0.85:
                status = "待支付"
            elif status_r < 0.95:
                status = "已退款"
            else:
                status = "已关闭"

            order_rows.append({
                "order_id": f"ORD{order_id_counter:08d}",
                "user_id": uid,
                "course_id": cid,
                "amount": amount,
                "pay_time": pay_time,
                "status": status,
            })

    async with engine.begin() as conn:
        for i in range(0, len(order_rows), batch_size):
            batch = order_rows[i:i + batch_size]
            values = ", ".join([f"('{o['order_id']}', '{o['user_id']}', '{o['course_id']}', "
                                f"{o['amount']}, '{o['pay_time']:%Y-%m-%d %H:%M:%S}', "
                                f"NULL, NULL, '{o['status']}')" for o in batch])
            await conn.execute(text(
                f"INSERT IGNORE INTO order_info (order_id, user_id, course_id, amount, pay_time, study_goal, expected_finish_days, order_status) VALUES {values}"
            ))
    print(f"  → {len(order_rows)} 订单")

    # ======== 6. 灌学习进度 ========
    print(f"\n[6/8] 灌学习进度 (~{n_user * 2} 条)...")
    progress_rows = []
    for uid in user_ids:
        risk = user_risk[uid]
        n_progress = random.randint(0, 4)
        for _ in range(n_progress):
            cid = f"C{random.randint(1, n_course):04d}"
            total_min = random.randint(0, 5000)
            completion = round(random.uniform(0, 100), 2) if total_min > 0 else 0
            if risk == "high":
                # 刷课特征: 凌晨 + 高完成率 + 短时间
                completion = round(random.uniform(90, 100), 2)
                total_min = random.randint(10, 60)
                last_active = now - timedelta(days=random.randint(0, 3), hours=random.randint(0, 5))
            else:
                last_active = now - timedelta(days=random.randint(0, 30), hours=random.randint(6, 23))
            progress_rows.append({
                "pid": f"LP{uid[1:]}_{_}_{random.randint(100, 999)}",
                "uid": uid,
                "cid": cid,
                "min": total_min,
                "rate": completion,
                "at": last_active,
            })

    async with engine.begin() as conn:
        for i in range(0, len(progress_rows), batch_size):
            batch = progress_rows[i:i + batch_size]
            values = ", ".join([f"('{p['pid']}', '{p['uid']}', '{p['cid']}', {p['min']}, "
                                f"{p['rate']}, '{p['at']:%Y-%m-%d %H:%M:%S}', NULL)" for p in batch])
            await conn.execute(text(
                f"INSERT IGNORE INTO learning_progress (progress_id, user_id, course_id, total_minutes, completion_rate, last_active_at, chapter_progress) VALUES {values}"
            ))
    print(f"  → {len(progress_rows)} 学习进度")

    # ======== 7. 灌退费申请 + 投诉 ========
    print(f"\n[7/8] 灌退费申请 (~{int(len(order_rows) * 0.10)} 条)...")
    refund_rows = []
    for o in order_rows:
        uid = o["user_id"]
        risk = user_risk[uid]
        refund_prob = 0.90 if risk == "high" else (0.30 if risk == "medium" else 0.05)
        if random.random() < refund_prob:
            refund_rows.append({
                "rid": f"RF{len(refund_rows) + 1:08d}",
                "oid": o["order_id"],
                "uid": uid,
                "reason": random.choice(["课程内容不符合预期", "找到工作不需要了", "课程难度太高", "老师水平差", "没时间学习", "经济原因"]),
                "minutes": random.randint(0, 5000),
                "amount": o["amount"],
                "status": random.choice(["待审核", "已通过", "已拒绝"]),
                "time": o["pay_time"] + timedelta(days=random.randint(1, 30)),
            })

    async with engine.begin() as conn:
        for i in range(0, len(refund_rows), batch_size):
            batch = refund_rows[i:i + batch_size]
            values = ", ".join([f"('{r['rid']}', '{r['oid']}', '{r['uid']}', "
                                f"'{r['reason']}', {r['minutes']}, {r['amount']}, "
                                f"'{r['status']}', '{r['time']:%Y-%m-%d %H:%M:%S}')" for r in batch])
            await conn.execute(text(
                f"INSERT IGNORE INTO refund_request (refund_id, order_id, user_id, reason, study_minutes_before_refund, refund_amount, status, apply_time) VALUES {values}"
            ))
    print(f"  → {len(refund_rows)} 退费申请")

    # 投诉
    print(f"  灌投诉 (~{int(len(order_rows) * 0.02)} 条)...")
    complaint_rows = []
    for o in order_rows:
        uid = o["user_id"]
        risk = user_risk[uid]
        cmp_prob = 0.20 if risk == "high" else (0.05 if risk == "medium" else 0.01)
        if random.random() < cmp_prob:
            complaint_rows.append({
                "cid": f"CMP{len(complaint_rows) + 1:08d}",
                "uid": uid,
                "course_id": o["course_id"],
                "type": random.choice(["虚假宣传", "侵权盗版", "内容违规", "师资不符"]),
                "content": fake.sentence(),
                "status": random.choice(["待处理", "已处理", "已驳回"]),
                "time": now - timedelta(days=random.randint(1, 60)),
            })

    async with engine.begin() as conn:
        for i in range(0, len(complaint_rows), batch_size):
            batch = complaint_rows[i:i + batch_size]
            values = ", ".join([f"('{c['cid']}', '{c['uid']}', '{c['course_id']}', "
                                f"'{c['type']}', '{c['content']}', '{c['status']}', "
                                f"'{c['time']:%Y-%m-%d %H:%M:%S}')" for c in batch])
            await conn.execute(text(
                f"INSERT IGNORE INTO complaint (complaint_id, user_id, course_id, complaint_type, content, status, create_time) VALUES {values}"
            ))
    print(f"  → {len(complaint_rows)} 投诉")

    # ======== 8. 灌支付账户 + 设备指纹 ========
    print(f"\n[8/8] 灌支付账户 (~{int(n_user * 1.5)} 条) + 设备指纹 (~{int(n_user * 1.2)} 条)...")
    # 支付账户
    pa_rows = []
    for uid in user_ids:
        risk = user_risk[uid]
        n_pa = random.randint(0, 2) if risk == "normal" else random.randint(1, 4)
        for j in range(n_pa):
            pa_rows.append({
                "aid": f"PA{uid[1:]}_{j}",
                "uid": uid,
                "type": random.choice(["微信", "支付宝", "银行卡"]),
                "hash": fake.sha256()[:40],
                "bind": now - timedelta(days=random.randint(0, 365)),
                "verified": 1 if random.random() > 0.2 else 0,
            })

    async with engine.begin() as conn:
        for i in range(0, len(pa_rows), batch_size):
            batch = pa_rows[i:i + batch_size]
            values = ", ".join([f"('{p['aid']}', '{p['uid']}', '{p['type']}', "
                                f"'{p['hash']}', '{p['bind']:%Y-%m-%d %H:%M:%S}', {p['verified']})" for p in batch])
            await conn.execute(text(
                f"INSERT IGNORE INTO payment_account (account_id, user_id, payment_type, account_hash, bind_time, is_verified) VALUES {values}"
            ))
    print(f"  → {len(pa_rows)} 支付账户")

    # 设备指纹
    df_rows = []
    for uid in user_ids:
        risk = user_risk[uid]
        n_dev = random.randint(1, 2) if risk == "normal" else random.randint(2, 5)
        for j in range(n_dev):
            df_rows.append({
                "did": f"DEV{uid[1:]}_{j}",
                "uid": uid,
                "hash": fake.sha256()[:48],
                "first": now - timedelta(days=random.randint(0, 365)),
                "last": now - timedelta(days=random.randint(0, 7)),
                "os": random.choice(["Windows 10", "Windows 11", "macOS 14", "Android 13", "Android 14", "iOS 17"]),
                "browser": random.choice(["Chrome 120", "Firefox 121", "Safari 17", "Edge 120", "Chrome Mobile"]),
                "ip": fake.ipv4(),
            })

    async with engine.begin() as conn:
        for i in range(0, len(df_rows), batch_size):
            batch = df_rows[i:i + batch_size]
            values = ", ".join([f"('{d['did']}', '{d['uid']}', '{d['hash']}', "
                                f"'{d['first']:%Y-%m-%d %H:%M:%S}', '{d['last']:%Y-%m-%d %H:%M:%S}', "
                                f"'{d['os']}', '{d['browser']}', '{d['ip']}')" for d in batch])
            await conn.execute(text(
                f"INSERT IGNORE INTO device_fingerprint (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser, ip) VALUES {values}"
            ))
    print(f"  → {len(df_rows)} 设备指纹")

    # ======== 汇总 ========
    total = (n_user + len(student_sample) + len(teacher_pool) + n_course + len(order_rows)
             + len(progress_rows) + len(refund_rows) + len(complaint_rows) + len(pa_rows) + len(df_rows))
    print(f"\n{'=' * 60}")
    print(f"完成! 总计生成 {total} 条教育业务数据")
    print(f"  - 用户:        {n_user}")
    print(f"  - 学籍档案:    {len(student_sample)}")
    print(f"  - 教师:        {len(teacher_pool)}")
    print(f"  - 课程:        {n_course}")
    print(f"  - 订单:        {len(order_rows)}")
    print(f"  - 学习进度:    {len(progress_rows)}")
    print(f"  - 退费申请:    {len(refund_rows)}")
    print(f"  - 投诉:        {len(complaint_rows)}")
    print(f"  - 支付账户:    {len(pa_rows)}")
    print(f"  - 设备指纹:    {len(df_rows)}")
    print(f"\n下一步: gen_risk_data.py → train_xgb_model.py → run_app.py")
    print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="10w 条教育业务数据生成 (一次性, 跑完即结束)"
    )
    parser.add_argument("--users", type=int, default=10_000, help="用户数 (默认 10000)")
    parser.add_argument("--courses", type=int, default=200, help="课程数 (默认 200)")
    parser.add_argument("--min-orders", type=int, default=1, help="每用户最少订单数 (默认 1)")
    parser.add_argument("--max-orders", type=int, default=8, help="每用户最多订单数 (默认 8)")
    parser.add_argument("--batch", type=int, default=500, help="批量 insert 批次大小 (默认 500)")
    args = parser.parse_args()

    asyncio.run(gen_edu_data(
        n_user=args.users,
        n_course=args.courses,
        min_orders=args.min_orders,
        max_orders=args.max_orders,
        batch_size=args.batch,
    ))
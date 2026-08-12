"""
教育业务数据生成器 — 造学员/课程/报名/缴费/退费/考试/作业数据
用法:
  python scripts/gen_edu_data.py 200          # 造 200 个学员 + 业务数据
  python scripts/gen_edu_data.py 200 --balance-pos  # 提高正例比例(训练用)
  python scripts/gen_edu_data.py 200 --target-pos-ratio 0.30  # 循环造数据直到正例达标
"""
import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal, async_engine, Base  # noqa: E402
from app.models import (  # noqa: E402
    AccountInfo, ComplaintRecord, CourseCategory, CourseInfo, DeviceRecord,
    Enrollment, EnrollmentDetail, ExamRecord, PaymentRecord, RefundRecord,
    School, UserInfo, gen_id,
)

COURSE_NAMES = [
    "少儿编程入门", "K12 数学培优", "英语口语集训", "书法启蒙", "钢琴一对一",
    "高考冲刺班", "考研数学", "成人英语", "绘画基础", "舞蹈形体",
]
CATEGORIES = ["编程", "数学", "英语", "艺术", "体育"]
CITIES = [("北京市", "北京"), ("上海市", "上海"), ("广东省", "深圳"),
          ("浙江省", "杭州"), ("江苏省", "南京"), ("四川省", "成都")]


async def seed_basic(db, n_users: int) -> list[str]:
    """建校区/分类/课程/教师 + n 个学员。返回 user_ids。"""
    schools = []
    for i, (prov, city) in enumerate(CITIES):
        s = School(school_id=f"SCH{i+1:03d}", school_name=f"{city}旗舰校区",
                   province=prov, city=city)
        db.add(s)
        schools.append(s)
    cats = [CourseCategory(category_id=f"CAT{i+1:02d}", category_name=c)
            for i, c in enumerate(CATEGORIES)]
    db.add_all(cats)
    courses = []
    for i, name in enumerate(COURSE_NAMES):
        c = CourseInfo(course_id=f"CRS{i+1:03d}", course_name=name,
                       category_id=f"CAT{(i % len(CATEGORIES))+1:02d}",
                       school_id=f"SCH{(i % len(schools))+1:03d}",
                       price=random.choice([199, 399, 899, 1999, 3999, 8999]))
        db.add(c)
        courses.append(c)

    user_ids = []
    for i in range(1, n_users + 1):
        uid = f"U{i:05d}"
        reg = datetime.now() - timedelta(days=random.randint(1, 400))
        db.add(UserInfo(user_id=uid, user_name=f"学员{i}",
                        phone=f"138{random.randint(10**7, 10**8 - 1)}",
                        register_time=reg,
                        user_level=random.choice(["普通", "黄金", "铂金", "钻石"])))
        db.add(AccountInfo(account_id=gen_id("ACC"), user_id=uid,
                           account_name=f"学员{i}", reg_time=reg))
        db.add(DeviceRecord(device_id=gen_id("DEV"), user_id=uid,
                            device_fp=f"fp_{random.randint(1000, 9999)}"))
        user_ids.append(uid)
    await db.flush()
    return user_ids


async def make_enrollment(db, uid: str, school_id: str) -> str:
    """造一笔报名 + 明细 + 缴费(80% 概率)。返回 enrollment_id。"""
    now = datetime.now()
    night = random.random() < 0.08
    create = now - timedelta(hours=random.randint(0, 72))
    if night:
        create = create.replace(hour=random.choice([23, 0, 1, 2, 3]))

    n_courses = random.choices([1, 2, 3, 5], weights=[60, 25, 10, 5])[0]
    price_total = sum(random.choice([199, 399, 899, 1999, 3999, 8999])
                      for _ in range(n_courses))
    coupon = random.choice([0, 0, 0, 199, 399])
    discount = round(random.uniform(0, 0.15) * price_total, 2)
    total = max(round(price_total - discount - coupon, 2), 1)

    enr = Enrollment(
        enrollment_id=gen_id("ENR"), user_id=uid, school_id=school_id,
        status="已缴费", total_amount=total, discount_amount=discount,
        coupon_amount=coupon, create_time=create)
    db.add(enr)
    await db.flush()

    for j in range(n_courses):
        db.add(EnrollmentDetail(detail_id=gen_id("DTL"), enrollment_id=enr.enrollment_id,
                                course_id=f"CRS{random.randint(1, 10):03d}",
                                class_id=f"CLS{random.randint(1, 50):03d}",
                                price=random.choice([199, 399, 899])))

    if random.random() < 0.8:
        pay_time = create + timedelta(seconds=random.randint(30, 3600))
        db.add(PaymentRecord(payment_id=gen_id("PAY"), enrollment_id=enr.enrollment_id,
                             user_id=uid, amount=total,
                             pay_method=random.choice(["微信", "支付宝", "银行卡"]),
                             pay_time=pay_time, status="成功"))
    else:
        enr.status = "已报名"

    return enr.enrollment_id


async def maybe_risk_actions(db, uid: str, is_risky: bool):
    """按概率造退费/投诉/作弊/多设备/多账号等风险行为。"""
    def r(p): return random.random() < p

    # 退费
    if is_risky and r(0.8) or (not is_risky and r(0.05)):
        for _ in range(random.randint(1, 3)):
            db.add(RefundRecord(refund_id=gen_id("RFD"), enrollment_id=gen_id("ENR"),
                                user_id=uid, amount=random.choice([399, 899, 1999]),
                                reason=random.choice(["课程不满意", "时间冲突", "价格太贵"]),
                                apply_time=datetime.now() - timedelta(days=random.randint(0, 30)),
                                status="已退费"))
    # 投诉
    if is_risky and r(0.6) or (not is_risky and r(0.02)):
        for _ in range(random.randint(1, 2)):
            db.add(ComplaintRecord(complaint_id=gen_id("CPT"), user_id=uid,
                                   enrollment_id=gen_id("ENR"),
                                   reason=random.choice(["教师质量差", "退费拖延", "宣传不符"]),
                                   create_time=datetime.now() - timedelta(days=random.randint(0, 30))))
    # 作弊
    if is_risky and r(0.5):
        for _ in range(random.randint(1, 2)):
            db.add(ExamRecord(exam_id=gen_id("EXM"), user_id=uid, course_id=gen_id("CRS"),
                              exam_time=datetime.now() - timedelta(days=random.randint(0, 30)),
                              duration_seconds=random.randint(60, 1800), score=random.uniform(0, 100),
                              cheat_flag=True, cheat_reason="切屏/替考嫌疑"))
    # 普通考试
    for _ in range(random.randint(0, 3)):
        db.add(ExamRecord(exam_id=gen_id("EXM"), user_id=uid, course_id=gen_id("CRS"),
                          exam_time=datetime.now() - timedelta(days=random.randint(0, 30)),
                          duration_seconds=random.randint(1800, 7200),
                          score=random.uniform(30, 100), cheat_flag=False))
    # 多账号
    if is_risky and r(0.7):
        for _ in range(random.randint(1, 3)):
            db.add(AccountInfo(account_id=gen_id("ACC"), user_id=uid,
                               account_name=f"小号{random.randint(1, 99)}",
                               reg_time=datetime.now() - timedelta(days=random.randint(1, 200))))
    # 多设备
    if is_risky and r(0.6):
        for _ in range(random.randint(1, 4)):
            db.add(DeviceRecord(device_id=gen_id("DEV"), user_id=uid,
                                device_fp=f"fp_{random.randint(1000, 9999)}"))


async def gen(n_users: int, risky_ratio: float = 0.08):
    async with AsyncSessionLocal() as db:
        await seed_basic(db, n_users)
        risky_count = max(1, int(n_users * risky_ratio))
        risky_ids = random.sample([f"U{i:05d}" for i in range(1, n_users + 1)], risky_count)

        for uid in [f"U{i:05d}" for i in range(1, n_users + 1)]:
            is_risky = uid in risky_ids
            school = f"SCH{random.randint(1, 6):03d}"
            n_enr = random.randint(1, 8) if is_risky else random.randint(1, 3)
            for _ in range(n_enr):
                await make_enrollment(db, uid, school)
            await maybe_risk_actions(db, uid, is_risky)
        await db.commit()
        print(f"[OK] 生成 {n_users} 学员(高风险 {risky_count} 人),业务数据已落库")
    await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="教育业务数据生成器")
    parser.add_argument("n_users", type=int, nargs="?", default=200)
    parser.add_argument("--balance-pos", action="store_true",
                        help="提高正例比例(等价 --target-pos-ratio 0.30, 训练用)")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例(如 0.30),循环造数据直到达标(最多 10 轮)")
    parser.add_argument("--max-rounds", type=int, default=10)
    args = parser.parse_args()

    if args.balance_pos and args.target_pos_ratio is None:
        args.target_pos_ratio = 0.30

    if args.target_pos_ratio:
        from sqlalchemy import func as _func, select as _select
        from app.models import RiskAssessment

        async def _pos_ratio() -> float:
            async with AsyncSessionLocal() as db:
                total = (await db.execute(_select(_func.count(RiskAssessment.assessment_id)))).scalar() or 0
                if total == 0:
                    return 0.0
                pos = (await db.execute(_select(_func.count(RiskAssessment.assessment_id)).where(
                    RiskAssessment.final_score >= 80))).scalar() or 0
                return pos / total

        for round_no in range(1, args.max_rounds + 1):
            print(f"=== 第 {round_no} 轮: 生成 {args.n_users} 用户 ===")
            asyncio.run(gen(args.n_users, risky_ratio=0.08 + round_no * 0.02))
            ratio = asyncio.run(_pos_ratio())
            print(f"当前正例比例: {ratio:.2%} (目标 {args.target_pos_ratio:.0%})")
            if ratio >= args.target_pos_ratio:
                print("[OK] 正例达标,可开始训练!")
                break
        else:
            print("[WARN] 10 轮仍未达标,建议提高 risky_ratio 或 n_users")
    else:
        asyncio.run(gen(args.n_users))

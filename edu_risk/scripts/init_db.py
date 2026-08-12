"""
初始化数据库 — 建 24 张表 + 预置 30 条教育风控规则
用法: python scripts/init_db.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 项目根目录

from app.database import Base, async_engine, AsyncSessionLocal  # noqa: E402
from app.models import RiskRule  # noqa: E402

# 30 条预置规则 — 6 大类风险(报名/缴费/退费/考试/账号/内容)
PRESET_RULES = [
    # ---------- 报名风险 (R001-R005) ----------
    ("R001", "新账号大额报名", "报名", "报名", {"field": "acct_is_new", "op": "==", "value": 1}, "高", 70, "人工审核", 90, "新账号(<7天)发起大额报名需人工审核"),
    ("R002", "深夜异常报名", "报名", "报名", {"field": "enroll_is_night", "op": "==", "value": 1}, "中", 45, "标记", 60, "深夜(22:00-06:00)报名"),
    ("R003", "单报多课程", "报名", "报名", {"field": "enroll_course_count", "op": ">=", "value": 5}, "中", 50, "标记", 55, "一门报名单含 5 门以上课程"),
    ("R004", "超高优惠率", "报名", "报名", {"field": "enroll_discount_rate", "op": ">=", "value": 0.9}, "高", 70, "人工审核", 65, "优惠率 ≥ 90%,疑似优惠券滥用"),
    ("R005", "短期内密集报名", "报名", "报名", {"field": "user_enrollments_7d", "op": ">=", "value": 10}, "高", 75, "人工审核", 70, "7 天内报名 ≥ 10 次,疑似批量注册"),
    # ---------- 缴费风险 (R006-R010) ----------
    ("R006", "深夜大额缴费", "缴费", "缴费", {"field": "enroll_is_night", "op": "==", "value": 1}, "高", 70, "人工审核", 70, "深夜大额缴费,疑似盗刷/洗钱"),
    ("R007", "单笔缴费异常高", "缴费", "缴费", {"field": "enroll_total_amount", "op": ">=", "value": 50000}, "高", 75, "人工审核", 75, "单笔报名金额 ≥ 5 万"),
    ("R008", "新账号首次大额缴费", "缴费", "缴费", {"and": [
        {"field": "acct_is_new", "op": "==", "value": 1},
        {"field": "enroll_total_amount", "op": ">=", "value": 30000},
    ]}, "极高", 95, "拒绝", 95, "新账号首次缴费即 ≥ 3 万(一票否决)"),
    ("R009", "报名缴费间隔极短", "缴费", "缴费", {"field": "enroll_pay_interval", "op": ">=", "value": 0}, "低", 20, "标记", 20, "报名后立即缴费(仅记录)"),
    ("R010", "缴费后退费率高", "缴费", "缴费", {"field": "user_refund_rate", "op": ">=", "value": 0.5}, "高", 70, "人工审核", 70, "历史退费率 ≥ 50%"),
    # ---------- 退费风险 (R011-R015) ----------
    ("R011", "高频退费", "退费", "退费", {"field": "user_refund_count", "op": ">=", "value": 3}, "中", 50, "标记", 60, "退费 ≥ 3 次"),
    ("R012", "退费金额异常", "退费", "退费", {"field": "user_refund_amount", "op": ">=", "value": 20000}, "高", 75, "人工审核", 75, "累计退费 ≥ 2 万"),
    ("R013", "退费率极高", "退费", "退费", {"and": [
        {"field": "user_refund_rate", "op": ">=", "value": 0.8},
        {"field": "user_total_enrollments", "op": ">=", "value": 5},
    ]}, "极高", 90, "拒绝", 90, "报名 5 次以上且退费 ≥ 80%,疑似薅羊毛(一票否决)"),
    ("R014", "报名即退费", "退费", "退费", {"field": "enroll_pay_interval", "op": "<=", "value": 60}, "中", 40, "标记", 50, "报名 1 分钟内退费"),
    ("R015", "退费+投诉组合", "退费", "退费", {"and": [
        {"field": "user_refund_count", "op": ">=", "value": 2},
        {"field": "user_complaint_count", "op": ">=", "value": 2},
    ]}, "高", 65, "人工审核", 65, "退费 ≥ 2 次且投诉 ≥ 2 次"),
    # ---------- 考试风险 (R016-R020) ----------
    ("R016", "考试作弊记录", "考试", "考试", {"field": "user_cheat_count", "op": ">=", "value": 1}, "高", 80, "人工审核", 85, "有考试作弊标记"),
    ("R017", "多次作弊", "考试", "考试", {"field": "user_cheat_count", "op": ">=", "value": 2}, "极高", 92, "拒绝", 92, "作弊 ≥ 2 次(一票否决)"),
    ("R018", "频繁考试", "考试", "考试", {"field": "user_exam_count", "op": ">=", "value": 20}, "低", 25, "标记", 30, "考试次数过多,疑似刷考"),
    ("R019", "跨校区异常考试", "考试", "考试", {"field": "acct_school_count", "op": ">=", "value": 3}, "中", 45, "标记", 55, "报名 3 个以上校区"),
    ("R020", "新账号考试", "考试", "考试", {"field": "acct_is_new", "op": "==", "value": 1}, "中", 35, "标记", 40, "新账号参加考试,关注替考风险"),
    # ---------- 账号风险 (R021-R025) ----------
    ("R021", "多账号", "通用", "通用", {"field": "acct_total_count", "op": ">=", "value": 3}, "中", 50, "标记", 60, "账号数 ≥ 3,疑似一人多号"),
    ("R022", "多设备", "通用", "通用", {"field": "user_device_count", "op": ">=", "value": 5}, "中", 45, "标记", 55, "设备数 ≥ 5"),
    ("R023", "跨校区报名", "通用", "通用", {"field": "acct_school_count", "op": ">=", "value": 5}, "高", 65, "人工审核", 65, "报名 ≥ 5 个校区,疑似刷补贴"),
    ("R024", "老账号高频操作", "通用", "通用", {"field": "user_total_enrollments", "op": ">=", "value": 50}, "中", 30, "标记", 35, "累计报名 ≥ 50 次"),
    ("R025", "历史高风险学员", "通用", "通用", {"and": [
        {"field": "user_refund_rate", "op": ">=", "value": 0.4},
        {"field": "user_complaint_count", "op": ">=", "value": 1},
    ]}, "高", 60, "人工审核", 60, "退费率 ≥ 40% 且有投诉"),
    # ---------- 内容/行为风险 (R026-R030) ----------
    ("R026", "大额优惠券使用", "报名", "报名", {"field": "enroll_coupon_count", "op": "==", "value": 1}, "中", 40, "标记", 50, "报名使用了优惠券"),
    ("R027", "大量使用优惠券", "报名", "报名", {"and": [
        {"field": "enroll_coupon_count", "op": "==", "value": 1},
        {"field": "enroll_discount_rate", "op": ">=", "value": 0.8},
    ]}, "高", 68, "人工审核", 68, "优惠券抵扣 ≥ 80%"),
    ("R028", "退款金额接近缴费", "退费", "退费", {"field": "user_refund_amount", "op": ">=", "value": 15000}, "高", 65, "人工审核", 62, "累计退款 ≥ 1.5 万"),
    ("R029", "报名取消频繁", "通用", "通用", {"field": "user_cancel_count", "op": ">=", "value": 5}, "中", 45, "标记", 58, "取消报名 ≥ 5 次"),
    ("R030", "综合高危画像", "通用", "通用", {"and": [
        {"field": "user_refund_rate", "op": ">=", "value": 0.5},
        {"field": "user_avg_payment", "op": ">=", "value": 2000},
        {"field": "acct_total_count", "op": ">=", "value": 3},
    ]}, "极高", 95, "拒绝", 95, "退费率≥50% + 平均缴费≥2000 + 多账号(一票否决)"),
]


async def init():
    # 1. 建表
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] 24 张表创建完成")

    # 2. 预置规则(已存在则跳过)
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        existing = (await db.execute(select(RiskRule.rule_id))).scalars().all()
        existing_set = set(existing)
        added = 0
        for rid, name, category, event_type, cond, level, score, action, priority, desc in PRESET_RULES:
            if rid in existing_set:
                continue
            rule = RiskRule(
                rule_id=rid, rule_name=name, rule_category=category, event_type=event_type,
                rule_condition=cond, risk_level=level, risk_score=score,
                action=action, priority=priority, description=desc,
            )
            db.add(rule)
            added += 1
        await db.commit()
        print(f"[OK] 预置规则: 新增 {added} 条,已存在 {len(existing_set)} 条")
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(init())
    print("完成! 运行: python _run.py")

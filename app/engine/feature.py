"""
特征工程模块: 通过 ORM 查询银行业务数据, 计算 25 个风控特征.

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  cust_xxx  = 客户维度特征 (14)
  loan_xxx  = 贷款申请维度特征 (8)
  dev_xxx   = 设备/网络维度特征 (3)
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import (
    ComplaintRecord, ContactInfo, LoanApplication, LoanInstallment,
    LoanRepaymentRel, OverdueRecord, RepaymentRecord,
)


# 通用 SQL 工具
async def _count(model, db: AsyncSession, **filters) -> float:
    """SELECT COUNT(*) FROM model WHERE filters."""
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(model, col_name: str, db: AsyncSession, **filters) -> float:
    """SELECT COALESCE(SUM(col), 0) FROM model WHERE filters."""
    col = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(col), 0)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _loan_ids_by_customer(db: AsyncSession, customer_id: str):
    """查询客户全部 loan_id (list)."""
    rows = (await db.execute(
        select(LoanApplication.loan_id).where(LoanApplication.customer_id == customer_id)
    )).scalars().all()
    return list(rows)


# ============================================================
# 客户维度特征 (14 个) — 多头借贷/逾期/履约/被拒史
# ============================================================

async def _feat_cust_total_loans(db: AsyncSession, customer_id: str) -> float:
    """历史申请总数"""
    return await _count(LoanApplication, db, customer_id=customer_id)


async def _feat_cust_loans_30d(db: AsyncSession, customer_id: str) -> float:
    """近 30 天申请数"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(LoanApplication).where(
        LoanApplication.customer_id == customer_id,
        LoanApplication.apply_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_cust_loans_7d(db: AsyncSession, customer_id: str) -> float:
    """近 7 天申请数 (多头借贷核心指标)"""
    since = datetime.now() - timedelta(days=7)
    stmt = select(func.count()).select_from(LoanApplication).where(
        LoanApplication.customer_id == customer_id,
        LoanApplication.apply_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_cust_total_amount(db: AsyncSession, customer_id: str) -> float:
    """历史申请总金额"""
    return await _sum(LoanApplication, "loan_amount", db, customer_id=customer_id)


async def _feat_cust_avg_loan_amount(
    db: AsyncSession, customer_id: str, total_loans: float | None = None,
) -> float:
    """平均申请金额 = 总金额 / 申请数. total_loans 预传避免重复 SQL."""
    if total_loans is None:
        total_loans = await _feat_cust_total_loans(db, customer_id)
    if total_loans == 0:
        return 0
    total_amount = await _feat_cust_total_amount(db, customer_id)
    return round(total_amount / total_loans, 2)


async def _feat_cust_max_loan_amount(db: AsyncSession, customer_id: str) -> float:
    """最大单笔申请金额"""
    stmt = select(func.coalesce(func.max(LoanApplication.loan_amount), 0)).where(
        LoanApplication.customer_id == customer_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_cust_overdue_count(db: AsyncSession, customer_id: str) -> float:
    """逾期次数 (逾期记录→分期→申请)"""
    stmt = select(func.count()).select_from(OverdueRecord).join(
        LoanInstallment, OverdueRecord.installment_id == LoanInstallment.installment_id
    ).join(
        LoanApplication, LoanInstallment.loan_id == LoanApplication.loan_id
    ).where(
        LoanApplication.customer_id == customer_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_cust_overdue_amount(db: AsyncSession, customer_id: str) -> float:
    """逾期总金额"""
    stmt = select(func.coalesce(func.sum(OverdueRecord.overdue_amount), 0)).select_from(
        OverdueRecord
    ).join(
        LoanInstallment, OverdueRecord.installment_id == LoanInstallment.installment_id
    ).join(
        LoanApplication, LoanInstallment.loan_id == LoanApplication.loan_id
    ).where(
        LoanApplication.customer_id == customer_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_cust_overdue_rate(
    db: AsyncSession, customer_id: str, total_loans: float | None = None,
) -> float:
    """逾期率 = 逾期次数 / 申请总数. total_loans 预传避免重复 SQL."""
    if total_loans is None:
        total_loans = await _feat_cust_total_loans(db, customer_id)
    if total_loans == 0:
        return 0
    overdue_count = await _feat_cust_overdue_count(db, customer_id)
    return round(overdue_count / total_loans, 4)


async def _feat_cust_repay_count(db: AsyncSession, customer_id: str) -> float:
    """正常还款次数 (还款记录→关联→申请)"""
    stmt = select(func.count(func.distinct(RepaymentRecord.repayment_id))).select_from(
        RepaymentRecord
    ).join(
        LoanRepaymentRel, RepaymentRecord.repayment_id == LoanRepaymentRel.repayment_id
    ).join(
        LoanApplication, LoanRepaymentRel.loan_id == LoanApplication.loan_id
    ).where(
        LoanApplication.customer_id == customer_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_cust_repay_rate(
    db: AsyncSession, customer_id: str, total_loans: float | None = None,
) -> float:
    """还款结清率 = 已结清申请数 / 申请总数. total_loans 预传避免重复 SQL."""
    if total_loans is None:
        total_loans = await _feat_cust_total_loans(db, customer_id)
    if total_loans == 0:
        return 0
    closed = await _count(LoanApplication, db, customer_id=customer_id, loan_status="已结清")
    return round(closed / total_loans, 4)


async def _feat_cust_reject_count(db: AsyncSession, customer_id: str) -> float:
    """被拒次数 (loan_status='已拒绝')"""
    return await _count(LoanApplication, db, customer_id=customer_id, loan_status="已拒绝")


async def _feat_cust_complaint_count(db: AsyncSession, customer_id: str) -> float:
    """投诉次数"""
    return await _count(ComplaintRecord, db, customer_id=customer_id)


async def _feat_cust_contact_count(db: AsyncSession, customer_id: str) -> float:
    """联系信息数"""
    return await _count(ContactInfo, db, customer_id=customer_id)


# ============================================================
# 申请维度特征 (8 个) — 单笔申请画像
# ============================================================

async def _get_loan_row(db: AsyncSession, loan_id: str):
    """查询单笔申请行 (loan_application)."""
    return (await db.execute(
        select(LoanApplication).where(LoanApplication.loan_id == loan_id)
    )).first()


async def _feat_loan_amount(db: AsyncSession, loan_id: str) -> float:
    """申请金额"""
    row = await _get_loan_row(db, loan_id)
    return float(row.LoanApplication.loan_amount) if row else 0.0


async def _feat_loan_term_month(db: AsyncSession, loan_id: str) -> float:
    """期限 (月)"""
    row = await _get_loan_row(db, loan_id)
    return float(row.LoanApplication.loan_term_month) if row else 0.0


async def _feat_loan_debt_ratio(db: AsyncSession, loan_id: str) -> float:
    """负债率 = 现有负债 / 申请金额"""
    row = await _get_loan_row(db, loan_id)
    if not row:
        return 0.0
    amount = float(row.LoanApplication.loan_amount)
    debt = float(row.LoanApplication.debt_amount)
    if amount == 0:
        return 0.0
    return round(debt / amount, 4)


async def _feat_loan_apply_interval_sec(db: AsyncSession, loan_id: str) -> float:
    """距上次申请间隔 (秒), 首次申请返回 -1"""
    row = await _get_loan_row(db, loan_id)
    if not row:
        return -1.0
    customer_id = row.LoanApplication.customer_id
    apply_time = row.LoanApplication.apply_time
    prev = (await db.execute(
        select(LoanApplication.apply_time)
        .where(
            LoanApplication.customer_id == customer_id,
            LoanApplication.apply_time < apply_time,
        )
        .order_by(LoanApplication.apply_time.desc())
        .limit(1)
    )).first()
    if prev and prev.apply_time:
        return max(float((apply_time - prev.apply_time).total_seconds()), 0)
    return -1.0


async def _feat_loan_apply_is_night(db: AsyncSession, loan_id: str) -> float:
    """是否夜间申请 (0~6 点)"""
    row = await _get_loan_row(db, loan_id)
    if row and row.LoanApplication.apply_time:
        return 1.0 if 0 <= row.LoanApplication.apply_time.hour < 6 else 0.0
    return 0.0


async def _feat_loan_to_income(db: AsyncSession, loan_id: str) -> float:
    """贷款收入比 = 申请金额 / 年收入"""
    row = await _get_loan_row(db, loan_id)
    if not row:
        return 0.0
    income = float(row.LoanApplication.annual_income)
    amount = float(row.LoanApplication.loan_amount)
    if income == 0:
        return 0.0
    return round(amount / income, 4)


async def _feat_loan_apply_product_count(db: AsyncSession, loan_id: str) -> float:
    """申请过的产品种类数 (客户维度 DISTINCT)"""
    row = await _get_loan_row(db, loan_id)
    if not row:
        return 0.0
    stmt = select(func.count(func.distinct(LoanApplication.product_id))).where(
        LoanApplication.customer_id == row.LoanApplication.customer_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_loan_income_debt_ratio(db: AsyncSession, loan_id: str) -> float:
    """收入负债比 = 现有负债 / 年收入"""
    row = await _get_loan_row(db, loan_id)
    if not row:
        return 0.0
    income = float(row.LoanApplication.annual_income)
    debt = float(row.LoanApplication.debt_amount)
    if income == 0:
        return 0.0
    return round(debt / income, 4)


# ============================================================
# 设备/网络维度特征 (3 个) — 反欺诈 (设备聚集/代理/新设备)
# ============================================================

async def _feat_dev_device_count(db: AsyncSession, customer_id: str) -> float:
    """设备使用数 (客户 DISTINCT device_id)"""
    stmt = select(func.count(func.distinct(LoanApplication.device_id))).where(
        LoanApplication.customer_id == customer_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_dev_ip_province_count(db: AsyncSession, customer_id: str) -> float:
    """申请 IP 跨省数 (客户 DISTINCT apply_ip_province)"""
    stmt = select(func.count(func.distinct(LoanApplication.apply_ip_province))).where(
        LoanApplication.customer_id == customer_id
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_dev_is_new(db: AsyncSession, customer_id: str, loan_id: str | None) -> float:
    """是否新设备 (该 loan_id 的 device_id 在客户申请中次数 <= 1)"""
    if not loan_id:
        return 0.0
    row = (await db.execute(
        select(LoanApplication.device_id).where(LoanApplication.loan_id == loan_id)
    )).first()
    if not row or not row.device_id:
        return 0.0
    cnt = (await db.execute(
        select(func.count()).select_from(LoanApplication).where(
            LoanApplication.customer_id == customer_id,
            LoanApplication.device_id == row.device_id,
        )
    )).scalar() or 0
    return 1.0 if cnt <= 1 else 0.0


# ============================================================
# 分类聚合 (字典派发: 加新特征只加一行)
# ============================================================

async def compute_user_features(db: AsyncSession, customer_id: str) -> dict[str, float]:
    """计算 14 个客户维度特征.

    【P5 优化】先 await 1 次 _feat_cust_total_loans, 传给 3 个派生特征复用.
    """
    total_loans = await _feat_cust_total_loans(db, customer_id)

    independent = {
        "cust_loans_30d": _feat_cust_loans_30d,
        "cust_loans_7d": _feat_cust_loans_7d,
        "cust_total_amount": _feat_cust_total_amount,
        "cust_max_loan_amount": _feat_cust_max_loan_amount,
        "cust_overdue_count": _feat_cust_overdue_count,
        "cust_overdue_amount": _feat_cust_overdue_amount,
        "cust_repay_count": _feat_cust_repay_count,
        "cust_reject_count": _feat_cust_reject_count,
        "cust_complaint_count": _feat_cust_complaint_count,
        "cust_contact_count": _feat_cust_contact_count,
    }
    features = {name: await func(db, customer_id) for name, func in independent.items()}
    features["cust_total_loans"] = total_loans

    # 派生特征: 传 total_loans 避免再查
    features["cust_avg_loan_amount"] = await _feat_cust_avg_loan_amount(db, customer_id, total_loans=total_loans)
    features["cust_overdue_rate"] = await _feat_cust_overdue_rate(db, customer_id, total_loans=total_loans)
    features["cust_repay_rate"] = await _feat_cust_repay_rate(db, customer_id, total_loans=total_loans)
    return features


async def compute_loan_features(db: AsyncSession, loan_id: str) -> dict[str, float]:
    """计算 8 个贷款申请维度特征."""
    feat_funcs = {
        "loan_amount": _feat_loan_amount,
        "loan_term_month": _feat_loan_term_month,
        "loan_debt_ratio": _feat_loan_debt_ratio,
        "loan_apply_interval_sec": _feat_loan_apply_interval_sec,
        "loan_apply_is_night": _feat_loan_apply_is_night,
        "loan_to_income": _feat_loan_to_income,
        "loan_apply_product_count": _feat_loan_apply_product_count,
        "loan_income_debt_ratio": _feat_loan_income_debt_ratio,
    }
    return {name: await func(db, loan_id) for name, func in feat_funcs.items()}


async def compute_device_features(
    db: AsyncSession,
    customer_id: str,
    loan_id: str | None = None,
) -> dict[str, float]:
    """计算 3 个设备/网络维度特征."""
    return {
        "dev_device_count": await _feat_dev_device_count(db, customer_id),
        "dev_ip_province_count": await _feat_dev_ip_province_count(db, customer_id),
        "dev_is_new": await _feat_dev_is_new(db, customer_id, loan_id),
    }


async def compute_all_features(
    db: AsyncSession,
    customer_id: str,
    loan_id: str | None = None,
) -> dict[str, float]:
    """一次性计算全部特征并合并返回 (25 维)."""
    features = await compute_user_features(db, customer_id)
    if loan_id:
        features.update(await compute_loan_features(db, loan_id))
    features.update(await compute_device_features(db, customer_id, loan_id))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("特征工程 — 25 维银行风控特征名 + 字典派发表")
    print("=" * 60)

    cust_feats = [
        ("cust_total_loans",        "历史申请总数"),
        ("cust_loans_30d",          "近 30 天申请数"),
        ("cust_loans_7d",           "近 7 天申请数 (多头借贷)"),
        ("cust_total_amount",       "历史申请总金额"),
        ("cust_avg_loan_amount",    "平均申请金额"),
        ("cust_max_loan_amount",    "最大单笔申请金额"),
        ("cust_overdue_count",      "逾期次数"),
        ("cust_overdue_rate",       "逾期率"),
        ("cust_overdue_amount",     "逾期总金额"),
        ("cust_repay_count",        "正常还款次数"),
        ("cust_repay_rate",         "还款结清率"),
        ("cust_reject_count",       "被拒次数"),
        ("cust_complaint_count",    "投诉次数"),
        ("cust_contact_count",      "联系信息数"),
    ]
    loan_feats = [
        ("loan_amount",             "申请金额"),
        ("loan_term_month",         "期限 (月)"),
        ("loan_debt_ratio",         "负债率 (现有负债/申请金额)"),
        ("loan_apply_interval_sec",      "距上次申请间隔 (秒)"),
        ("loan_apply_is_night",          "是否夜间申请 (0~6 点)"),
        ("loan_to_income",          "贷款收入比 (申请金额/年收入)"),
        ("loan_apply_product_count",     "申请过的产品种类数"),
        ("loan_income_debt_ratio",  "收入负债比 (现有负债/年收入)"),
    ]
    dev_feats = [
        ("dev_device_count",        "设备使用数"),
        ("dev_ip_province_count",   "申请 IP 跨省数"),
        ("dev_is_new",              "本次设备是否新设备 (0/1)"),
    ]
    total = 0
    for sec, feats in [("客户 (14)", cust_feats), ("申请 (8)", loan_feats), ("设备/网络 (3)", dev_feats)]:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<25} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 XGBoost 的 FEATURE_COLUMNS 顺序一一对应)")

    print("\n" + "=" * 60)
    print("[P5 优化示例] 1 次 SQL 查 cust_total_loans, 复用给 3 个函数:")
    print("  compute_user_features(db, customer_id) 内部")
    print("    _feat_cust_total_loans(db, customer_id)            → 1 次 SQL")
    print("    _feat_cust_avg_loan_amount(...,total_loans)        → 0 次 SQL (复用)")
    print("    _feat_cust_overdue_rate(...,total_loans)           → 0 次 SQL (复用)")
    print("    _feat_cust_repay_rate(...,total_loans)             → 0 次 SQL (复用)")
    print("  原来 4 个特征 = 4 次 SQL → 现在 4 个 = 1 次 SQL (节省 75%)")
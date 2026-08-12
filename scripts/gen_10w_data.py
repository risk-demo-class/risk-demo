"""银行信贷风控 - 数据生成器.

规模 (D8 决策): 5000 客户 / 3 万贷款申请, 风险画像 80% 正常 / 15% 中 / 5% 高.
高风险客户注入: 多头借贷/逾期/被拒史 (PD 训练正例来源).

生成数据 (FK 完整):
  - customer_info + contact_info
  - loan_application (含设备/IP/收入负债)
  - loan_installment (分期明细) + repayment_record + loan_repayment_rel
  - overdue_record + overdue_repayment_rel
  - complaint_record
"""
import random
from datetime import datetime, timedelta

import ulid
from faker import Faker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

RISK_TIERS = {"normal": 0.80, "medium": 0.15, "high": 0.05}
DEFAULT_N_CUSTOMER = 5000
DEFAULT_N_LOAN = 30000

PRODUCT_IDS = ["P001", "P002", "P003", "P004", "P005", "P006"]
PROVINCES = ["上海", "北京", "广东", "浙江", "江苏", "四川", "湖北", "山东", "福建", "河南"]
OVERDUE_REASONS = ["临时资金周转困难", "失业", "经营失败", "疾病医疗支出", "恶意拖欠", "其他"]
COMPLAINTS = ["客服态度恶劣", "利率过高", "催收方式不当", "合同条款不清晰", "APP 无法正常使用"]

fake = Faker("zh_CN")

# 从 region 表读取的真实区划 (v1: 每省取前 3 条, 保证 FK 有效)
REGION_ROWS: list[tuple[str, str, str]] = []


def _rid(prefix: str = "") -> str:
    return f"{prefix}{ulid.new().str.lower()}"


def _risk_tier() -> str:
    r = random.random()
    if r < RISK_TIERS["normal"]:
        return "normal"
    if r < RISK_TIERS["normal"] + RISK_TIERS["medium"]:
        return "medium"
    return "high"


def _gen_contact(cid: str) -> dict:
    """1 条联系信息 (区划取自 region 表保证 FK)."""
    prov, city, dist = random.choice(REGION_ROWS) if REGION_ROWS else ("上海", "上海市", "浦东新区")
    return {
        "contact_id": _rid("ct"),
        "customer_id": cid,
        "contact_person": fake.name(),
        "contact_phone": fake.phone_number(),
        "contact_province": prov,
        "contact_city": city,
        "contact_district": dist,
        "contact_address": fake.address()[:45],
        "emergency_name": fake.name(),
        "emergency_phone": fake.phone_number(),
    }


def loan_application_row(
    loan_id: str, cid: str, contact_id: str, tier: str, apply_time: datetime,
    device_id: str, ip_province: str,
) -> dict:
    """1 条贷款申请行 (银行时间线字段 apply_time/approve_time/loan_time/mature_time)."""
    amount = random.choice([30000, 50000, 80000, 100000, 150000, 200000])
    term = random.choice([12, 24, 36, 60])
    income = random.randint(80000, 300000)
    debt = random.randint(0, 150000)
    status = random.choice(["申请中", "审批中", "已放款", "还款中", "已结清"])
    if tier == "high":
        status = random.choices(["已拒绝", "逾期", "还款中", "已放款"], weights=[0.3, 0.3, 0.2, 0.2])[0]
        amount = random.choice([50000, 100000, 150000, 200000, 300000])
        debt = random.randint(80000, 250000)
    elif tier == "medium":
        status = random.choices(["已拒绝", "还款中", "已放款", "已结清"], weights=[0.15, 0.35, 0.25, 0.25])[0]

    approved = status not in ("申请中", "已拒绝")
    approve = apply_time + timedelta(days=random.randint(1, 7)) if approved else None
    loan_t = approve + timedelta(days=random.randint(1, 3)) if approve and status != "逾期" else None
    mature = loan_t + timedelta(days=30 * term) if loan_t else None
    return {
        "loan_id": loan_id, "apply_time": apply_time, "approve_time": approve,
        "loan_time": loan_t, "mature_time": mature, "customer_id": cid,
        "contact_id": contact_id, "product_id": random.choice(PRODUCT_IDS),
        "loan_status": status, "loan_amount": amount, "loan_term_month": term,
        "installment_count": term, "annual_income": income, "debt_amount": debt,
        "device_id": device_id, "apply_ip_province": ip_province,
    }


def gen_customers(n: int) -> dict[str, str]:
    """生成客户 id -> 风险分层 (tier)."""
    return {f"C{i:05d}": _risk_tier() for i in range(1, n + 1)}


def gen_loan_applications(
    customers: dict[str, str], contacts: dict[str, str], n_loan: int,
) -> list[dict]:
    """生成贷款申请. 高风险客户申请更频繁 (多头借贷特征)."""
    weights = {"normal": 3, "medium": 5, "high": 8}
    pool = [cid for cid, tier in customers.items() for _ in range(weights[tier])]
    now = datetime.now()
    rows = []
    for i in range(n_loan):
        cid = random.choice(pool)
        tier = customers[cid]
        days_ago = random.randint(0, 90 if tier == "normal" else (30 if tier == "medium" else 7))
        apply_time = now - timedelta(days=days_ago, hours=random.randint(0, 23))
        device = f"DEV-{random.randint(1, 2000):04d}" if tier != "high" else f"DEV-H{random.randint(1, 300):03d}"
        ip_prov = random.choice(PROVINCES) if tier != "high" else random.choice(["广东", "福建", "广西", "云南", "贵州"])
        rows.append(loan_application_row(
            f"LN{i:06d}", cid, contacts[cid], tier, apply_time, device, ip_prov,
        ))
    return rows


def _active_loans(loans: list[dict]) -> list[dict]:
    """已放款/还款中/已结清/逾期的申请 (有分期与还款)."""
    return [lo for lo in loans if lo["loan_status"] in ("已放款", "还款中", "已结清", "逾期")]


def gen_installments(loans: list[dict]) -> list[dict]:
    """分期明细: 每笔已放款申请按期限生成期数."""
    rows = []
    for lo in _active_loans(loans):
        loan_time = lo["loan_time"] or lo["apply_time"]
        paid_no = 0
        if lo["loan_status"] == "已结清":
            paid_no = lo["installment_count"]
        elif lo["loan_status"] == "逾期":
            paid_no = random.randint(0, max(lo["installment_count"] - 1, 0))
        else:
            paid_no = random.randint(1, max(min(lo["installment_count"], 4), 1))
        for no in range(1, lo["installment_count"] + 1):
            due = loan_time + timedelta(days=30 * no)
            paid = due if no <= paid_no else None
            rows.append({
                "installment_id": f"INS{lo['loan_id']}-{no}",
                "loan_id": lo["loan_id"],
                "product_id": lo["product_id"],
                "installment_no": no,
                "due_amount": round(lo["loan_amount"] / lo["installment_count"], 2),
                "paid_amount": round(lo["loan_amount"] / lo["installment_count"], 2) if paid else 0,
                "due_date": due,
                "paid_date": paid,
            })
    return rows


def gen_repayments(loans: list[dict]) -> tuple[list[dict], list[dict]]:
    """还款记录 + loan_repayment_rel 关联."""
    rows, rels = [], []
    for lo in _active_loans(loans):
        n_pay = 1 if lo["loan_status"] in ("已放款", "逾期") else random.randint(1, min(lo["installment_count"], 6))
        for k in range(1, n_pay + 1):
            rp_id = _rid("rp")
            pay_time = (lo["loan_time"] or lo["apply_time"]) + timedelta(days=30 * k)
            rows.append({
                "repayment_id": rp_id, "create_time": pay_time, "repaid_time": pay_time,
                "repayment_amount": round(lo["loan_amount"] / lo["installment_count"], 2),
                "repayment_category": random.choice(["正常还款", "正常还款", "提前还款"]),
            })
            rels.append({"loan_id": lo["loan_id"], "repayment_id": rp_id})
    return rows, rels


def gen_overdues(loans: list[dict]) -> tuple[list[dict], list[dict]]:
    """逾期记录 (关联逾期期分期). overdue_repayment_rel 留空 (演示不需要)."""
    rows = []
    for lo in loans:
        if lo["loan_status"] != "逾期":
            continue
        due_no = lo["installment_count"]  # 最后一期未还
        ov_id = _rid("ov")
        pay_time = (lo["loan_time"] or lo["apply_time"]) + timedelta(days=30 * due_no)
        rows.append({
            "overdue_id": ov_id, "create_time": pay_time,
            "complete_time": None, "installment_id": f"INS{lo['loan_id']}-{due_no}",
            "overdue_amount": round(lo["loan_amount"] / lo["installment_count"], 2),
            "overdue_days": random.randint(5, 90),
            "overdue_reason": random.choice(OVERDUE_REASONS),
            "overdue_status": "逾期", "contact_id": lo["contact_id"],
        })
    return rows, []


def gen_complaints(loans: list[dict]) -> list[dict]:
    """投诉记录: 约 3% 申请产生投诉."""
    rows = []
    for lo in loans:
        if random.random() < 0.03:
            rows.append({
                "customer_id": lo["customer_id"], "loan_id": lo["loan_id"],
                "complaint_content": random.choice(COMPLAINTS),
                "complaint_time": (lo["approve_time"] or lo["apply_time"]) + timedelta(days=random.randint(1, 30)),
            })
    return rows


async def gen_10w_data(n_user: int = DEFAULT_N_CUSTOMER, n_loan: int = DEFAULT_N_LOAN, batch_size: int = 500):
    """主入口: 生成银行数据并批量入库."""
    engine = create_async_engine(settings.get_database_url_async(), echo=False)
    print("=" * 60)
    print(f"银行风控数据生成: 客户 {n_user} / 申请 {n_loan} (80/15/5 风险分层)")
    print("=" * 60)

    customers = gen_customers(n_user)
    # 预加载 region 真实区划 (保证 FK)
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT province, city, district FROM region ORDER BY RAND() LIMIT 300"
        ))
        REGION_ROWS.extend([(r[0], r[1], r[2]) for r in result.fetchall()])
    contact_rows = [_gen_contact(cid) for cid in customers]
    contacts = {c["customer_id"]: c["contact_id"] for c in contact_rows}
    loans = gen_loan_applications(customers, contacts, n_loan)
    installments = gen_installments(loans)
    repayments, rel_rp = gen_repayments(loans)
    overdues, rel_ov = gen_overdues(loans)
    complaints = gen_complaints(loans)

    async with engine.begin() as conn:
        await conn.execute(text("INSERT IGNORE INTO customer_info (customer_id, customer_name, customer_phone, id_card_no, status) VALUES (:customer_id, :customer_name, :customer_phone, :id_card_no, :status)"),
                           [{"customer_id": cid, "customer_name": fake.name(), "customer_phone": fake.phone_number(),
                             "id_card_no": fake.ssn(), "status": "正常"} for cid in customers])
        await conn.execute(text("INSERT IGNORE INTO contact_info (contact_id, customer_id, contact_person, contact_phone, contact_province, contact_city, contact_district, contact_address, emergency_name, emergency_phone) VALUES (:contact_id, :customer_id, :contact_person, :contact_phone, :contact_province, :contact_city, :contact_district, :contact_address, :emergency_name, :emergency_phone)"), contact_rows)
        await conn.execute(text("INSERT IGNORE INTO loan_application (loan_id, apply_time, approve_time, loan_time, mature_time, customer_id, contact_id, product_id, loan_status, loan_amount, loan_term_month, installment_count, annual_income, debt_amount, device_id, apply_ip_province) VALUES (:loan_id, :apply_time, :approve_time, :loan_time, :mature_time, :customer_id, :contact_id, :product_id, :loan_status, :loan_amount, :loan_term_month, :installment_count, :annual_income, :debt_amount, :device_id, :apply_ip_province)"), loans)
        await conn.execute(text("INSERT IGNORE INTO loan_installment (installment_id, loan_id, product_id, installment_no, due_amount, paid_amount, due_date, paid_date) VALUES (:installment_id, :loan_id, :product_id, :installment_no, :due_amount, :paid_amount, :due_date, :paid_date)"), installments)
        await conn.execute(text("INSERT IGNORE INTO repayment_record (repayment_id, create_time, repaid_time, repayment_amount, repayment_category) VALUES (:repayment_id, :create_time, :repaid_time, :repayment_amount, :repayment_category)"), repayments)
        await conn.execute(text("INSERT IGNORE INTO loan_repayment_rel (loan_id, repayment_id) VALUES (:loan_id, :repayment_id)"), rel_rp)
        await conn.execute(text("INSERT IGNORE INTO overdue_record (overdue_id, create_time, complete_time, installment_id, overdue_amount, overdue_days, overdue_reason, overdue_status, contact_id) VALUES (:overdue_id, :create_time, :complete_time, :installment_id, :overdue_amount, :overdue_days, :overdue_reason, :overdue_status, :contact_id)"), overdues)
        await conn.execute(text("INSERT IGNORE INTO overdue_repayment_rel (overdue_id, repayment_id) VALUES (:overdue_id, :repayment_id)"), rel_ov) if rel_ov else None
        await conn.execute(text("INSERT IGNORE INTO complaint_record (customer_id, loan_id, complaint_content, complaint_time) VALUES (:customer_id, :loan_id, :complaint_content, :complaint_time)"), complaints)

    print(f"  → 客户 {len(customers)} / 联系信息 {len(contact_rows)}")
    print(f"  → 贷款申请 {len(loans)} / 分期 {len(installments)}")
    print(f"  → 还款 {len(repayments)} / 关联 {len(rel_rp)} / 逾期 {len(overdues)} / 投诉 {len(complaints)}")
    await engine.dispose()
    return len(customers), len(loans)


if __name__ == "__main__":
    import asyncio
    import argparse

    parser = argparse.ArgumentParser(description="生成银行信贷风控演示数据")
    parser.add_argument("--users", type=int, default=DEFAULT_N_CUSTOMER, help="客户数 (默认 5000)")
    parser.add_argument("--loans", type=int, default=DEFAULT_N_LOAN, help="申请数 (默认 30000)")
    parser.add_argument("--batch", type=int, default=500, help="批量插入批次 (默认 500)")
    args = parser.parse_args()
    asyncio.run(gen_10w_data(args.users, args.loans, args.batch))
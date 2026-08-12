"""
银行信贷风控系统 - 业务造数脚本 (Task 2 交付物)

生成 17 张银行业务表的全量数据, 覆盖信贷全生命周期:
  借款人主档 / 企业档案 / 账户 / 申请 / 合同 / 还款计划 / 还款流水 /
  征信 / 收入核验 / 抵押 / 担保 / 交易 / 登录 / 设备 / IP / 黑名单 / 关联关系

【内置欺诈人群 (为 Task 3 规则命中 + XGBoost 训练标签准备)】
  - ring_member   团伙: 共享设备/共享地址/共享收款账户/互保, 代理IP申请
  - multi_loan    多头借贷: 30-60 天内密集申请, DTI 高, 硬查询多
  - income_fraud  材料造假: 申报收入 3-6 倍于核验收入, 三源交叉显著偏差
  - shell_ent     空壳公司: 注册时间短, 实缴低, 纳税近0, 信用代码上黑名单
  - default_risk  逾期: M1/M2/M3 逾期计划, 部分核销/不良
  - fund_return   资金回流: 放款受托支付后 1-7 天转回本人/关联账户
  - internal      内部员工骗贷: 本行员工 + 伪造收入材料

用法:
  python scripts/gen_business_data.py                 # 生成 sql/init_business_data.sql
  python scripts/gen_business_data.py --insert        # 生成 SQL 并直接写入 MySQL (先清空业务表)
  python scripts/gen_business_data.py --users 200     # 200 个借款人 (默认 120)
  python scripts/gen_business_data.py --seed 42       # 固定随机种子, 可重复
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import hashlib
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

import aiomysql
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ============================================================
# 数据基准"今天": 默认取当天, 保证演示数据新鲜;
# 需要复现历史数据时用 --date YYYY-MM-DD 固定 (如 --date 2026-08-11)
# ============================================================
REF_DATE = date.today()
REF_DATETIME = datetime.combine(REF_DATE, time(12, 0))

# ============================================================
# 造数常量
# ============================================================
DEFAULT_USERS = 120
DEFAULT_SEED = 42
BATCH_SIZE = 500

SURNAMES = "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
GIVEN_NAMES = "伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛明超霞平刚桂英华玉萍红梅文辉建斌玲军兰海燕峰成东福林林鹏飞雪松涛志强宇轩子涵欣怡浩然思远俊杰雨桐梓豪佳琪天佑博文梦琪"
EDUCATIONS = ("初中及以下", "高中/中专", "大专", "本科", "硕士", "博士")
OCCUPATIONS = ("企业职员", "公务员", "教师", "医生", "程序员", "销售", "个体户", "企业主", "自由职业", "司机", "会计", "工程师")
EMPLOYER_CATEGORIES = ("国企", "民企", "外企", "机关事业单位", "个体工商户", "自由职业", "其他")
INDUSTRIES = ("制造业", "批发零售业", "信息技术业", "建筑业", "交通运输业", "餐饮业", "教育业", "医疗业", "房地产业", "金融业")

AREA_CODES = ("110101", "310101", "440301", "440101", "330102", "510104", "420102", "320102",
              "120101", "500103", "610102", "210102", "350102", "370102", "410102", "430102",
              "510107", "440106", "310115", "110105")

CITIES = [
    ("北京市", "北京", "朝阳区"), ("上海市", "上海", "浦东新区"), ("广东省", "深圳市", "南山区"),
    ("广东省", "广州市", "天河区"), ("浙江省", "杭州市", "西湖区"), ("四川省", "成都市", "武侯区"),
    ("湖北省", "武汉市", "武昌区"), ("江苏省", "南京市", "鼓楼区"), ("天津市", "天津", "和平区"),
    ("重庆市", "重庆", "渝北区"), ("陕西省", "西安市", "雁塔区"), ("辽宁省", "沈阳市", "和平区"),
    ("福建省", "福州市", "鼓楼区"), ("山东省", "济南市", "历下区"), ("河南省", "郑州市", "金水区"),
    ("湖南省", "长沙市", "岳麓区"), ("安徽省", "合肥市", "蜀山区"), ("江西省", "南昌市", "东湖区"),
    ("广西壮族自治区", "南宁市", "青秀区"), ("云南省", "昆明市", "五华区"),
]

PURPOSE_PRODUCT = {
    "消费": ("XF001", "消费易贷"),
    "经营": ("JY001", "经营快贷"),
    "购房": ("FD001", "房抵贷"),
    "购车": ("GC001", "车易贷"),
    "装修": ("ZX001", "装修贷"),
    "教育": ("ED001", "教育分期"),
    "医疗": ("YL001", "医疗分期"),
    "其他": ("QT001", "综合消费贷"),
}
PURPOSE_AMOUNT = {
    "消费": (10_000, 300_000), "经营": (300_000, 3_000_000), "购房": (500_000, 3_000_000),
    "购车": (50_000, 600_000), "装修": (50_000, 400_000), "教育": (10_000, 200_000),
    "医疗": (10_000, 150_000), "其他": (10_000, 200_000),
}
PURPOSE_TERM = {
    "消费": (12, 24, 36), "经营": (12, 24, 36, 60), "购房": (120, 240, 360),
    "购车": (24, 36, 48, 60), "装修": (12, 24, 36), "教育": (6, 12, 24),
    "医疗": (6, 12, 24), "其他": (6, 12),
}
PURPOSE_RATE = {
    "消费": (4.5, 7.0), "经营": (4.0, 8.0), "购房": (3.5, 5.5), "购车": (4.0, 6.5),
    "装修": (5.0, 8.0), "教育": (5.0, 7.0), "医疗": (4.5, 6.0), "其他": (6.0, 9.0),
}

BANK_CODES = (("ICBC", "中国工商银行"), ("CCB", "中国建设银行"), ("ABC", "中国农业银行"),
              ("BOC", "中国银行"), ("CMB", "招商银行"), ("CIB", "兴业银行"),
              ("SPDB", "浦发银行"), ("CMBC", "民生银行"), ("CITIC", "中信银行"), ("CEB", "光大银行"))

OS_LIST = ("Android 12", "Android 13", "Android 14", "iOS 16.4", "iOS 17.2", "iOS 17.5", "HarmonyOS 4.0")
BROWSERS = ("Chrome 125", "Safari 17.5", "Edge 126", "内置浏览器", None)
ISPS = ("中国电信", "中国联通", "中国移动")

ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
ID_CHECK_CODES = "10X98765432"
CREDIT_CODE_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"

# 表按外键依赖顺序
TABLE_ORDER = [
    "user_info", "enterprise_info", "bank_account", "device_fingerprint", "ip_geo_location",
    "loan_application", "credit_report", "income_verify", "loan_contract", "collateral",
    "guarantee", "repayment_plan", "repayment_record", "transaction", "login_log",
    "blacklist_extra", "user_relation",
]
# 清库时的逆序 (先删有外键指向别人的表)
TRUNCATE_ORDER = list(reversed(TABLE_ORDER))


# ============================================================
# 基础工具
# ============================================================

def D(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def U(rng: random.Random, lo: float, hi: float) -> Decimal:
    """返回 Decimal 均匀随机数, 避免 Decimal * float 报错"""
    return Decimal(str(rng.uniform(lo, hi)))


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def rand_dt(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """start ~ end 之间随机一个时间"""
    span = (end - start).total_seconds()
    return start + timedelta(seconds=rng.uniform(0, max(span, 1)))


def rand_days_ago(rng: random.Random, min_days: int, max_days: int, hour=(9, 21)) -> datetime:
    """n 天前 (含时间)"""
    days = rng.randint(min_days, max_days)
    dt = REF_DATETIME - timedelta(days=days)
    return dt.replace(hour=rng.randint(hour[0], hour[1]), minute=rng.randint(0, 59), second=rng.randint(0, 59))


def gen_id_card(rng: random.Random, birth_date: date, gender: str) -> str:
    area = rng.choice(AREA_CODES)
    dob = birth_date.strftime("%Y%m%d")
    base = rng.randrange(0, 1000, 2)  # 偶数为女
    seq = base if gender == "女" else min(base + 1, 999)
    body = area + dob + f"{seq:03d}"
    checksum = sum(int(c) * w for c, w in zip(body, ID_WEIGHTS)) % 11
    return body + ID_CHECK_CODES[checksum]


def gen_credit_code(rng: random.Random) -> str:
    area = rng.choice(AREA_CODES)
    mid = "".join(rng.choice(CREDIT_CODE_CHARS) for _ in range(9))
    check = rng.choice(CREDIT_CODE_CHARS)
    return "91" + area + mid + check


def gen_mobile(rng: random.Random) -> str:
    return "1" + rng.choice("3456789") + "".join(str(rng.randint(0, 9)) for _ in range(9))


def gen_account_no(rng: random.Random) -> str:
    return "62" + "".join(str(rng.randint(0, 9)) for _ in range(17))


def gen_name(rng: random.Random) -> str:
    surname = rng.choice(SURNAMES)
    given = "".join(rng.choice(GIVEN_NAMES) for _ in range(rng.choice((1, 1, 2))))
    return surname + given


def fmt_sql(v):
    """把 Python 值格式化成 SQL 字面量"""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    if isinstance(v, (datetime, date)):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S') if isinstance(v, datetime) else v.isoformat()}'"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    raise TypeError(f"unsupported type: {type(v)}")


def build_schedule(loan_amount: Decimal, annual_rate: Decimal, term: int, repay_type: str):
    """生成还款计划: [(principal, interest, total), ...]"""
    r = annual_rate / Decimal("100") / Decimal("12")
    p = loan_amount
    plan = []
    if repay_type == "等额本息":
        if r == 0:
            per = p / term
        else:
            per = p * r * (1 + r) ** term / ((1 + r) ** term - 1)
        balance = p
        for i in range(term):
            interest = (balance * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            principal = (per - interest).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if i == term - 1:
                principal = balance
            balance = (balance - principal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            plan.append((principal, interest, principal + interest))
    elif repay_type == "等额本金":
        per_p = (p / term).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        balance = p
        for i in range(term):
            principal = per_p if i < term - 1 else balance
            interest = (balance * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            balance = (balance - principal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            plan.append((principal, interest, principal + interest))
    else:  # 先息后本
        interest = (p * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for i in range(term):
            principal = p if i == term - 1 else D("0.00")
            plan.append((principal, interest, principal + interest))
    return plan


# ============================================================
# 数据生成器
# ============================================================

class Dataset:
    """所有业务表的内存数据集: {table: (columns, rows)}"""

    def __init__(self):
        self.data: dict[str, tuple[list[str], list[list]]] = {}

    def add(self, table: str, columns: list[str], rows: list[list]):
        self.data[table] = (columns, rows)

    def rows(self, table: str) -> int:
        cols, rows = self.data.get(table, ([], []))
        return len(rows)


def generate(users_count: int, seed: int) -> Dataset:
    rng = random.Random(seed)
    ds = Dataset()

    # ---------------- 生成用户池 (含欺诈人群) ----------------
    all_specials = [
        ("ring_member", 12), ("multi_loan", 8), ("income_fraud", 6),
        ("shell_ent", 5), ("default_risk", 10), ("fund_return", 7), ("internal", 2),
    ]
    # 欺诈人群最多 50 人; --users 小于 50 时按顺序裁剪
    effective_special = min(sum(c for _, c in all_specials), users_count)
    special_specs: list[tuple[str, int]] = []
    remaining = effective_special
    for tag, cnt in all_specials:
        take = min(cnt, remaining)
        if take > 0:
            special_specs.append((tag, take))
        remaining -= take
        if remaining <= 0:
            break
    good_count = max(users_count - effective_special, 0)
    profiles: list[tuple[str, str]] = []  # (user_id, risk_tag)
    for tag, cnt in special_specs:
        profiles.extend([(f"U{i + 1:04d}", tag) for i in range(len(profiles), len(profiles) + cnt)])
    profiles.extend([(f"U{i + 1:04d}", "good") for i in range(len(profiles), len(profiles) + good_count)])

    used_mobiles, used_id_cards, used_account_nos, used_codes = set(), set(), set(), set()
    users: list[dict] = []

    for user_id, tag in profiles:
        gender = rng.choice(("男", "男", "男", "女", "女"))
        birth_date = date(rng.randint(1965, 2000), rng.randint(1, 12), rng.randint(1, 28))
        id_card = gen_id_card(rng, birth_date, gender)
        while id_card in used_id_cards:
            id_card = gen_id_card(rng, birth_date, gender)
        used_id_cards.add(id_card)
        mobile = gen_mobile(rng)
        while mobile in used_mobiles:
            mobile = gen_mobile(rng)
        used_mobiles.add(mobile)

        is_employee = 1 if tag == "internal" else 0
        if tag in ("ring_member", "income_fraud", "shell_ent", "internal"):
            kyc = rng.choice(("未认证", "L1", "L1", "L2"))
        else:
            kyc = rng.choice(("L2", "L2", "L3"))

        if tag == "good":
            income = D(rng.randint(8_000, 60_000))
            verified = income
            register_days = rng.randint(180, 2000)
            credit_score = rng.randint(650, 850)
            income_source = rng.choice(("受雇", "受雇", "受雇", "经营", "自雇"))
            maritial = rng.choice(("未婚", "已婚", "已婚", "已婚", "离异"))
        elif tag == "ring_member":
            income = D(rng.randint(6_000, 30_000))
            verified = D(int(income * U(rng, 0.4, 0.7) / 100) * 100)
            register_days = rng.randint(30, 180)
            credit_score = rng.randint(480, 620)
            income_source = rng.choice(("受雇", "自雇"))
            maritial = rng.choice(("未婚", "未婚", "离异"))
        elif tag == "multi_loan":
            income = D(rng.randint(10_000, 40_000))
            verified = income
            register_days = rng.randint(100, 900)
            credit_score = rng.randint(520, 660)
            income_source = rng.choice(("受雇", "受雇", "自雇"))
            maritial = "已婚"
        elif tag == "income_fraud":
            verified = D(rng.randint(6_000, 25_000))
            income = D(int(verified * U(rng, 2.5, 5.5) / 100) * 100)
            register_days = rng.randint(60, 500)
            credit_score = rng.randint(600, 700)
            income_source = rng.choice(("受雇", "自雇"))
            maritial = rng.choice(("未婚", "已婚"))
        elif tag == "shell_ent":
            income = D(rng.randint(15_000, 60_000))
            verified = D(int(income * U(rng, 0.3, 0.5) / 100) * 100)
            register_days = rng.randint(30, 120)
            credit_score = rng.randint(540, 640)
            income_source = "经营"
            maritial = "已婚"
        elif tag == "default_risk":
            income = D(rng.randint(6_000, 30_000))
            verified = income
            register_days = rng.randint(200, 1200)
            credit_score = rng.randint(400, 580)
            income_source = rng.choice(("受雇", "自雇", "经营"))
            maritial = rng.choice(("未婚", "已婚", "离异"))
        elif tag == "fund_return":
            income = D(rng.randint(10_000, 50_000))
            verified = income
            register_days = rng.randint(150, 800)
            credit_score = rng.randint(620, 750)
            income_source = rng.choice(("受雇", "经营"))
            maritial = "已婚"
        else:  # internal
            income = D(rng.randint(12_000, 40_000))
            verified = D(int(income * Decimal("0.5") / 100) * 100)
            register_days = rng.randint(500, 2000)
            credit_score = rng.randint(700, 800)
            income_source = "受雇"
            maritial = "已婚"

        register_at = REF_DATETIME - timedelta(days=register_days, hours=rng.randint(0, 20))
        province, city, district = rng.choice(CITIES)
        street = f"{district}{rng.choice(('幸福里', '阳光花园', '金地国际', '翡翠城', '世纪华庭', '龙湖天街', '滨江壹号'))}{rng.randint(1, 99)}栋{rng.randint(1, 30)}室"
        employer = rng.choice(EMPLOYER_CATEGORIES)
        users.append({
            "user_id": user_id, "name": gen_name(rng), "gender": gender,
            "birth_date": birth_date, "age": REF_DATE.year - birth_date.year,
            "id_card_hash": sha256_hex(id_card), "mobile": mobile,
            "marital_status": maritial, "education": rng.choice(EDUCATIONS),
            "occupation": rng.choice(OCCUPATIONS), "employer_name": None if employer == "自由职业" else f"{rng.choice(('华信', '中科', '恒润', '远大', '锦程', '联创'))}{rng.choice(('科技', '贸易', '实业', '咨询', '物流', '建筑'))}有限公司",
            "employer_category": employer, "industry_code": f"{rng.randint(1, 99):02d}",
            "household_province": province, "household_city": city, "household_district": district,
            "household_address": street, "living_province": province, "living_city": city,
            "living_district": district, "living_address": street,
            "monthly_income": income, "verified_income": verified,
            "income_source": income_source, "credit_score": credit_score,
            "kyc_level": kyc, "register_at": register_at,
            "account_age_days": register_days, "is_employee": is_employee,
        })

    # ---------------- 企业档案 (经营类用户) ----------------
    # 业务语义: 企业只属于"收入来源=经营"的用户, 且空壳公司(shell_ent)强制建档;
    # 之前用 user_id 后缀 (001/013/025) 的魔法 ID 选择, 无业务含义, 已移除
    enterprises: list[dict] = []
    tag_of = dict(profiles)
    ent_users = [
        u for u in users
        if u["income_source"] == "经营" or tag_of[u["user_id"]] == "shell_ent"
    ]
    shell_ids = {uid for uid, tag in profiles if tag == "shell_ent"}
    for idx, u in enumerate(ent_users, 1):
        if u["user_id"] not in shell_ids and rng.random() > 0.5:
            continue
        is_shell = u["user_id"] in shell_ids
        reg_date = (REF_DATE - timedelta(days=rng.randint(60, 400))) if is_shell else (REF_DATE - timedelta(days=rng.randint(3 * 365, 15 * 365)))
        credit_code = gen_credit_code(rng)
        while credit_code in used_codes:
            credit_code = gen_credit_code(rng)
        used_codes.add(credit_code)
        if is_shell:
            reg_capital = D(rng.randint(10, 100) * 10_000)
            paid_in = D(int(reg_capital * U(rng, 0, 0.1)))
            revenue = D(rng.randint(0, 50) * 10_000)
            tax = D(rng.randint(0, 1_000))
            employees = rng.randint(0, 2)
        else:
            reg_capital = D(rng.randint(100, 5000) * 10_000)
            paid_in = D(int(reg_capital * U(rng, 0.5, 1.0)))
            revenue = D(rng.randint(50, 2000) * 10_000)
            tax = D(int(revenue * U(rng, 0.01, 0.05)))
            employees = rng.randint(5, 200)
        enterprises.append({
            "ent_id": f"E{idx:04d}", "user_id": u["user_id"],
            "ent_name": f"{rng.choice(('华信', '中科', '恒润', '远大', '锦程', '联创'))}{rng.choice(('科技', '贸易', '实业', '咨询', '物流', '建筑'))}有限公司",
            "credit_code": credit_code, "legal_person": u["name"], "reg_date": reg_date,
            "business_years": (REF_DATE - reg_date).days // 365,
            "industry": rng.choice(INDUSTRIES), "reg_capital": reg_capital,
            "paid_in_capital": paid_in, "annual_revenue": revenue,
            "annual_tax_amount": tax, "employee_count": employees,
            "operation_status": rng.choice(("存续", "存续", "存续", "在业")),
            "reg_address": f"{u['living_province']}{u['living_city']}{u['living_district']}高新区{rng.randint(1, 88)}号",
        })

    # ---------------- 银行账户 ----------------
    accounts: list[dict] = []
    acc_idx = 0
    ring_shared_accounts: dict[int, str] = {}  # ring_index -> shared account_id
    for u in users:
        tag = next(t for uid, t in profiles if uid == u["user_id"])
        # 团伙/资金回流用户必须 2 张卡: 团伙需要"归集转出+收款", 资金回流需要"放款卡+回流卡"
        if tag in ("ring_member", "fund_return"):
            n_accounts = 2
        elif tag == "good":
            n_accounts = 2 if rng.random() < 0.5 else 1
        else:
            n_accounts = 1
        for k in range(n_accounts):
            acc_idx += 1
            acc_no = gen_account_no(rng)
            while acc_no in used_account_nos:
                acc_no = gen_account_no(rng)
            used_account_nos.add(acc_no)
            is_credit = (k == 0 and tag == "good" and rng.random() < 0.3)
            bank = rng.choice(BANK_CODES)
            open_time = u["register_at"] + timedelta(days=rng.randint(1, 10))
            account = {
                "account_id": f"ACCT{acc_idx:04d}", "user_id": u["user_id"],
                "account_no_hash": sha256_hex(acc_no), "account_no_tail": acc_no[-4:],
                "bank_code": bank[0], "bank_name": bank[1],
                "account_type": "信用卡" if is_credit else "储蓄卡",
                "card_status": "正常", "credit_limit": D(rng.randint(10_000, 200_000)) if is_credit else D("0.00"),
                "open_time": open_time, "account_age_days": (REF_DATETIME - open_time).days,
                "is_default": 1 if k == 0 else 0,
            }
            accounts.append(account)

    # 团伙共享收款账户 (挂在每个 ring 的第一个用户下, 额外一张卡)
    ring_members: dict[int, list[str]] = {}
    for uid, tag in profiles:
        if tag == "ring_member":
            ring_idx = (int(uid[1:]) - 1) // 4
            ring_members.setdefault(ring_idx, []).append(uid)
    for ring_idx, member_ids in ring_members.items():
        leader = member_ids[0]
        acc_idx += 1
        acc_no = gen_account_no(rng)
        while acc_no in used_account_nos:
            acc_no = gen_account_no(rng)
        used_account_nos.add(acc_no)
        accounts.append({
            "account_id": f"ACCT{acc_idx:04d}", "user_id": leader,
            "account_no_hash": sha256_hex(acc_no), "account_no_tail": acc_no[-4:],
            "bank_code": "ICBC", "bank_name": "中国工商银行",
            "account_type": "储蓄卡", "card_status": "正常",
            "credit_limit": D("0.00"), "open_time": REF_DATETIME - timedelta(days=rng.randint(90, 200)),
            "account_age_days": rng.randint(90, 200), "is_default": 0,
        })
        ring_shared_accounts[ring_idx] = f"ACCT{acc_idx:04d}"

    # ---------------- IP 地理库 ----------------
    ip_rows: list[list] = []
    normal_ips = [f"114.{rng.randint(1, 254)}.{rng.randint(0, 254)}.{rng.randint(1, 254)}" for _ in range(40)]
    proxy_ips = [f"47.{rng.randint(1, 254)}.{rng.randint(0, 254)}.{rng.randint(1, 254)}" for _ in range(12)]
    tor_ips = [f"45.{rng.randint(1, 254)}.{rng.randint(0, 254)}.{rng.randint(1, 254)}" for _ in range(3)]
    mobile_ips = [f"120.{rng.randint(1, 254)}.{rng.randint(0, 254)}.{rng.randint(1, 254)}" for _ in range(5)]
    for ip in normal_ips:
        province, city, _ = rng.choice(CITIES)
        ip_rows.append([ip, "中国", province, city, rng.choice(ISPS), 0, 0, 0, 0])
    for ip in proxy_ips:
        province, city, _ = rng.choice(CITIES)
        ip_rows.append([ip, "中国", province, city, rng.choice(ISPS), 1, 0, 0, 0])
    for ip in tor_ips:
        ip_rows.append([ip, rng.choice(("美国", "荷兰", "德国")), "海外", "海外", "海外节点", 0, 1, 0, 1])
    for ip in mobile_ips:
        province, city, _ = rng.choice(CITIES)
        ip_rows.append([ip, "中国", province, city, rng.choice(ISPS), 0, 0, 1, 0])
    ip_pool = {"normal": normal_ips, "proxy": proxy_ips, "tor": tor_ips, "mobile": mobile_ips}

    def ip_geo(ip: str) -> str:
        for row in ip_rows:
            if row[0] == ip:
                return f"{row[2]}-{row[3]}"
        return "未知"

    # ---------------- 设备指纹 ----------------
    devices: list[dict] = []
    dev_idx = 0
    shared_devices: dict[int, str] = {}
    for ring_idx in ring_members:
        dev_idx += 1
        device_id = f"DEV-R{ring_idx + 1}-01"
        leader = ring_members[ring_idx][0]
        fp = f"FP-RING-{ring_idx + 1}-" + "".join(rng.choice("0123456789abcdef") for _ in range(20))
        devices.append({
            "device_id": device_id, "user_id": leader, "fingerprint_hash": sha256_hex(fp),
            "os": rng.choice(OS_LIST), "browser": rng.choice(BROWSERS), "device_type": "手机",
            "is_root": 1, "mac_hash": sha256_hex(f"mac-{device_id}"), "imei_hash": sha256_hex(f"imei-{device_id}"),
            "first_seen": REF_DATETIME - timedelta(days=120), "last_seen": REF_DATETIME,
        })
        shared_devices[ring_idx] = device_id
    for u in users:
        tag = next(t for uid, t in profiles if uid == u["user_id"])
        ring_idx = (int(u["user_id"][1:]) - 1) // 4 if tag == "ring_member" else -1
        if tag == "ring_member" and ring_idx in shared_devices:
            # 团伙其他成员也用共享设备, 但 device_fingerprint 主键是 device_id, 只能一条
            # 这里把 device 归属记到 leader, 其余成员通过 user_relation 表达共用
            continue
        dev_idx += 1
        device_id = f"DEV{dev_idx:04d}"
        fp = "".join(rng.choice("0123456789abcdef") for _ in range(32))
        is_root = 1 if tag in ("multi_loan", "income_fraud") and rng.random() < 0.4 else 0
        devices.append({
            "device_id": device_id, "user_id": u["user_id"], "fingerprint_hash": sha256_hex(fp),
            "os": rng.choice(OS_LIST), "browser": rng.choice(BROWSERS),
            "device_type": rng.choice(("手机", "手机", "手机", "平板", "PC")), "is_root": is_root,
            "mac_hash": sha256_hex(f"mac-{device_id}"), "imei_hash": sha256_hex(f"imei-{device_id}"),
            "first_seen": u["register_at"], "last_seen": REF_DATETIME,
        })
    device_of_user: dict[str, str] = {}
    for d in devices:
        device_of_user.setdefault(d["user_id"], d["device_id"])
    for ring_idx, member_ids in ring_members.items():
        for uid in member_ids:
            device_of_user[uid] = shared_devices[ring_idx]

    # ---------------- 贷款申请 / 征信 / 收入核验 ----------------
    apps: list[dict] = []
    credits: list[dict] = []
    incomes: list[dict] = []
    app_idx = 0
    applications_by_user: dict[str, list[str]] = {}
    app_approved: list[str] = []  # 审批通过的 application_id

    for u in users:
        user_id = u["user_id"]
        tag = next(t for uid, t in profiles if uid == user_id)
        if tag == "multi_loan":
            n_apps = rng.randint(3, 4)
            window_days = rng.randint(30, 60)
        elif tag == "good":
            n_apps = rng.randint(1, 2)
            window_days = rng.randint(60, 300)
        else:
            n_apps = rng.randint(1, 2)
            window_days = rng.randint(20, 90)

        for k in range(n_apps):
            app_idx += 1
            app_id = f"LA{app_idx:04d}"
            purpose = rng.choice(tuple(PURPOSE_PRODUCT.keys()))
            if tag == "shell_ent":
                purpose = "经营"
            elif tag == "ring_member" and rng.random() < 0.5:
                purpose = "消费"
            lo, hi = PURPOSE_AMOUNT[purpose]
            if tag == "good" and purpose == "经营":
                hi = min(hi, 1_000_000)
            amount = D(rng.randint(lo // 1000, hi // 1000) * 1000)
            term = rng.choice(PURPOSE_TERM[purpose])
            rate_lo, rate_hi = PURPOSE_RATE[purpose]
            rate = D(f"{rng.uniform(rate_lo, rate_hi):.2f}")
            apply_time = rand_days_ago(rng, max(window_days - k * 7, 1), window_days + k * 7)
            if tag == "multi_loan":
                apply_time = rand_days_ago(rng, 1, 60)

            if tag == "ring_member":
                ip = rng.choice(proxy_ips)
                device_id = device_of_user[user_id]
                monthly_debt = D(int(u["monthly_income"] * U(rng, 0.35, 0.6)))
                guarantee_type = rng.choice(("保证", "组合", "信用"))
            elif tag == "multi_loan":
                ip = rng.choice(ip_pool["normal"] + ip_pool["mobile"])
                device_id = device_of_user[user_id]
                monthly_debt = D(int(u["monthly_income"] * U(rng, 0.55, 0.85)))
                guarantee_type = rng.choice(("信用", "信用", "保证"))
            elif tag == "income_fraud":
                ip = rng.choice(ip_pool["normal"])
                device_id = device_of_user[user_id]
                monthly_debt = D(int(u["monthly_income"] * U(rng, 0.1, 0.25)))
                guarantee_type = "信用"
            elif tag == "shell_ent":
                ip = rng.choice(ip_pool["normal"])
                device_id = device_of_user[user_id]
                monthly_debt = D(int(u["monthly_income"] * U(rng, 0.1, 0.2)))
                guarantee_type = rng.choice(("信用", "抵押"))
            elif tag == "internal":
                ip = rng.choice(ip_pool["normal"])
                device_id = device_of_user[user_id]
                monthly_debt = D(int(u["monthly_income"] * U(rng, 0.05, 0.15)))
                guarantee_type = "信用"
            else:
                ip = rng.choice(ip_pool["normal"])
                device_id = device_of_user[user_id]
                monthly_debt = D(int(u["monthly_income"] * U(rng, 0.15, 0.4)))
                guarantee_type = rng.choice(("信用", "信用", "信用", "抵押", "保证"))

            declared_income = u["monthly_income"]
            verified_income = u["verified_income"]
            debt_ratio = (monthly_debt / declared_income).quantize(Decimal("0.0001")) if declared_income else D("0.0000")
            product_code, product_name = PURPOSE_PRODUCT[purpose]

            # 状态机: 决定审批结果
            status, reject_reason, approval_amount, is_repay = "进件", None, None, 0
            if tag == "income_fraud":
                status, reject_reason = "审批拒绝", "收入核验不通过(三源交叉显著偏差)"
            elif tag == "shell_ent" and rng.random() < 0.8:
                status, reject_reason = "审批拒绝", "企业经营资质存疑(疑似空壳)"
            elif tag == "internal":
                status, reject_reason = "审批拒绝", "内部欺诈核查拦截"
            elif tag == "multi_loan" and rng.random() < 0.6:
                status, reject_reason = "审批拒绝", "多头借贷, 负债率过高"
            elif tag == "multi_loan":
                status, reject_reason = "人工审核中", None
            elif tag == "ring_member" and rng.random() < 0.3:
                status, reject_reason = "审批拒绝", "欺诈规则命中(设备/关联关系异常)"
            else:
                # 审批通过 -> 放款
                monthly_loan_pay = 0.0
                if purpose in ("购房", "购车"):
                    monthly_loan_pay = float(amount) * 0.006
                else:
                    monthly_loan_pay = float(amount) * (float(rate) / 100 / 12) + float(amount) / term
                dti_after = (float(monthly_debt) + monthly_loan_pay) / float(declared_income or 1)
                if dti_after > 0.6 or (tag == "good" and rng.random() < 0.15):
                    if tag in ("fund_return", "default_risk"):
                        # 设计上这两个人群必须放款成功, 才能造出资金回流 / 逾期样本
                        status = "放款"
                        approval_amount = amount
                        is_repay = 1
                    else:
                        status, reject_reason = "审批拒绝", "收入覆盖不足"
                else:
                    status = "放款"
                    approval_amount = amount
                    is_repay = 1

            if status == "放款":
                app_approved.append(app_id)

            apps.append({
                "application_id": app_id, "user_id": user_id, "product_code": product_code,
                "product_name": product_name, "apply_amount": amount, "term_months": term,
                "purpose": purpose, "guarantee_type": guarantee_type,
                "repay_type": rng.choice(("等额本息", "等额本息", "等额本息", "先息后本")),
                "monthly_income": declared_income, "monthly_debt": monthly_debt,
                "debt_ratio": debt_ratio, "apply_time": apply_time,
                "channel": rng.choice(("线上APP", "线上APP", "线上APP", "网上银行", "线下网点")),
                "device_id": device_id, "ip": ip, "geo": ip_geo(ip),
                "status": status, "reject_reason": reject_reason,
                "approval_amount": approval_amount, "approval_rate": rate,
                "is_repay_plan_generated": is_repay,
            })
            applications_by_user.setdefault(user_id, []).append(app_id)

            # ---- 征信快照 (每次申请查一次) ----
            if tag == "good":
                score = rng.randint(680, 860)
                hard_query = rng.randint(0, 3)
                overdue_cnt, overdue_days, current_od, five_level = 0, 0, 0, "正常"
                out_loan, cc_cnt = rng.randint(0, 2), rng.randint(0, 3)
                judgement = executed = discredited = daichang = 0
            elif tag == "multi_loan":
                score = rng.randint(520, 650)
                hard_query = rng.randint(6, 12)
                overdue_cnt, overdue_days, current_od, five_level = rng.randint(0, 2), rng.randint(0, 2), rng.randint(0, 1), rng.choice(("正常", "关注"))
                out_loan, cc_cnt = rng.randint(4, 8), rng.randint(3, 6)
                judgement = executed = discredited = daichang = 0
            elif tag == "income_fraud":
                score = rng.randint(600, 700)
                hard_query = rng.randint(0, 4)
                overdue_cnt, overdue_days, current_od, five_level = 0, 0, 0, "正常"
                out_loan, cc_cnt = rng.randint(0, 2), rng.randint(0, 3)
                judgement = executed = discredited = daichang = 0
            elif tag == "shell_ent":
                score = rng.randint(540, 650)
                hard_query = rng.randint(2, 6)
                overdue_cnt, overdue_days, current_od, five_level = rng.randint(0, 1), rng.randint(0, 1), 0, "正常"
                out_loan, cc_cnt = rng.randint(1, 3), rng.randint(1, 4)
                judgement = executed = discredited = daichang = 0
            elif tag == "default_risk":
                score = rng.randint(380, 560)
                hard_query = rng.randint(1, 5)
                overdue_cnt = rng.randint(3, 9)
                overdue_days = rng.randint(1, 6)
                current_od = rng.randint(1, 3)
                five_level = rng.choice(("关注", "次级", "可疑"))
                out_loan, cc_cnt = rng.randint(2, 5), rng.randint(1, 4)
                judgement = rng.choice((0, 0, 1))
                executed = rng.choice((0, 0, 0, 1))
                discredited = rng.choice((0, 0, 0, 1))
                daichang = rng.choice((0, 0, 1))
            elif tag == "fund_return":
                score = rng.randint(620, 750)
                hard_query = rng.randint(0, 3)
                overdue_cnt, overdue_days, current_od, five_level = 0, 0, 0, "正常"
                out_loan, cc_cnt = rng.randint(0, 2), rng.randint(1, 3)
                judgement = executed = discredited = daichang = 0
            else:  # ring / internal
                score = rng.randint(460, 620)
                hard_query = rng.randint(4, 9)
                overdue_cnt, overdue_days = rng.randint(0, 2), rng.randint(0, 2)
                current_od = rng.choice((0, 0, 1))
                five_level = rng.choice(("正常", "关注"))
                out_loan, cc_cnt = rng.randint(1, 4), rng.randint(2, 5)
                judgement = executed = discredited = daichang = 0
            report_date = apply_time.date()
            first_loan = (REF_DATE - timedelta(days=rng.randint(365, 3650))) if rng.random() < 0.7 else None
            credits.append({
                "report_id": f"CR{app_idx:04d}", "application_id": app_id, "user_id": user_id,
                "report_date": report_date, "credit_score": score,
                "overdue_24m_count": overdue_cnt, "overdue_24m_max_days": overdue_days,
                "current_overdue_count": current_od,
                "current_overdue_amount": D(rng.randint(0, 30_000)) if current_od else D("0.00"),
                "five_level_class": five_level, "has_judgement": judgement,
                "is_executed": executed, "is_discredited": discredited, "is_daichang": daichang,
                "guarantee_amount": D(rng.randint(0, 200_000)) if guarantee_type in ("保证", "组合") else D("0.00"),
                "outstanding_loan_count": out_loan, "credit_card_count": cc_cnt,
                "recent_6m_hard_query_count": hard_query, "recent_1m_query_count": max(0, hard_query - rng.randint(0, 2)),
                "open_account_count": rng.randint(2, 10), "settled_account_count": rng.randint(0, 6),
                "first_loan_date": first_loan,
                "loan_history_years": D(f"{rng.uniform(0, 10):.1f}") if first_loan else D("0.0"),
            })

            # ---- 收入三源交叉核验 ----
            actual = verified_income
            declared = declared_income
            if tag == "income_fraud":
                salary_proof = D(int(declared * U(rng, 0.9, 1.1)))      # 伪造的收入证明接近申报
                bank_flow = D(int(actual * U(rng, 0.7, 1.2)))          # 流水偏低
                tax_proof = D(int(actual * U(rng, 0.8, 1.0)))          # 完税偏低
                cross = "显著偏差"
                payroll = 0
            elif tag == "good":
                salary_proof = D(int(declared * U(rng, 0.95, 1.05)))
                bank_flow = D(int(actual * U(rng, 0.9, 1.1)))
                tax_proof = D(int(actual * U(rng, 0.85, 1.0)))
                cross = rng.choice(("一致", "一致", "轻微偏差"))
                payroll = 1 if income_source == "受雇" else 0
            elif tag == "internal":
                salary_proof = D(int(declared * U(rng, 0.98, 1.02)))
                bank_flow = D(int(actual * U(rng, 0.8, 1.0)))
                tax_proof = D(int(actual * U(rng, 0.7, 0.9)))
                cross = "显著偏差"
                payroll = 0
            else:
                salary_proof = D(int(declared * U(rng, 0.8, 1.1)))
                bank_flow = D(int(actual * U(rng, 0.6, 1.0)))
                tax_proof = D(int(actual * U(rng, 0.5, 0.9)))
                cross = rng.choice(("一致", "轻微偏差", "显著偏差"))
                payroll = rng.choice((0, 1)) if income_source == "受雇" else 0
            incomes.append({
                "verify_id": f"IV{app_idx:04d}", "application_id": app_id, "user_id": user_id,
                "declared_monthly_income": declared, "salary_proof_income": salary_proof,
                "bank_flow_avg_income": bank_flow, "tax_proof_income": tax_proof,
                "verified_monthly_income": actual, "has_payroll_record": payroll,
                "bank_flow_min_balance_3m": D(rng.randint(500, 50_000)),
                "bank_flow_total_in_6m": D(int(actual * U(rng, 4.5, 7.5))),
                "cross_check_result": cross, "verify_time": apply_time + timedelta(days=1),
            })

    # ---------------- 合同 / 还款计划 / 还款流水 ----------------
    contracts: list[dict] = []
    plans: list[dict] = []
    records: list[dict] = []
    contract_idx = 0
    plan_idx = 0
    record_idx = 0
    contract_of_app: dict[str, str] = {}

    for app in apps:
        if app["application_id"] not in app_approved:
            continue
        user_id = app["user_id"]
        tag = next(t for uid, t in profiles if uid == user_id)
        contract_idx += 1
        contract_id = f"LC{contract_idx:04d}"
        contract_of_app[app["application_id"]] = contract_id
        loan_amount = app["approval_amount"]
        rate = app["approval_rate"]
        term = app["term_months"]
        disburse_date = app["apply_time"].date() + timedelta(days=rng.randint(2, 7))
        maturity = add_months(disburse_date, term)

        user_accounts = [a for a in accounts if a["user_id"] == user_id]
        repay_account = next((a for a in user_accounts if a["is_default"] == 1), user_accounts[0] if user_accounts else None)
        # 放款账户优先选非默认卡, 便于资金回流监控区分"放款卡"和"还款卡"
        disburse_account = next((a for a in user_accounts if a["is_default"] == 0), None) or (user_accounts[0] if user_accounts else None)
        trustee = 0
        trustee_payee = None
        if tag == "fund_return":
            trustee = 1
            trustee_payee = f"{rng.choice(('腾达', '宏远', '鑫盛', '瑞丰'))}商贸有限公司"

        # 合同状态
        if tag == "default_risk":
            if rng.random() < 0.2:
                status = "核销"
            elif rng.random() < 0.5:
                status = "不良"
            else:
                status = "逾期"
            age_days = rng.randint(180, 900)
        elif tag == "good" and rng.random() < 0.35:
            status = "结清"
            age_days = rng.randint(term * 30 + 30, term * 30 + 180)
        else:
            status = "正常"
            age_days = rng.randint(60, 700)

        # 放款时间要早于"今天"
        disburse_date = REF_DATE - timedelta(days=age_days)
        maturity = add_months(disburse_date, term)
        schedule = build_schedule(loan_amount, rate, term, app["repay_type"])
        status_for_contract = status
        overdue_days_max = 0
        overdue_amount = D("0.00")

        for i, (principal, interest, total) in enumerate(schedule, 1):
            plan_idx += 1
            due = add_months(disburse_date, i)
            if status == "结清":
                p_status, p_od = "已还", 0
                actual_date = due
                actual_amt = total
                record_idx += 1
                records.append({
                    "record_id": f"RR{record_idx:06d}", "contract_id": contract_id,
                    "plan_id": f"PL{plan_idx:06d}", "user_id": user_id, "repay_amount": total,
                    "principal_part": principal, "interest_part": interest, "penalty_part": D("0.00"),
                    "channel": rng.choice(("自动扣款", "自动扣款", "主动还款")),
                    "repay_time": datetime.combine(actual_date, time(9, rng.randint(0, 59), 0)),
                    "is_success": 1,
                })
            elif status in ("核销", "不良"):
                if due < REF_DATE and rng.random() < 0.4:
                    p_status = "已还"
                    p_od = 0
                    actual_date = due
                    actual_amt = total
                    record_idx += 1
                    records.append({
                        "record_id": f"RR{record_idx:06d}", "contract_id": contract_id,
                        "plan_id": f"PL{plan_idx:06d}", "user_id": user_id, "repay_amount": total,
                        "principal_part": principal, "interest_part": interest, "penalty_part": D("0.00"),
                        "channel": "自动扣款",
                        "repay_time": datetime.combine(actual_date, time(9, 0, 0)),
                        "is_success": 1,
                    })
                else:
                    p_status, p_od = "逾期", (REF_DATE - due).days if due < REF_DATE else 0
                    actual_date, actual_amt = None, None
                    overdue_days_max = max(overdue_days_max, p_od)
                    overdue_amount += total
            else:  # 正常 / 逾期
                if due < REF_DATE:
                    if tag == "default_risk" and i > term // 3 and rng.random() < 0.7:
                        # 逾期计划 (M1/M2/M3)
                        p_od = (REF_DATE - due).days
                        p_status = "逾期"
                        actual_date, actual_amt = None, None
                        overdue_days_max = max(overdue_days_max, p_od)
                        overdue_amount += total
                        status_for_contract = "逾期"
                    else:
                        p_status = "已还"
                        p_od = rng.randint(0, 5) if tag in ("ring_member", "fund_return") and rng.random() < 0.3 else 0
                        actual_date = due + timedelta(days=p_od)
                        penalty = D(f"{float(total) * 0.0005 * p_od:.2f}") if p_od else D("0.00")
                        actual_amt = total + penalty
                        record_idx += 1
                        records.append({
                            "record_id": f"RR{record_idx:06d}", "contract_id": contract_id,
                            "plan_id": f"PL{plan_idx:06d}", "user_id": user_id,
                            "repay_amount": actual_amt, "principal_part": principal,
                            "interest_part": interest, "penalty_part": penalty,
                            "channel": rng.choice(("自动扣款", "主动还款")),
                            "repay_time": datetime.combine(actual_date, time(9, rng.randint(0, 59), 0)),
                            "is_success": 1,
                        })
                elif due == REF_DATE:
                    p_status, p_od, actual_date, actual_amt = "待还", 0, None, None
                else:
                    p_status, p_od, actual_date, actual_amt = "未到期", 0, None, None
            plans.append({
                "plan_id": f"PL{plan_idx:06d}", "contract_id": contract_id, "user_id": user_id,
                "period_no": i, "due_date": due, "principal": principal, "interest": interest,
                "total_due": total, "status": p_status, "overdue_days": p_od,
                "actual_repay_date": actual_date, "actual_repay_amount": actual_amt,
            })

        contracts.append({
            "contract_id": contract_id, "application_id": app["application_id"], "user_id": user_id,
            "contract_no": f"BK{REF_DATE.year}{contract_idx:08d}",
            "product_code": app["product_code"], "product_name": app["product_name"],
            "loan_amount": loan_amount, "interest_rate": rate, "term_months": term,
            "repay_type": app["repay_type"], "disbursement_date": disburse_date,
            "maturity_date": maturity,
            "repay_account_id": repay_account["account_id"] if repay_account else None,
            "disbursement_account_id": disburse_account["account_id"] if disburse_account else None,
            "is_trustee_payment": trustee, "trustee_payee": trustee_payee,
            "status": status_for_contract, "overdue_days": overdue_days_max,
            "current_overdue_amount": overdue_amount,
        })

    # ---------------- 抵押物 (含一房多贷) ----------------
    collaterals: list[dict] = []
    coll_idx = 0
    cert_usage: dict[str, int] = {}
    for app in apps:
        if app["guarantee_type"] not in ("抵押", "组合"):
            continue
        contract_id = contract_of_app.get(app["application_id"])
        user = next(u for u in users if u["user_id"] == app["user_id"])
        coll_idx += 1
        reuse = rng.random() < 0.12 and app["user_id"] in {uid for uid, t in profiles if t == "ring_member"}
        if reuse:
            # 复用已有权证 (一房多贷)
            reused_cert = rng.choice(list(cert_usage.keys())) if cert_usage else None
        else:
            reused_cert = None
        if reused_cert:
            cert_no = reused_cert
            query_status = "重复抵押"
        else:
            cert_no = f"沪({rng.randint(2016, 2025)}){rng.choice(('闵行区', '浦东新区', '静安区', '徐汇区'))}不动产权第{rng.randint(100000, 999999)}号"
            query_status = rng.choice(("无查封", "无查封", "无查封", "已抵押"))
        cert_usage[cert_no] = cert_usage.get(cert_no, 0) + 1
        eval_value = D(int(app["apply_amount"] / U(rng, 0.5, 0.75)))
        collaterals.append({
            "collateral_id": f"CO{coll_idx:04d}", "application_id": app["application_id"],
            "contract_id": contract_id, "user_id": app["user_id"],
            "collateral_type": rng.choice(("不动产", "不动产", "不动产", "车辆")),
            "cert_no": cert_no, "cert_no_hash": sha256_hex(cert_no),
            "property_address": f"{user['living_province']}{user['living_city']}{user['living_district']}{rng.choice(('金地名邸', '翡翠湾', '香樟花园'))}{rng.randint(1, 88)}号",
            "owner_name": user["name"], "eval_value": eval_value,
            "mortgage_rate": D(f"{app['apply_amount'] / eval_value:.4f}"),
            "query_status": query_status, "pledge_time": app["apply_time"].date() + timedelta(days=3),
            "release_time": None, "status": "在押",
        })

    # 确定性兜底: 如果这轮随机没造出"一房多贷", 强制构造一组跨借款人重复抵押
    if collaterals and all(v == 1 for v in cert_usage.values()):
        by_user: dict[str, list[dict]] = {}
        for co in collaterals:
            by_user.setdefault(co["user_id"], []).append(co)
        if len(by_user) >= 2:
            user_keys = list(by_user.keys())
            co_a = by_user[user_keys[0]][0]
            co_b = by_user[user_keys[1]][0]
            co_b["cert_no"] = co_a["cert_no"]
            co_b["cert_no_hash"] = co_a["cert_no_hash"]
            co_b["property_address"] = co_a["property_address"]
            co_b["query_status"] = "重复抵押"

    # ---------------- 担保关系 (保证/组合 + 团伙互保) ----------------
    guarantees: list[dict] = []
    gua_idx = 0
    for app in apps:
        if app["guarantee_type"] not in ("保证", "组合"):
            continue
        contract_id = contract_of_app.get(app["application_id"])
        if not contract_id:
            continue
        user_id = app["user_id"]
        tag = next(t for uid, t in profiles if uid == user_id)
        gua_idx += 1
        if tag == "ring_member":
            ring_idx = (int(user_id[1:]) - 1) // 4
            candidates = [uid for uid in ring_members[ring_idx] if uid != user_id]
            guarantor = rng.choice(candidates) if candidates else None
            relation_type = "互保"
            source = "担保"
        else:
            # 找同城用户做担保人
            candidates = [u for u in users if u["user_id"] != user_id and u["living_city"] == next(x for x in users if x["user_id"] == user_id)["living_city"]]
            guarantor = rng.choice(candidates)["user_id"] if candidates else None
            relation_type = rng.choice(("亲属", "同事", "朋友"))
            source = "申请"
        if not guarantor:
            continue
        guarantor_name = next(u["name"] for u in users if u["user_id"] == guarantor)
        guarantees.append({
            "guarantee_id": f"GU{gua_idx:04d}", "contract_id": contract_id,
            "user_id": user_id, "guarantor_id": guarantor, "guarantor_name": guarantor_name,
            "guarantee_type": rng.choice(("连带责任保证", "一般保证")),
            "guarantee_amount": app["apply_amount"],
            "relation_type": relation_type, "sign_time": app["apply_time"].date(),
            "status": rng.choice(("有效", "有效", "有效", "履行完毕")),
        })

    # ---------------- 交易流水 ----------------
    txns: list[dict] = []
    txn_idx = 0
    account_of_id = {a["account_id"]: a for a in accounts}

    def add_txn(user_id, from_acc, to_acc, counterparty, amount, txn_type, channel, txn_time,
                device_id, ip, is_suspicious, remark):
        nonlocal txn_idx
        txn_idx += 1
        txns.append({
            "txn_id": f"TX{txn_idx:06d}", "user_id": user_id,
            "from_account_id": from_acc, "to_account_id": to_acc,
            "counterparty_name": counterparty, "amount": amount, "txn_type": txn_type,
            "channel": channel, "txn_time": txn_time, "device_id": device_id, "ip": ip,
            "geo": ip_geo(ip) if ip else None, "is_suspicious": is_suspicious, "remark": remark,
        })

    for u in users:
        user_id = u["user_id"]
        tag = next(t for uid, t in profiles if uid == user_id)
        u_accounts = [a for a in accounts if a["user_id"] == user_id]
        if not u_accounts:
            continue
        default_acc = next((a for a in u_accounts if a["is_default"] == 1), u_accounts[0])
        device_id = device_of_user.get(user_id)
        normal_ip = rng.choice(ip_pool["normal"])

        # 工资入账 (近 6 个月)
        if u["income_source"] == "受雇" and tag not in ("income_fraud", "internal"):
            for m in range(6):
                pay_day = REF_DATE.replace(day=rng.randint(5, 10)) - timedelta(days=30 * m)
                if pay_day > REF_DATE:
                    continue
                add_txn(user_id, None, default_acc["account_id"], u["employer_name"],
                        D(int(u["verified_income"] * U(rng, 0.95, 1.05))), "工资入账", "代发工资",
                        datetime.combine(pay_day, time(10, 0, 0)), device_id, normal_ip, 0, None)

        # 消费流水
        for _ in range(rng.randint(2, 6)):
            t = rand_days_ago(rng, 5, 180)
            add_txn(user_id, default_acc["account_id"], None,
                    rng.choice(("盒马鲜生", "永辉超市", "美团", "中石化", "万达广场", "京东", "拼多多")),
                    D(rng.randint(20, 3000)), "消费", rng.choice(("POS", "快捷支付", "第三方支付")),
                    t, device_id, normal_ip, 0, None)

        # 资金回流: 放款受托支付后 1-7 天转回本人另一账户
        if tag == "fund_return":
            contracts_of_user = [c for c in contracts if c["user_id"] == user_id and c["is_trustee_payment"] == 1]
            for c in contracts_of_user:
                disburse_acc = c["disbursement_account_id"]
                other_acc = next((a for a in u_accounts if a["account_id"] != disburse_acc), None)
                if not disburse_acc or not other_acc:
                    continue
                back_time = datetime.combine(c["disbursement_date"], time(14, 0, 0)) + timedelta(days=rng.randint(1, 7))
                add_txn(user_id, disburse_acc, other_acc["account_id"], c["trustee_payee"],
                        D(int(c["loan_amount"] * U(rng, 0.8, 1.0))), "转账", "手机银行",
                        back_time, device_id, normal_ip, 1, "放款资金回流(受托支付收款人转回借款人)")
                break

        # 团伙: 多卡归集到共享收款账户
        if tag == "ring_member":
            ring_idx = (int(user_id[1:]) - 1) // 4
            shared_acc = ring_shared_accounts.get(ring_idx)
            if shared_acc:
                for _ in range(rng.randint(1, 3)):
                    t = rand_days_ago(rng, 5, 90)
                    add_txn(user_id, default_acc["account_id"], shared_acc,
                            next(x["name"] for x in users if x["user_id"] == ring_members[ring_idx][0]),
                            D(rng.randint(5_000, 80_000)), "转账", "手机银行", t, device_id,
                            rng.choice(proxy_ips), 1, "多卡归集至团伙收款账户")

    # ---------------- 登录日志 ----------------
    logins: list[dict] = []
    login_idx = 0
    for u in users:
        user_id = u["user_id"]
        tag = next(t for uid, t in profiles if uid == user_id)
        device_id = device_of_user.get(user_id)
        if tag == "ring_member":
            n = rng.randint(3, 5)
            hour_range = (0, 5) if rng.random() < 0.5 else (9, 22)
            ip = rng.choice(proxy_ips)
        elif tag in ("multi_loan", "income_fraud", "shell_ent"):
            n = rng.randint(2, 4)
            hour_range = (0, 5) if rng.random() < 0.3 else (9, 22)
            ip = rng.choice(ip_pool["normal"])
        else:
            n = rng.randint(2, 3)
            hour_range = (9, 22)
            ip = rng.choice(ip_pool["normal"])
        for _ in range(n):
            login_idx += 1
            login_time = rand_days_ago(rng, 1, 120, hour_range)
            logins.append({
                "login_id": f"LG{login_idx:06d}", "user_id": user_id, "device_id": device_id,
                "ip": ip, "geo": ip_geo(ip), "channel": rng.choice(("APP", "APP", "网上银行")),
                "success": 1, "login_time": login_time,
            })

    # ---------------- 行业黑名单 ----------------
    blacklist_rows: list[list] = []
    bl_type_idx = {"设备指纹": set(), "IP": set(), "银行卡号": set(), "身份证号": set(),
                   "手机号": set(), "对公账户": set(), "统一社会信用代码": set()}

    def add_blacklist(bl_type, value, reason, source="内部案件", expire_days=None):
        if value in bl_type_idx[bl_type]:
            return
        bl_type_idx[bl_type].add(value)
        expire = None
        if expire_days:
            expire = REF_DATETIME + timedelta(days=expire_days)
        blacklist_rows.append([bl_type, value, reason, source, expire])

    for ring_idx, member_ids in ring_members.items():
        shared_dev = shared_devices[ring_idx]
        dev = next(d for d in devices if d["device_id"] == shared_dev)
        add_blacklist("设备指纹", dev["fingerprint_hash"], f"团伙共用设备(第{ring_idx + 1}团伙)")
        add_blacklist("银行卡号", account_of_id[ring_shared_accounts[ring_idx]]["account_no_hash"], "团伙收款账户")
    for ip in proxy_ips:
        add_blacklist("IP", ip, "代理IP/秒拨池")
    for ip in tor_ips:
        add_blacklist("IP", ip, "Tor出口")
    for u in users:
        tag = next(t for uid, t in profiles if uid == u["user_id"])
        if tag == "income_fraud":
            add_blacklist("身份证号", u["id_card_hash"], "伪造收入材料骗贷")
        if tag == "shell_ent":
            ent = next((e for e in enterprises if e["user_id"] == u["user_id"]), None)
            if ent:
                add_blacklist("统一社会信用代码", ent["credit_code"], "空壳公司虚构经营资质")
        if tag == "ring_member" and rng.random() < 0.5:
            add_blacklist("手机号", u["mobile"], "团伙申请手机号")
        if tag == "internal":
            add_blacklist("身份证号", u["id_card_hash"], "内部员工伪造材料骗贷")

    # ---------------- 用户关联关系 (图谱) ----------------
    relations: list[dict] = []
    rel_idx = 0
    rel_seen = set()

    def add_relation(a, b, rel_type, detail, source, first_seen, last_seen):
        nonlocal rel_idx
        if a == b or (a, b, rel_type) in rel_seen or (b, a, rel_type) in rel_seen:
            return
        rel_seen.add((a, b, rel_type))
        rel_idx += 1
        relations.append({
            "relation_id": f"RL{rel_idx:04d}", "user_id": a, "related_user_id": b,
            "relation_type": rel_type, "detail_value": detail, "source": source,
            "first_seen": first_seen, "last_seen": last_seen, "is_active": 1,
        })

    for ring_idx, member_ids in ring_members.items():
        shared_dev = shared_devices[ring_idx]
        leader = member_ids[0]
        shared_addr = next(u["living_address"] for u in users if u["user_id"] == leader)
        for uid in member_ids[1:]:
            add_relation(leader, uid, "共享设备", shared_dev, "设备",
                         REF_DATETIME - timedelta(days=120), REF_DATETIME)
            add_relation(leader, uid, "共享地址", shared_addr, "申请",
                         REF_DATETIME - timedelta(days=120), REF_DATETIME)
    for g in guarantees:
        if g["relation_type"] == "互保":
            add_relation(g["user_id"], g["guarantor_id"], "互保", g["contract_id"], "担保",
                         REF_DATETIME - timedelta(days=120), REF_DATETIME)
        else:
            add_relation(g["user_id"], g["guarantor_id"], g["relation_type"], None, "担保",
                         REF_DATETIME - timedelta(days=120), REF_DATETIME)
    for txn in txns:
        if txn["is_suspicious"] == 1 and txn["to_account_id"]:
            to_user = account_of_id[txn["to_account_id"]]["user_id"]
            if to_user != txn["user_id"]:
                add_relation(txn["user_id"], to_user, "资金往来", txn["to_account_id"], "交易",
                             txn["txn_time"], REF_DATETIME)

    # ---------------- 组装 Dataset ----------------
    ds.add("user_info",
           ["user_id", "name", "gender", "birth_date", "age", "id_card_hash", "mobile", "marital_status",
            "education", "occupation", "employer_name", "employer_category", "industry_code",
            "household_province", "household_city", "household_district", "household_address",
            "living_province", "living_city", "living_district", "living_address",
            "monthly_income", "verified_income", "income_source", "credit_score", "kyc_level",
            "register_at", "account_age_days", "is_employee"],
           [[u["user_id"], u["name"], u["gender"], u["birth_date"], u["age"], u["id_card_hash"],
             u["mobile"], u["marital_status"], u["education"], u["occupation"], u["employer_name"],
             u["employer_category"], u["industry_code"], u["household_province"], u["household_city"],
             u["household_district"], u["household_address"], u["living_province"], u["living_city"],
             u["living_district"], u["living_address"], u["monthly_income"], u["verified_income"],
             u["income_source"], u["credit_score"], u["kyc_level"], u["register_at"],
             u["account_age_days"], u["is_employee"]] for u in users])

    ds.add("enterprise_info",
           ["ent_id", "user_id", "ent_name", "credit_code", "legal_person", "reg_date", "business_years",
            "industry", "reg_capital", "paid_in_capital", "annual_revenue", "annual_tax_amount",
            "employee_count", "operation_status", "reg_address"],
           [[e["ent_id"], e["user_id"], e["ent_name"], e["credit_code"], e["legal_person"], e["reg_date"],
             e["business_years"], e["industry"], e["reg_capital"], e["paid_in_capital"], e["annual_revenue"],
             e["annual_tax_amount"], e["employee_count"], e["operation_status"], e["reg_address"]]
            for e in enterprises])

    ds.add("bank_account",
           ["account_id", "user_id", "account_no_hash", "account_no_tail", "bank_code", "bank_name",
            "account_type", "card_status", "credit_limit", "open_time", "account_age_days", "is_default"],
           [[a["account_id"], a["user_id"], a["account_no_hash"], a["account_no_tail"], a["bank_code"],
             a["bank_name"], a["account_type"], a["card_status"], a["credit_limit"], a["open_time"],
             a["account_age_days"], a["is_default"]] for a in accounts])

    ds.add("device_fingerprint",
           ["device_id", "user_id", "fingerprint_hash", "os", "browser", "device_type", "is_root",
            "mac_hash", "imei_hash", "first_seen", "last_seen"],
           [[d["device_id"], d["user_id"], d["fingerprint_hash"], d["os"], d["browser"], d["device_type"],
             d["is_root"], d["mac_hash"], d["imei_hash"], d["first_seen"], d["last_seen"]] for d in devices])

    ds.add("ip_geo_location",
           ["ip", "country", "province", "city", "isp", "is_proxy", "is_tor", "is_mobile", "is_abroad"],
           [r for r in ip_rows])

    ds.add("loan_application",
           ["application_id", "user_id", "product_code", "product_name", "apply_amount", "term_months",
            "purpose", "guarantee_type", "repay_type", "monthly_income", "monthly_debt", "debt_ratio",
            "apply_time", "channel", "device_id", "ip", "geo", "status", "reject_reason",
            "approval_amount", "approval_rate", "is_repay_plan_generated"],
           [[a["application_id"], a["user_id"], a["product_code"], a["product_name"], a["apply_amount"],
             a["term_months"], a["purpose"], a["guarantee_type"], a["repay_type"], a["monthly_income"],
             a["monthly_debt"], a["debt_ratio"], a["apply_time"], a["channel"], a["device_id"], a["ip"],
             a["geo"], a["status"], a["reject_reason"], a["approval_amount"], a["approval_rate"],
             a["is_repay_plan_generated"]] for a in apps])

    ds.add("credit_report",
           ["report_id", "application_id", "user_id", "report_date", "credit_score", "overdue_24m_count",
            "overdue_24m_max_days", "current_overdue_count", "current_overdue_amount", "five_level_class",
            "has_judgement", "is_executed", "is_discredited", "is_daichang", "guarantee_amount",
            "outstanding_loan_count", "credit_card_count", "recent_6m_hard_query_count",
            "recent_1m_query_count", "open_account_count", "settled_account_count", "first_loan_date",
            "loan_history_years"],
           [[c["report_id"], c["application_id"], c["user_id"], c["report_date"], c["credit_score"],
             c["overdue_24m_count"], c["overdue_24m_max_days"], c["current_overdue_count"],
             c["current_overdue_amount"], c["five_level_class"], c["has_judgement"], c["is_executed"],
             c["is_discredited"], c["is_daichang"], c["guarantee_amount"], c["outstanding_loan_count"],
             c["credit_card_count"], c["recent_6m_hard_query_count"], c["recent_1m_query_count"],
             c["open_account_count"], c["settled_account_count"], c["first_loan_date"],
             c["loan_history_years"]] for c in credits])

    ds.add("income_verify",
           ["verify_id", "application_id", "user_id", "declared_monthly_income", "salary_proof_income",
            "bank_flow_avg_income", "tax_proof_income", "verified_monthly_income", "has_payroll_record",
            "bank_flow_min_balance_3m", "bank_flow_total_in_6m", "cross_check_result", "verify_time"],
           [[iv["verify_id"], iv["application_id"], iv["user_id"], iv["declared_monthly_income"],
             iv["salary_proof_income"], iv["bank_flow_avg_income"], iv["tax_proof_income"],
             iv["verified_monthly_income"], iv["has_payroll_record"], iv["bank_flow_min_balance_3m"],
             iv["bank_flow_total_in_6m"], iv["cross_check_result"], iv["verify_time"]] for iv in incomes])

    ds.add("loan_contract",
           ["contract_id", "application_id", "user_id", "contract_no", "product_code", "product_name",
            "loan_amount", "interest_rate", "term_months", "repay_type", "disbursement_date",
            "maturity_date", "repay_account_id", "disbursement_account_id", "is_trustee_payment",
            "trustee_payee", "status", "overdue_days", "current_overdue_amount"],
           [[c["contract_id"], c["application_id"], c["user_id"], c["contract_no"], c["product_code"],
             c["product_name"], c["loan_amount"], c["interest_rate"], c["term_months"], c["repay_type"],
             c["disbursement_date"], c["maturity_date"], c["repay_account_id"],
             c["disbursement_account_id"], c["is_trustee_payment"], c["trustee_payee"], c["status"],
             c["overdue_days"], c["current_overdue_amount"]] for c in contracts])

    ds.add("collateral",
           ["collateral_id", "application_id", "contract_id", "user_id", "collateral_type", "cert_no",
            "cert_no_hash", "property_address", "owner_name", "eval_value", "mortgage_rate",
            "query_status", "pledge_time", "release_time", "status"],
           [[co["collateral_id"], co["application_id"], co["contract_id"], co["user_id"],
             co["collateral_type"], co["cert_no"], co["cert_no_hash"], co["property_address"],
             co["owner_name"], co["eval_value"], co["mortgage_rate"], co["query_status"],
             co["pledge_time"], co["release_time"], co["status"]] for co in collaterals])

    ds.add("guarantee",
           ["guarantee_id", "contract_id", "user_id", "guarantor_id", "guarantor_name", "guarantee_type",
            "guarantee_amount", "relation_type", "sign_time", "status"],
           [[g["guarantee_id"], g["contract_id"], g["user_id"], g["guarantor_id"], g["guarantor_name"],
             g["guarantee_type"], g["guarantee_amount"], g["relation_type"], g["sign_time"], g["status"]]
            for g in guarantees])

    ds.add("repayment_plan",
           ["plan_id", "contract_id", "user_id", "period_no", "due_date", "principal", "interest",
            "total_due", "status", "overdue_days", "actual_repay_date", "actual_repay_amount"],
           [[p["plan_id"], p["contract_id"], p["user_id"], p["period_no"], p["due_date"], p["principal"],
             p["interest"], p["total_due"], p["status"], p["overdue_days"], p["actual_repay_date"],
             p["actual_repay_amount"]] for p in plans])

    ds.add("repayment_record",
           ["record_id", "contract_id", "plan_id", "user_id", "repay_amount", "principal_part",
            "interest_part", "penalty_part", "channel", "repay_time", "is_success"],
           [[r["record_id"], r["contract_id"], r["plan_id"], r["user_id"], r["repay_amount"],
             r["principal_part"], r["interest_part"], r["penalty_part"], r["channel"], r["repay_time"],
             r["is_success"]] for r in records])

    ds.add("transaction",
           ["txn_id", "user_id", "from_account_id", "to_account_id", "counterparty_name", "amount",
            "txn_type", "channel", "txn_time", "device_id", "ip", "geo", "is_suspicious", "remark"],
           [[t["txn_id"], t["user_id"], t["from_account_id"], t["to_account_id"], t["counterparty_name"],
             t["amount"], t["txn_type"], t["channel"], t["txn_time"], t["device_id"], t["ip"], t["geo"],
             t["is_suspicious"], t["remark"]] for t in txns])

    ds.add("login_log",
           ["login_id", "user_id", "device_id", "ip", "geo", "channel", "success", "login_time"],
           [[l["login_id"], l["user_id"], l["device_id"], l["ip"], l["geo"], l["channel"], l["success"],
             l["login_time"]] for l in logins])

    ds.add("blacklist_extra",
           ["type", "value", "reason", "source", "expire_time"],
           [r for r in blacklist_rows])

    ds.add("user_relation",
           ["relation_id", "user_id", "related_user_id", "relation_type", "detail_value", "source",
            "first_seen", "last_seen", "is_active"],
           [[r["relation_id"], r["user_id"], r["related_user_id"], r["relation_type"], r["detail_value"],
             r["source"], r["first_seen"], r["last_seen"], r["is_active"]] for r in relations])

    return ds


# ============================================================
# SQL 文件输出
# ============================================================

def write_sql_file(ds: Dataset, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("-- ============================================\n")
        f.write("-- 银行信贷风控系统 - 业务表数据初始化脚本\n")
        f.write(f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (固定随机种子, 可复现)\n")
        f.write("-- 生成脚本: python scripts/gen_business_data.py\n")
        f.write("-- ============================================\n\n")
        f.write("SET NAMES utf8mb4;\n")
        f.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

        for table in TABLE_ORDER:
            cols, rows = ds.data.get(table, ([], []))
            f.write(f"-- Table `{table}`: {len(rows)} rows\n")
            if not rows:
                continue
            col_sql = ", ".join(f"`{c}`" for c in cols)
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                values = ",\n".join(
                    "(" + ", ".join(fmt_sql(v) for v in row) + ")" for row in batch
                )
                f.write(f"INSERT INTO `{table}` ({col_sql}) VALUES\n{values};\n")
            f.write("\n")

        f.write("SET FOREIGN_KEY_CHECKS = 1;\n")


# ============================================================
# 直接写入 MySQL (可重复: 先清空业务表)
# ============================================================

async def insert_into_db(ds: Dataset) -> None:
    """直连入库 (可重复: 先清空业务表).

    注意: TRUNCATE 会隐式提交, 中途失败无法整库回滚;
    因此失败时抛出带表名的清晰错误, 并在成功后做行数校验防半套数据.
    """
    import aiomysql as _mysql

    conn = await _mysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "123321"),
        db=os.getenv("DB_NAME", "ecs"),
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for table in TRUNCATE_ORDER:
                await cur.execute(f"TRUNCATE TABLE `{table}`")
            for table in TABLE_ORDER:
                cols, rows = ds.data.get(table, ([], []))
                if not rows:
                    continue
                col_sql = ", ".join(f"`{c}`" for c in cols)
                try:
                    for i in range(0, len(rows), BATCH_SIZE):
                        batch = rows[i:i + BATCH_SIZE]
                        values = ",\n".join(
                            "(" + ", ".join(fmt_sql(v) for v in row) + ")" for row in batch
                        )
                        await cur.execute(f"INSERT INTO `{table}` ({col_sql}) VALUES\n{values}")
                except Exception as e:
                    raise RuntimeError(
                        f"插入表 {table} 失败: {type(e).__name__}: {str(e)[:200]}"
                    ) from e
            await cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        await conn.commit()

        # 行数校验: 每张表期望行数 vs 实际行数, 防"半套数据"
        async with conn.cursor() as cur:
            mismatches = []
            for table in TABLE_ORDER:
                await cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                actual = (await cur.fetchone())[0]
                expected = ds.rows(table)
                if actual != expected:
                    mismatches.append(f"{table}: 期望 {expected} 行, 实际 {actual} 行")
            if mismatches:
                raise RuntimeError("入库行数校验未通过: " + "; ".join(mismatches))
    finally:
        conn.close()


def print_summary(ds: Dataset) -> int:
    print("\n" + "=" * 62)
    print("生成结果汇总")
    print("=" * 62)
    total = 0
    for table in TABLE_ORDER:
        n = ds.rows(table)
        total += n
        print(f"  {table:<22} {n:>7} 行")
    print("-" * 62)
    print(f"  合计(全部业务表)           {total:>7} 行")
    print(f"  借款人                    {ds.rows('user_info'):>7} 人 (>=100 满足验收)")
    print(f"  贷款申请                  {ds.rows('loan_application'):>7} 笔")
    print(f"  贷款合同                  {ds.rows('loan_contract'):>7} 份")
    print("=" * 62)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="银行信贷风控 - 业务造数脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python scripts/gen_business_data.py                # 生成 SQL 文件\n"
               "  python scripts/gen_business_data.py --insert       # 生成 SQL + 直接入库\n"
               "  python scripts/gen_business_data.py --users 200    # 200 个借款人\n",
    )
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help=f"借款人数量 (默认 {DEFAULT_USERS})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"随机种子 (默认 {DEFAULT_SEED})")
    parser.add_argument("--date", default=None, help="数据基准日期 YYYY-MM-DD (默认今天, 固定日期可复现历史数据)")
    parser.add_argument("--out", default=os.path.join(BASE_DIR, "sql", "init_business_data.sql"),
                        help="SQL 输出路径 (默认 sql/init_business_data.sql)")
    parser.add_argument("--insert", action="store_true", help="生成 SQL 后直接写入 MySQL (先清空业务表)")
    args = parser.parse_args()

    if args.users < 1:
        print("错误: --users 至少为 1")
        return 1

    if args.date:
        global REF_DATE, REF_DATETIME
        try:
            REF_DATE = date.fromisoformat(args.date)
        except ValueError:
            print("错误: --date 格式应为 YYYY-MM-DD")
            return 1
        REF_DATETIME = datetime.combine(REF_DATE, time(12, 0))

    print(f"开始造数: {args.users} 个借款人, seed={args.seed}")
    ds = generate(args.users, args.seed)
    total = print_summary(ds)

    out_path = os.path.abspath(args.out)
    write_sql_file(ds, out_path)
    print(f"\nSQL 已写入: {out_path}")

    if args.insert:
        print(f"\n直接写入 MySQL ({os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', 3306)}/{os.getenv('DB_NAME', 'ecs')}) ...")
        try:
            asyncio.run(insert_into_db(ds))
            print("入库完成 (业务表已清空重建, 行数校验通过)")
        except Exception as e:
            print(f"入库失败: {e}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

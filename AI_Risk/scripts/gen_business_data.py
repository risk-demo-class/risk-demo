"""
银行工商风控系统 - 业务数据生成脚本
生成 30 张业务表中的模拟数据, 可重复运行
用法: python scripts/gen_business_data.py --count 25 --truncate
"""
import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timedelta, date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


NOW = datetime.now()
ONE_YEAR_AGO = NOW - timedelta(days=365)
TWO_YEARS_AGO = NOW - timedelta(days=730)
CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "重庆", "西安",
          "昆明", "南宁", "福州", "厦门", "长沙", "郑州", "济宁", "龙岩", "莆田", "泉州"]
NORMAL_CITIES = CITIES[:10]
HIGH_RISK_CITIES = ["济宁", "龙岩", "莆田", "泉州"]
BANKS = ["中国工商银行", "中国建设银行", "中国农业银行", "中国银行", "招商银行", "交通银行"]
PURPOSE_OK = ["购车", "装修", "旅游", "教育培训", "医疗", "家电购置", "婚庆", "购买家具"]
PURPOSE_BAD = ["炒股", "投资理财", "虚拟币交易", "赌博", "购买彩票", "民间借贷"]
CHANNELS = ["网银", "手机银行", "快捷支付", "柜面", "ATM", "POS"]
LOAN_TYPES = ["个人消费贷", "个人经营贷", "住房按揭", "汽车贷款", "信用卡分期"]
COMPANIES = ["华为技术", "腾讯科技", "阿里巴巴", "字节跳动", "招商银行",
             "中兴通讯", "比亚迪", "平安集团", "万科集团", "格力电器"]
POSITIONS = ["工程师", "产品经理", "设计师", "销售经理", "财务主管", "运营总监", "人事经理", "项目经理"]
RELATIONSHIPS = ["配偶", "父母", "子女", "兄弟姐妹", "朋友", "同事"]


def random_time(start, end):
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=random.uniform(0, delta))


def random_date(start, end):
    return random_time(start, end).date()


def random_ip():
    return f"{random.randint(10,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def random_amount(lo, hi):
    return Decimal(str(round(random.uniform(lo, hi), 2)))


class DataGen:
    def __init__(self, n_users=25):
        self.n_users = n_users
        self.n_risk = max(1, n_users // 5)
        self.user_ids = []
        self.risk_user_ids = []
        self.card_ids = {}
        self.device_ids = {}
        self.rows = {}
        for t in TABLES:
            self.rows[t] = []

    def run(self):
        self._gen_ref_data()
        self._gen_users()
        self._gen_cards()
        self._gen_login_devices()
        self._gen_transactions()
        self._gen_loans()
        self._gen_risk_data()
        self._gen_agg()
        self.report()

    def report(self):
        total = 0
        print("\n" + "=" * 60)
        print(f"数据生成完成: {self.n_users} 用户, {self.n_risk} 高风险")
        print("=" * 60)
        for t in TABLES:
            c = len(self.rows[t])
            total += c
            print(f"  {t:<30} {c:>5} 行")
        print("-" * 60)
        print(f"  {'合计':<30} {total:>5} 行")

    def _gen_ref_data(self):
        for ch in CHANNELS:
            w = {"网银": 20, "手机银行": 15, "快捷支付": 40, "柜面": 5, "ATM": 10, "POS": 30}[ch]
            self.rows["txn_channel_risk"].append({
                "channel": ch, "risk_weight": w,
                "max_single_limit": 500000, "max_daily_limit": 1000000,
                "max_daily_count": 50, "is_enabled": 1
            })
        regions = [
            ("济宁", None, "极高", "电信诈骗"), ("龙岩", None, "极高", "电信诈骗"),
            ("莆田", None, "高", "赌博"), ("泉州", None, "高", "洗钱"),
            ("昆明", None, "中", "非法集资"), ("南宁", "宾阳", "极高", "电信诈骗"),
        ]
        for p, c, lvl, cat in regions:
            self.rows["high_risk_region"].append({
                "province": p, "city": c, "risk_level": lvl, "risk_category": cat,
                "valid_from": TWO_YEARS_AGO.date(), "valid_to": None
            })
        for i in range(5):
            self.rows["enterprise_blacklist"].append({
                "enterprise_name": f"空壳贸易公司{i+1}号",
                "credit_code": f"91110000MA000000{i:02d}",
                "legal_person_hash": sha256(f"BLACK_LEGAL_{i}"),
                "black_reason": "工商吊销 / 无实际经营", "black_source": "工商吊销",
                "black_time": random_time(ONE_YEAR_AGO, NOW)
            })
        for i in range(8):
            self.rows["txn_black_account"].append({
                "account_number_hash": sha256(f"BLACK_CARD_{i}"),
                "account_name_hash": sha256(f"BLACK_NAME_{i}"),
                "bank_name": random.choice(BANKS),
                "hit_count": random.randint(3, 50),
                "risk_level": random.choice(["高", "极高"]),
                "source": random.choice(["公安", "人行"]),
                "hit_date": random_time(ONE_YEAR_AGO, NOW)
            })
        for i in range(6):
            self.rows["ip_geo_location"].append({
                "ip_cidr": f"103.{random.randint(1,250)}.{random.randint(1,250)}.0/24",
                "country": "中国", "province": random.choice(CITIES),
                "city": random.choice(CITIES),
                "isp": random.choice(["电信", "联通", "移动"]),
                "is_proxy": 0, "is_tor": 0, "is_data_center": 0, "risk_level": "低"
            })
        for i in range(4):
            self.rows["ip_geo_location"].append({
                "ip_cidr": f"45.{random.randint(1,250)}.{random.randint(1,250)}.0/24",
                "country": "美国", "province": None, "city": None,
                "isp": "Cloudflare", "is_proxy": 1, "is_tor": 0,
                "is_data_center": 1, "risk_level": "高"
            })

    def _gen_users(self):
        for i in range(self.n_users):
            uid = f"U{i+1:04d}"
            is_risk = i < self.n_risk
            if is_risk:
                uid = f"RISK{i+1:03d}"
                self.risk_user_ids.append(uid)
            self.user_ids.append(uid)
            city = random.choice(HIGH_RISK_CITIES if is_risk else NORMAL_CITIES)
            reg_date = random_time(TWO_YEARS_AGO, ONE_YEAR_AGO)
            self.rows["user_info"].append({
                "user_id": uid,
                "name_hash": sha256(f"NAME_{uid}"),
                "id_card_hash": sha256(f"ID_CARD_{uid}"),
                "phone_hash": sha256(f"1380000{1000+i:04d}"),
                "email": f"user{i+1}@example.com",
                "kyc_level": "L1" if is_risk else random.choice(["L2","L3","L3","L4","L5"]),
                "credit_score": random.randint(350,550) if is_risk else random.randint(600,850),
                "reg_date": reg_date, "status": "正常",
                "reg_ip": random_ip(), "reg_city": city,
            })
            self.rows["user_employment"].append({
                "user_id": uid,
                "company_name": random.choice(COMPANIES),
                "position": random.choice(POSITIONS),
                "monthly_income": random_amount(3000,8000) if is_risk else random_amount(8000,50000),
                "annual_income": None, "employment_status": "在职",
                "verify_status": "未验证" if is_risk else random.choice(["已验证","已验证","验证中"]),
            })
            self.rows["user_contact"].append({
                "user_id": uid,
                "contact_name_hash": sha256(f"CONTACT_NAME_{uid}"),
                "contact_phone_hash": sha256(f"1390000{2000+i:04d}"),
                "relationship": random.choice(RELATIONSHIPS), "is_emergency": 1,
            })
            if random.random() < 0.3:
                company = random.choice(["A科技有限公司","B贸易有限公司","C建筑工程公司"])
                self.rows["user_enterprise"].append({
                    "user_id": uid, "enterprise_name": company,
                    "credit_code": f"91110000MA00000{i:03d}",
                    "legal_person_hash": sha256(f"LEGAL_{uid}"),
                    "registered_capital": random_amount(100,5000),
                    "business_scope": "技术开发、服务、咨询",
                    "establish_date": random_date(NOW - timedelta(days=365*10), ONE_YEAR_AGO),
                    "industry_category": random.choice(["信息技术","贸易","建筑"]),
                    "ubo_count": random.randint(1,3),
                })
            lvls = ["L1","L2","L3","L4","L5"]
            if random.random() < 0.4 and not is_risk:
                c = lvls.index("L3")
                n = min(c + 1, 4)
                self.rows["user_kyc_record"].append({
                    "user_id": uid, "level_before": lvls[c], "level_after": lvls[n],
                    "audit_status": "通过", "auditor": "KYC审核员01",
                    "audit_remark": "客户信息完整, 通过升级审核",
                    "audit_time": random_time(reg_date, NOW),
                })

    def _gen_cards(self):
        for uid in self.user_ids:
            n_cards = random.randint(1, 3)
            for j in range(n_cards):
                cid = f"C_{uid}_{j+1}"
                is_credit = random.random() < 0.4
                ct = "信用卡" if is_credit else "借记卡"
                cl = random_amount(10000,200000) if is_credit else None
                av = cl * Decimal(str(random.uniform(0.3,1.0))) if cl else None
                od = random_date(TWO_YEARS_AGO, ONE_YEAR_AGO)
                self.rows["bank_card"].append({
                    "card_id": cid, "user_id": uid,
                    "card_number_hash": sha256(f"CARD_NUM_{cid}"),
                    "card_type": ct, "bank_name": random.choice(BANKS),
                    "credit_limit": cl, "available_limit": av,
                    "open_date": od, "card_status": "正常", "is_virtual": 0,
                })
                self.card_ids.setdefault(uid, []).append(cid)
                self.rows["card_bind_record"].append({
                    "user_id": uid, "card_id": cid, "bind_type": "绑定",
                    "bind_ip": random_ip(), "bind_device_id": None,
                    "bind_city": random.choice(CITIES), "bind_time": od,
                    "unbind_time": None
                })
                if is_credit:
                    for m in range(random.randint(3, 12)):
                        mo = NOW.month - m - 1
                        yr = NOW.year
                        if mo <= 0:
                            mo += 12; yr -= 1
                        ta = random_amount(2000, 50000)
                        mp = round(ta * Decimal("0.1"), 2)
                        pa = ta if random.random() < 0.6 else (mp if random.random() < 0.5 else Decimal("0"))
                        st = "已还清" if pa >= ta else ("部分还" if pa > 0 else "未还")
                        self.rows["credit_card_bill"].append({
                            "card_id": cid, "user_id": uid,
                            "bill_month": f"{yr}-{mo:02d}",
                            "total_amount": ta, "min_payment": mp,
                            "paid_amount": pa, "payment_status": st,
                            "due_date": date(yr, mo, 25),
                            "paid_date": date(yr, mo, random.randint(20,25)) if pa > 0 else None,
                        })

    def _gen_login_devices(self):
        n_devices = max(6, self.n_users // 2)
        for i in range(n_devices):
            did = f"DEV_{i+1:04d}"
            uid = random.choice(self.user_ids)
            self.device_ids[did] = uid
            self.rows["device_fingerprint"].append({
                "device_id": did, "user_id": uid,
                "device_type": random.choice(["iOS","Android","PC","Web"]),
                "os": random.choice(["iOS","Android","Windows","macOS"]),
                "browser": random.choice(["Chrome","Safari","WeChat"]),
                "is_rooted": 1 if random.random() < 0.05 else 0,
                "is_emulator": 1 if random.random() < 0.03 else 0,
                "fingerprint_hash": sha256(f"FP_{did}"),
                "first_seen": random_time(ONE_YEAR_AGO, NOW),
                "associated_users": random.randint(1, 3),
            })
        for uid in self.user_ids:
            n_logins = random.randint(5, 30)
            for _ in range(n_logins):
                ltime = random_time(ONE_YEAR_AGO, NOW)
                city = random.choice(HIGH_RISK_CITIES if uid in self.risk_user_ids else NORMAL_CITIES)
                did = random.choice(list(self.device_ids.keys()))
                result = "成功" if random.random() < 0.85 else "失败"
                self.rows["login_log"].append({
                    "user_id": uid, "login_time": ltime, "login_ip": random_ip(),
                    "login_city": city, "login_device_id": did,
                    "login_result": result,
                    "fail_reason": "密码错误" if result == "失败" else None,
                    "is_new_device": 1 if random.random() < 0.1 else 0,
                    "is_proxy_ip": 1 if random.random() < 0.05 else 0,
                    "session_id": f"SESS_{uid}_{int(ltime.timestamp())}"
                })
            self.rows["session_tracking"].append({
                "session_id": f"SESS_{uid}_active", "user_id": uid,
                "login_time": random_time(ONE_YEAR_AGO, NOW),
                "logout_time": None,
                "device_id": random.choice(list(self.device_ids.keys())),
                "is_active": 1, "ip_change_count": random.randint(0, 3),
            })
            if random.random() < 0.3:
                self.rows["password_change_log"].append({
                    "user_id": uid, "change_type": "修改密码",
                    "change_ip": random_ip(),
                    "change_device_id": random.choice(list(self.device_ids.keys())),
                    "change_time": random_time(ONE_YEAR_AGO, NOW),
                })

    def _gen_transactions(self):
        for uid in self.user_ids:
            cards = self.card_ids.get(uid, [])
            if not cards:
                continue
            n_txns = random.randint(5, 30)
            for j in range(n_txns):
                tid = f"TXN_{uid}_{j+1:03d}"
                fc = random.choice(cards)
                all_to = [c for cl in self.card_ids.values() for c in cl if c != fc]
                tc = random.choice(all_to) if all_to else fc
                amt = random_amount(10, 50000)
                ttime = random_time(ONE_YEAR_AGO, NOW)
                city = random.choice(HIGH_RISK_CITIES if uid in self.risk_user_ids else NORMAL_CITIES)
                self.rows["transaction"].append({
                    "txn_id": tid, "from_card": fc, "to_card": tc,
                    "user_id": uid, "amount": amt,
                    "txn_type": "转账" if random.random() < 0.7 else random.choice(["消费","取现"]),
                    "channel": random.choice(CHANNELS),
                    "txn_time": ttime, "txn_status": "成功",
                    "ip": random_ip(), "city": city,
                    "device_id": random.choice(list(self.device_ids.keys())),
                    "is_international": 1 if random.random() < 0.02 else 0,
                })
                if amt > 50000:
                    self.rows["txn_suspicious_report"].append({
                        "txn_id": tid, "user_id": uid,
                        "report_type": "大额", "amount": amt,
                        "trigger_rule": "PBOC_DR",
                        "report_status": random.choice(["待上报","已上报"]),
                        "submit_time": ttime if random.random() < 0.5 else None,
                    })
                if random.random() < 0.08:
                    self.rows["txn_split_chain"].append({
                        "root_txn_id": tid, "from_card": fc, "to_card": tc,
                        "amount": amt, "split_level": 1,
                        "split_time": ttime + timedelta(minutes=random.randint(1,30)),
                    })
                self.rows["txn_counterparty"].append({
                    "counterparty_name_hash": sha256(f"CPTY_NAME_{tc}"),
                    "counterparty_account_hash": sha256(f"CPTY_{tc}"),
                    "counterparty_bank": random.choice(BANKS),
                    "risk_flag": 1 if random.random() < 0.05 else 0,
                    "risk_region": random.choice(HIGH_RISK_CITIES) if random.random() < 0.05 else random.choice(NORMAL_CITIES),
                    "first_seen": ttime, "last_seen": ttime, "txn_count": 1,
                })

    def _gen_loans(self):
        for uid in self.user_ids:
            if random.random() < 0.3:
                continue
            aid = f"LOAN_{uid}_001"
            aa = random_amount(50000, 1000000)
            dr = Decimal(str(round(random.uniform(0.2, 0.85), 4)))
            inc = random_amount(5000, 50000)
            pur = random.choice(PURPOSE_BAD) if uid in self.risk_user_ids and random.random() < 0.4 else random.choice(PURPOSE_OK)
            atime = random_time(ONE_YEAR_AGO, NOW)
            self.rows["loan_application"].append({
                "application_id": aid, "user_id": uid,
                "loan_type": random.choice(LOAN_TYPES),
                "apply_amount": aa, "term_months": random.choice([12,24,36,60,120]),
                "purpose": pur, "debt_ratio": dr, "monthly_income": inc,
                "credit_score": random.randint(350,850),
                "is_entrusted": 1 if random.random() < 0.3 else 0,
                "apply_status": random.choice(["已通过","已通过","已放款","已拒绝"]),
                "apply_time": atime,
            })
            approved = random.random() < 0.7
            self.rows["loan_approval"].append({
                "application_id": aid, "user_id": uid,
                "approval_status": "通过" if approved else "驳回",
                "approved_amount": aa * Decimal(str(round(random.uniform(0.7,1.0),2))) if approved else None,
                "approved_term": random.choice([12,24,36]) if approved else None,
                "interest_rate": Decimal(str(round(random.uniform(3.5,6.5),4))) if approved else None,
                "reject_reason": "收入负债比过高" if not approved else None,
                "approver": "信贷审批员01",
                "approval_time": atime + timedelta(days=random.randint(1,5)),
            })
            if approved:
                cid = f"CTR_{aid}"
                sd = atime.date() + timedelta(days=random.randint(3,10))
                term = random.choice([12,24,36])
                self.rows["loan_contract"].append({
                    "contract_id": cid, "application_id": aid, "user_id": uid,
                    "loan_amount": aa, "term_months": term,
                    "interest_rate": Decimal(str(round(random.uniform(4.0,6.0),4))),
                    "monthly_payment": aa / Decimal(term),
                    "contract_status": random.choice(["正常","正常","正常","关注","已结清"]),
                    "sign_time": atime + timedelta(days=random.randint(5,10)),
                    "start_date": sd,
                    "end_date": sd + timedelta(days=term * 30),
                })
                for k in range(random.randint(3, 12)):
                    dd = sd + timedelta(days=k * 30)
                    da = aa / Decimal(term)
                    pd = da if random.random() < 0.8 else Decimal("0")
                    od = 0 if pd > 0 else random.randint(0, 90)
                    self.rows["loan_repayment"].append({
                        "contract_id": cid, "user_id": uid,
                        "due_date": dd, "due_amount": da,
                        "paid_amount": pd,
                        "paid_date": dd if pd > 0 else None,
                        "payment_status": "已还清" if pd >= da else ("逾期" if od > 0 else "未还"),
                        "overdue_days": od,
                    })
            for _ in range(random.randint(0, 3)):
                self.rows["loan_multi_platform"].append({
                    "user_id": uid,
                    "institution_name": random.choice(["招商银行","平安银行","微众银行","网商银行"]),
                    "loan_amount": random_amount(10000, 300000),
                    "loan_date": random_date(ONE_YEAR_AGO, NOW),
                    "loan_status": random.choice(["正常","已结清"]),
                    "report_source": random.choice(["征信报告","第三方"]),
                })

    def _gen_risk_data(self):
        for uid in self.risk_user_ids:
            self.rows["fraud_case_record"].append({
                "fraud_scenario": random.choice(["F1","F2","F3","F6","F8"]),
                "user_id": uid,
                "involved_amount": random_amount(50000, 1000000),
                "report_source": random.choice(["行内风控","公安通报"]),
                "report_time": random_time(ONE_YEAR_AGO, NOW),
                "case_status": random.choice(["调查中","已结案"]),
            })
        for uid in random.sample(self.user_ids, min(5, len(self.user_ids))):
            self.rows["regulatory_report"].append({
                "reg_type": random.choice(["大额交易报告","可疑交易报告"]),
                "ref_id": f"TXN_{uid}_001",
                "report_content": json.dumps({"user_id": uid, "amount": str(random_amount(200000,1000000))}, ensure_ascii=False),
                "report_status": random.choice(["已生成","已上报"]),
                "submit_time": random_time(ONE_YEAR_AGO, NOW),
            })

    def _gen_agg(self):
        for uid in self.user_ids:
            for d in range(random.randint(3, 10)):
                ad = (NOW - timedelta(days=d * 5)).date()
                tc = random.randint(1, 20)
                ta = random_amount(100, 100000)
                self.rows["txn_agg_daily"].append({
                    "user_id": uid, "agg_date": ad,
                    "txn_count": tc, "total_amount": ta,
                    "avg_amount": ta / tc,
                    "max_amount": random_amount(1000, 50000),
                    "min_amount": random_amount(1, 100),
                    "card_count": random.randint(1, 3),
                    "city_count": random.randint(1, 3),
                    "device_count": random.randint(1, 2),
                    "counterparty_count": random.randint(1, tc),
                    "night_txn_count": random.randint(0, tc // 4),
                })


TABLES = [
    "user_info","user_kyc_record","user_employment","user_contact","user_enterprise",
    "bank_card","card_bind_record","credit_card_bill","card_limit_change",
    "transaction","txn_suspicious_report","txn_split_chain","txn_agg_daily",
    "txn_counterparty","txn_channel_risk","txn_black_account",
    "loan_application","loan_approval","loan_contract","loan_repayment","loan_multi_platform",
    "login_log","device_fingerprint","ip_geo_location","password_change_log","session_tracking",
    "high_risk_region","enterprise_blacklist","fraud_case_record","regulatory_report",
]


def format_value(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, (Decimal,)):
        return str(v)
    if isinstance(v, (datetime,)):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(v, (date,)):
        return f"'{v.strftime('%Y-%m-%d')}'"
    if isinstance(v, str):
        escaped = v.replace("'", "''")
        return f"'{escaped}'"
    return str(v)


def to_sql(rows: dict) -> str:
    lines = ["SET NAMES utf8mb4;", "SET FOREIGN_KEY_CHECKS = 0;", ""]
    for table in TABLES:
        data = rows.get(table, [])
        if not data:
            continue
        cols = list(data[0].keys())
        col_str = ", ".join(f"`{c}`" for c in cols)
        inserts = []
        for row in data:
            vals = ", ".join(format_value(row[c]) for c in cols)
            inserts.append(f"({vals})")
        lines.append(f"-- {table} ({len(inserts)} rows)")
        lines.append(f"INSERT INTO `{table}` ({col_str}) VALUES")
        for idx, ins in enumerate(inserts):
            sep = "," if idx < len(inserts) - 1 else ";"
            lines.append(f"  {ins}{sep}")
        lines.append("")
    lines.append("SET FOREIGN_KEY_CHECKS = 1;")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成银行工商风控业务模拟数据")
    parser.add_argument("--count", type=int, default=25, help="用户数量 (默认 25, 生成 30 张表 500+ 行)")
    parser.add_argument("--truncate", action="store_true", help="同时输出 TRUNCATE 清表语句")
    parser.add_argument("--output-sql", type=str, default=None, help="输出 SQL 文件路径")
    args = parser.parse_args()

    gen = DataGen(n_users=args.count)
    gen.run()

    sql = to_sql(gen.rows)
    if args.truncate:
        trunc_lines = ["-- TRUNCATE ALL BUSINESS TABLES"]
        for t in TABLES:
            trunc_lines.append(f"TRUNCATE TABLE `{t}`;")
        sql = "\n".join(trunc_lines) + "\n\n" + sql

    out_path = args.output_sql
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(sql)
        print(f"\nSQL 已输出到: {out_path}")
    else:
        # 默认输出到 sql/init_business_data.sql
        default_path = os.path.join(
            os.path.dirname(__file__), "..", "sql", "init_business_data.sql"
        )
        with open(os.path.normpath(default_path), "w", encoding="utf-8") as f:
            f.write(sql)
        print(f"\nSQL 已输出到: {os.path.normpath(default_path)}")


if __name__ == "__main__":
    main()

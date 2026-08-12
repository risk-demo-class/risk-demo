"""
银行风控系统 - 业务数据造数脚本 (Faker)

生成 6 张核心表的关联模拟数据, 并写出 INSERT 脚本到 sql/init_business_data.sql:
  - merchant_info       商户信息表   (20 个)
  - txn_flow            交易流水表   (>=100 条, 关联 merchant / cust)
  - settlement_log      结算记录表   (每笔成功交易 1 条, 金额一致)
  - user_behavior_log   用户行为日志表 (>=100 条, 含登录/改绑前置行为)
  - risk_event_biz      风险事件表   (命中规则的交易触发)
  - relation_graph      关联关系表   (同设备/IP 归集边)

一致性保证:
  1) 交易流水 txn_flow.merchant_id 必存在于 merchant_info
  2) 结算 settlement_log.txn_id 必对应一笔成功交易, 且 net_amount = settle_amount - fee_amount
  3) 行为日志 cust_id 必为已有客户
  4) 风险事件 txn_id 必对应一笔交易

用法:
  python scripts/gen_business_data.py --count 120 --out sql/init_business_data.sql
依赖: pip install faker
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta

# 将项目根目录加入 Python 路径 (同基线 gen_risk_data.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from faker import Faker
except ImportError:  # pragma: no cover
    raise SystemExit("请先安装依赖: pip install faker")

from app.config import BANK_EVENT_TYPES, BLACKLIST_TYPES

fake = Faker("zh_CN")
random.seed(20260811)
Faker.seed(20260811)

# 业务常量
MERCHANT_TYPES = ["个体", "企业", "对公通道", "个人收款码"]
TXN_TYPES = BANK_EVENT_TYPES  # transfer/loan_apply/card_txn/repay/login
CHANNELS = ["手机银行", "网银", "ATM", "POS", "柜面"]
PROVINCES = ["上海", "北京", "广东", "浙江", "江苏", "四川", "湖北"]
TXN_STATUS = {"success": 1, "fail": 2, "suspect": 3, "freeze": 4, "report": 5}
EVENT_TYPES = ["aml_suspect", "veto", "anti_fraud_freeze", "blacklist_hit"]
DECISIONS = ["pass", "review", "reject", "freeze", "report"]
REL_TYPES = ["fund_collect", "device_share", "ip_share", "beneficiary", "same_phone"]


def _dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _sql_val(v):
    """转义并包裹 SQL 值."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def generate(merchant_n: int = 20, txn_n: int = 120, behavior_n: int = 120, fraud_ratio: float = 0.2):
    """返回 (表名->[行dict], 统计). 内部保证外键一致.
    fraud_ratio: 欺诈样本占比 (默认 0.2 => 正例:负例 ≈ 1:4).
    """
    base_time = datetime(2026, 5, 1)

    # --- 1. 商户 ---
    merchants = []
    for i in range(1, merchant_n + 1):
        mid = f"M{100000 + i}"
        mtype = random.choice(MERCHANT_TYPES)
        merchants.append({
            "merchant_id": mid,
            "merchant_name": fake.company(),
            "merchant_type": mtype,
            "mcc_code": random.choice(["5411", "5812", "5999", "6011", "7399"]),
            "legal_person": fake.name(),
            "id_card_no": fake.ssn()[:18],
            "contact_phone": fake.phone_number()[-11:],
            "province": random.choice(PROVINCES),
            "city": fake.city(),
            "risk_level": random.choices([0, 1, 2], weights=[80, 15, 5])[0],
            "status": random.choices([1, 2, 3, 4], weights=[90, 4, 3, 3])[0],
            "open_date": _dt(base_time - timedelta(days=random.randint(30, 800))),
            "f_ext_json": json.dumps({"monthly_avg_amt": round(random.uniform(1e4, 5e6), 2)}),
            "created_at": _dt(base_time),
        })
    merchant_ids = [m["merchant_id"] for m in merchants]
    cust_pool = [f"C{200000 + j}" for j in range(1, 61)]  # 60 个客户

    # --- 2. 交易流水 ---
    # 精确控制欺诈比例: 先按比例抽取要标记为欺诈的交易索引, 保证正例:负例 ≈ 1:4
    n_fraud = int(txn_n * fraud_ratio)
    fraud_idx = set(random.sample(range(1, txn_n + 1), n_fraud))

    txns = []
    for i in range(1, txn_n + 1):
        tid = f"T{300000 + i}"
        ctime = base_time + timedelta(
            days=random.randint(0, 90),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        ttype = random.choice(TXN_TYPES)
        # login 类不挂商户
        mid = random.choice(merchant_ids) if ttype != "login" and random.random() < 0.7 else None
        cust = random.choice(cust_pool)
        cp = random.choice(cust_pool)
        # 注入可疑样本: 快进快出 / 对公洗钱通道 / 夜间盗卡
        # fraud_ratio 默认 0.2 (正例:负例 = 1:4), 满足银行风控训练样本配比
        is_fraud = i in fraud_idx
        st = TXN_STATUS["success"]
        if is_fraud:
            st = random.choice([3, 4, 5])
            # 欺诈特征: 偏向大额/高对手数/夜间, 但与正常样本保留现实重叠区间
            if ttype in ("transfer", "card_txn"):
                amt = round(random.uniform(30000, 500000), 2)
            else:
                amt = round(random.uniform(5000, 200000), 2)
            ctime = base_time + timedelta(
                days=random.randint(0, 90),
                hours=random.choice([1, 2, 3, 4, 5, 6, 22, 23]),  # 偏向夜间/凌晨
                minutes=random.randint(0, 59),
            )
            geo_dev = random.random() < 0.75  # 欺诈以 75% 概率异地, 制造与正常的重叠
        else:
            # 正常样本覆盖更宽区间 (含重叠区), 避免模型线性可分导致的虚假 AUC=1.0
            amt = round(random.uniform(50, 250000), 2)
            geo_dev = random.random() < 0.15  # 偶发异地但非欺诈
            if random.random() < 0.2:  # 部分正常交易也落在夜间, 制造混淆
                ctime = base_time + timedelta(
                    days=random.randint(0, 90),
                    hours=random.choice([1, 2, 3, 4, 5, 6, 22, 23]),
                    minutes=random.randint(0, 59),
                )
        txns.append({
            "txn_id": tid,
            "merchant_id": mid,
            "cust_id": cust,
            "counterparty_id": cp if ttype in ("transfer", "card_txn") else None,
            "counterparty_account": ("6228" + str(random.randint(10**14, 10**15 - 1))) if ttype in ("transfer", "card_txn") else None,
            "txn_type": ttype,
            "channel": random.choice(CHANNELS) if ttype != "login" else "手机银行",
            "amount": amt,
            "currency": "CNY",
            "txn_time": ctime,
            "device_fingerprint": fake.sha1()[:64],
            "ip_addr": fake.ipv4(),
            "geo_province": random.choice(PROVINCES),
            "geo_city": fake.city(),
            "txn_status": st,
            "is_fraud": is_fraud,
            "f_speed": round(random.uniform(0.1, 30), 2) if is_fraud else round(random.uniform(1, 200), 2),
            "f_counterparty_cnt": random.randint(8, 35) if is_fraud else random.randint(1, 8),
            "f_ext_json": json.dumps({
                "peer_industry": random.choice(["餐饮", "零售", "珠宝", "虚拟币"]),
                "geo_ip_deviation": geo_dev,
                "amount_mean": round(random.uniform(3000, 15000), 2),
            }),
            "created_at": ctime,
        })

    txn_ids = [t["txn_id"] for t in txns]
    cust_ids_all = list({t["cust_id"] for t in txns} | set(cust_pool))

    # --- 3. 结算 (仅成功交易生成) ---
    settlements = []
    for t in txns:
        if t["txn_status"] != TXN_STATUS["success"]:
            continue
        sid = f"S{400000 + len(settlements) + 1}"
        settle_amt = t["amount"]
        fee = round(settle_amt * random.uniform(0.001, 0.006), 4)
        net = round(settle_amt - fee, 4)
        sdate = t["txn_time"] + timedelta(days=1)
        settlements.append({
            "settle_id": sid,
            "txn_id": t["txn_id"],
            "merchant_id": t["merchant_id"],
            "settle_amount": settle_amt,
            "fee_amount": fee,
            "net_amount": net,
            "settle_date": sdate,
            "settle_status": random.choices([1, 2, 3, 4, 5], weights=[5, 85, 4, 3, 3])[0],
            "error_code": None if random.random() < 0.9 else random.choice(["E01", "E02"]),
            "f_ext_json": json.dumps({"batch": fake.bothify(text="B##???")}),
            "created_at": sdate,
        })

    # --- 4. 用户行为日志 ---
    behaviors = []
    for i in range(1, behavior_n + 1):
        cust = random.choice(cust_ids_all)
        atime = base_time + timedelta(
            days=random.randint(0, 90),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        action = random.choices(
            ["login", "login_fail", "change_bind", "transfer_prepay", "query"],
            weights=[55, 15, 8, 12, 10],
        )[0]
        behaviors.append({
            "cust_id": cust,
            "action": action,
            "action_time": atime,
            "device_fingerprint": fake.sha1()[:64],
            "ip_addr": fake.ipv4(),
            "geo_province": random.choice(PROVINCES),
            "geo_city": fake.city(),
            "result": 0 if action == "login_fail" else 1,
            "f_ext_json": json.dumps({"ua": fake.user_agent()}),
            "created_at": atime,
        })

    # --- 5. 风险事件 (可疑/欺诈交易触发) ---
    events = []
    for t in txns:
        if t["is_fraud"] or t["txn_status"] in (3, 4, 5):
            eid = f"E{500000 + len(events) + 1}"
            etype = random.choice(EVENT_TYPES)
            sev = random.choices([2, 3, 4], weights=[30, 40, 30])[0]
            dec = "freeze" if etype == "anti_fraud_freeze" else ("report" if etype == "aml_suspect" else "reject")
            events.append({
                "event_id": eid,
                "txn_id": t["txn_id"],
                "cust_id": t["cust_id"],
                "event_type": etype,
                "trigger_rule": random.choice(["rule_fast_transfer", "rule_amt_threshold", "model_xgb_v1"]),
                "severity": sev,
                "decision": dec,
                "reported": dec == "report",
                "report_no": (f"R{600000 + len(events)}" if dec == "report" else None),
                "detail_json": json.dumps({"peer": t["counterparty_id"], "amt": t["amount"]}),
                "created_at": t["txn_time"],
            })

    # --- 6. 关联关系 (同设备/同IP/资金归集) ---
    relations = []
    seen = set()
    for t in txns:
        if t["counterparty_id"]:
            edge = (t["cust_id"], t["counterparty_id"], "fund_collect")
            if edge not in seen:
                seen.add(edge)
                relations.append({
                    "src_id": edge[0], "dst_id": edge[1], "rel_type": edge[2],
                    "weight": round(random.uniform(1, 5), 2),
                    "first_seen": t["txn_time"], "last_seen": t["txn_time"],
                    "is_suspicious": t["is_fraud"],
                    "f_ext_json": json.dumps({"cnt": random.randint(1, 9)}),
                    "created_at": t["txn_time"],
                })
    # 补充同设备边
    for _ in range(min(20, len(txn_ids))):
        a, b = random.sample(cust_ids_all, 2)
        edge = (a, b, random.choice(["device_share", "ip_share", "same_phone"]))
        if edge not in seen:
            seen.add(edge)
            relations.append({
                "src_id": a, "dst_id": b, "rel_type": edge[2],
                "weight": round(random.uniform(1, 3), 2),
                "first_seen": base_time, "last_seen": base_time + timedelta(days=90),
                "is_suspicious": random.random() < 0.2,
                "f_ext_json": json.dumps({}), "created_at": base_time,
            })

    return {
        "merchant_info": merchants,
        "txn_flow": txns,
        "settlement_log": settlements,
        "user_behavior_log": behaviors,
        "risk_event_biz": events,
        "relation_graph": relations,
    }


def to_insert_sql(table: str, rows: list, columns: list) -> str:
    if not rows:
        return ""
    lines = [f"-- Table `{table}`: {len(rows)} rows"]
    head = ", ".join(columns)
    val_parts = []
    for r in rows:
        vals = ", ".join(_sql_val(r.get(c)) for c in columns)
        val_parts.append(f"({vals})")
    # 分批, 每批 50 行
    chunk = 50
    out = [lines[0]]
    for i in range(0, len(val_parts), chunk):
        batch = val_parts[i:i + chunk]
        out.append(f"INSERT INTO `{table}` ({head}) VALUES")
        out.append(",\n".join(batch) + ";")
    return "\n".join(out)


COLUMNS = {
    "merchant_info": ["merchant_id", "merchant_name", "merchant_type", "mcc_code", "legal_person",
                      "id_card_no", "contact_phone", "province", "city", "risk_level", "status",
                      "open_date", "f_ext_json", "created_at"],
    "txn_flow": ["txn_id", "merchant_id", "cust_id", "counterparty_id", "counterparty_account",
                 "txn_type", "channel", "amount", "currency", "txn_time", "device_fingerprint",
                 "ip_addr", "geo_province", "geo_city", "txn_status", "is_fraud",
                 "f_speed", "f_counterparty_cnt", "f_ext_json", "created_at"],
    "settlement_log": ["settle_id", "txn_id", "merchant_id", "settle_amount", "fee_amount",
                       "net_amount", "settle_date", "settle_status", "error_code", "f_ext_json", "created_at"],
    "user_behavior_log": ["cust_id", "action", "action_time", "device_fingerprint", "ip_addr",
                          "geo_province", "geo_city", "result", "f_ext_json", "created_at"],
    "risk_event_biz": ["event_id", "txn_id", "cust_id", "event_type", "trigger_rule", "severity",
                       "decision", "reported", "report_no", "detail_json", "created_at"],
    "relation_graph": ["src_id", "dst_id", "rel_type", "weight", "first_seen", "last_seen",
                       "is_suspicious", "f_ext_json", "created_at"],
}


def emit_sql(data: dict, out_path: str):
    parts = ["-- ============================================",
             "-- 银行风控系统 - 业务初始化数据 (Faker 生成)",
             f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             "-- 外键一致: 交易->商户, 结算->交易, 事件->交易",
             "-- ============================================", "",
             "SET NAMES utf8mb4;", "SET FOREIGN_KEY_CHECKS = 0;", ""]
    for tbl in ["merchant_info", "txn_flow", "settlement_log",
                "user_behavior_log", "risk_event_biz", "relation_graph"]:
        parts.append(to_insert_sql(tbl, data[tbl], COLUMNS[tbl]))
        parts.append("")
    parts.append("SET FOREIGN_KEY_CHECKS = 1;")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"✅ 已写出初始化数据: {out_path}")
    for tbl in data:
        print(f"   {tbl}: {len(data[tbl])} 行")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="银行风控业务造数 (Faker) -> init_business_data.sql")
    parser.add_argument("--merchants", type=int, default=20, help="商户数 (默认 20)")
    parser.add_argument("--count", type=int, default=120, help="交易流水条数 (>=100, 默认 120)")
    parser.add_argument("--behaviors", type=int, default=120, help="行为日志条数 (默认 120)")
    parser.add_argument("--out", type=str, default="sql/init_business_data.sql", help="输出 SQL 路径")
    args = parser.parse_args()

    data = generate(merchant_n=args.merchants, txn_n=args.count, behavior_n=args.behaviors)
    emit_sql(data, args.out)

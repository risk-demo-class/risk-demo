"""
规则命中演示 (验证 8 条反欺诈规则路由与五级决策语义)

直接调用 validator.validate() 便捷入口, 构造覆盖各类命中场景的样本,
展示 8 条规则 (黑名单冻结/大额转账报送/分散转入集中转出/地理IP偏离/
多头借贷预警/过度查询拦截/登录撞库封控/异常时段交易) 的判断结果.
"""
import os
import sys

# 将项目根目录加入 Python 路径, 支持 `python scripts/demo_rules.py` 直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from app.config import DECISION_REJECT, DECISION_REVIEW, DECISION_FREEZE, DECISION_REPORT, DECISION_PASS
from app.service import validator as V
from app.service.validator import TxnContext

BLACKLIST = {("account", "C200099"), ("ip", "203.0.113.9")}


def ctx(**kw):
    base = dict(
        txn_id="T0", cust_id="C0", txn_type="transfer", amount=0.0,
        counterparty_id=None, device_fingerprint="d1", ip_addr="10.0.0.1",
        geo_province="上海", geo_city="上海", peer_cnt_1h=0,
        login_fail_5m=0, geo_ip_deviation=False, credit_query_30d=0,
        multi_loan_platforms=0, txn_time=None,
    )
    base.update(kw)
    return TxnContext(**base)


DEMOS = [
    ("黑名单冻结", ctx(txn_type="transfer", cust_id="C200099", amount=5000.0)),
    ("大额转账报送", ctx(txn_type="transfer", amount=260000.0)),
    ("分散转入集中转出", ctx(txn_type="transfer", amount=80000.0, peer_cnt_1h=15)),
    ("地理IP偏离", ctx(txn_type="transfer", geo_ip_deviation=True, amount=60000.0)),
    ("多头借贷预警", ctx(txn_type="loan_apply", credit_query_30d=12, multi_loan_platforms=6)),
    ("异常时段交易", ctx(txn_type="card_txn", amount=90000.0, txn_time=datetime(2026, 5, 3, 3, 0))),
    ("登录撞库封控", ctx(txn_type="login", login_fail_5m=8)),
    ("正常放行", ctx(txn_type="repay", amount=3000.0)),
]


if __name__ == "__main__":
    print("=" * 60)
    print("8 条反欺诈规则命中演示 (五级决策: pass/review/reject/freeze/report)")
    print("=" * 60)
    for name, c in DEMOS:
        res = V.validate_txn(c, blacklist=BLACKLIST)
        max_sev = max((r.severity for r in res.triggered_rules), default=0)
        print(f"\n【{name}】 -> 最终决策: {res.decision.upper()} (max_severity={max_sev})")
        for r in res.triggered_rules:
            print(f"   ✓ {r.rule}: {r.decision} | {r.message}")
        if not res.triggered_rules:
            print("   · 无命中, PASS")

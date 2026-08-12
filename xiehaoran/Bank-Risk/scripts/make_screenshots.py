"""
运行截图生成 (固化 5 份运行输出为 PNG)

使用 matplotlib 把风控模型建设的运行结果可视化为图片, 存放于 scripts/screenshots/:
  01_feature.png    三大特征族: 可疑 vs 正常 对比
  02_rules.png      8 条反欺诈规则命中 + 五级决策
  03_event.png      5 种银行事件枚举 -> 决策 分发
  04_train.png      训练指标: 基础 vs 难负样本增强 (val_auc/val_f1 对比)
  05_eval.png       评估历史 (eval_history.jsonl 多运行记录)

数据来源: 直接复用 app.engine.feature / app.service.validator / app.service.event
          与 scripts/eval_history.jsonl, 无需重新训练.
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime

# 中文字体 (Windows 优先 Microsoft YaHei / SimHei; 缺失时回退仍可读)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in __import__("sys").path:
    __import__("sys").path.insert(0, ROOT)

from app.engine import feature as feat  # noqa: E402
from app.service import validator as V  # noqa: E402
from app.service.event import _demo_events, process_event  # noqa: E402

OUT_DIR = os.path.join(ROOT, "scripts", "screenshots")
EVAL_HISTORY_PATH = os.path.join(ROOT, "scripts", "eval_history.jsonl")
os.makedirs(OUT_DIR, exist_ok=True)

DECISION_COLORS = {
    "pass": "#2ecc71", "review": "#f39c12", "reject": "#e67e22",
    "freeze": "#e74c3c", "report": "#3498db",
}


# ----------------------------------------------------------
# 1. 特征计算对比
# ----------------------------------------------------------
def make_feature_chart():
    suspicious = {
        "amount": 260000.0, "f_counterparty_cnt": 18, "f_speed": 3.2,
        "txn_time": "2026-05-03 03:14:00", "geo_ip_deviation": True,
        "credit_query_30d": 12, "multi_loan_platforms": 6, "login_fail_5m": 7,
        "ip_addr": "203.0.113.9", "device_fingerprint": "dev_new_001",
        "f_ext_json": json.dumps({"amount_mean": 8000.0, "hist_device_fingerprint": "dev_old"}),
    }
    normal = {
        "amount": 1200.0, "f_counterparty_cnt": 2, "f_speed": 45.0,
        "txn_time": "2026-05-03 14:20:00", "geo_ip_deviation": False,
        "credit_query_30d": 1, "multi_loan_platforms": 0, "login_fail_5m": 0,
        "ip_addr": "10.20.3.4", "device_fingerprint": "dev_old",
        "f_ext_json": json.dumps({"amount_mean": 8000.0, "hist_device_fingerprint": "dev_old"}),
    }
    fs, fn = feat.compute_all_features(suspicious), feat.compute_all_features(normal)
    keys = [k for k in fs.keys() if not k.endswith("_raw")]  # 截图仅展示归一化训练特征
    xs = range(len(keys))
    w = 0.38
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.bar([x - w / 2 for x in xs], [fs[k] for k in keys], w, label="可疑转账", color="#e74c3c")
    ax.bar([x + w / 2 for x in xs], [fn[k] for k in keys], w, label="正常交易", color="#2ecc71")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(keys, rotation=35, ha="right")
    ax.set_title("图1  三大特征族计算: 可疑样本 vs 正常样本", fontsize=13, fontweight="bold")
    ax.set_ylabel("特征值")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT_DIR, "01_feature.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


# ----------------------------------------------------------
# 2. 规则命中 (8 条)
# ----------------------------------------------------------
def make_rules_chart():
    from datetime import datetime as _dt
    BL = {("account", "C200099"), ("ip", "203.0.113.9")}

    def ctx(**kw):
        return V.TxnContext(
            txn_id=kw.get("txn_id", "T0"),
            cust_id=kw.get("cust_id", "C0"),
            txn_type=kw.get("txn_type", "transfer"),
            amount=float(kw.get("amount", 0.0)),
            counterparty_id=kw.get("counterparty_id", None),
            device_fingerprint=kw.get("device_fingerprint", "d1"),
            ip_addr=kw.get("ip_addr", "10.0.0.1"),
            geo_province=kw.get("geo_province", "上海"),
            geo_city=kw.get("geo_city", "上海"),
            peer_cnt_1h=int(kw.get("peer_cnt_1h", 0)),
            login_fail_5m=int(kw.get("login_fail_5m", 0)),
            geo_ip_deviation=bool(kw.get("geo_ip_deviation", False)),
            credit_query_30d=int(kw.get("credit_query_30d", 0)),
            multi_loan_platforms=int(kw.get("multi_loan_platforms", 0)),
            txn_time=kw.get("txn_time", None),
        )

    demos = [
        ("黑名单冻结", ctx(txn_type="transfer", cust_id="C200099", amount=5000.0)),
        ("大额转账报送", ctx(txn_type="transfer", amount=260000.0)),
        ("分散转入集中转出", ctx(txn_type="transfer", amount=80000.0, peer_cnt_1h=15)),
        ("地理IP偏离", ctx(txn_type="transfer", geo_ip_deviation=True, amount=60000.0)),
        ("多头借贷预警", ctx(txn_type="loan_apply", credit_query_30d=12, multi_loan_platforms=6)),
        ("异常时段交易", ctx(txn_type="card_txn", amount=90000.0, txn_time=_dt(2026, 5, 3, 3, 0))),
        ("登录撞库封控", ctx(txn_type="login", login_fail_5m=8)),
        ("正常放行", ctx(txn_type="repay", amount=3000.0)),
    ]
    names, decisions, sevs = [], [], []
    for name, c in demos:
        res = V.validate_txn(c, blacklist=BL)
        names.append(name)
        decisions.append(res.decision)
        sevs.append(max((r.severity for r in res.triggered_rules), default=0))

    fig, ax = plt.subplots(figsize=(12, 5.5))
    colors = [DECISION_COLORS.get(d, "#95a5a6") for d in decisions]
    bars = ax.barh(range(len(names)), [max(s, 1) for s in sevs], color=colors)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("规则严重度 (severity)")
    ax.set_title("图2  8 条反欺诈规则命中 (颜色=五级决策语义)", fontsize=13, fontweight="bold")
    for i, (d, s) in enumerate(zip(decisions, sevs)):
        ax.text(max(s, 1) + 0.05, i, d.upper(), va="center", fontsize=10, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT_DIR, "02_rules.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


# ----------------------------------------------------------
# 3. 事件分发 (5 种枚举)
# ----------------------------------------------------------
def make_event_chart():
    evs = _demo_events()
    names, decisions = [], []
    for ev in evs:
        res = process_event(ev)
        names.append(f"{ev['txn_type']}\n({res['txn_id']})")
        decisions.append(res["decision"])
    fig, ax = plt.subplots(figsize=(11, 4.8))
    colors = [DECISION_COLORS.get(d, "#95a5a6") for d in decisions]
    bars = ax.bar(range(len(names)), [1] * len(names), color=colors)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names)
    ax.set_yticks([])
    ax.set_title("图3  5 种银行事件枚举 -> 决策分发 (process_event)", fontsize=13, fontweight="bold")
    for i, d in enumerate(decisions):
        ax.text(i, 0.5, d.upper(), ha="center", va="center", fontsize=11, fontweight="bold", color="white")
    fig.tight_layout()
    p = os.path.join(OUT_DIR, "03_event.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


# ----------------------------------------------------------
# 4. 训练指标对比 (基础 vs 难负样本)
# ----------------------------------------------------------
def make_train_chart():
    if not os.path.exists(EVAL_HISTORY_PATH):
        return None
    rows = [json.loads(l) for l in open(EVAL_HISTORY_PATH, encoding="utf-8") if l.strip()]
    if not rows:
        return None
    labels = [f"run{i+1}\n({'HARD' if r.get('hard_negative_aug') else 'BASE'})" for i, r in enumerate(rows)]
    train_aucs = [r.get("train_auc", r["val_auc"]) for r in rows]
    val_aucs = [r["val_auc"] for r in rows]
    f1s = [r["val_f1"] for r in rows]
    xs = range(len(rows))
    w = 0.26
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([x - w for x in xs], train_aucs, w, label="train_auc", color="#9b59b6")
    ax.bar([x for x in xs], val_aucs, w, label="val_auc", color="#3498db")
    ax.bar([x + w for x in xs], f1s, w, label="val_f1", color="#e67e22")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("指标值")
    ax.set_title("图4  XGBoost 训练评估 (BASE vs 难负样本增强 HARD)\n"
                 "train_auc 与 val_auc 的 gap 越小, 过拟合越轻", fontsize=12, fontweight="bold")
    for i, (t, v, f) in enumerate(zip(train_aucs, val_aucs, f1s)):
        ax.text(i - w, t + 0.015, f"{t:.3f}", ha="center", fontsize=8)
        ax.text(i, v + 0.015, f"{v:.3f}", ha="center", fontsize=8)
        ax.text(i + w, f + 0.015, f"{f:.3f}", ha="center", fontsize=8)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT_DIR, "04_train.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


# ----------------------------------------------------------
# 5. 评估历史
# ----------------------------------------------------------
def make_eval_chart():
    if not os.path.exists(EVAL_HISTORY_PATH):
        return None
    rows = [json.loads(l) for l in open(EVAL_HISTORY_PATH, encoding="utf-8") if l.strip()]
    if not rows:
        return None
    ts = [r["ts"][5:16].replace("T", " ") for r in rows]
    aucs = [r["val_auc"] for r in rows]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(range(len(rows)), aucs, marker="o", color="#3498db", label="val_auc")
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(ts, rotation=30, ha="right")
    ax.set_ylim(0.8, 1.02)
    ax.set_ylabel("val_auc")
    ax.set_title("图5  评估历史 (eval_history.jsonl)", fontsize=13, fontweight="bold")
    for i, a in enumerate(aucs):
        ax.text(i, a + 0.003, f"{a:.3f}", ha="center", fontsize=9)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    p = os.path.join(OUT_DIR, "05_eval.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


if __name__ == "__main__":
    paths = [make_feature_chart(), make_rules_chart(), make_event_chart(),
             make_train_chart(), make_eval_chart()]
    for p in paths:
        print("生成:", p if p else "(跳过: 无评估历史)")
    print(f"\n全部截图已保存至: {OUT_DIR}")

# -*- coding: utf-8 -*-
r"""训练 XGBoost 风控模型（宝典第 7 章 7.7 / 7.8 + 第 17 章 练习 3）

    python scripts/train_xgb_model.py
    python scripts/train_xgb_model.py --force              # 样本不足也硬训（教学演示假收敛）
    python scripts/train_xgb_model.py --dry-run            # 只看指标，不覆盖线上模型
    python scripts/train_xgb_model.py --from feature-table # 从 risk_feature 逐行还原（校验快照一致性）

## 数据来自哪里？

`gen_risk_data.py` 已经把业务数据喂过真实 7 步流水线，产物落在两处：

    risk_assessment.feature_snapshot   ← 25 维特征的 JSON 快照（默认读这里，快）
    risk_feature (event_id, name, val) ← 每条事件 25 行明细（--from feature-table，慢但可校验）

两条路读出来的 X 必须**完全一致**；不一致说明落库环节出了 bug，脚本会直接报警。
label 来自 `risk_assessment.label`（宝典 7.11 三来源，默认「规则反推」）。

## 这个脚本额外做了什么（宝典 7.7 抗假收敛 5 件套的「第 5 件」）

`ml_model.train_and_save()` 已经内置了早停 / warmup / L1+L2 / 3 信号检测。
本脚本负责把这些**摊开给人看**：

    ① 数据体检     —— 样本量 / 正例比 / 缺失率 / 零方差特征（喂垃圾进去必出垃圾）
    ② baseline 对比 —— acc 打不过「全预测多数类」就是白练（FAQ 22 最容易自欺的一项）
    ③ 阈值扫描表   —— 0.10~0.85 全表，肉眼确认 0.5 是不是错位了（7.8）
    ④ 假收敛诊断   —— 4 个信号逐条列出 PASS / FAIL，不合格给出具体修复命令
    ⑤ 回环校验     —— 存盘后重新 load，随机抽样比对概率，确认 JSON 序列化无损

## 训练完之后会发生什么？

决策融合权重立刻从「降级纯规则 α=1.0/β=0.0」切回「双轨 α=0.5/β=0.5」
（宝典 8.4 ④）。也就是说：**训练模型这件事本身会改变线上决策分布**，
脚本末尾会把这个影响明确提示出来。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import settings                                      # noqa: E402
from app.database import pool, session_scope                          # noqa: E402
from app.engine import ml_model                                       # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, MISSING              # noqa: E402
from app.engine.feature import FEATURE_DIM as FEATURE_DIM_OF          # noqa: E402

BAR = "=" * 76
SUB = "-" * 76

#: 复用 ml_model 内部的分层拆分 —— 同 seed 才能复现出训练时那一份验证集
_stratified_split = ml_model._stratified_split      # noqa: SLF001
_prf = ml_model._prf                                # noqa: SLF001


# ============================================================== 终端表格（中文对齐）
def _w(text: str) -> int:
    """显示宽度：CJK 全角字符算 2 列，否则终端表格会歪。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in str(text))


def _pad(text: str, width: int, align: str = "l") -> str:
    gap = max(width - _w(text), 0)
    if align == "r":
        return " " * gap + str(text)
    if align == "c":
        left = gap // 2
        return " " * left + str(text) + " " * (gap - left)
    return str(text) + " " * gap


def print_table(headers: Sequence[str], rows: Sequence[Sequence[Any]],
                aligns: str = "", indent: str = "  ") -> None:
    body = [[("" if c is None else str(c)) for c in row] for row in rows]
    widths = [max(_w(headers[i]), *(_w(r[i]) for r in body)) if body else _w(headers[i])
              for i in range(len(headers))]
    aligns = (aligns or "l" * len(headers)).ljust(len(headers), "l")
    line = indent + "  ".join(_pad(headers[i], widths[i], "c") for i in range(len(headers)))
    print(line)
    print(indent + "  ".join("-" * widths[i] for i in range(len(headers))))
    for row in body:
        print(indent + "  ".join(_pad(row[i], widths[i], aligns[i]) for i in range(len(headers))))


def verdict(ok: bool) -> str:
    return "✅ PASS" if ok else "❌ FAIL"


# ============================================================== 取数
_SQL_ASSESS = """
SELECT assessment_id, event_id, user_id, event_type, label, label_source,
       final_score, rule_score, ml_score, risk_level, decision, is_veto,
       feature_snapshot, create_time
FROM risk_assessment
WHERE label IS NOT NULL
"""


def load_from_snapshot(db: Any, label_source: str = "", limit: int = 0) -> List[Dict[str, Any]]:
    """默认路径：直接反序列化 risk_assessment.feature_snapshot。"""
    sql, params = _SQL_ASSESS, []
    if label_source:
        sql += " AND label_source = ?"
        params.append(label_source)
    sql += " ORDER BY create_time, assessment_id"
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetch_all(sql, tuple(params))
    for row in rows:
        try:
            row["_features"] = json.loads(row.get("feature_snapshot") or "{}")
        except (TypeError, ValueError):
            row["_features"] = {}
    return rows


def load_from_feature_table(db: Any, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """校验路径：从 risk_feature 明细行还原 {event_id: {name: value}}。"""
    if not rows:
        return {}
    event_ids = [r["event_id"] for r in rows]
    out: Dict[str, Dict[str, float]] = {eid: {} for eid in event_ids}
    chunk = 500
    for i in range(0, len(event_ids), chunk):
        part = event_ids[i:i + chunk]
        marks = ",".join("?" * len(part))
        detail = db.fetch_all(
            f"SELECT event_id, feature_name, feature_value FROM risk_feature "
            f"WHERE event_id IN ({marks})", tuple(part))
        for d in detail:
            out.setdefault(d["event_id"], {})[d["feature_name"]] = d["feature_value"]
    return out


def to_matrix(features: Dict[str, Any]) -> List[float]:
    """dict → 25 列（顺序 = FEATURE_COLUMNS，缺失填 NaN 交给稀疏感知）。"""
    row: List[float] = []
    for name in FEATURE_COLUMNS:
        value = features.get(name)
        if value is None:
            row.append(MISSING)
            continue
        try:
            row.append(float(value))
        except (TypeError, ValueError):
            row.append(MISSING)
    return row


# ============================================================== ① 数据体检
def data_health(x: List[List[float]], y: List[int]) -> Dict[str, Any]:
    n = len(y)
    report: Dict[str, Any] = {"n": n, "pos": sum(y), "missing": [], "constant": [], "columns": []}
    for j, name in enumerate(FEATURE_COLUMNS):
        column = [row[j] for row in x]
        valid = [v for v in column if not math.isnan(v)]
        miss_rate = 1.0 - len(valid) / n if n else 1.0
        if valid:
            lo, hi = min(valid), max(valid)
            mean = sum(valid) / len(valid)
            var = sum((v - mean) ** 2 for v in valid) / len(valid)
        else:
            lo = hi = mean = var = 0.0
        info = {"name": name, "dim": FEATURE_DIM_OF.get(name, ""), "miss_rate": miss_rate,
                "min": lo, "max": hi, "mean": mean, "std": math.sqrt(var), "unique": len(set(valid))}
        report["columns"].append(info)
        if miss_rate > 0.30:
            report["missing"].append(info)
        if len(set(valid)) <= 1:
            report["constant"].append(info)
    return report


# ============================================================== ③ 阈值扫描全表
def threshold_table(y_true: Sequence[int], y_prob: Sequence[float]) -> List[List[Any]]:
    """0.10→0.85 全表。best 行在生成时就记下下标 ——
    别拿格式化后的字符串（"0.9130"）回头和原始 float（0.91304347…）比，差 4e-5 永远匹配不上。
    """
    rows: List[List[Any]] = []
    best_f1, best_idx = -1.0, -1
    threshold = settings.XGB_THRESHOLD_SCAN_START
    while threshold <= settings.XGB_THRESHOLD_SCAN_END + 1e-9:
        pred = [1 if p > threshold else 0 for p in y_prob]
        precision, recall, f1 = _prf(y_true, pred)
        tp = sum(1 for t, p in zip(y_true, pred) if t == 1 and p == 1)
        fp = sum(1 for t, p in zip(y_true, pred) if t == 0 and p == 1)
        fn = sum(1 for t, p in zip(y_true, pred) if t == 1 and p == 0)
        if f1 > best_f1:
            best_f1, best_idx = f1, len(rows)
        rows.append([f"{threshold:.2f}", tp, fp, fn,
                     f"{precision:.4f}", f"{recall:.4f}", f"{f1:.4f}", ""])
        threshold += settings.XGB_THRESHOLD_SCAN_STEP
    if best_idx >= 0:
        rows[best_idx][7] = "◀ 最佳 F1"
    return rows


# ============================================================== CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="训练 XGBoost 风控模型（含数据体检 / baseline 对比 / 阈值扫描 / 假收敛诊断）")
    p.add_argument("--from", dest="source", choices=["snapshot", "feature-table"],
                   default="snapshot",
                   help="X 来源：snapshot=特征快照 JSON（默认，快）| feature-table=risk_feature 明细")
    p.add_argument("--label-source", default="",
                   help="只用某一来源的 label：规则反推 / 人工标注 / 投诉反推（默认全用）")
    p.add_argument("--limit", type=int, default=0, help="最多取多少条样本（0=全部）")
    p.add_argument("--n-estimators", type=int, default=0,
                   help=f"树的数量（默认取配置 {settings.XGB_N_ESTIMATORS}）")
    p.add_argument("--seed", type=int, default=42, help="随机种子（同 seed 结果可复现）")
    p.add_argument("--model-path", default="", help=f"模型保存路径（默认 {settings.XGB_MODEL_PATH}）")
    p.add_argument("--dry-run", action="store_true",
                   help="只训练看指标，训练完删掉临时模型，不覆盖线上文件")
    p.add_argument("--force", action="store_true",
                   help=f"样本量 < XGB_MIN_SAMPLES({settings.XGB_MIN_SAMPLES}) 时仍然训练")
    p.add_argument("--top-k", type=int, default=12, help="特征重要性展示前 K 个")
    p.add_argument("--quiet", action="store_true", help="不打印每轮训练日志")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    print(f"\n{BAR}\n  训练 XGBoost 风控模型 · 25 维特征 → 二分类\n{BAR}")
    print(f"  X 来源     : {'risk_assessment.feature_snapshot' if args.source == 'snapshot' else 'risk_feature 明细表'}")
    print(f"  label 过滤 : {args.label_source or '全部来源'}")
    print(f"  实现        : {'原生 xgboost ' + ml_model._NATIVE_VERSION if ml_model._NATIVE_AVAILABLE else '纯 Python 同构 GBDT（无第三方依赖）'}")
    print(f"  随机种子   : {args.seed}")

    # ---------------------------------------------------------- 取数
    with session_scope() as db:
        rows = load_from_snapshot(db, args.label_source, args.limit)
        detail = load_from_feature_table(db, rows) if args.source == "feature-table" else {}
        cross = load_from_feature_table(db, rows[:min(len(rows), 50)]) if args.source == "snapshot" else {}

    if not rows:
        print(f"\n  ❌ risk_assessment 里没有带 label 的样本。先造数据：")
        print(f"     python scripts/init_db.py --with-business")
        print(f"     python scripts/gen_risk_data.py {settings.XGB_MIN_SAMPLES} --target-pos-ratio 0.30\n")
        return 1

    x: List[List[float]] = []
    y: List[int] = []
    kept: List[Dict[str, Any]] = []
    empty = 0
    for row in rows:
        feats = detail.get(row["event_id"], {}) if args.source == "feature-table" else row["_features"]
        if not feats:
            empty += 1
            continue
        x.append(to_matrix(feats))
        y.append(int(row["label"] or 0))
        kept.append(row)
    if empty:
        print(f"  ⚠️ {empty} 条样本特征为空，已跳过")

    # ---- 快照 vs 明细表一致性交叉校验（抽前 50 条）
    if cross:
        mismatch = 0
        for row in rows[:len(cross)]:
            snap = row["_features"]
            table = cross.get(row["event_id"], {})
            for name in FEATURE_COLUMNS:
                a, b = snap.get(name), table.get(name)
                if a is None or b is None:
                    continue
                if abs(float(a) - float(b)) > 1e-4:
                    mismatch += 1
                    break
        flag = "✅ 一致" if mismatch == 0 else f"❌ {mismatch} 条不一致"
        print(f"  落库校验   : 抽查 {len(cross)} 条，feature_snapshot vs risk_feature → {flag}")

    n_total, n_pos = len(y), sum(y)
    n_neg = n_total - n_pos
    print(f"  样本        : {n_total} 条（正 {n_pos} / 负 {n_neg}，正例比 "
          f"{n_pos / n_total:.1%}）" if n_total else "  样本        : 0")

    # ---------------------------------------------------------- ① 数据体检
    print(f"\n{BAR}\n  ① 数据体检\n{BAR}")
    health = data_health(x, y)
    checks = [
        ["样本量 ≥ XGB_MIN_SAMPLES", f"{n_total} / {settings.XGB_MIN_SAMPLES}",
         verdict(n_total >= settings.XGB_MIN_SAMPLES)],
        ["正负样本都存在", f"正 {n_pos} · 负 {n_neg}", verdict(n_pos > 0 and n_neg > 0)],
        ["正例比在 15%~50%", f"{(n_pos / n_total) if n_total else 0:.1%}",
         verdict(n_total > 0 and 0.15 <= n_pos / n_total <= 0.50)],
        ["特征维度 = 25", f"{len(FEATURE_COLUMNS)}", verdict(len(FEATURE_COLUMNS) == 25)],
        ["无高缺失特征（>30%）", f"{len(health['missing'])} 个", verdict(not health["missing"])],
        ["无零方差特征", f"{len(health['constant'])} 个", verdict(not health["constant"])],
    ]
    print_table(["体检项", "实测值", "结论"], checks, "llc")

    if health["constant"]:
        print(f"\n  ⚠️ 零方差特征（全表同一个值 → 树永远不会选它分裂，等于白算）：")
        print_table(["特征", "维度", "取值"],
                    [[c["name"], c["dim"], f"{c['min']:.4f}"] for c in health["constant"]], "llr")
        print("     常见原因：业务数据太单薄（如所有用户都没投诉）→ 加大 gen_risk_data.py 的用户数")
    if health["missing"]:
        print(f"\n  ⚠️ 高缺失特征（缺失 > 30%，靠稀疏感知默认方向兜底）：")
        print_table(["特征", "维度", "缺失率"],
                    [[c["name"], c["dim"], f"{c['miss_rate']:.1%}"] for c in health["missing"]], "llr")

    print(f"\n  特征分布抽样（前 8 维）：")
    print_table(["#", "特征", "维度", "缺失率", "min", "max", "mean", "std", "取值数"],
                [[i + 1, c["name"], c["dim"], f"{c['miss_rate']:.0%}", f"{c['min']:.2f}",
                  f"{c['max']:.2f}", f"{c['mean']:.2f}", f"{c['std']:.2f}", c["unique"]]
                 for i, c in enumerate(health["columns"][:8])], "rllrrrrrr")

    if n_pos == 0 or n_neg == 0:
        print(f"\n  ❌ 只有单一类别，无法训练（宝典 FAQ 4）。重造数据：")
        print("     python scripts/gen_risk_data.py 1500 --target-pos-ratio 0.30 --reset\n")
        return 1
    if n_total < settings.XGB_MIN_SAMPLES and not args.force:
        need = settings.XGB_MIN_SAMPLES - n_total
        print(f"\n  ❌ 样本量 {n_total} < XGB_MIN_SAMPLES({settings.XGB_MIN_SAMPLES} = 25 维 × 50)，"
              f"还差 {need} 条（宝典 7.7 必做 ④）")
        print(f"     补数据: python scripts/gen_risk_data.py {need} --target-pos-ratio 0.30")
        print(f"     或硬训: python scripts/train_xgb_model.py --force   "
              f"（会欠拟合，仅用于演示假收敛）\n")
        return 1

    # ---------------------------------------------------------- ② 训练
    print(f"\n{BAR}\n  ② 训练（早停 + warmup + L1/L2 + scale_pos_weight 截断）\n{BAR}")
    dry_path = ""
    if args.dry_run:
        fd, dry_path = tempfile.mkstemp(suffix=".json", prefix="xgb_dryrun_")
        os.close(fd)
        model_path = dry_path
        print("  🧪 dry-run：训练产物写临时文件，结束后删除，不影响线上模型")
    else:
        model_path = args.model_path or settings.XGB_MODEL_PATH

    log = (lambda msg: None) if args.quiet else (lambda msg: print(f"  {msg}"))
    started = time.time()
    metrics, booster = ml_model.train_and_save(
        x, y, model_path=model_path, return_model=True, log=log,
        n_estimators=args.n_estimators or None, seed=args.seed)

    if booster is None:
        print(f"\n  ❌ 训练失败：{'; '.join(metrics.get('warnings') or ['未知原因'])}\n")
        return 1

    # ---------------------------------------------------------- ③ 五指标
    print(f"\n{BAR}\n  ③ 评估五指标（宝典 7.8）\n{BAR}")
    train_m, val_m = metrics["train"], metrics["val"]
    best_m = metrics["val_best_threshold"]

    def metric_row(name: str, m: Dict[str, Any]) -> List[Any]:
        # 统一 :.4f —— evaluate() 里 round(x, 4) 会把 0.8630 变成 0.863，表格会歪
        return [name, f"{m['threshold']:.2f}", f"{m['auc']:.4f}", f"{m['ks']:.4f}",
                f"{m['precision']:.4f}", f"{m['recall']:.4f}", f"{m['f1']:.4f}",
                f"{m['acc']:.4f}", f"{m['total']}（正 {m['pos']}）"]

    print_table(
        ["数据集", "阈值", "AUC", "KS", "Precision", "Recall", "F1", "Acc", "样本"],
        [metric_row("训练集", train_m), metric_row("验证集", val_m),
         metric_row("验证集@最佳", best_m)],
        "lrrrrrrrr")
    gap = train_m["f1"] - val_m["f1"]
    print(f"\n  过拟合观察  : F1 训练 {train_m['f1']} - 验证 {val_m['f1']} = {gap:+.4f}"
          f"  → {'⚠️ 差距 > 0.25，疑似过拟合' if gap > 0.25 else '✅ 差距可接受'}")
    print(f"  最佳阈值    : {metrics['best_f1_threshold']}（F1={metrics['best_f1']}）"
          f"  ← 线上用这个，不要硬编码 0.5")
    print(f"  树 / 早停   : 保留 {metrics['n_trees']} 棵，best_iteration={metrics['best_iteration']}，"
          f"耗时 {metrics['train_seconds']}s")
    print(f"  样本权重    : scale_pos_weight 理论 {metrics['scale_pos_weight_raw']} → "
          f"实用 {metrics['scale_pos_weight']}（上限 {settings.XGB_MAX_SCALE_POS_WEIGHT}）")

    # ---------------------------------------------------------- ④ baseline 对比
    print(f"\n{BAR}\n  ④ baseline 对比 —— 「比全预测多数类强多少」（宝典 7.7 第 5 件套）\n{BAR}")
    baseline = val_m["baseline_acc"]
    margin = val_m["acc"] - baseline
    print_table(
        ["方案", "说明", "Acc", "F1", "结论"],
        [["baseline", "全部预测为多数类（不用模型）", f"{baseline:.4f}", "0.0000", "—"],
         ["本次模型", f"XGBoost @ 阈值 0.5", f"{val_m['acc']:.4f}", f"{val_m['f1']:.4f}",
          verdict(margin >= settings.XGB_BASELINE_ACC_MARGIN)],
         ["本次模型", f"XGBoost @ 阈值 {best_m['threshold']:.2f}", f"{best_m['acc']:.4f}",
          f"{best_m['f1']:.4f}",
          verdict(best_m["acc"] - baseline >= settings.XGB_BASELINE_ACC_MARGIN)]],
        "llrrc")
    print(f"\n  提升        : {margin:+.4f}（要求 ≥ +{settings.XGB_BASELINE_ACC_MARGIN}）")
    print("  为什么必看  : 正例只有 2% 时「全预测负例」acc=0.98，比模型还高 ——")
    print("                不做这一步对比，acc 0.98 会让人误以为模型很强（FAQ 22）")

    # ---------------------------------------------------------- ⑤ 阈值扫描全表
    x_tr, y_tr, x_val, y_val = _stratified_split(x, y, settings.XGB_TEST_SIZE, args.seed)
    val_prob = [booster.predict_proba(row) for row in x_val]
    print(f"\n{BAR}\n  ⑤ 阈值扫描（{settings.XGB_THRESHOLD_SCAN_START}→"
          f"{settings.XGB_THRESHOLD_SCAN_END}，步长 {settings.XGB_THRESHOLD_SCAN_STEP}）\n{BAR}")
    print_table(["阈值", "TP", "FP", "FN", "Precision", "Recall", "F1", ""],
                threshold_table(y_val, val_prob), "rrrrrrrl")
    print("\n  风控取舍    : 阈值调低 → Recall↑（少漏坏人）但 FP↑（误伤好人客诉）")
    print("                阈值调高 → Precision↑（误伤少）但 Recall↓（漏抓）")

    # ---------------------------------------------------------- ⑥ 假收敛诊断
    print(f"\n{BAR}\n  ⑥ 假收敛诊断（宝典 7.7 四信号）\n{BAR}")
    signals = [
        ["① best_iteration", f"{metrics['best_iteration']}", f"≥ {settings.XGB_MIN_BEST_ITER}",
         verdict(metrics["best_iteration"] >= settings.XGB_MIN_BEST_ITER), "收敛太快=没学到东西"],
        ["② val_auc", f"{val_m['auc']}", f"≥ {settings.XGB_MIN_VAL_AUC}",
         verdict(val_m["auc"] >= settings.XGB_MIN_VAL_AUC), "整体排序能力"],
        ["③ val_f1", f"{max(val_m['f1'], metrics['best_f1'])}", f"≥ {settings.XGB_MIN_VAL_F1}",
         verdict(max(val_m["f1"], metrics["best_f1"]) >= settings.XGB_MIN_VAL_F1), "召回是否够"],
        ["④ acc - baseline", f"{margin:+.4f}", f"≥ +{settings.XGB_BASELINE_ACC_MARGIN}",
         verdict(margin >= settings.XGB_BASELINE_ACC_MARGIN), "是否强于不用模型"],
    ]
    print_table(["信号", "实测", "门槛", "结论", "含义"], signals, "lrrcl")

    if metrics["is_fake_convergence"]:
        print(f"\n  ❌ 判定：假收敛（{len(metrics['fake_convergence_reasons'])} 个信号不合格）")
        for i, reason in enumerate(metrics["fake_convergence_reasons"], 1):
            print(f"     {i}. {reason}")
        print("\n  修复优先级（宝典 7.7 / FAQ 21-22）：")
        print("     1) 样本量与正例比 —— python scripts/gen_risk_data.py 2000 "
              "--target-pos-ratio 0.30 --reset")
        print("     2) 特征信息量 —— 检查上面「零方差 / 高缺失」特征，加大 init_db.py --users")
        print("     3) 再调参 —— XGB_MAX_DEPTH ↑ / XGB_LEARNING_RATE ↓ / XGB_WARMUP_ROUNDS ↑")
        print("     ⚠️ 顺序别倒过来：数据问题调参是调不出来的")
    else:
        print(f"\n  ✅ 判定：正常收敛，模型可用")
    for warn in metrics.get("warnings", []):
        print(f"  ⚠️ {warn}")

    # ---------------------------------------------------------- ⑦ 特征重要性
    print(f"\n{BAR}\n  ⑦ 特征重要性 Top {args.top_k}（宝典 7.9）\n{BAR}")
    importance = ml_model.feature_importance()
    if importance.get("available"):
        gain_map = {d["feature"]: d["value"] for d in importance["gain"]}
        cover_map = {d["feature"]: d["value"] for d in importance["cover"]}
        table = [[i + 1, d["feature"], FEATURE_DIM_OF.get(d["feature"], ""), int(d["value"]),
                  gain_map.get(d["feature"], 0.0), cover_map.get(d["feature"], 0.0)]
                 for i, d in enumerate(importance["weight"][:args.top_k])]
        print_table(["#", "特征", "维度", "weight(分裂次数)", "gain(平均增益)", "cover(样本覆盖)"],
                    table, "rllrrr")
        used = {d["feature"] for d in importance["weight"]}
        unused = [c for c in FEATURE_COLUMNS if c not in used]
        if unused:
            print(f"\n  未被任何树使用的特征（{len(unused)}/{len(FEATURE_COLUMNS)}）：{'、'.join(unused)}")
            print("     不代表没用 —— 可能是与已选特征强相关，或该维度业务数据太单薄")
        print(f"\n  {importance['shap_note']}")
    else:
        print(f"  （不可用：{importance.get('reason')}）")

    # ---------------------------------------------------------- ⑧ 回环校验
    print(f"\n{BAR}\n  ⑧ 存盘回环校验\n{BAR}")
    size_kb = os.path.getsize(model_path) / 1024 if os.path.exists(model_path) else 0
    reloaded = ml_model.Booster.load(model_path)
    rng = random.Random(args.seed)
    picks = rng.sample(range(len(x)), min(20, len(x)))
    max_delta = max(abs(booster.predict_proba(x[i]) - reloaded.predict_proba(x[i])) for i in picks)
    # 容差不能设 1e-9：叶子权重存盘时 round(value, 6) 是刻意的体积优化，
    # 36 棵树累计下来概率会差 ~1e-7 量级。这是设计结果，不是精度 bug。
    proba_tol = 1e-5
    print_table(
        ["校验项", "结果", "结论"],
        [["模型文件", f"{os.path.basename(model_path)}（{size_kb:.1f} KB）",
          verdict(size_kb > 0)],
         ["树数量", f"存 {len(booster.trees)} → 读 {len(reloaded.trees)}",
          verdict(len(booster.trees) == len(reloaded.trees))],
         ["特征名顺序", f"{len(reloaded.feature_columns)} 列",
          verdict(reloaded.feature_columns == list(FEATURE_COLUMNS))],
         ["最佳阈值", f"{reloaded.best_f1_threshold}",
          verdict(abs(reloaded.best_f1_threshold - booster.best_f1_threshold) < 1e-9)],
         ["概率一致性", f"抽 {len(picks)} 条，最大误差 {max_delta:.2e}（容差 {proba_tol:.0e}）",
          verdict(max_delta < proba_tol)]],
        "llc")
    print(f"\n  说明        : 叶子权重存盘 round 6 位小数 → 概率有 ~1e-7 量级误差，属预期；"
          f"超过 {proba_tol:.0e} 才说明序列化有问题")

    # ---------------------------------------------------------- ⑨ 影响与下一步
    print(f"\n{BAR}\n  ⑨ 训练后的线上影响\n{BAR}")
    alpha, beta = settings.ML_WEIGHT_RULE, settings.ML_WEIGHT_XGB
    if args.dry_run:
        print("  🧪 dry-run 模式：临时模型已删除，线上仍是「降级纯规则 α=1.0 / β=0.0」")
    else:
        print(f"  融合权重     : 降级纯规则（α=1.0 / β=0.0） → 双轨融合（α={alpha} / β={beta}）")
        print(f"  影响         : 同一笔请求的 final_score 会变化 —— 规则分被 α 缩放，"
              f"再叠加 β× 模型分")
        print(f"  不变的部分   : 一票否决（risk_level=极高 → final=max(final, 90)）永远优先于融合")
        print(f"  推理阈值     : 线上判正建议用 best_f1_threshold={metrics['best_f1_threshold']}，"
              f"而非 0.5")

    print(f"\n{BAR}\n  下一步\n{BAR}")
    if args.dry_run:
        print("  正式训练并写入线上模型：")
        print("     python scripts/train_xgb_model.py")
    elif metrics["is_fake_convergence"]:
        print("  先按上面「修复优先级」补数据，再重训：")
        print("     python scripts/gen_risk_data.py 2000 --target-pos-ratio 0.30 --reset")
        print("     python scripts/train_xgb_model.py")
    else:
        print("  启动服务，模型会在 import 时自动懒加载：")
        print("     python _run.py")
        print("  验证模型状态：")
        print("     curl http://127.0.0.1:8000/api/model/status")
        print("  跑一笔风控检查，观察双轨融合：")
        print("     curl -X POST http://127.0.0.1:8000/api/risk/check -H \"Content-Type: application/json\" \\")
        print("          -d '{\"event_type\":\"考试\",\"source_id\":\"EXAM10130002\",\"user_id\":\"1013\"}'")

    if dry_path and os.path.exists(dry_path):
        os.remove(dry_path)
        ml_model.unload_model()
    print()
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        pool.dispose()
    sys.exit(code)

# -*- coding: utf-8 -*-
r"""生成风控训练数据（宝典第 7 章 7.11 label 三来源 / 第 17 章 练习 3）

    python scripts/gen_risk_data.py 200
    python scripts/gen_risk_data.py 1500 --target-pos-ratio 0.30
    python scripts/gen_risk_data.py 1500 --target-pos-ratio 0.30 --reset

## 它到底做了什么？

**不是凭空造特征**，而是把业务数据真实地喂进 7 步流水线：

    (user_id, source_id) → process_event() → 25 维特征快照 + risk_assessment(label)

这样训练集里的每一行都和线上推理路径**完全同源** —— 没有训练/线上特征不一致
（feature skew）这个经典大坑。代价是慢一点（每条要走一遍完整流水线）。

## label 三来源（宝典 7.11）

| 方式 | 说明 | 本脚本 |
|------|------|--------|
| 人工标注 | 风控员在案件工作台判「已拒绝」→ label=1 | 结案时写入（case.py）|
| 投诉反推 | `logistics_complaints_record.is_verified=1` → label=1 | `--label-mode complaint` |
| 规则反推 | `final_score >= XGB_LABEL_SCORE_THRESHOLD(80)` → label=1 | **默认**（教学用）|

## --target-pos-ratio 为什么必须有？（宝典 FAQ 21 / 22）

自然采样下正例只有 2% 左右，训练出来会：
    · scale_pos_weight 理论值飙到 50 → 被截断到 10 → 权重补偿失效
    · 训练集 F1=0.73 但验证集 F1=0.09 → **固定阈值错位**
    · acc=0.98 看着很美，其实还不如「全预测负例」的 baseline

`--target-pos-ratio 0.30` 用**自适应采样**把正例拉到 30%：
维护两个用户池（hot=高危画像 / cold=普通），每生成一条就看当前正例比例，
低于目标就从 hot 抽，高于目标就从 cold 抽。因为 label 是流水线跑完才知道的，
这个反馈环会自动收敛到目标附近。
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import settings                              # noqa: E402
from app.database import pool, session_scope                  # noqa: E402
from app.framework import HTTPError                           # noqa: E402
from app.service import event as event_service                # noqa: E402

BAR = "=" * 76

# 高危画像候选打分 SQL：把「退款率 / 近 7 天单量 / 地址数 / 均单价」拼成一个粗排分。
# 只用于**采样倾向**，不参与任何风控决策 —— 决策永远由 30 条规则 + 模型说话。
_HOT_SQL = """
SELECT o.user_id,
       COUNT(DISTINCT o.order_id)                                  AS orders,
       AVG(o.total_amount)                                         AS avg_amount,
       (SELECT COUNT(1) FROM refund_record r WHERE r.user_id = o.user_id)     AS refunds,
       (SELECT COUNT(1) FROM postsale p WHERE p.user_id = o.user_id)          AS postsales,
       (SELECT COUNT(1) FROM user_address a
         WHERE a.user_id = o.user_id AND a.deleted_at IS NULL)                AS addresses,
       (SELECT COUNT(1) FROM order_info o2
         WHERE o2.user_id = o.user_id AND o2.deleted_at IS NULL
           AND o2.create_time >= datetime('now', '-7 day'))                   AS orders_7d
FROM order_info o
WHERE o.deleted_at IS NULL
GROUP BY o.user_id
HAVING orders > 0
"""


def _risk_proxy(row: Dict[str, Any]) -> float:
    """粗排分：越高越可能被 30 条规则判为高危。"""
    orders = max(int(row["orders"] or 0), 1)
    refund_rate = float(row["refunds"] or 0) / orders
    postsale_rate = float(row["postsales"] or 0) / orders
    avg_amount = float(row["avg_amount"] or 0)
    return (refund_rate * 40 + postsale_rate * 25
            + min(float(row["addresses"] or 0) / 10.0, 1.0) * 15
            + min(float(row["orders_7d"] or 0) / 20.0, 1.0) * 15
            + min(avg_amount / 5000.0, 1.0) * 15)


def _load_pools(db: Any, hot_quantile: float = 0.4) -> Tuple[List[Dict], List[Dict]]:
    """把用户按粗排分切成 hot / cold 两个池。"""
    rows = db.fetch_all(_HOT_SQL)
    if not rows:
        raise RuntimeError("业务表没有订单数据。先跑：python scripts/init_db.py --with-business")
    for r in rows:
        r["_proxy"] = _risk_proxy(r)
    rows.sort(key=lambda r: -r["_proxy"])
    cut = max(1, int(len(rows) * hot_quantile))
    return rows[:cut], rows[cut:] or rows[:cut]


def _sources_for(db: Any, user_id: str, event_type: str) -> List[str]:
    """按 event_type 取该用户可用的 source_id（对齐 validator 的字典驱动）。"""
    if event_type in ("考试", "作业"):
        sql = ("SELECT order_id AS sid FROM order_info "
               "WHERE user_id = ? AND deleted_at IS NULL")
        if event_type == "作业":
            sql += " AND pay_time IS NOT NULL"
        return [r["sid"] for r in db.fetch_all(sql + " LIMIT 200", (user_id,))]
    if event_type == "选课":
        return [r["sid"] for r in db.fetch_all(
            "SELECT postsale_id AS sid FROM postsale WHERE user_id = ? LIMIT 200", (user_id,))]
    return [str(r["sid"]) for r in db.fetch_all(
        "SELECT record_id AS sid FROM logistics_complaints_record WHERE user_id = ? LIMIT 200",
        (user_id,))]


def _order_of(db: Any, event_type: str, source_id: str) -> Optional[str]:
    """选课/成绩申诉事件需要补 order_id，才能算出 8 维学习行为特征。"""
    if event_type in ("考试", "作业"):
        return source_id
    if event_type == "选课":
        row = db.fetch_one("SELECT order_id FROM postsale WHERE postsale_id = ?", (source_id,))
    else:
        row = db.fetch_one("SELECT order_id FROM logistics_complaints_record WHERE record_id = ?",
                           (source_id,))
    return (row or {}).get("order_id") or None


def _complaint_label(db: Any, user_id: str) -> Optional[int]:
    """投诉反推：该用户有查实投诉 → label=1（宝典 7.11 方式 2）。"""
    verified = db.scalar(
        "SELECT COUNT(1) FROM logistics_complaints_record WHERE user_id = ? AND is_verified = 1",
        (user_id,))
    total = db.scalar(
        "SELECT COUNT(1) FROM logistics_complaints_record WHERE user_id = ?", (user_id,))
    if not total:
        return None
    return 1 if int(verified) > 0 else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="生成风控训练数据（跑真实 7 步流水线，产出 25 维特征 + label）")
    p.add_argument("count", nargs="?", type=int, default=200,
                   help="生成事件条数（默认 200；建议 ≥ %d 以满足 XGB_MIN_SAMPLES）"
                        % settings.XGB_MIN_SAMPLES)
    p.add_argument("--target-pos-ratio", type=float, default=0.0,
                   help="目标正例比例（如 0.30）。0 = 自然采样（FAQ 21/22 强烈建议设 0.30）")
    p.add_argument("--event-types", default="考试,作业,选课,成绩申诉",
                   help="参与生成的事件类型，逗号分隔")
    p.add_argument("--label-mode", choices=["rule", "complaint"], default="rule",
                   help="label 来源：rule=规则反推（默认）| complaint=投诉反推")
    p.add_argument("--reset", action="store_true",
                   help="先清空 risk_event / risk_feature / risk_assessment / risk_case / 画像")
    p.add_argument("--seed", type=int, default=42, help="随机种子")
    p.add_argument("--operator", default="data_generator", help="审计日志中的操作人")
    return p


def reset_risk_data(db: Any) -> Dict[str, int]:
    removed: Dict[str, int] = {}
    for table in ("risk_feature", "risk_case", "risk_assessment", "risk_event",
                  "risk_user_profile"):
        cur = db.execute(f'DELETE FROM "{table}"')
        removed[table] = max(cur.rowcount, 0)
    return removed


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rnd = random.Random(args.seed)
    event_types = [t.strip() for t in args.event_types.split(",") if t.strip()]

    print(f"\n{BAR}\n  生成风控训练数据 · 目标 {args.count} 条\n{BAR}")
    print(f"  事件类型   : {', '.join(event_types)}")
    print(f"  label 来源 : {'规则反推（final_score >= %d）' % settings.XGB_LABEL_SCORE_THRESHOLD if args.label_mode == 'rule' else '投诉反推（is_verified=1）'}")
    print(f"  目标正例比 : {'自然采样' if args.target_pos_ratio <= 0 else f'{args.target_pos_ratio:.0%}（自适应采样）'}")
    print(f"  随机种子   : {args.seed}")

    if args.reset:
        with session_scope() as db:
            removed = reset_risk_data(db)
        print(f"  已清空风控表: " + " · ".join(f"{k} {v}" for k, v in removed.items()))

    with session_scope() as db:
        hot, cold = _load_pools(db)
    print(f"  用户池     : hot {len(hot)} 人（高危画像） / cold {len(cold)} 人")

    stats = {"ok": 0, "pos": 0, "neg": 0, "skip": 0, "error": 0}
    decisions: Dict[str, int] = {}
    levels: Dict[str, int] = {}
    veto_count = 0
    started = time.time()
    attempts = 0
    max_attempts = args.count * 6

    while stats["ok"] < args.count and attempts < max_attempts:
        attempts += 1
        # ---- 自适应采样：按当前正例比例决定从哪个池抽人
        if args.target_pos_ratio > 0 and stats["ok"] > 0:
            current = stats["pos"] / stats["ok"]
            pool_pick = hot if current < args.target_pos_ratio else cold
        elif args.target_pos_ratio > 0:
            pool_pick = hot
        else:
            pool_pick = hot if rnd.random() < 0.4 else cold

        candidate = rnd.choice(pool_pick)
        user_id = str(candidate["user_id"])
        event_type = rnd.choice(event_types)

        try:
            with session_scope() as db:
                sources = _sources_for(db, user_id, event_type)
                if not sources:
                    stats["skip"] += 1
                    continue
                source_id = rnd.choice(sources)
                order_id = _order_of(db, event_type, source_id)

                payload = {"event_type": event_type, "source_id": source_id,
                           "user_id": user_id, "order_id": order_id,
                           "client_ip": f"10.{rnd.randint(0, 255)}.{rnd.randint(0, 255)}.{rnd.randint(1, 254)}",
                           "device_id": f"DEV_{user_id}_1"}
                result = event_service.process_event(db, payload, operator=args.operator)

                # ---- 投诉反推模式：覆写 label
                if args.label_mode == "complaint":
                    label = _complaint_label(db, user_id)
                    if label is not None:
                        db.update("risk_assessment",
                                  {"label": label, "label_source": "投诉反推"},
                                  "assessment_id = ?", (result["assessment_id"],))
                        result["label"] = label
        except HTTPError as exc:
            # 400/403/404 都是**校验层正常工作**的表现（例如支付事件但订单未支付）
            stats["skip"] += 1
            continue
        except Exception as exc:  # noqa: BLE001
            stats["error"] += 1
            if stats["error"] <= 5:
                print(f"  ⚠️ 生成失败（{type(exc).__name__}）: {exc}")
            continue

        label = int(result.get("label", 0) or 0)
        stats["ok"] += 1
        stats["pos" if label == 1 else "neg"] += 1
        decisions[result["decision"]] = decisions.get(result["decision"], 0) + 1
        levels[result["risk_level"]] = levels.get(result["risk_level"], 0) + 1
        veto_count += 1 if result.get("is_veto") else 0

        if stats["ok"] % 100 == 0 or stats["ok"] == args.count:
            ratio = stats["pos"] / stats["ok"]
            print(f"  进度 {stats['ok']:>5}/{args.count}  正例 {stats['pos']:>4}"
                  f"（{ratio:.1%}）  跳过 {stats['skip']}  耗时 {time.time() - started:.1f}s")

    elapsed = time.time() - started
    print(f"\n{BAR}\n  生成结果\n{BAR}")
    print(f"  成功       : {stats['ok']} 条（尝试 {attempts} 次，耗时 {elapsed:.1f}s，"
          f"{stats['ok'] / elapsed:.1f} 条/秒）")
    print(f"  正 / 负    : {stats['pos']} / {stats['neg']}"
          + (f"  → 正例比 {stats['pos'] / stats['ok']:.1%}" if stats["ok"] else ""))
    print(f"  跳过 / 错误: {stats['skip']} / {stats['error']}（跳过多为校验层正常拦截）")
    print(f"  决策分布   : " + " · ".join(f"{k} {v}" for k, v in sorted(decisions.items(),
                                                                       key=lambda kv: -kv[1])))
    print(f"  等级分布   : " + " · ".join(f"{k} {v}" for k, v in sorted(levels.items(),
                                                                       key=lambda kv: -kv[1])))
    print(f"  一票否决   : {veto_count} 条")

    with session_scope() as db:
        total = int(db.scalar("SELECT COUNT(1) FROM risk_assessment WHERE label IS NOT NULL"))
        pos = int(db.scalar("SELECT COUNT(1) FROM risk_assessment WHERE label = 1"))
        feats = int(db.scalar("SELECT COUNT(1) FROM risk_feature"))
        cases = int(db.scalar("SELECT COUNT(1) FROM risk_case WHERE deleted_at IS NULL"))
    print(f"\n  【累计训练集】")
    print(f"  已标注样本 : {total} 条（正例 {pos}，占比 {pos / total:.1%}）" if total
          else "  已标注样本 : 0 条")
    print(f"  特征快照   : {feats} 行（{total} × 25 维）")
    print(f"  风控案件   : {cases} 个")

    ready = total >= settings.XGB_MIN_SAMPLES and 0 < pos < total
    print(f"\n{BAR}\n  下一步\n{BAR}")
    if ready:
        print(f"  ✅ 样本量 {total} ≥ XGB_MIN_SAMPLES({settings.XGB_MIN_SAMPLES})，可以训练：")
        print("     python scripts/train_xgb_model.py")
    else:
        need = max(settings.XGB_MIN_SAMPLES - total, 0)
        print(f"  ⚠️ 样本量 {total} < XGB_MIN_SAMPLES({settings.XGB_MIN_SAMPLES} = 25 维 × 50)，"
              f"还差 {need} 条（宝典 FAQ 5）")
        print(f"     python scripts/gen_risk_data.py {max(need, 200)} --target-pos-ratio 0.30")
    if total and not (0.15 <= pos / total <= 0.5):
        print(f"  ⚠️ 正例比 {pos / total:.1%} 偏离健康区间 15%~50%（宝典 FAQ 22）：")
        print("     python scripts/gen_risk_data.py 1500 --target-pos-ratio 0.30 --reset")
    print()
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        pool.dispose()
    sys.exit(code)

"""
银行信贷风控 - 批量风控事件生成脚本 (Task 3 训练数据准备)

把业务表里的真实记录灌进 process_event, 生成 risk_event / risk_feature /
risk_assessment / risk_case, 供 XGBoost 训练和演示使用.

事件映射 (业务记录 -> 风控事件):
  loan_application   -> 贷款申请 (source_id=application_id)
  loan_contract      -> 放款     (source_id=contract_id)
  repayment_record   -> 还款     (source_id=record_id)
  transaction        -> 转账     (source_id=txn_id)
  login_log          -> 登录     (source_id=login_id)

用法:
  python scripts/gen_bank_risk_events.py                # 全量事件 (默认)
  python scripts/gen_bank_risk_events.py --event-type 贷款申请   # 只跑某类事件
  python scripts/gen_bank_risk_events.py --limit 500    # 随机抽 500 条
  python scripts/gen_bank_risk_events.py --good-rate 0.35  # 低风险用户事件只抽 35% (提升正例比)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter
from pathlib import Path

import pymysql
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from app.config import BUSINESS_EVENT_TYPES, settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gen_bank_risk_events")

# 一致性约束: 本脚本支持的事件类型必须与 config.BUSINESS_EVENT_TYPES 完全一致
_FETCHED_EVENT_TYPES = {"贷款申请", "放款", "还款", "转账", "登录"}
assert _FETCHED_EVENT_TYPES == set(BUSINESS_EVENT_TYPES), (
    "gen_bank_risk_events 支持的事件类型与 config.BUSINESS_EVENT_TYPES 不一致"
)


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
    )


def _fetch_events(conn, event_type: str | None = None) -> list[dict]:
    """从业务表拉取待处理事件."""
    events: list[dict] = []
    with conn.cursor() as cur:
        if event_type in (None, "贷款申请"):
            cur.execute("""
                SELECT application_id, user_id, apply_amount, purpose, device_id, ip, apply_time
                FROM loan_application
            """)
            for row in cur.fetchall():
                events.append({
                    "event_type": "贷款申请", "source_id": row[0], "user_id": row[1],
                    "event_data": {"apply_amount": float(row[2]), "purpose": row[3],
                                   "device_id": row[4], "ip": row[5]},
                })
        if event_type in (None, "放款"):
            cur.execute("""
                SELECT contract_id, user_id, loan_amount, disbursement_date
                FROM loan_contract
            """)
            for row in cur.fetchall():
                events.append({
                    "event_type": "放款", "source_id": row[0], "user_id": row[1],
                    "event_data": {"loan_amount": float(row[2]),
                                   "disbursement_date": str(row[3])},
                })
        if event_type in (None, "还款"):
            cur.execute("""
                SELECT record_id, user_id, repay_amount, repay_time
                FROM repayment_record
            """)
            for row in cur.fetchall():
                events.append({
                    "event_type": "还款", "source_id": row[0], "user_id": row[1],
                    "event_data": {"repay_amount": float(row[2])},
                })
        if event_type in (None, "转账"):
            cur.execute("""
                SELECT txn_id, user_id, amount, txn_time
                FROM transaction
            """)
            for row in cur.fetchall():
                events.append({
                    "event_type": "转账", "source_id": row[0], "user_id": row[1],
                    "event_data": {"amount": float(row[2])},
                })
        if event_type in (None, "登录"):
            cur.execute("""
                SELECT login_id, user_id, login_time, device_id, ip
                FROM login_log
            """)
            for row in cur.fetchall():
                events.append({
                    "event_type": "登录", "source_id": row[0], "user_id": row[1],
                    "event_data": {"device_id": row[3], "ip": row[4]},
                })
    return events


def _fetch_risk_users(conn) -> set[str]:
    """高风险用户集合 (收入虚高/逾期/关联密集/低信用分/新开户), 用于 --risk-repeats"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT user_id FROM (
                SELECT user_id FROM user_info
                    WHERE credit_score < 620 OR account_age_days <= 90
                       OR (verified_income > 0 AND monthly_income >= verified_income * 1.5)
                UNION
                SELECT user_id FROM repayment_plan WHERE status = '逾期'
                UNION
                SELECT user_id FROM user_relation WHERE is_active = 1
                UNION
                SELECT user_id FROM income_verify
                    WHERE verified_monthly_income > 0
                      AND declared_monthly_income >= verified_monthly_income * 1.5
            ) t
        """)
        return {r[0] for r in cur.fetchall()}


async def _run_one(
    sem: asyncio.Semaphore, event: dict, failures: list[dict],
) -> str:
    async with sem:
        async with AsyncSessionLocal() as session:
            try:
                request = RiskCheckRequest(
                    event_type=event["event_type"],
                    source_id=event["source_id"],
                    user_id=event["user_id"],
                    event_data=event["event_data"],
                )
                resp = await process_event(session, request)
                if resp.blocked_by:
                    return "黑名单拦截"
                return resp.decision
            except Exception as e:  # noqa: BLE001
                await session.rollback()
                failures.append({
                    "event_type": event["event_type"],
                    "source_id": event["source_id"],
                    "user_id": event["user_id"],
                    "error": f"{type(e).__name__}: {str(e)[:150]}",
                })
                logger.warning("事件处理失败: %s %s %s -> %s",
                               event["event_type"], event["source_id"], event["user_id"], e)
                return "失败"


async def main() -> int:
    parser = argparse.ArgumentParser(description="银行风控批量事件生成")
    parser.add_argument("--event-type", default=None, choices=BUSINESS_EVENT_TYPES,
                        help=f"只跑某类事件: {'/'.join(BUSINESS_EVENT_TYPES)}")
    parser.add_argument("--limit", type=int, default=0, help="随机抽 N 条 (0=全量)")
    parser.add_argument("--risk-repeats", type=int, default=1,
                        help="高风险用户事件重复次数 (默认 1, 调 2-3 提升正例比)")
    parser.add_argument("--good-rate", type=float, default=1.0,
                        help="低风险用户事件采样率 (默认 1.0; 训练可设 0.3-0.5 提升正例比)")
    parser.add_argument("--concurrency", type=int, default=8, help="并发数 (默认 8)")
    parser.add_argument("--no-clean", action="store_true", help="不清空 risk_* 表 (默认先清空)")
    parser.add_argument("--resume", action="store_true",
                        help="断点续跑: 跳过 risk_event 里已存在的 (event_type, source_id)")
    args = parser.parse_args()

    if args.resume and not args.no_clean:
        print("注意: --resume 需要保留已有数据, 自动启用 --no-clean (不清空 risk_* 表)")
        args.no_clean = True

    conn = _connect()
    try:
        events = _fetch_events(conn, args.event_type)
        if args.resume:
            with conn.cursor() as cur:
                cur.execute("SELECT event_type, event_source_id FROM risk_event")
                existing = {(r[0], r[1]) for r in cur.fetchall()}
            before = len(events)
            events = [ev for ev in events if (ev["event_type"], ev["source_id"]) not in existing]
            print(f"  --resume: 跳过已存在事件 {before - len(events)} 条, 待处理 {len(events)} 条")
        if args.limit > 0:
            import random
            random.Random(42).shuffle(events)
            events = events[: args.limit]

        risk_users = _fetch_risk_users(conn) if (args.risk_repeats > 1 or args.good_rate < 1.0) else set()
        if args.good_rate < 1.0:
            import random
            rng = random.Random(42)
            kept = [ev for ev in events if ev["user_id"] in risk_users or rng.random() < args.good_rate]
            print(f"  低风险用户采样率 {args.good_rate}: {len(events)} -> {len(kept)} 条")
            events = kept
        if args.risk_repeats > 1:
            expanded: list[dict] = []
            for ev in events:
                times = args.risk_repeats if ev["user_id"] in risk_users else 1
                expanded.extend([ev] * times)
            events = expanded

        print(f"待处理事件: {len(events)} 条 (event_type={args.event_type or '全部'}, "
              f"good_rate={args.good_rate}, "
              f"risk_repeats={args.risk_repeats}, 高风险用户={len(risk_users)})")
    finally:
        conn.close()

    # 清空风控表 (保证可重复运行; 业务表和规则不动)
    if not args.no_clean:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            for table in ["risk_alert", "risk_action_log", "risk_user_profile", "risk_case",
                          "risk_assessment", "risk_feature", "risk_event"]:
                await session.execute(text(f"TRUNCATE TABLE `{table}`"))
            await session.commit()
        print("已清空 risk_event/feature/assessment/case/profile/action_log/alert")

    # 按用户分组: 同一用户的多个事件串行处理, 不同用户并行
    # 原因: risk_user_profile 主键是 user_id, 同用户并发会撞 Duplicate entry
    by_user: dict[str, list[dict]] = {}
    for ev in events:
        by_user.setdefault(ev["user_id"], []).append(ev)

    sem = asyncio.Semaphore(args.concurrency)
    counter: Counter = Counter()
    failures: list[dict] = []
    done = 0
    total = len(events)

    async def worker_user(user_events: list[dict]) -> None:
        nonlocal done
        for ev in user_events:
            decision = await _run_one(sem, ev, failures)
            counter[decision] += 1
            done += 1
            if done % 300 == 0 or done == total:
                print(f"  进度 {done}/{total}, 当前分布: {dict(counter)}")

    await asyncio.gather(*(worker_user(evs) for evs in by_user.values()))

    print("\n" + "=" * 60)
    print("事件生成完成")
    print("=" * 60)
    for k, v in counter.most_common():
        print(f"  {k:<12} {v:>6} 条")
    n_total = sum(counter.values())
    n_pos = counter.get("人工审核", 0) + counter.get("拒绝", 0)
    if n_total:
        print("-" * 60)
        print(f"  正例(人工审核/拒绝)占比: {100 * n_pos / n_total:.1f}%")
    if failures:
        print("-" * 60)
        print(f"  失败事件 {len(failures)} 条, TOP 10 明细:")
        from collections import defaultdict
        groups: dict[str, list[dict]] = defaultdict(list)
        for f in failures:
            groups[f["error"]].append(f)
        for i, (err, items) in enumerate(sorted(groups.items(), key=lambda x: -len(x[1]))[:10], 1):
            sample = items[0]
            print(f"    {i:>2}. [{err}] x{len(items)} 例: {sample['event_type']} {sample['source_id']} {sample['user_id']}")

    # 训练数据严格化: 生成阶段模型未加载, ml_score=0.0 是占位值,
    # 重置为 NULL 让 train_xgb_model.py 能正常取数 (训练只用无 ML 痕迹的数据)
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        await session.execute(text(
            "UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL"
        ))
        await session.commit()
    print("已重置 risk_assessment.ml_score=NULL (训练数据纯净)")
    print("下一步: python scripts/train_xgb_model.py")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""从真实银行 source 运行统一 pipeline，生成可训练的评估与 25 维快照。"""

import argparse
import asyncio
import random
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select, update

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine import ml_model  # noqa: E402
from app.models import (  # noqa: E402
    BankCard,
    LoanApplication,
    LoginLog,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
    Transaction,
)
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402
from scripts._console import (  # noqa: E402
    banner,
    ok,
    progress,
    silence_loggers,
    summary,
    warn,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


async def _load_sources(db) -> list[tuple[str, str, str, datetime]]:
    """返回 ``(event_type, source_id, user_id, event_time)``，不使用 ID 前缀猜类型。"""
    sources: list[tuple[str, str, str, datetime]] = []
    sources.extend(
        ("登录", source_id, user_id, event_time)
        for source_id, user_id, event_time in (
            await db.execute(
                select(LoginLog.login_id, LoginLog.user_id, LoginLog.login_at)
            )
        ).all()
    )
    sources.extend(
        ("贷款申请", source_id, user_id, event_time)
        for source_id, user_id, event_time in (
            await db.execute(
                select(LoanApplication.loan_id, LoanApplication.user_id, LoanApplication.apply_at)
            )
        ).all()
    )
    sources.extend(
        ("绑卡", source_id, user_id, event_time)
        for source_id, user_id, event_time in (
            await db.execute(
                select(BankCard.card_id, BankCard.user_id, BankCard.bind_at)
            )
        ).all()
    )
    sources.extend(
        ("转账", source_id, user_id, event_time)
        for source_id, user_id, event_time in (
            await db.execute(
                select(Transaction.txn_id, BankCard.user_id, Transaction.txn_at).join(
                    BankCard, Transaction.from_card == BankCard.card_id
                )
            )
        ).all()
    )
    return sources


async def _clean_training_records(db) -> None:
    """只清理专用教学库中的衍生风控记录，不触碰业务 source 或规则。"""
    for model in (RiskCase, RiskFeature, RiskAssessment, RiskEvent, RiskUserProfile):
        await db.execute(delete(model))
    await db.commit()


async def gen_train_dataset(
    count: int = 2000,
    seed: int = 20260812,
    *,
    clean: bool = False,
    spread_days: int | None = None,
    live: bool = False,
) -> dict:
    """每个 source 最多使用一次；标签只来自规则/决策结果。

    spread_days: 生成的评估 create_time 确定性铺到最近 N 天（含今天）。
    live:        create_time 一律为当前时间（今日数据，兼容 one_command 第 6 步）。
    两者都未设置时：create_time 取 source 业务时间（真实时间跨度，供训练使用）。
    """
    if count < 50:
        raise ValueError("训练样本数至少为 50")
    rng = random.Random(seed)
    now = datetime.now()
    async with AsyncSessionLocal() as db:
        if clean:
            await _clean_training_records(db)
        sources = await _load_sources(db)
        rng.shuffle(sources)
        if count > len(sources):
            raise ValueError(
                f"可用唯一 source 仅 {len(sources)} 条，无法生成 {count} 条；"
                "请先运行 gen_business_data.py 扩充四类业务数据"
            )

        decisions: Counter[str] = Counter()
        events: Counter[str] = Counter()
        failures: list[str] = []
        blacklist_hits = 0
        time_values: list[datetime] = []
        for index, (event_type, source_id, user_id, source_time) in enumerate(
            sources[:count], 1
        ):
            try:
                if live:
                    create_time = now
                elif spread_days:
                    create_time = now - timedelta(
                        days=rng.randint(0, spread_days - 1),
                        seconds=rng.randint(0, 86399),
                    )
                else:
                    create_time = source_time or now

                # 禁用 ML 推理，确保标签只来自规则/决策；否则已加载的旧模型会参与
                # 决策融合，置空 ml_score 也不能纠正 decision，导致重训标签自举污染。
                # 同时静音 app.service.event 的"撞黑名单"warning，结尾统一汇总。
                with ml_model.disabled(), silence_loggers(["app.service.event"]):
                    response = await process_event(
                        db,
                        RiskCheckRequest(
                            event_type=event_type,
                            source_id=source_id,
                            user_id=user_id,
                            create_time=create_time,
                            event_data={"dataset_seed": seed, "sample_index": index},
                        ),
                    )
                decisions[response.decision] += 1
                events[event_type] += 1
                if response.assessment_id == "blacklist_reject":
                    blacklist_hits += 1
                else:
                    # 训练样本明确标记为“尚未经过模型回填”，避免旧模型污染标签集。
                    await db.execute(
                        update(RiskAssessment)
                        .where(RiskAssessment.assessment_id == response.assessment_id)
                        .values(ml_score=None, ml_decision=None)
                    )
                    await db.commit()
                    time_values.append(response.create_time)
                progress(index, count)
            except Exception as exc:  # 单条失败留证，其余 source 继续
                await db.rollback()
                failures.append(f"{event_type}/{source_id}: {exc}")

        total = sum(decisions.values())
        positive = decisions["人工审核"] + decisions["拒绝"]
        return {
            "seed": seed,
            "requested": count,
            "generated": total,
            "positive": positive,
            "positive_ratio": round(positive / total, 4) if total else 0.0,
            "decisions": dict(decisions),
            "events": dict(events),
            "blacklist_hits": blacklist_hits,
            "time_min": min(time_values).isoformat() if time_values else None,
            "time_max": max(time_values).isoformat() if time_values else None,
            "failures": failures,
        }


def _print_result(result: dict) -> None:
    """以 init_db.py 风格打印生成结果。"""
    print()
    summary(
        [
            ("seed", result["seed"]),
            ("请求样本", result["requested"]),
            ("成功生成", result["generated"]),
            (
                "正例 (拒绝+人工审核)",
                f"{result['positive']} ({result['positive_ratio']:.1%})",
            ),
            ("教学黑卡拦截 (不入库)", result["blacklist_hits"]),
        ],
        title="生成结果",
    )
    if result["time_min"]:
        summary([("时间范围", f"{result['time_min']} ~ {result['time_max']}")])
    summary(
        [(k, v) for k, v in result["decisions"].items()],
        title="决策分布",
    )
    summary(
        [(k, v) for k, v in result["events"].items()],
        title="事件分布",
    )


async def _runner() -> int:
    parser = argparse.ArgumentParser(description="运行银行 pipeline 生成真实训练数据")
    parser.add_argument("--count", type=int, default=2000, help="唯一 source 样本数")
    parser.add_argument("--seed", type=int, default=20260812, help="固定随机 seed")
    parser.add_argument("--clean", action="store_true", help="先清理衍生风控记录")
    parser.add_argument("--reset", action="store_true", help="兼容别名，等同 --clean")
    parser.add_argument(
        "--spread-days", type=int, default=None, help="把 create_time 铺到最近 N 天"
    )
    parser.add_argument("--live", action="store_true", help="create_time 一律当前时间")
    args = parser.parse_args()
    try:
        banner(
            "银行风控训练数据生成",
            f"seed={args.seed} | 请求 {args.count} 条 | 真实 pipeline (纯规则, 禁 ML)",
        )
        result = await gen_train_dataset(
            count=args.count,
            seed=args.seed,
            clean=args.clean or args.reset,
            spread_days=args.spread_days,
            live=args.live,
        )
        _print_result(result)
        if result["failures"]:
            warn("失败样本（前 10 条）:")
            for item in result["failures"][:10]:
                print(f"- {item}")
        if result["blacklist_hits"]:
            ok(
                f"教学黑卡前置拦截 {result['blacklist_hits']} 条"
                "（黑名单前置、不入库，符合教学演示预期）"
            )
        return 0 if result["generated"] >= 50 else 1
    finally:
        # 在事件循环关闭前释放全局引擎连接池，避免解释器退出时
        # aiomysql 在已关闭的 loop 上 close() 报 "Event loop is closed"
        await async_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_runner()))

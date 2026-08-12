"""为教育风控仪表盘生成带日期的真实评估数据。

脚本从现有教育业务表随机抽取课程报名、退费、直播打赏和学习行为，
逐条调用正式风控流水线，再将事件、特征、评估和案件回写到目标日期。
脚本会先按正式风控流水线的计算逻辑，将候选业务分为“正常、人工审核、
拒绝”三类，再按每日配额生成。默认每天 10 条包含 7 条正常、2 条人工
审核和 1 条拒绝，因此案件管理中会同时出现“待审核”和“已拒绝”。

示例：
    python scripts/gen_education_risk_data.py
    python scripts/gen_education_risk_data.py --days 7 --per-day 10
    python scripts/gen_education_risk_data.py --start 2026-08-05 --end 2026-08-11 --per-day 10
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.education_compat import to_core_event  # noqa: E402
from app.engine.decision import (  # noqa: E402
    _build_context,
    _calculate_decision,
    _compute_features,
    _enrich_receive_id,
    _evaluate_rules,
)
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import _check_all_blacklists, _enrich_request, process_event  # noqa: E402


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


@dataclass(frozen=True)
class EventCandidate:
    event_type: str
    source_id: str
    user_id: str
    device_id: str | None


DECISION_BUCKET = {
    "通过": "normal",
    "标记": "normal",
    "人工审核": "review",
    "拒绝": "reject",
}


def calculate_daily_quotas(
    per_day: int,
    review_ratio: float = 0.20,
    reject_ratio: float = 0.10,
) -> dict[str, int]:
    """把每日总数换算为正常、人工审核和拒绝三类配额。"""
    if per_day < 1:
        raise ValueError("--per-day 必须大于等于 1")
    if not 0 <= review_ratio <= 1:
        raise ValueError("--review-ratio 必须在 0 到 1 之间")
    if not 0 <= reject_ratio <= 1:
        raise ValueError("--positive-ratio 必须在 0 到 1 之间")
    if review_ratio + reject_ratio > 1:
        raise ValueError("--review-ratio 与 --positive-ratio 之和不能超过 1")

    review = round(per_day * review_ratio)
    reject = round(per_day * reject_ratio)
    return {
        "normal": per_day - review - reject,
        "review": review,
        "reject": reject,
    }


def build_date_range(days: int, start: str | None, end: str | None) -> list[date]:
    if days < 1:
        raise ValueError("--days 必须大于等于 1")
    end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else datetime.now().date()
    start_date = (
        datetime.strptime(start, "%Y-%m-%d").date()
        if start
        else end_date - timedelta(days=days - 1)
    )
    if start_date > end_date:
        raise ValueError("起始日期不能晚于结束日期")
    return [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    ]


def random_time_on_day(target_date: date, rng: random.Random) -> datetime:
    max_second = 86_399
    today = datetime.now()
    if target_date == today.date():
        max_second = max(0, today.hour * 3600 + today.minute * 60 + today.second)
    second = rng.randint(0, max_second)
    return datetime.combine(target_date, time.min) + timedelta(seconds=second)


async def load_candidates(db) -> list[EventCandidate]:
    """加载可用业务候选；真正的风险分组由 classify_candidates 计算。"""
    candidates: list[EventCandidate] = []

    orders = (await db.execute(text("""
        SELECT o.order_id, o.user_id, u.device_id
        FROM order_info o
        JOIN user_info u ON u.user_id = o.user_id
        WHERE o.user_id NOT LIKE 'RISK%'
          AND o.total_amount < 10000
    """))).all()
    candidates.extend(
        EventCandidate("课程报名", r.order_id, r.user_id, r.device_id)
        for r in orders
    )

    rewards = (await db.execute(text("""
        SELECT lr.reward_id, lr.user_id, COALESCE(lr.device_id, u.device_id) AS device_id
        FROM live_reward lr
        JOIN user_info u ON u.user_id = lr.user_id
        WHERE lr.user_id NOT LIKE 'RISK%'
    """))).all()
    candidates.extend(
        EventCandidate("直播打赏", r.reward_id, r.user_id, r.device_id)
        for r in rewards
    )

    risky_rows = (await db.execute(text("""
        SELECT rr.refund_id, o.user_id, u.device_id
        FROM refund_request rr
        JOIN order_info o ON o.order_id = rr.order_id
        JOIN user_info u ON u.user_id = o.user_id
        WHERE o.user_id IN ('RISK_REFUND_001', 'RISK_REFUND_002')
    """))).all()
    candidates.extend(
        EventCandidate("退费申请", r.refund_id, r.user_id, r.device_id)
        for r in risky_rows
    )

    if not candidates:
        raise RuntimeError("没有可用的教育业务数据，请先执行 scripts/init_db.py --reset --yes")
    return candidates


def build_request(candidate: EventCandidate, requested_bucket: str) -> RiskCheckRequest:
    return RiskCheckRequest(
        event_type=candidate.event_type,
        source_id=candidate.source_id,
        user_id=candidate.user_id,
        device_id=candidate.device_id,
        event_data={
            "generated_by": "gen_education_risk_data",
            "requested_decision_bucket": requested_bucket,
            "requested_risk_sample": requested_bucket != "normal",
        },
    )


async def classify_candidates(db, candidates: list[EventCandidate]) -> dict[str, list[EventCandidate]]:
    """使用正式特征、规则和模型做只读预判，不向风险流水表写数据。"""
    pools: dict[str, list[EventCandidate]] = {
        "normal": [],
        "review": [],
        "reject": [],
    }
    open_case_rows = (await db.execute(text("""
        SELECT source_id, event_type
        FROM risk_case
        WHERE case_status IN ('待审核', '审核中')
    """))).all()
    open_case_keys = {(row.source_id, row.event_type) for row in open_case_rows}

    for candidate in candidates:
        request = build_request(candidate, "preview")
        request = await _enrich_request(db, request)
        if await _check_all_blacklists(db, request):
            continue

        education_event_type = request.event_type
        event_data = dict(request.event_data or {})
        event_data["education_event_type"] = education_event_type
        core_request = request.model_copy(update={
            "event_type": to_core_event(education_event_type),
            "event_data": event_data,
        })
        ctx = _build_context(core_request)
        await _enrich_receive_id(db, ctx)
        features = await _compute_features(db, ctx)
        rules = await _evaluate_rules(db, ctx, features)
        _, _, decision, _, _ = _calculate_decision(rules, features)
        bucket = DECISION_BUCKET[decision]

        # 人工审核案件只有使用新的 (source_id, event_type) 才会真正产生待审核案件。
        if bucket == "review" and (candidate.source_id, core_request.event_type) in open_case_keys:
            continue
        pools[bucket].append(candidate)

    return pools


async def backdate_result(db, assessment_id: str, event_id: str, target: datetime) -> None:
    await db.execute(
        text("UPDATE risk_event SET create_time=:target WHERE event_id=:event_id"),
        {"target": target, "event_id": event_id},
    )
    await db.execute(
        text("UPDATE risk_feature SET compute_time=:target WHERE event_id=:event_id"),
        {"target": target, "event_id": event_id},
    )
    await db.execute(
        text("UPDATE risk_assessment SET create_time=:target WHERE assessment_id=:assessment_id"),
        {"target": target, "assessment_id": assessment_id},
    )
    await db.execute(
        text("UPDATE risk_case SET create_time=:target WHERE assessment_id=:assessment_id"),
        {"target": target, "assessment_id": assessment_id},
    )


async def generate(
    dates: list[date],
    per_day: int,
    positive_ratio: float,
    review_ratio: float,
    seed: int,
) -> dict:
    quotas = calculate_daily_quotas(per_day, review_ratio, positive_ratio)

    rng = random.Random(seed)
    total_success = 0
    total_failed = 0
    total_high = 0
    total_decisions = {"通过": 0, "标记": 0, "人工审核": 0, "拒绝": 0}
    by_day: dict[str, dict[str, int]] = {}

    async with AsyncSessionLocal() as db:
        candidates = await load_candidates(db)
        pools = await classify_candidates(db, candidates)
        required_reviews = quotas["review"] * len(dates)
        for bucket, count in quotas.items():
            if count and not pools[bucket]:
                raise RuntimeError(f"{bucket} 候选池为空，无法按配额生成")

        review_queue = list(pools["review"])
        rng.shuffle(review_queue)
        print(f"目标数据库：{settings.DB_NAME}")
        print(
            "候选池："
            f"正常 {len(pools['normal'])}，人工审核 {len(pools['review'])}，"
            f"拒绝 {len(pools['reject'])}"
        )
        print(f"日期范围：{dates[0]} 至 {dates[-1]}，每天 {per_day} 条")
        print(
            "每日配额："
            f"正常 {quotas['normal']}，人工审核 {quotas['review']}，"
            f"拒绝 {quotas['reject']}"
        )
        if len(review_queue) < required_reviews:
            print(
                f"提示：可产生独立待审核案件的业务单号有 {len(review_queue)} 个；"
                f"其余 {required_reviews - len(review_queue)} 条人工审核评估将复用业务单号，"
                "不会重复建案。"
            )

        for target_date in dates:
            day_success = 0
            day_failed = 0
            day_high = 0
            day_decisions = {"通过": 0, "标记": 0, "人工审核": 0, "拒绝": 0}
            attempts = 0
            max_attempts = max(per_day * 20, 50)

            targets = [
                bucket
                for bucket, count in quotas.items()
                for _ in range(count)
            ]
            rng.shuffle(targets)

            while targets and attempts < max_attempts:
                attempts += 1
                target_bucket = targets[0]
                used_unique_review = target_bucket == "review" and bool(review_queue)
                if used_unique_review:
                    candidate = review_queue.pop()
                else:
                    candidate = rng.choice(pools[target_bucket])
                request = build_request(candidate, target_bucket)
                try:
                    result = await process_event(db, request)
                    if result.assessment_id == "blacklist_reject":
                        if used_unique_review:
                            review_queue.insert(0, candidate)
                        day_failed += 1
                        continue
                    actual_bucket = DECISION_BUCKET[result.decision]
                    if actual_bucket != target_bucket:
                        await db.rollback()
                        day_failed += 1
                        if used_unique_review:
                            review_queue.insert(0, candidate)
                        continue
                    target_time = random_time_on_day(target_date, rng)
                    await backdate_result(
                        db, result.assessment_id, result.event_id, target_time
                    )
                    await db.commit()
                    targets.pop(0)
                    day_success += 1
                    total_decisions[result.decision] += 1
                    day_decisions[result.decision] += 1
                    if result.risk_level in ("高", "极高"):
                        day_high += 1
                except Exception as exc:
                    await db.rollback()
                    if used_unique_review:
                        review_queue.insert(0, candidate)
                    day_failed += 1
                    if day_failed <= 3:
                        print(
                            f"  {target_date} 跳过失败样本 "
                            f"{candidate.event_type}/{candidate.source_id}: {exc}"
                        )

            if day_success != per_day:
                raise RuntimeError(
                    f"{target_date} 只成功生成 {day_success}/{per_day} 条，"
                    "请检查业务数据和错误输出"
                )

            by_day[str(target_date)] = {
                "created": day_success,
                "high_risk": day_high,
                "skipped": day_failed,
                "normal": quotas["normal"],
                "review": quotas["review"],
                "reject": quotas["reject"],
            }
            total_success += day_success
            total_failed += day_failed
            total_high += day_high
            print(
                f"[{target_date}] 成功 {day_success}："
                f"通过/标记 {day_decisions['通过'] + day_decisions['标记']}，"
                f"人工审核 {day_decisions['人工审核']}，拒绝 {day_decisions['拒绝']}，"
                f"跳过 {day_failed}"
            )

    return {
        "database": settings.DB_NAME,
        "created": total_success,
        "high_risk": total_high,
        "skipped": total_failed,
        "decisions": total_decisions,
        "by_day": by_day,
    }


async def preview(
    dates: list[date],
    per_day: int,
    positive_ratio: float,
    review_ratio: float,
) -> dict:
    """只读预览候选池和配额，不生成任何数据库记录。"""
    quotas = calculate_daily_quotas(per_day, review_ratio, positive_ratio)
    async with AsyncSessionLocal() as db:
        pools = await classify_candidates(db, await load_candidates(db))
    return {
        "quotas": quotas,
        "pool_sizes": {name: len(rows) for name, rows in pools.items()},
        "required_reviews": quotas["review"] * len(dates),
        "new_review_cases": min(
            len(pools["review"]), quotas["review"] * len(dates)
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="教育风控评估测试数据生成：默认过去 7 天每天 10 条"
    )
    parser.add_argument("--days", type=int, default=7, help="过去 N 天，默认 7")
    parser.add_argument("--per-day", type=int, default=10, help="每天生成条数，默认 10")
    parser.add_argument("--start", help="起始日期 YYYY-MM-DD；设置后覆盖 --days 的起始日")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD；默认今天")
    parser.add_argument(
        "--positive-ratio",
        type=float,
        default=0.10,
        help="拒绝评估占比，默认 0.10（保留旧参数名以兼容已有命令）",
    )
    parser.add_argument(
        "--review-ratio",
        type=float,
        default=0.20,
        help="人工审核评估占比，默认 0.20",
    )
    parser.add_argument("--seed", type=int, default=20260811, help="随机种子")
    parser.add_argument("--preview", action="store_true", help="只读预览候选池，不写数据库")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    dates = build_date_range(args.days, args.start, args.end)
    try:
        if args.preview:
            result = await preview(
                dates, args.per_day, args.positive_ratio, args.review_ratio
            )
            print(f"目标数据库：{settings.DB_NAME}")
            print(f"候选池：{result['pool_sizes']}")
            print(f"每日配额：{result['quotas']}")
            print(f"本次需要人工审核候选：{result['required_reviews']}")
            print(f"预计新增独立待审核案件：{result['new_review_cases']}")
            print("预览完成：未写入任何数据。")
            return 0
        summary = await generate(
            dates,
            args.per_day,
            args.positive_ratio,
            args.review_ratio,
            args.seed,
        )
    finally:
        await async_engine.dispose()

    print("=" * 60)
    print(
        f"完成：向 {summary['database']} 追加 {summary['created']} 条评估，"
        f"其中高风险 {summary['high_risk']} 条"
    )
    print(f"决策分布：{summary['decisions']}")
    print("刷新仪表盘即可查看近 7 天趋势。")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(async_main(args))
    except (ValueError, RuntimeError) as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

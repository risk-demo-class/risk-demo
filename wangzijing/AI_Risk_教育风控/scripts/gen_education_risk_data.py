"""批量生成教育行业风控评估和案件数据。

从现有的课程报名、退费申请和学历认证记录中抽样，统一调用
``process_event``，因此生成的数据会正常经过实体校验、25 维特征、
规则/XGBoost 决策、评估落库和案件生成。

示例：
  python scripts/gen_education_risk_data.py --count 200
  python scripts/gen_education_risk_data.py --count 500 --risk-ratio 0.8
  python scripts/gen_education_risk_data.py --count 100 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from app.database import AsyncSessionLocal, async_engine
from app.models import IdentityVerification, OrderInfo, RefundRequest
from app.schemas import RiskCheckRequest
from app.service.event import process_event


@dataclass(frozen=True)
class EventSource:
    event_type: str
    source_id: str
    user_id: str

    @property
    def is_risky(self) -> bool:
        return self.user_id.startswith("RISK")


async def load_event_sources(db) -> list[EventSource]:
    """加载三类教育业务来源，不引用任何旧电商表。"""
    sources: list[EventSource] = []

    orders = (await db.execute(
        select(OrderInfo.order_id, OrderInfo.user_id)
    )).all()
    sources.extend(EventSource("课程报名", row.order_id, row.user_id) for row in orders)

    refunds = (await db.execute(
        select(RefundRequest.refund_id, RefundRequest.user_id)
    )).all()
    sources.extend(EventSource("退费申请", row.refund_id, row.user_id) for row in refunds)

    verifications = (await db.execute(
        select(IdentityVerification.verify_id, IdentityVerification.user_id)
    )).all()
    sources.extend(EventSource("学历认证", row.verify_id, row.user_id) for row in verifications)
    return sources


def choose_source(
    sources: list[EventSource],
    risky_sources: list[EventSource],
    *,
    risk_ratio: float,
    rng: random.Random,
) -> EventSource:
    if risky_sources and rng.random() < risk_ratio:
        return rng.choice(risky_sources)
    return rng.choice(sources)


async def generate(count: int, risk_ratio: float, seed: int, dry_run: bool = False) -> int:
    rng = random.Random(seed)
    async with AsyncSessionLocal() as db:
        sources = await load_event_sources(db)
        if not sources:
            print("[失败] 没有教育业务数据，请先运行: python scripts/gen_business_data.py")
            return 2

        risky_sources = [source for source in sources if source.is_risky]
        type_counts = Counter(source.event_type for source in sources)
        print("=" * 64)
        print("教育行业风控数据批量生成")
        print("=" * 64)
        print(f"可用业务来源: {len(sources)} 条")
        print(f"  课程报名 {type_counts['课程报名']} / 退费申请 {type_counts['退费申请']} / 学历认证 {type_counts['学历认证']}")
        print(f"高风险来源: {len(risky_sources)} 条，抽取比例: {risk_ratio:.0%}")
        print(f"目标评估数: {count} 条")

        if dry_run:
            print("[DRY-RUN] 仅检查数据池，不写入数据库。")
            return 0

        success = 0
        positive = 0
        blocked = 0
        failed = 0
        attempts = 0
        decision_counts: Counter[str] = Counter()
        event_counts: Counter[str] = Counter()
        max_attempts = max(count * 3, count + 20)

        while success < count and attempts < max_attempts:
            attempts += 1
            source = choose_source(
                sources, risky_sources, risk_ratio=risk_ratio, rng=rng,
            )
            request = RiskCheckRequest(
                event_type=source.event_type,
                source_id=source.source_id,
                user_id=source.user_id,
            )
            try:
                result = await process_event(db, request)
                if result.blocked_by:
                    blocked += 1
                    continue
                success += 1
                event_counts[source.event_type] += 1
                decision_counts[result.decision] += 1
                if result.decision in {"人工审核", "拒绝"}:
                    positive += 1
                if success % 25 == 0 or success == count:
                    print(
                        f"进度 {success}/{count}: 正例 {positive} "
                        f"({positive / success:.1%})，失败 {failed}，黑名单短路 {blocked}"
                    )
            except Exception as exc:
                failed += 1
                await db.rollback()
                if failed <= 5:
                    print(
                        f"[跳过] {source.event_type} {source.source_id} / "
                        f"{source.user_id}: {exc}"
                    )

    print("\n生成完成")
    print(f"成功评估: {success} 条")
    print(f"事件分布: {dict(event_counts)}")
    print(f"决策分布: {dict(decision_counts)}")
    print(f"人工审核或拒绝: {positive} 条 ({positive / success:.1%})" if success else "人工审核或拒绝: 0 条")
    if success < count:
        print(f"[提示] 达到最大尝试次数，只生成了 {success}/{count} 条。")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量生成教育行业风控评估和案件")
    parser.add_argument("--count", type=int, default=100, help="生成评估条数，默认 100")
    parser.add_argument(
        "--risk-ratio", type=float, default=0.7,
        help="从 RISK 用户业务记录抽样的概率，默认 0.7",
    )
    parser.add_argument("--seed", type=int, default=20260811, help="随机种子")
    parser.add_argument("--dry-run", action="store_true", help="只检查来源数据，不写库")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count 必须大于等于 1")
    if not 0 <= args.risk_ratio <= 1:
        parser.error("--risk-ratio 必须在 0 到 1 之间")
    return args


async def _main(args: argparse.Namespace) -> int:
    try:
        return await generate(args.count, args.risk_ratio, args.seed, args.dry_run)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(parse_args())))

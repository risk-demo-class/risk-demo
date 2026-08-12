"""
物流风控系统 - 带日期范围的评估数据生成 (从运单抽样跑 process_event)

用途:
  - 填充仪表盘 7 天趋势 / 案件工作台 / 评估历史
  - 生成 XGBoost 训练数据 (加 --balance-pos 拉高正例比例)

用法:
  python scripts/gen_risk_data_with_dates.py                      # 近 7 天, 每天随机 1~30 条
  python scripts/gen_risk_data_with_dates.py --days 7 --per-day 50  # 近 7 天, 每天 50 条
  python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos
  python scripts/gen_risk_data_with_dates.py --clean                # 先清空风控评估表
  python scripts/gen_risk_data_with_dates.py --live                 # 只造今天

说明:
  - 每次 process_event 会写 risk_event / risk_feature / risk_assessment / risk_case / risk_user_profile
  - 生成后按目标日期回填 create_time, 让仪表盘跨天趋势可见
  - --balance-pos 时优先抽 RISK 高风险用户的运单, 正例(人工审核/拒绝)占比可拉到 30%+
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import Shipment  # noqa: E402
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402


async def _clear_risk_tables(db) -> None:
    """清空风控评估相关的 4 张表 + 画像 (不碰规则/黑名单)."""
    for table in ("risk_case", "risk_assessment", "risk_feature", "risk_event", "risk_user_profile"):
        await db.execute(text(f"DELETE FROM {table}"))
    await db.commit()
    print("已清空风控评估表 (risk_event/feature/assessment/case/user_profile)")


async def _sample_shipments(db, day_start: datetime, day_end: datetime,
                            per_day: int, balance_pos: bool, rng: random.Random):
    """从全部运单里抽样 per_day 个 (business 数据只有 ~120 单, 按天筛会不够).

    评估记录的日期由 _backfill_dates 回填到目标天, 所以抽样不必限制在当天.
    balance_pos 时 70% 概率从 RISK 用户抽, 拉高正例比例.
    """
    base = select(Shipment.shipment_id, Shipment.user_id, Shipment.shipment_type,
                  Shipment.create_time)
    rows = (await db.execute(base)).all()
    if not rows:
        return []
    rows = list(rows)
    rng.shuffle(rows)
    if balance_pos:
        risk_rows = [r for r in rows if str(r.user_id).startswith("RISK")]
        normal_rows = [r for r in rows if not str(r.user_id).startswith("RISK")]
        picked = []
        for _ in range(per_day):
            if risk_rows and rng.random() < 0.7:
                picked.append(rng.choice(risk_rows))
            elif normal_rows:
                picked.append(rng.choice(normal_rows))
            else:
                break
        return picked
    return rows[:per_day]


async def _backfill_dates(db, assessment_ids: list[str], target: datetime) -> None:
    """把本次生成记录的时间回填到目标日期, 让仪表盘趋势按天分布."""
    if not assessment_ids:
        return
    ids = ",".join(f"'{a}'" for a in assessment_ids)
    ts = target.strftime("%Y-%m-%d %H:%M:%S")
    # 顺带把 ml_score/ml_decision 强制置 NULL: 训练脚本只拉 ml_score IS NULL 的干净数据,
    # 模型未加载时 decision.py 会写 0.0, 会让训练拉不到新数据 (跟基线 gen_train_dataset 同策略)
    await db.execute(text(
        f"UPDATE risk_assessment SET create_time='{ts}', ml_score=NULL, ml_decision=NULL "
        f"WHERE assessment_id IN ({ids})"))
    await db.execute(text(
        f"UPDATE risk_event SET create_time='{ts}' WHERE event_id IN "
        f"(SELECT event_id FROM risk_assessment WHERE assessment_id IN ({ids}))"))
    await db.execute(text(
        f"UPDATE risk_case SET create_time='{ts}' WHERE assessment_id IN ({ids})"))


async def run(days: int, per_day: int, clean: bool, balance_pos: bool,
              live: bool, start: str | None, end: str | None) -> None:
    rng = random.Random(2026)
    today = datetime.now()

    if live:
        day_list = [today.date()]
    elif start and end:
        d0 = datetime.strptime(start, "%Y-%m-%d").date()
        d1 = datetime.strptime(end, "%Y-%m-%d").date()
        day_list = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    else:
        day_list = [today.date() - timedelta(days=i) for i in range(days - 1, -1, -1)]

    async with AsyncSessionLocal() as db:
        if clean:
            await _clear_risk_tables(db)

        total_ok = 0
        total_pos = 0
        for day in day_list:
            day_start = datetime(day.year, day.month, day.day)
            day_end = day_start + timedelta(days=1)
            picked = await _sample_shipments(db, day_start, day_end, per_day, balance_pos, rng)
            print(f"\n[{day}] 可用运单 {len(picked)} 条, 目标 {per_day} 条")
            ok = 0
            pos = 0
            blocked = 0
            assessment_ids: list[str] = []
            for row in picked:
                shipment_id, uid, stype, create_time = row
                # 5% 概率跑"实名认证"事件 (只算用户特征)
                if rng.random() < 0.05:
                    event_type, source_id = "实名认证", uid
                elif stype == "跨境":
                    event_type, source_id = "跨境申报", shipment_id
                elif stype == "代收货款":
                    event_type, source_id = "代收货款", shipment_id
                else:
                    event_type, source_id = "寄件", shipment_id
                req = RiskCheckRequest(
                    event_type=event_type,
                    source_id=source_id,
                    user_id=uid,
                    shipment_id=shipment_id if event_type != "实名认证" else None,
                    event_data={"weight_kg": 1},
                )
                try:
                    resp = await process_event(db, req)
                    # 撞黑拦截不算一次评估 (assessment_id 固定为 blacklist_reject, 不写库)
                    if resp.assessment_id == "blacklist_reject":
                        blocked += 1
                    else:
                        assessment_ids.append(resp.assessment_id)
                        ok += 1
                        if resp.decision in ("人工审核", "拒绝"):
                            pos += 1
                except Exception as e:
                    print(f"    [失败] {shipment_id}: {type(e).__name__}: {e}")
            # 回填当天日期
            hour = 10 if day == today.date() else 9
            await _backfill_dates(db, assessment_ids, datetime(day.year, day.month, day.day, hour, 30))
            await db.commit()
            total_ok += ok
            total_pos += pos
            print(f"  -> 成功 {ok}, 撞黑拦截 {blocked}, 失败 {len(picked) - ok - blocked}, 正例 {pos}")

    print("\n" + "=" * 60)
    print(f"完成! 总计 {total_ok} 次, 正例 {total_pos} ({100 * total_pos / max(1, total_ok):.1f}%)")
    print("刷新仪表盘: http://localhost:8000/")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="物流风控 - 带日期范围造评估数据")
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--per-day", type=int, default=30, help="每天条数 (默认 30)")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD (与 --days 互斥)")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--clean", action="store_true", help="先清空风控评估表")
    parser.add_argument("--live", action="store_true", help="只造今天")
    parser.add_argument("--balance-pos", action="store_true",
                        help="优先抽 RISK 高风险用户运单, 拉高正例比例")
    args = parser.parse_args()
    asyncio.run(run(args.days, args.per_day, args.clean, args.balance_pos,
                    args.live, args.start, args.end))


if __name__ == "__main__":
    main()

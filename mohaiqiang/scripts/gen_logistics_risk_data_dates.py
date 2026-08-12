"""
物流风控系统 - 带日期范围的模拟风控评估数据生成 (异步)

支持指定"近 N 天"或"起止日期"造数据, 让仪表盘趋势图有跨天数据.

用法:
  python scripts/gen_logistics_risk_data_dates.py                          # 近 7 天, 每天随机 1~30
  python scripts/gen_logistics_risk_data_dates.py --days 30 --per-day 50 --balance-pos
  python scripts/gen_logistics_risk_data_dates.py --days 15 --per-day 100 --clean --live
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event

RISKY_USER_PREFIX = "RISK"

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
FAIL_LOG = os.path.join(LOG_DIR, "gen_risk_fail.log")


def _log_failure(target_time, request, error) -> None:
    import json
    os.makedirs(LOG_DIR, exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "target_time": target_time.isoformat() if target_time else None,
        "user_id": getattr(request, "user_id", None),
        "event_type": getattr(request, "event_type", None),
        "source_id": getattr(request, "source_id", None),
        "error": str(error)[:500],
    }
    with open(FAIL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def clean_risk_tables(db) -> None:
    print("清空风控运行时表...")
    for tbl in ["risk_feature", "risk_assessment", "risk_event",
                "risk_case", "risk_user_profile", "risk_blacklist"]:
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception as e:
            print(f"  清空 {tbl} 失败: {e}")
    await db.commit()


async def _pick_waybill(db, balance_pos: bool = False) -> tuple | None:
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT waybill_no, sender_id FROM logistics_waybill
            WHERE sender_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.waybill_no, row.sender_id)
    r = await db.execute(text(
        "SELECT waybill_no, sender_id FROM logistics_waybill ORDER BY RAND() LIMIT 1"
    ))
    row = r.first()
    return (row.waybill_no, row.sender_id) if row else None


async def _pick_risk_waybill(db) -> tuple | None:
    """高风险运单: 未实名/危险品/跨境/COD拒收/异常状态."""
    r = await db.execute(text("""
        SELECT w.waybill_no, w.sender_id
        FROM logistics_waybill w
        LEFT JOIN logistics_sender s ON s.sender_id = w.sender_id
        LEFT JOIN logistics_cod_settlement c
               ON c.waybill_no = w.waybill_no AND c.collect_status = '拒收'
        WHERE s.is_real_name_verified = 0
           OR s.verify_fail_count >= 3
           OR w.item_category IN ('电池', '化学品')
           OR w.is_cross_border = 1
           OR c.cod_id IS NOT NULL
           OR w.status IN ('拒收', '退回', '异常')
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.waybill_no, row.sender_id) if row else None


async def _pick_cross_waybill(db, balance_pos: bool = False) -> tuple | None:
    sql = """
        SELECT w.waybill_no, w.sender_id
        FROM logistics_waybill w
        JOIN logistics_customs_info c ON c.waybill_no = w.waybill_no
    """
    params = {}
    if balance_pos and random.random() < 0.8:
        sql += " WHERE w.sender_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    sql += " ORDER BY RAND() LIMIT 1"
    row = (await db.execute(text(sql), params)).first()
    return (row.waybill_no, row.sender_id) if row else None


async def _pick_complaint(db, balance_pos: bool = False) -> tuple | None:
    sql = """
        SELECT c.complaint_id, w.sender_id
        FROM logistics_complaint_record c
        JOIN logistics_waybill w ON w.waybill_no = c.waybill_no
    """
    params = {}
    if balance_pos and random.random() < 0.8:
        sql += " WHERE w.sender_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    sql += " ORDER BY RAND() LIMIT 1"
    row = (await db.execute(text(sql), params)).first()
    return (row.complaint_id, row.sender_id) if row else None


async def _pick_claim(db, balance_pos: bool = False) -> tuple | None:
    sql = """
        SELECT c.claim_id, w.sender_id
        FROM logistics_claim c
        JOIN logistics_waybill w ON w.waybill_no = c.waybill_no
    """
    params = {}
    if balance_pos and random.random() < 0.8:
        sql += " WHERE w.sender_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    sql += " ORDER BY RAND() LIMIT 1"
    row = (await db.execute(text(sql), params)).first()
    return (row.claim_id, row.sender_id) if row else None


async def _pick_cod(db, balance_pos: bool = False) -> tuple | None:
    sql = """
        SELECT c.cod_id, w.sender_id
        FROM logistics_cod_settlement c
        JOIN logistics_waybill w ON w.waybill_no = c.waybill_no
    """
    params = {}
    if balance_pos and random.random() < 0.8:
        sql += " WHERE w.sender_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    sql += " ORDER BY RAND() LIMIT 1"
    row = (await db.execute(text(sql), params)).first()
    return (row.cod_id, row.sender_id) if row else None


async def _backdate(db, target_time: datetime, user_id: str) -> None:
    """把刚生成的评估/事件/特征/案件/画像时间改写成目标时间."""
    ev = (await db.execute(text("""
        SELECT event_id FROM risk_event
        WHERE user_id = :uid ORDER BY create_time DESC LIMIT 1
    """), {"uid": user_id})).first()
    ast = (await db.execute(text("""
        SELECT assessment_id FROM risk_assessment
        WHERE user_id = :uid ORDER BY create_time DESC LIMIT 1
    """), {"uid": user_id})).first()
    if ev:
        await db.execute(text(
            "UPDATE risk_event SET create_time = :t WHERE event_id = :eid"
        ), {"t": target_time, "eid": ev.event_id})
        await db.execute(text(
            "UPDATE risk_feature SET compute_time = :t WHERE event_id = :eid"
        ), {"t": target_time, "eid": ev.event_id})
    if ast:
        await db.execute(text(
            "UPDATE risk_assessment SET create_time = :t WHERE assessment_id = :aid"
        ), {"t": target_time, "aid": ast.assessment_id})
        await db.execute(text(
            "UPDATE risk_case SET create_time = :t WHERE assessment_id = :aid"
        ), {"t": target_time, "aid": ast.assessment_id})
    await db.execute(text("""
        UPDATE risk_user_profile SET last_assessment_time = :t, update_time = :t
        WHERE user_id = :uid
    """), {"t": target_time, "uid": user_id})


async def generate_risk_data_with_dates(
    days: int = 7,
    per_day: int | None = None,
    max_per_day: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    clean: bool = False,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
    live: bool = False,
    force_pos_ratio: float | None = None,
) -> None:
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    else:
        end_dt = datetime.now()
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
    else:
        start_dt = (end_dt - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0)

    total_days = (end_dt.date() - start_dt.date()).days + 1
    max_rounds = 10 if target_pos_ratio else 1

    async with AsyncSessionLocal() as db:
        if clean:
            await clean_risk_tables(db)

        grand_total = 0
        grand_success = 0
        grand_positive = 0
        grand_fail = 0

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {'固定 ' + str(per_day) if per_day else f'随机 1~{max_per_day}'}")

        for round_idx in range(max_rounds):
            for day_offset in range(total_days):
                current_date = start_dt.date() + timedelta(days=day_offset)
                day_count = per_day if per_day else random.randint(1, max_per_day)
                day_success = 0
                day_positive = 0
                for _ in range(day_count):
                    target_time = datetime.combine(
                        current_date, datetime.min.time()
                    ).replace(
                        hour=random.randint(0, 23),
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59),
                    )

                    use_force = force_pos_ratio is not None and random.random() < force_pos_ratio
                    request = None
                    if use_force:
                        picked = await _pick_risk_waybill(db)
                        if picked:
                            wb, uid = picked
                            request = RiskCheckRequest(event_type="寄件下单", source_id=wb, user_id=uid)
                    else:
                        event_type = random.choices(
                            ["寄件下单", "揽收", "签收", "投诉", "理赔申请", "COD结算", "报关清关"],
                            weights=[40, 15, 15, 8, 8, 8, 6],
                        )[0]
                        picked = None
                        if event_type == "报关清关":
                            picked = await _pick_cross_waybill(db, balance_pos)
                        elif event_type == "投诉":
                            picked = await _pick_complaint(db, balance_pos)
                        elif event_type == "理赔申请":
                            picked = await _pick_claim(db, balance_pos)
                        elif event_type == "COD结算":
                            picked = await _pick_cod(db, balance_pos)
                        else:
                            picked = await _pick_waybill(db, balance_pos)
                        if picked:
                            source_id, uid = picked
                            request = RiskCheckRequest(
                                event_type=event_type, source_id=source_id, user_id=uid,
                            )

                    if request is None:
                        continue
                    try:
                        await process_event(db, request)
                        if not live:
                            await _backdate(db, target_time, request.user_id)
                        await db.commit()
                        day_success += 1
                        grand_success += 1
                        ast = (await db.execute(text("""
                            SELECT decision FROM risk_assessment
                            WHERE user_id = :uid ORDER BY create_time DESC LIMIT 1
                        """), {"uid": request.user_id})).first()
                        if ast and ast.decision in ("人工审核", "拒绝"):
                            day_positive += 1
                            grand_positive += 1
                    except Exception as e:
                        await db.rollback()
                        grand_fail += 1
                        _log_failure(target_time, request, e)

                grand_total += day_count
                print(f"  [{current_date}] 成功 {day_success}, 正例 {day_positive}")

            if target_pos_ratio is None or (
                grand_success > 0 and grand_positive / grand_success >= target_pos_ratio * 0.7
            ):
                break

        pos_ratio = grand_positive / grand_success * 100 if grand_success else 0
        print("=" * 60)
        print(f"完成! 总计 {grand_total} 次, 成功 {grand_success}, 失败 {grand_fail}, 正例 {grand_positive} ({pos_ratio:.1f}%)")
        if grand_fail:
            print(f"失败详情见: {FAIL_LOG}")


def main() -> None:
    parser = argparse.ArgumentParser(description="带日期范围的物流风控评估数据生成")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--per-day", type=int, default=None)
    parser.add_argument("--max-per-day", type=int, default=30)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--live", action="store_true", help="不回写 create_time")
    parser.add_argument("--balance-pos", action="store_true", help="80% 概率挑 RISK 高风险寄件人")
    parser.add_argument("--target-pos-ratio", type=float, default=None)
    parser.add_argument("--force-pos-ratio", type=float, default=None)
    args = parser.parse_args()

    async def _runner() -> None:
        try:
            await generate_risk_data_with_dates(
                days=args.days,
                per_day=args.per_day,
                max_per_day=args.max_per_day,
                start_date=args.start,
                end_date=args.end,
                clean=args.clean,
                balance_pos=args.balance_pos,
                target_pos_ratio=args.target_pos_ratio,
                live=args.live,
                force_pos_ratio=args.force_pos_ratio,
            )
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()

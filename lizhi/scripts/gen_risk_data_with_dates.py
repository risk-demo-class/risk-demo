"""
旅游风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据，让仪表盘趋势图有跨天数据

【P4-L3 2026-08-08 第三轮】支持 --balance-pos / --target-pos-ratio 控制正负例比例:
  - --balance-pos: 80% 概率从 RISK 高风险用户挑样本
  - --target-pos-ratio: 目标正例比例 (0.0-1.0), 自动循环造数据直到达标 (最多 10 轮)

每天数据量规则 (优先级从高到低):
    1. --per-day 固定值       → 每天生成固定条数
    2. --max-per-day 仅指定   → 每天随机 1 ~ max-per-day 条
    3. 都不指定              → 每天随机 1 ~ 30 条 (默认)

用法:
    # 默认: 近 7 天, 每天随机 1~30 条
    python scripts/gen_risk_data_with_dates.py

    # 近 30 天, 每天固定 200 条, 循环造到正例 30% (训练用)
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos --target-pos-ratio 0.30

    # 每天固定 50 条 (demo: 近 1 天, 仪表盘今日数据)
    python scripts/gen_risk_data_with_dates.py --days 1 --per-day 50 --live

    # 强制正例路径 (RISK 签证/囤票/大额订单, 保证规则命中)
    python scripts/gen_risk_data_with_dates.py --days 15 --per-day 100 --force-pos-ratio 0.30 --clean
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

# RISK 高风险用户前缀 (跟 gen_business_data.py 的 5 类风险模式对齐)
RISKY_USER_PREFIX = "RISK"

# 订单类事件池 (预订下单为主, 退改签申请留给高风险用户拉正例)
ORDER_EVENT_TYPES = ["预订下单", "预订下单", "预订下单", "支付成功", "出票确认",
                     "出行核销", "退改签申请", "索赔投诉", "评价发布"]

# ============================================================
# 失败日志
# ============================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
FAIL_LOG = os.path.join(LOG_DIR, "gen_risk_fail.log")


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _log_failure(target_time, request, error):
    """追加 1 条失败记录到日志 (1 行 JSON)."""
    import json
    _ensure_log_dir()
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


async def clean_risk_tables(db):
    """清空风控运行时表 (不影响 risk_rule)"""
    print("清空风控运行时表...")
    for tbl in ["risk_feature", "risk_assessment", "risk_event",
                "risk_case", "risk_user_profile", "risk_blacklist"]:
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception as e:
            print(f"  清空 {tbl} 失败 (可能表不存在): {e}")
    await db.commit()


# ============================================================
# 事件挑选器 (旅游行业)
# ============================================================
async def _pick_order_for_balance(db, balance_pos: bool):
    """从订单池挑一条; balance_pos=True 时 80% 概率挑 RISK 用户订单."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT order_id, user_id FROM order_info
            WHERE user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.order_id, row.user_id)
    r = await db.execute(text("""
        SELECT order_id, user_id FROM order_info
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.order_id, row.user_id) if row else None


async def _pick_visa_for_balance(db, balance_pos: bool):
    """从签证申请池挑一条; balance_pos=True 时 80% 概率挑 RISK 用户."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT visa_id, user_id FROM visa_application
            WHERE user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.visa_id, row.user_id)
    r = await db.execute(text("""
        SELECT visa_id, user_id FROM visa_application
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.visa_id, row.user_id) if row else None


# ---- --force-pos-ratio 高风险事件路径 (必触发规则) ----
async def _pick_forced_visa(db):
    """RISK 用户的签证申请 (R001 拒签历史 / R002 短期多国)."""
    r = await db.execute(text("""
        SELECT visa_id, user_id FROM visa_application
        WHERE user_id LIKE :prefix
        ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    return (row.visa_id, row.user_id) if row else None


async def _pick_forced_scalper_order(db):
    """RISK 用户的机票囤票订单 (R003 黄牛囤票)."""
    r = await db.execute(text("""
        SELECT oi.order_id, oi.user_id
        FROM order_info oi
        JOIN booking_flight bf ON oi.order_id = bf.order_id
        WHERE oi.user_id LIKE :prefix
        ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    return (row.order_id, row.user_id) if row else None


async def _pick_forced_high_amount_order(db):
    """RISK 用户的大额订单 (R005 大额跨境游 / R006 新用户大单)."""
    r = await db.execute(text("""
        SELECT order_id, user_id FROM order_info
        WHERE user_id LIKE :prefix AND total_amount > 10000
        ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    return (row.order_id, row.user_id) if row else None


async def backdate_record(db, table: str, time_col: str, event_id: str, target_time: datetime):
    """把指定记录的某个时间字段改写成目标时间 (异步)"""
    id_col = (
        'event_id' if 'event' in table
        else 'assessment_id' if 'assess' in table
        else 'case_id' if 'case' in table
        else 'user_id'
    )
    await db.execute(
        text(f"UPDATE {table} SET {time_col} = :t WHERE {id_col} = :eid"),
        {"t": target_time, "eid": event_id},
    )


async def generate_risk_data_with_dates(
    days: int = 7,
    per_day: int = None,
    max_per_day: int = 30,
    start_date: str = None,
    end_date: str = None,
    clean: bool = False,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
    live: bool = False,
    force_pos_ratio: float | None = None,
):
    """
    在指定日期范围内生成风控评估数据 (异步).
    每天数据量: --per-day 固定, 或随机 1 ~ max_per_day.
    --live: 不回写 create_time (数据 create_time=now, 仪表盘"今日"能看到).
    """
    async with AsyncSessionLocal() as db:
        if clean:
            await clean_risk_tables(db)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        else:
            end_dt = datetime.now()

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        else:
            start_dt = (end_dt - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0)

        daily_rule = f"每天固定 {per_day} 条" if per_day is not None else f"每天随机 1~{max_per_day} 条"

        if target_pos_ratio is not None and not balance_pos:
            print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True
        if balance_pos:
            print("⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户")
        if live:
            print("📌 --live 模式: 不回写 create_time, 仪表盘'今日'能看到")
        if force_pos_ratio is not None:
            print(f"[FORCE-POS] --force-pos-ratio 模式: 强制 {force_pos_ratio*100:.0f}% 走高风险事件路径 "
                  f"(RISK 签证/囤票订单/大额订单)")

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {daily_rule}")

        # 事件池: 订单 + 签证申请
        all_orders_result = await db.execute(text("""
            SELECT order_id, user_id FROM order_info
        """))
        all_orders = all_orders_result.all()
        all_visas_result = await db.execute(text("""
            SELECT visa_id, user_id FROM visa_application
        """))
        all_visas = all_visas_result.all()

        if not all_orders:
            print("错误: 数据库里没有订单数据, 请先跑 init_db.py + gen_business_data.py")
            return

        print(f"可用订单: {len(all_orders)} 条, 签证申请: {len(all_visas)} 条\n")

        total_days = (end_dt.date() - start_dt.date()).days + 1
        grand_total = 0
        grand_success = 0
        grand_reject = 0
        grand_positive = 0

        for day_offset in range(total_days):
            current_date = start_dt.date() + timedelta(days=day_offset)
            day_count = per_day if per_day is not None else random.randint(1, max_per_day)
            print(f"[{current_date}] 生成 {day_count} 条评估...")

            day_success = 0
            day_reject = 0
            day_positive = 0

            for i in range(day_count):
                target_time = datetime.combine(current_date, datetime.min.time()).replace(
                    hour=random.randint(0, 23), minute=random.randint(0, 59),
                    second=random.randint(0, 59))

                use_force_pos = (
                    force_pos_ratio is not None and random.random() < force_pos_ratio
                )
                if use_force_pos:
                    pickers = [
                        ("签证申请", _pick_forced_visa, "visa"),
                        ("预订下单", _pick_forced_scalper_order, "order"),
                        ("预订下单", _pick_forced_high_amount_order, "order"),
                    ]
                    random.shuffle(pickers)

                success_done = False
                for try_idx in range(3 if use_force_pos else 1):
                    if use_force_pos:
                        et, picker, ptype = pickers[try_idx % len(pickers)]
                        picked = await picker(db)
                        if picked is None:
                            continue
                        if ptype == "visa":
                            visa_id, user_id = picked
                            request = RiskCheckRequest(
                                event_type=et, source_id=visa_id, user_id=user_id,
                            )
                        else:
                            order_id, user_id = picked
                            request = RiskCheckRequest(
                                event_type=et, source_id=order_id, user_id=user_id,
                                order_id=order_id,
                            )
                    else:
                        # 普通路径: balance_pos 时更倾向签证 (拒签历史用户正例高)
                        visa_odds = 0.35 if balance_pos else 0.20
                        use_visa = random.random() < visa_odds and bool(all_visas)
                        if use_visa:
                            picked = await _pick_visa_for_balance(db, balance_pos)
                            if not picked:
                                picked = await _pick_order_for_balance(db, balance_pos)
                                if not picked:
                                    break
                                order_id, user_id = picked
                                request = RiskCheckRequest(
                                    event_type=random.choice(ORDER_EVENT_TYPES),
                                    source_id=order_id, user_id=user_id, order_id=order_id,
                                )
                            else:
                                visa_id, user_id = picked
                                request = RiskCheckRequest(
                                    event_type="签证申请", source_id=visa_id, user_id=user_id,
                                )
                        else:
                            picked = await _pick_order_for_balance(db, balance_pos)
                            if not picked:
                                break
                            order_id, user_id = picked
                            request = RiskCheckRequest(
                                event_type=random.choice(ORDER_EVENT_TYPES),
                                source_id=order_id, user_id=user_id, order_id=order_id,
                            )

                    try:
                        await process_event(db, request)
                        backdate_target = None if live else target_time

                        new_event = (await db.execute(text("""
                            SELECT event_id FROM risk_event
                            WHERE user_id = :uid
                            ORDER BY create_time DESC LIMIT 1
                        """), {"uid": request.user_id})).first()
                        new_assess = (await db.execute(text("""
                            SELECT assessment_id, decision FROM risk_assessment
                            WHERE user_id = :uid
                            ORDER BY create_time DESC LIMIT 1
                        """), {"uid": request.user_id})).first()

                        if new_event and backdate_target is not None:
                            await backdate_record(db, "risk_event", "create_time",
                                                  new_event.event_id, backdate_target)
                            await db.execute(
                                text("UPDATE risk_feature SET compute_time = :t WHERE event_id = :eid"),
                                {"t": backdate_target, "eid": new_event.event_id},
                            )
                        if new_assess:
                            if backdate_target is not None:
                                await backdate_record(db, "risk_assessment", "create_time",
                                                      new_assess.assessment_id, backdate_target)
                                await db.execute(
                                    text("UPDATE risk_case SET create_time = :t WHERE assessment_id = :aid"),
                                    {"t": backdate_target, "aid": new_assess.assessment_id},
                                )
                            if new_assess.decision in ("拒绝", "人工审核"):
                                day_positive += 1
                                grand_positive += 1

                        await db.execute(
                            text("UPDATE risk_user_profile SET last_assessment_time = :t, "
                                 "update_time = :t WHERE user_id = :uid"),
                            {"t": backdate_target or datetime.now(), "uid": request.user_id},
                        )
                        await db.commit()
                        day_success += 1
                        grand_success += 1
                        success_done = True
                        break
                    except Exception as e:
                        await db.rollback()
                        day_reject += 1
                        grand_reject += 1
                        _log_failure(target_time, request, e)
                        success_done = True
                        break

            print(f"  -> 成功 {day_success}, 失败 {day_reject}, 正例 {day_positive}")
            grand_total += day_count

            if target_pos_ratio is not None and day_success > 0:
                current_pos_ratio = day_positive / day_success
                if current_pos_ratio < target_pos_ratio * 0.7:
                    print(f"  ⚠️  今日正例比例 {current_pos_ratio*100:.1f}% < 目标 "
                          f"{target_pos_ratio*100:.0f}% 的 70%, 检查 RISK 用户是否存在")

        print(f"\n{'=' * 50}")
        overall_pos = grand_positive / grand_success * 100 if grand_success else 0
        print(f"完成! 总计 {grand_total} 次, 成功 {grand_success}, 失败 {grand_reject}, "
              f"正例 {grand_positive} ({overall_pos:.1f}%)")
        if grand_reject > 0:
            print(f"失败详情见: {FAIL_LOG}")
        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print("刷新仪表盘: http://localhost:8000/")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="旅游风控 - 带日期范围的造评估数据 (每天条数: --per-day 固定, 或随机 1~--max-per-day)"
    )
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD (与 --days 互斥)")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--per-day", type=int, default=None, help="每天固定条数 (不指定则随机)")
    parser.add_argument("--max-per-day", type=int, default=30, help="每天最多多少条 (默认 30)")
    parser.add_argument("--clean", action="store_true", help="先清空风控表")
    parser.add_argument("--live", action="store_true",
                        help="不回写 create_time (数据 create_time=now, 仪表盘'今日'能看到)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="80% 概率挑 RISK 高风险用户, 拉高正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 循环造数到达标")
    parser.add_argument("--force-pos-ratio", type=float, default=None,
                        help="强制每条按此概率走'高风险事件'路径 (RISK 签证/囤票订单/大额订单), "
                             "并 retry 最多 3 次换事件")
    args = parser.parse_args()

    async def _runner():
        from app.database import async_engine
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

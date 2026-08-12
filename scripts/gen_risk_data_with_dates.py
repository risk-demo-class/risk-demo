"""
医疗风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据，让仪表盘趋势图有跨天数据

支持 --balance-pos / --target-pos-ratio / --force-pos-ratio 控制正负例比例:
  - --balance-pos: 优先从 RISK 高风险患者挑样本
  - --target-pos-ratio: 目标正例比例 (0.0-1.0), 自动循环造数据直到达标 (最多 10 轮)
  - --force-pos-ratio: 强制按概率走"已知能触发规则"的高风险单据路径

每天数据量规则 (优先级从高到低):
    1. --per-day 固定值       → 每天生成固定条数
    2. --max-per-day 仅指定   → 每天随机 1 ~ max-per-day 条
    3. 都不指定              → 每天随机 1 ~ 30 条 (默认)

用法:
    # 默认: 近 7 天, 每天随机 1~30 条
    python scripts/gen_risk_data_with_dates.py

    # 近 30 天, 每天固定 200 条, 循环造到正例 30% (训练用, 推荐)
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos --target-pos-ratio 0.30

    # 近 30 天, 每天固定 10 条
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 10

    # 指定日期范围
    python scripts/gen_risk_data_with_dates.py --start 2026-06-10 --end 2026-06-16 --per-day 20

    # 清空后重建 + 强制 30% 正例
    python scripts/gen_risk_data_with_dates.py --days 15 --per-day 100 --force-pos-ratio 0.30 --clean

    # 造 50 条今日数据 (demo, 仪表盘能看到)
    python scripts/gen_risk_data_with_dates.py --days 1 --per-day 50 --live
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows GBK 终端不能编码 emoji, 强制 stdout UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

# RISK 高风险患者前缀 (跟 gen_risky_users.py 对齐)
RISKY_USER_PREFIX = "RISK"

# 4 种单据池: (event_type, 表名, 主键列)
DOC_POOLS = [
    ("挂号", "appointment", "appt_id"),
    ("处方开具", "prescription", "rx_id"),
    ("医保结算", "insurance_claim", "claim_id"),
    ("药品下单", "drug_order", "drug_order_id"),
]

# ============================================================
# 失败日志: 写入 logs/gen_risk_fail.log (供事后查, 不刷屏终端)
# ============================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
FAIL_LOG = os.path.join(LOG_DIR, "gen_risk_fail.log")


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _log_failure(target_time, request, error):
    """追加 1 条失败记录到日志 (1 行 JSON, 方便后续解析)."""
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
# 单据挑选器
# ============================================================
async def _pick_document(db, balance_pos: bool) -> tuple | None:
    """随机挑一条诊疗单据; balance_pos=True 时优先从 RISK 高风险患者挑.

    返回: (event_type, source_id, user_id) 或 None
    """
    pools = list(DOC_POOLS)
    random.shuffle(pools)
    for event_type, table, pk in pools:
        if balance_pos and random.random() < 0.8:
            r = await db.execute(text(f"""
                SELECT {pk} AS sid, user_id FROM {table}
                WHERE user_id LIKE :prefix
                ORDER BY RAND() LIMIT 1
            """), {"prefix": f"{RISKY_USER_PREFIX}%"})
            row = r.first()
            if row:
                return (event_type, row.sid, row.user_id)
        r = await db.execute(text(f"""
            SELECT {pk} AS sid, user_id FROM {table}
            ORDER BY RAND() LIMIT 1
        """))
        row = r.first()
        if row:
            return (event_type, row.sid, row.user_id)
    return None


async def _pick_forced_document(db) -> tuple | None:
    """强制正例路径: 只从 RISK 患者里挑单据 (盗刷结算/超量处方/黄牛挂号等已知触发规则)."""
    pools = list(DOC_POOLS)
    random.shuffle(pools)
    for event_type, table, pk in pools:
        r = await db.execute(text(f"""
            SELECT {pk} AS sid, user_id FROM {table}
            WHERE user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (event_type, row.sid, row.user_id)
    return None


async def backdate_record(db, table: str, time_col: str, entity_id: str, target_time: datetime):
    """把指定记录的某个时间字段改写成目标时间 (异步)"""
    id_col = (
        'event_id' if 'event' in table
        else 'assessment_id' if 'assess' in table
        else 'case_id' if 'case' in table
        else 'user_id'
    )
    await db.execute(
        text(f"UPDATE {table} SET {time_col} = :t WHERE {id_col} = :eid"),
        {"t": target_time, "eid": entity_id},
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
    在指定日期范围内生成医疗风控评估数据 (异步).

    参数:
        balance_pos: 优先从 RISK 高风险患者挑样本 (拉高正例比例)
        target_pos_ratio: 目标正例比例, 循环造数据直到达标 (最多 10 轮)
        live: True=不回写 create_time (demo 用); False=回写到目标日期 (训练用)
        force_pos_ratio: 每条按此概率强制走 RISK 患者单据路径 (retry 最多 3 次)
    """
    async with AsyncSessionLocal() as db:
        if clean:
            await clean_risk_tables(db)

        # 解析日期范围
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        else:
            end_dt = datetime.now()

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        else:
            start_dt = end_dt - timedelta(days=days - 1)
            start_dt = start_dt.replace(hour=0, minute=0, second=0)

        daily_rule = f"每天固定 {per_day} 条" if per_day is not None else f"每天随机 1~{max_per_day} 条"

        if target_pos_ratio is not None and not balance_pos:
            print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True
        if balance_pos:
            print("⚠️  --balance-pos 模式: 优先挑 RISK 高风险患者")
        if target_pos_ratio is not None:
            print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标 (最多 10 轮)")
        if live:
            print("📌 --live 模式: 不回写 create_time, 数据 create_time=now, 仪表盘'今日'能看到")
        if force_pos_ratio is not None:
            print(f"[FORCE-POS] 强制 {force_pos_ratio*100:.0f}% 走 RISK 患者单据路径 (retry 最多 3 次)")

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {daily_rule}")

        # 1. 统计可用单据池
        pool_counts = []
        for event_type, table, pk in DOC_POOLS:
            cnt = (await db.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar() or 0
            pool_counts.append((event_type, cnt))
        total_docs = sum(c for _, c in pool_counts)
        if total_docs == 0:
            print("错误: 数据库里没有诊疗单据数据, 请先跑 init_db.py")
            return
        print("可用单据: " + ", ".join(f"{et} {c} 条" for et, c in pool_counts) + "\n")

        total_days = (end_dt.date() - start_dt.date()).days + 1
        grand_total = 0
        grand_success = 0
        grand_reject = 0
        grand_positive = 0

        for round_idx in range(10):
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
                    # 在当天随机一个时刻
                    target_time = datetime.combine(current_date, datetime.min.time()).replace(
                        hour=random.randint(0, 23),
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59),
                    )

                    use_force_pos = (
                        force_pos_ratio is not None
                        and random.random() < force_pos_ratio
                    )
                    max_tries = 3 if use_force_pos else 1

                    for try_idx in range(max_tries):
                        if use_force_pos:
                            picked = await _pick_forced_document(db)
                        else:
                            picked = await _pick_document(db, balance_pos)
                        if picked is None:
                            break
                        event_type, source_id, user_id = picked
                        request = RiskCheckRequest(
                            event_type=event_type,
                            source_id=source_id,
                            user_id=user_id,
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
                                await backdate_record(db, "risk_event", "create_time", new_event.event_id, backdate_target)
                                await db.execute(
                                    text("UPDATE risk_feature SET compute_time = :t WHERE event_id = :eid"),
                                    {"t": backdate_target, "eid": new_event.event_id},
                                )

                            if new_assess:
                                if backdate_target is not None:
                                    await backdate_record(db, "risk_assessment", "create_time", new_assess.assessment_id, backdate_target)
                                    await db.execute(
                                        text("UPDATE risk_case SET create_time = :t WHERE assessment_id = :aid"),
                                        {"t": backdate_target, "aid": new_assess.assessment_id},
                                    )
                                if new_assess.decision in ("拒绝", "人工审核"):
                                    day_positive += 1
                                    grand_positive += 1

                            await db.execute(
                                text("UPDATE risk_user_profile SET last_assessment_time = :t, update_time = :t WHERE user_id = :uid"),
                                {"t": backdate_target or datetime.now(), "uid": request.user_id},
                            )

                            await db.commit()
                            day_success += 1
                            grand_success += 1
                            break
                        except Exception as e:
                            await db.rollback()
                            day_reject += 1
                            grand_reject += 1
                            _log_failure(target_time, request, e)
                            break  # 业务异常不 retry

                print(f"  -> 成功 {day_success}, 失败 {day_reject}, 正例 {day_positive}")
                grand_total += day_count

            overall_pos = grand_positive / grand_success * 100 if grand_success else 0
            print(f"\n{'=' * 50}")
            print(f"第 {round_idx + 1} 轮完成! 总计 {grand_total} 次, 成功 {grand_success}, "
                  f"失败 {grand_reject}, 正例 {grand_positive} ({overall_pos:.1f}%)")

            # target 模式: 达标就停
            if target_pos_ratio is None or overall_pos / 100 >= target_pos_ratio:
                if target_pos_ratio is not None:
                    print(f"✅ 正例比例 {overall_pos:.1f}% >= 目标 {target_pos_ratio*100:.0f}%, 达标!")
                break
            print(f"⚠️  正例比例 {overall_pos:.1f}% < 目标 {target_pos_ratio*100:.0f}%, 继续造数据...")
            balance_pos = True  # 下一轮强制走 RISK 患者

        if grand_reject > 0:
            print(f"失败详情见: {FAIL_LOG}")
        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        overall_pos = grand_positive / grand_success * 100 if grand_success else 0
        if overall_pos < 15 and grand_success > 0:
            print(f"⚠️  正例比例仅 {overall_pos:.1f}%, 训练可能假收敛. 建议: --balance-pos --target-pos-ratio 0.30 重造")
        print("刷新仪表盘: http://localhost:8000/")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="带日期范围的造医疗风控数据 (每天条数: --per-day 固定, 或随机 1~--max-per-day)"
    )
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD (与 --days 互斥)")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--per-day", type=int, default=None,
                        help="每天固定条数 (不指定则随机)")
    parser.add_argument("--max-per-day", type=int, default=30,
                        help="每天最多多少条 (默认 30, 仅在未指定 --per-day 时生效)")
    parser.add_argument("--clean", action="store_true", help="先清空风控表")
    parser.add_argument("--live", action="store_true",
                        help="不回写 create_time (数据 create_time=now), 适合 demo (仪表盘/趋势图能看到)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="优先挑 RISK 高风险患者, 拉高正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 循环造数到达标")
    parser.add_argument("--force-pos-ratio", type=float, default=None,
                        help="强制每条按此概率走 RISK 患者单据路径 (retry 最多 3 次), "
                             "比 --balance-pos 更激进, 保证正例比例接近该值")
    args = parser.parse_args()

    async def _runner():
        """包装函数: 业务跑完后显式 dispose engine, 避免 Event loop is closed 警告"""
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

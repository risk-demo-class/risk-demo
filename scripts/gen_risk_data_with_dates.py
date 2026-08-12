"""
物流风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据，让仪表盘趋势图有跨天数据

【物流版】跟 gen_risk_data.py 对齐, 覆盖 4 类物流事件:
  - parcel_pickup    揽收      (source_id = parcel_id)
  - cross_border_ship 跨境发运  (source_id = parcel_id, 优先国际件)
  - dangerous_declare 危险品申报 (source_id = decl_id)
  - cod_settlement    COD结算    (source_id = cod_id)

--balance-pos / --target-pos-ratio: 80% 概率从 RISK 高风险用户挑样本, 拉高正例比例
--force-pos-ratio: 强制走"已知能触发规则"的物流高风险事件路径 (RISK 危险品申报 / COD / 国际件 / 普通包裹),
    并 retry 最多 3 次换事件, 保证最终正例比例接近 force_pos_ratio.

每天数据量规则 (优先级从高到低):
    1. --per-day 固定值       → 每天生成固定条数
    2. --max-per-day 仅指定   → 每天随机 1 ~ max-per-day 条
    3. 都不指定              → 每天随机 1 ~ 30 条 (默认)

用法:
    # 默认: 近 7 天, 每天随机 1~30 条
    python scripts/gen_risk_data_with_dates.py

    # 近 30 天, 每天固定 200 条, 循环造到正例 30% (训练用, 推荐)
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos --target-pos-ratio 0.30

    # 每天固定 15 条
    python scripts/gen_risk_data_with_dates.py --per-day 15

    # 每天最多 30 条 (随机 1~30)
    python scripts/gen_risk_data_with_dates.py --max-per-day 30

    # 指定日期范围
    python scripts/gen_risk_data_with_dates.py --start 2026-06-10 --end 2026-06-16 --per-day 20

    # 清空后重建 + 强制 30% 正例
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

# RISK 高风险用户前缀 (跟 gen_risky_users.py 对齐)
RISKY_USER_PREFIX = "RISK"

# 4 类物流事件 + 采样权重
EVENT_TYPES = ["parcel_pickup", "cross_border_ship", "dangerous_declare", "cod_settlement"]
EVENT_WEIGHTS = [4, 2, 2, 2]

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
# 普通路径 picker (balance_pos=True 时 80% 概率从 RISK 用户挑)
# ============================================================
async def _pick_parcel(db, balance_pos: bool, international_only: bool = False) -> tuple | None:
    """挑一个包裹; international_only=True 时只挑国际件. 返回 (parcel_id, user_id)."""
    intl_sql = "AND is_international = 1" if international_only else ""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text(f"""
            SELECT parcel_id, user_id FROM parcel
            WHERE user_id LIKE :prefix {intl_sql}
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.parcel_id, row.user_id)
    r = await db.execute(text(f"""
        SELECT parcel_id, user_id FROM parcel
        WHERE 1=1 {intl_sql}
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.parcel_id, row.user_id) if row else None


async def _pick_declaration(db, balance_pos: bool) -> tuple | None:
    """挑一条危险品申报. 返回 (decl_id, user_id)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT d.decl_id, p.user_id
            FROM dangerous_declaration d JOIN parcel p ON d.parcel_id = p.parcel_id
            WHERE p.user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.decl_id, row.user_id)
    r = await db.execute(text("""
        SELECT d.decl_id, p.user_id
        FROM dangerous_declaration d JOIN parcel p ON d.parcel_id = p.parcel_id
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.decl_id, row.user_id) if row else None


async def _pick_cod(db, balance_pos: bool) -> tuple | None:
    """挑一条 COD 流水. 返回 (cod_id, user_id)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT c.cod_id, p.user_id
            FROM cod_transaction c JOIN parcel p ON c.parcel_id = p.parcel_id
            WHERE p.user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.cod_id, row.user_id)
    r = await db.execute(text("""
        SELECT c.cod_id, p.user_id
        FROM cod_transaction c JOIN parcel p ON c.parcel_id = p.parcel_id
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.cod_id, row.user_id) if row else None


async def _build_normal_request(db, balance_pos: bool) -> RiskCheckRequest | None:
    """普通路径: 按权重随机挑 1 类物流事件并构造请求."""
    evt = random.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0]

    if evt == "parcel_pickup":
        picked = await _pick_parcel(db, balance_pos)
        if not picked:
            return None
        pid, uid = picked
        return RiskCheckRequest(event_type="parcel_pickup", source_id=pid, user_id=uid)

    if evt == "cross_border_ship":
        picked = await _pick_parcel(db, balance_pos, international_only=True)
        if not picked:
            picked = await _pick_parcel(db, balance_pos)
        if not picked:
            return None
        pid, uid = picked
        return RiskCheckRequest(event_type="cross_border_ship", source_id=pid, user_id=uid)

    if evt == "dangerous_declare":
        picked = await _pick_declaration(db, balance_pos)
        if not picked:
            return None
        did, uid = picked
        return RiskCheckRequest(event_type="dangerous_declare", source_id=did, user_id=uid)

    picked = await _pick_cod(db, balance_pos)
    if not picked:
        return None
    cid, uid = picked
    return RiskCheckRequest(event_type="cod_settlement", source_id=cid, user_id=uid)


# ============================================================
# --force-pos-ratio 配套: 强制造"高风险事件"路径
# 选"已知能触发物流高风险规则"的事件 (RISK 危险品申报/COD/国际件/包裹),
# 跑完 process_event 后判断 decision, 如果不是正例就 retry (换其他高风险事件).
# ============================================================
async def _pick_forced_declaration(db) -> RiskCheckRequest | None:
    """强制正例: RISK 危险品申报 (→ R002 危险品瞒报)."""
    r = await db.execute(text("""
        SELECT d.decl_id, p.user_id
        FROM dangerous_declaration d JOIN parcel p ON d.parcel_id = p.parcel_id
        WHERE p.user_id LIKE :prefix
        ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    if not row:
        return None
    return RiskCheckRequest(event_type="dangerous_declare", source_id=row.decl_id, user_id=row.user_id)


async def _pick_forced_cod(db) -> RiskCheckRequest | None:
    """强制正例: RISK 大额 COD (≥1000, → R008 COD 卷款)."""
    r = await db.execute(text("""
        SELECT c.cod_id, p.user_id
        FROM cod_transaction c JOIN parcel p ON c.parcel_id = p.parcel_id
        WHERE p.user_id LIKE :prefix AND c.amount >= 1000
        ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    if not row:
        return None
    return RiskCheckRequest(event_type="cod_settlement", source_id=row.cod_id, user_id=row.user_id)


async def _pick_forced_international(db) -> RiskCheckRequest | None:
    """强制正例: RISK 国际件 (→ R005 跨境违禁品)."""
    r = await db.execute(text("""
        SELECT parcel_id, user_id FROM parcel
        WHERE user_id LIKE :prefix AND is_international = 1
        ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    if not row:
        return None
    return RiskCheckRequest(event_type="cross_border_ship", source_id=row.parcel_id, user_id=row.user_id)


async def _pick_forced_risky_parcel(db) -> RiskCheckRequest | None:
    """强制正例: RISK 普通包裹 (→ R001 未实名 / R018 改派 / R025 大额低报 / R030 黑地址 / R012 同地址高频)."""
    r = await db.execute(text("""
        SELECT parcel_id, user_id FROM parcel
        WHERE user_id LIKE :prefix
        ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    if not row:
        return None
    return RiskCheckRequest(event_type="parcel_pickup", source_id=row.parcel_id, user_id=row.user_id)


# 强制正例 picker 列表 (事件类型, picker)
FORCE_PICKERS = [
    ("dangerous_declare", _pick_forced_declaration),
    ("cod_settlement", _pick_forced_cod),
    ("cross_border_ship", _pick_forced_international),
    ("parcel_pickup", _pick_forced_risky_parcel),
]


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
    在指定日期范围内生成风控评估数据 (异步)
    每天数据量:
        - 指定了 per_day:      每天固定 per_day 条
        - 未指定 per_day:     每天随机 1 ~ max_per_day 条

    live=True: 不回写 create_time, 数据 create_time=now (适合 demo, 仪表盘"今日"能看到)
    live=False (默认): 回写 create_time 到目标日期 (适合训练, 跨天数据更真实)
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

        # 打印每天数据量规则
        if per_day is not None:
            daily_rule = f"每天固定 {per_day} 条"
        else:
            daily_rule = f"每天随机 1~{max_per_day} 条"

        if target_pos_ratio is not None and not balance_pos:
            print(f"⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True
        if balance_pos:
            print(f"⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户")
        if target_pos_ratio is not None:
            print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标")
        if live:
            print(f"📌 --live 模式: 不回写 create_time, 数据 create_time=now, 仪表盘'今日'能看到")
        if force_pos_ratio is not None:
            print(f"[FORCE-POS] --force-pos-ratio 模式: 强制 {force_pos_ratio*100:.0f}% 走高风险事件路径 (RISK 危险品申报/COD/国际件/包裹 + retry)")

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {daily_rule}")

        # 数据池检查
        all_parcels = (await db.execute(text("SELECT COUNT(*) FROM parcel"))).scalar()
        all_decls = (await db.execute(text("SELECT COUNT(*) FROM dangerous_declaration"))).scalar()
        all_cods = (await db.execute(text("SELECT COUNT(*) FROM cod_transaction"))).scalar()
        if not all_parcels:
            print("错误: 数据库里没有包裹数据, 请先跑 init_db.py + gen_risky_users.py")
            return
        print(f"可用包裹: {all_parcels} 票, 危险品申报: {all_decls} 条, COD: {all_cods} 条\n")

        total_days = (end_dt.date() - start_dt.date()).days + 1
        grand_total = 0
        grand_success = 0
        grand_fail = 0
        grand_positive = 0

        for day_offset in range(total_days):
            current_date = start_dt.date() + timedelta(days=day_offset)
            if per_day is not None:
                day_count = per_day
            else:
                day_count = random.randint(1, max_per_day)

            print(f"[{current_date}] 生成 {day_count} 条评估...")

            day_success = 0
            day_fail = 0
            day_positive = 0

            for i in range(day_count):
                random_hour = random.randint(0, 23)
                random_minute = random.randint(0, 59)
                random_second = random.randint(0, 59)
                target_time = datetime.combine(
                    current_date,
                    datetime.min.time(),
                ).replace(hour=random_hour, minute=random_minute, second=random_second)

                # force 模式: 按概率走高风险事件路径
                use_force_pos = (
                    force_pos_ratio is not None
                    and random.random() < force_pos_ratio
                )
                max_tries = 3 if use_force_pos else 1

                for try_idx in range(max_tries):
                    try:
                        if use_force_pos:
                            et, picker = FORCE_PICKERS[try_idx % len(FORCE_PICKERS)]
                            request = await picker(db)
                            if request is None:
                                continue  # 试下一个 picker
                        else:
                            request = await _build_normal_request(db, balance_pos)
                            if request is None:
                                break  # 没有可用数据, 退出当天循环

                        result = await process_event(db, request)

                        # 回写 create_time 到目标日期 (live 模式跳过)
                        backdate_target = None if live else target_time
                        if backdate_target is not None:
                            await backdate_record(db, "risk_event", "create_time", result.event_id, backdate_target)
                            await db.execute(
                                text("UPDATE risk_feature SET compute_time = :t WHERE event_id = :eid"),
                                {"t": backdate_target, "eid": result.event_id},
                            )
                            await backdate_record(db, "risk_assessment", "create_time", result.assessment_id, backdate_target)
                            await db.execute(
                                text("UPDATE risk_case SET create_time = :t WHERE assessment_id = :aid"),
                                {"t": backdate_target, "aid": result.assessment_id},
                            )
                            await db.execute(
                                text("UPDATE risk_user_profile SET last_assessment_time = :t, update_time = :t WHERE user_id = :uid"),
                                {"t": backdate_target, "uid": request.user_id},
                            )

                        await db.commit()
                        day_success += 1
                        grand_success += 1
                        if result.decision in ("拒绝", "人工审核"):
                            day_positive += 1
                            grand_positive += 1
                        break  # 成功, 不再 retry
                    except Exception as e:
                        await db.rollback()
                        day_fail += 1
                        grand_fail += 1
                        _log_failure(target_time, request, e)
                        if not use_force_pos:
                            break  # 普通模式异常不 retry
                        # force 模式: 试下一个高风险 picker

            print(f"  -> 成功 {day_success}, 失败 {day_fail}, 正例 {day_positive}")
            grand_total += day_count

            # target 模式: 每天完成后提示比例不达标
            if target_pos_ratio is not None and day_success > 0:
                current_pos_ratio = day_positive / day_success
                if current_pos_ratio < target_pos_ratio * 0.7:
                    print(f"  ⚠️  今日正例比例 {current_pos_ratio*100:.1f}% < 目标 {target_pos_ratio*100:.0f}% 的 70%, 检查 RISK 用户是否存在")

        print(f"\n{'=' * 50}")
        overall_pos = grand_positive / grand_success * 100 if grand_success else 0
        print(f"完成! 总计 {grand_total} 次, 成功 {grand_success}, 失败 {grand_fail}, 正例 {grand_positive} ({overall_pos:.1f}%)")
        if grand_fail > 0:
            print(f"失败详情见: {FAIL_LOG}")
        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        if overall_pos < 15 and grand_success > 0:
            print(f"⚠️  正例比例仅 {overall_pos:.1f}%, 训练可能假收敛. 建议: --balance-pos --target-pos-ratio 0.30 重造")
        print("刷新仪表盘: http://localhost:8000/")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="带日期范围的造数据脚本 (物流版). 每天条数: --per-day 固定, 或随机 1~--max-per-day"
    )
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD (与 --days 互斥)")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--per-day", type=int, default=None, help="每天固定条数 (不指定则随机)")
    parser.add_argument("--max-per-day", type=int, default=30, help="每天最多多少条 (默认 30, 仅在未指定 --per-day 时生效)")
    parser.add_argument("--clean", action="store_true", help="先清空风控表")
    parser.add_argument("--live", action="store_true",
                        help="不回写 create_time (数据 create_time=now), 适合 demo (仪表盘/趋势图能看到)")
    parser.add_argument("--balance-pos", action="store_true", help="80% 概率挑 RISK 高风险用户, 拉高正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 循环造数到达标")
    parser.add_argument("--force-pos-ratio", type=float, default=None,
                        help="强制每条按此概率走'高风险事件'路径 (RISK 危险品申报/COD/国际件/包裹), "
                             "并 retry 最多 3 次换事件, 保证最终正例比例接近 force_pos_ratio")
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

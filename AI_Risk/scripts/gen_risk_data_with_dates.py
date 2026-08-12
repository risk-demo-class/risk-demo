"""
物流行业风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
从 shipment / shipment_complaint / user_info 里随机选运单, 跑 process_event
生成 risk_event / risk_feature / risk_assessment / risk_case / risk_user_profile

事件类型 (物流域):
  shipment_create   寄件
  shipment_cancel   取消运单
  shipment_receive  签收
  id_verification   实名认证

支持:
  --balance-pos: 80% 概率从高频寄件用户挑 (拉高正例比例)
  --target-pos-ratio: 目标正例比例, 循环造数据直到达标 (最多 10 轮)
  --force-pos-ratio: 强制走高风险路径 (已取消运单 / 投诉运单 / 高申报价值运单 + retry)
  --live: 不回写 create_time, 数据 create_time=now (仪表盘"今日"能看到)
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

RISKY_USER_PREFIX = "RISK"

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
    """清空风控运行态表 (不影响 risk_rule)"""
    print("清空风控运行态表...")
    for tbl in ["risk_feature", "risk_assessment", "risk_event",
                "risk_case", "risk_user_profile", "risk_blacklist"]:
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception as e:
            print(f"  清空 {tbl} 失败 (可能表不存在): {e}")
    await db.commit()


# ============================================================
# Pickers (物流域)
# ============================================================

async def _pick_shipment(db, balance_pos: bool):
    """随机挑一张运单; balance_pos=True 时 80% 概率从高频寄件用户里挑."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT shipment_id, sender_id, dest_address_id
            FROM shipment
            WHERE sender_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.shipment_id, row.sender_id, row.dest_address_id)
        r = await db.execute(text("""
            SELECT s.shipment_id, s.sender_id, s.dest_address_id
            FROM shipment s
            JOIN (
                SELECT sender_id, COUNT(*) AS cnt
                FROM shipment
                GROUP BY sender_id
                ORDER BY cnt DESC
                LIMIT 10
            ) top ON top.sender_id = s.sender_id
            ORDER BY RAND() LIMIT 1
        """))
        row = r.first()
        if row:
            return (row.shipment_id, row.sender_id, row.dest_address_id)
    r = await db.execute(text("""
        SELECT shipment_id, sender_id, dest_address_id
        FROM shipment ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.shipment_id, row.sender_id, row.dest_address_id) if row else None


async def _pick_user(db):
    """随机挑一个用户 (实名认证事件用)."""
    r = await db.execute(text("SELECT user_id FROM user_info ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return row.user_id if row else None


async def _pick_forced_postsale(db):
    """强制正例路径: 已取消运单 (触发取消率规则)."""
    r = await db.execute(text("""
        SELECT shipment_id, sender_id, dest_address_id
        FROM shipment WHERE status = '已取消' ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.shipment_id, row.sender_id, row.dest_address_id) if row else None


async def _pick_forced_logistics_complaint(db):
    """强制正例路径: 有投诉记录的运单 (触发投诉规则)."""
    r = await db.execute(text("""
        SELECT c.shipment_id, c.user_id
        FROM shipment_complaint c
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.shipment_id, row.user_id) if row else None


async def _pick_forced_order_for_high_amount(db):
    """强制正例路径: 高申报价值运单 (触发大额规则)."""
    r = await db.execute(text("""
        SELECT shipment_id, sender_id, dest_address_id
        FROM shipment WHERE declared_value >= 8000 ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.shipment_id, row.sender_id, row.dest_address_id) if row else None


async def _pick_postsale_for_balance(db, balance_pos: bool):
    """兼容旧调用: 挑一张运单 (取消/投诉方向)."""
    return await _pick_shipment(db, balance_pos)


async def _pick_order_for_balance(db, balance_pos: bool):
    """兼容旧调用: 挑一张运单."""
    return await _pick_shipment(db, balance_pos)


def _shipment_request(event_type: str, row) -> RiskCheckRequest:
    shipment_id, user_id, receive_id = row
    return RiskCheckRequest(
        event_type=event_type,
        source_id=shipment_id,
        user_id=user_id,
        order_id=shipment_id,
        receive_id=receive_id,
    )


async def backdate_record(db, table: str, time_col: str, event_id: str, target_time: datetime):
    """把指定记录的时间字段改写成目标时间 (异步)."""
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
    """在指定日期范围内生成风控评估数据 (物流域)."""
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

        if per_day is not None:
            daily_rule = f"每天固定 {per_day} 条"
        else:
            daily_rule = f"每天随机 1~{max_per_day} 条"

        if target_pos_ratio is not None and not balance_pos:
            print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True
        if balance_pos:
            print("⚠️  --balance-pos 模式: 80% 概率挑高频寄件用户")
        if target_pos_ratio is not None:
            print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标 (最多 10 轮)")
        if live:
            print("📌 --live 模式: 不回写 create_time, 数据 create_time=now, 仪表盘'今日'能看到")
        if force_pos_ratio is not None:
            print(f"[FORCE-POS] --force-pos-ratio 模式: 强制 {force_pos_ratio*100:.0f}% 走高风险事件路径 (已取消/投诉/高额运单 + retry)")

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {daily_rule}")

        # 检查业务数据
        shipment_count = (await db.execute(text("SELECT COUNT(*) FROM shipment"))).scalar() or 0
        if not shipment_count:
            print("错误: 数据库里没有运单数据, 请先跑 init_logistics_db.py / gen_logistics_data.py")
            return
        print(f"可用运单: {shipment_count} 条\n")

        total_days = (end_dt.date() - start_dt.date()).days + 1
        grand_success = 0
        grand_positive = 0

        for day_offset in range(total_days):
            current_date = start_dt.date() + timedelta(days=day_offset)
            if per_day is not None:
                day_count = per_day
            else:
                day_count = random.randint(1, max_per_day)

            print(f"[{current_date}] 生成 {day_count} 条评估...")

            day_success = 0
            day_positive = 0

            for _i in range(day_count):
                random_hour = random.randint(0, 23)
                random_minute = random.randint(0, 59)
                random_second = random.randint(0, 59)
                target_time = datetime.combine(
                    current_date, datetime.min.time()
                ).replace(hour=random_hour, minute=random_minute, second=random_second)

                use_force_pos = (
                    force_pos_ratio is not None
                    and random.random() < force_pos_ratio
                )
                if use_force_pos:
                    pickers = [
                        ("shipment_cancel", _pick_forced_postsale, "shipment"),
                        ("shipment_create", _pick_forced_logistics_complaint, "complaint"),
                        ("shipment_create", _pick_forced_order_for_high_amount, "shipment"),
                    ]
                    random.shuffle(pickers)
                max_tries = 3 if use_force_pos else 1

                for try_idx in range(max_tries):
                    if use_force_pos:
                        et, picker, ptype = pickers[try_idx % len(pickers)]
                        picked = await picker(db)
                        if picked is None:
                            continue
                        if ptype == "complaint":
                            shipment_id, user_id = picked
                            request = RiskCheckRequest(
                                event_type="shipment_create",
                                source_id=shipment_id,
                                user_id=user_id,
                                order_id=shipment_id,
                            )
                        else:
                            request = _shipment_request(et, picked)
                    else:
                        roll = random.random()
                        if roll < 0.15 and (await db.execute(
                            text("SELECT COUNT(*) FROM shipment WHERE status='已取消'")
                        )).scalar():
                            picked = await _pick_forced_postsale(db)
                            if picked:
                                request = _shipment_request("shipment_cancel", picked)
                            else:
                                continue
                        elif roll < 0.30:
                            picked = await _pick_shipment(db, balance_pos)
                            if not picked:
                                continue
                            request = _shipment_request("shipment_receive", picked)
                        elif roll < 0.45:
                            user_id = await _pick_user(db)
                            if not user_id:
                                continue
                            request = RiskCheckRequest(
                                event_type="id_verification",
                                source_id=user_id,
                                user_id=user_id,
                            )
                        else:
                            picked = await _pick_shipment(db, balance_pos)
                            if not picked:
                                continue
                            request = _shipment_request("shipment_create", picked)

                    try:
                        result = await process_event(db, request)
                        success_done = True
                        # 回写时间 (非 live 模式)
                        if not live:
                            await backdate_record(db, "risk_event", "create_time", result.event_id, target_time)
                            await backdate_record(db, "risk_assessment", "create_time", result.assessment_id, target_time)
                        day_success += 1
                        if result.decision in ("拒绝", "人工审核"):
                            day_positive += 1
                        if target_pos_ratio is None:
                            print(f"  [{_i+1}/{day_count}] {request.event_type} 用户={request.user_id}, "
                                  f"评分={result.final_score}, 决策={result.decision}, "
                                  f"命中={result.rule_count}条规则")
                        break
                    except Exception as e:
                        if target_pos_ratio is None:
                            print(f"  [{_i+1}/{day_count}] 失败: {e}")
                        _log_failure(target_time, request, e)

            # 提交回写
            await db.commit()

            current_ratio = day_positive / day_success if day_success else 0.0
            print(f"  [{current_date}] 成功 {day_success} 条, 正例 {day_positive} 条 ({current_ratio*100:.1f}%)")
            grand_success += day_success
            grand_positive += day_positive

            # target 模式: 达标即可提前退出; 普通模式跑完所有天
            if target_pos_ratio is not None and day_success and current_ratio >= target_pos_ratio:
                break

        grand_ratio = grand_positive / grand_success if grand_success else 0.0
        print(f"\n完成! 成功生成 {grand_success} 条风控评估记录, 正例 {grand_positive} 条 ({grand_ratio*100:.1f}%)")


async def _runner(args):
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="物流风控 - 造评估数据 (--balance-pos 优先挑高频寄件用户, 拉高正例比例)."
    )
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--per-day", type=int, default=None, help="每天固定多少条")
    parser.add_argument("--max-per-day", type=int, default=30,
                        help="每天最多多少条 (默认 30, 仅在未指定 --per-day 时生效)")
    parser.add_argument("--start", type=str, default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--clean", action="store_true", help="先清空风控表")
    parser.add_argument("--live", action="store_true",
                        help="不回写 create_time (数据 create_time=now), 适合 demo (仪表盘'今日'能看到)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="80% 概率挑高频寄件用户, 拉高正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 循环造数据直到达标")
    parser.add_argument("--force-pos-ratio", type=float, default=None,
                        help="强制按此概率走'高风险事件'路径 (已取消/投诉/高额运单), 并 retry 最多 3 次")
    args = parser.parse_args()
    asyncio.run(_runner(args))

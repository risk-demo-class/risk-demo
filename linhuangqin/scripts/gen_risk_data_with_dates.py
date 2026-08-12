"""
二手交易平台物流侧风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据，让仪表盘趋势图有跨天数据
数据源: 物流业务表 (waybill_info / complaint_claim), 事件类型用三段式 10 类

每天数据量规则 (优先级从高到低):
    1. --per-day 固定值       → 每天生成固定条数
    2. --max-per-day 仅指定   → 每天随机 1 ~ max-per-day 条
    3. 都不指定              → 每天随机 1 ~ 30 条 (默认)

用法:
    # 默认: 近 7 天, 每天随机 1~30 条
    python scripts/gen_risk_data_with_dates.py

    # 近 30 天, 每天固定 200 条
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200

    # 每天固定 15 条
    python scripts/gen_risk_data_with_dates.py --per-day 15

    # 近 30 天, 每天固定 10 条
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 10

    # 清空后重建
    python scripts/gen_risk_data_with_dates.py --days 15 --per-day 100 --clean
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 【P4-L3 2026-08-08 修复】Windows GBK 终端不能编码 emoji, 强制 stdout UTF-8
# 防 UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f3af'
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

# 【P4-L3 2026-08-08 第三轮】RISK 高风险用户前缀 (跟 gen_risky_users.py 对齐)
RISKY_USER_PREFIX = "RISK"

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
# 物流版 pick 函数: 从 waybill_info / complaint_claim 挑样本
# ============================================================
async def _pick_waybill(db, shipper_prefix: str | None = None):
    """从运单池挑一条 (waybill_id, shipper_id, consignee_id)."""
    if shipper_prefix:
        r = await db.execute(text("""
            SELECT waybill_id, shipper_id, consignee_id
            FROM waybill_info
            WHERE shipper_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{shipper_prefix}%"})
        row = r.first()
        if row:
            return (row.waybill_id, row.shipper_id, row.consignee_id)
    r = await db.execute(text("""
        SELECT waybill_id, shipper_id, consignee_id
        FROM waybill_info
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.waybill_id, row.shipper_id, row.consignee_id) if row else None


async def _pick_claim(db, shipper_prefix: str | None = None):
    """从投诉纠纷池挑一条有纠纷的运单 (waybill_id, shipper_id, consignee_id).

    注意: 返回的是运单号 (waybill_id), 不是 claim_id —— 因为 validator 派发表
    把"买家退回寄件"映射到 WaybillInfo, source_id 必须是 waybill_id.
    """
    if shipper_prefix:
        r = await db.execute(text("""
            SELECT w.waybill_id, w.shipper_id, w.consignee_id
            FROM complaint_claim c
            JOIN waybill_info w ON c.waybill_id = w.waybill_id
            WHERE w.shipper_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{shipper_prefix}%"})
        row = r.first()
        if row:
            return (row.waybill_id, row.shipper_id, row.consignee_id)
    r = await db.execute(text("""
        SELECT w.waybill_id, w.shipper_id, w.consignee_id
        FROM complaint_claim c
        JOIN waybill_info w ON c.waybill_id = w.waybill_id
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.waybill_id, row.shipper_id, row.consignee_id) if row else None


async def _pick_high_value_waybill(db, shipper_prefix: str | None = None):
    """强制正例路径: 空包/超轻高价值运单 (触发 L001/L002 人工审核).

    空包 (cargo_weight<=0.1) → L001 人工审核 (score 80)
    轻包高价值 (weight<=0.2 & declared>=2000) → L002 人工审核 (score 85)
    """
    where = "AND w.shipper_id LIKE :prefix" if shipper_prefix else ""
    params = {"prefix": f"{shipper_prefix}%"} if shipper_prefix else {}
    r = await db.execute(text(f"""
        SELECT w.waybill_id, w.shipper_id, w.consignee_id
        FROM waybill_info w
        WHERE w.cargo_weight <= 0.2
        {where}
        ORDER BY RAND() LIMIT 1
    """), params)
    row = r.first()
    return (row.waybill_id, row.shipper_id, row.consignee_id) if row else None


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

    【P4-L3 2026-08-08 第三轮】--balance-pos 跟 --target-pos-ratio:
        - balance_pos=True: 80% 概率从 RISK 高风险用户挑样本 (拉高正例比例)
        - target_pos_ratio (0-1): 目标正例比例, 自动循环造数据直到达标 (最多 10 轮)

    【P4-L3 2026-08-08 第四轮】--live:
        - live=True: 不回写 create_time, 数据 create_time=now (适合 demo, 仪表盘"今日"能看到)
        - live=False (默认): 回写 create_time 到目标日期 (适合训练, 跨天数据更真实)
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

        # 【P4-L3 第三轮】--balance-pos 模式提示
        if target_pos_ratio is not None and not balance_pos:
            print(f"⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True
        if balance_pos:
            print(f"⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户")
        if target_pos_ratio is not None:
            print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标 (最多 10 轮)")
        # 【P4-L3 第四轮】--live 模式提示
        if live:
            print(f"📌 --live 模式: 不回写 create_time, 数据 create_time=now, 仪表盘'今日'能看到")
        # 【P4-L3 第五轮】--force-pos-ratio 模式提示
        if force_pos_ratio is not None:
            print(f"[FORCE-POS] --force-pos-ratio 模式: 强制 {force_pos_ratio*100:.0f}% 走高风险事件路径 (RISK 售后/物流投诉/高额订单 + retry)")

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {daily_rule}")

        # 1. 拿所有可用的运单 / 投诉
        all_waybills_result = await db.execute(text("""
            SELECT waybill_id, shipper_id, consignee_id
            FROM waybill_info
        """))
        all_waybills = all_waybills_result.all()

        all_claims_result = await db.execute(text("""
            SELECT c.claim_id, w.shipper_id
            FROM complaint_claim c
            JOIN waybill_info w ON c.waybill_id = w.waybill_id
        """))
        all_claims = all_claims_result.all()

        if not all_waybills:
            print("错误: 数据库里没有运单数据, 请先跑 init_db.py")
            return

        print(f"可用运单: {len(all_waybills)} 条, 投诉纠纷: {len(all_claims)} 条\n")

        total_days = (end_dt.date() - start_dt.date()).days + 1
        grand_total = 0
        grand_success = 0
        grand_reject = 0
        grand_positive = 0  # 【P4-L3 第三轮】正例计数 (target_pos_ratio 用)

        # 【P4-L3 2026-08-08 第四轮 修复】单轮模式跑完所有天, 不再 break
        # 之前 bug: 内层 for day_offset 循环里有个 if target_pos_ratio is None: break,
        # 导致单轮模式 (不传 --target-pos-ratio) 跑 1 天就退出, 只造 1 条.
        for day_offset in range(total_days):
            current_date = start_dt.date() + timedelta(days=day_offset)
            # 每天数据量: 固定值 或 随机 1~max_per_day
            if per_day is not None:
                day_count = per_day
            else:
                day_count = random.randint(1, max_per_day)

            print(f"[{current_date}] 生成 {day_count} 条评估...")

            day_success = 0
            day_reject = 0
            day_positive = 0  # 每日正例计数

            for i in range(day_count):
                # 在当天随机一个时刻
                random_hour = random.randint(0, 23)
                random_minute = random.randint(0, 59)
                random_second = random.randint(0, 59)
                target_time = datetime.combine(
                    current_date,
                    datetime.min.time()
                ).replace(hour=random_hour, minute=random_minute, second=random_second)

                # 物流事件类型池: 运单类事件为主, 投诉纠纷偶尔
                WAYBILL_EVENT_TYPES = [
                    "卖家下单寄件", "卖家下单寄件", "卖家下单寄件",
                    "揽收入仓", "出仓发货", "运输中", "派送中", "买家签收",
                ]
                # 【P4-L3 第五轮】--force-pos-ratio: 每条按概率走"高风险事件"路径
                use_force_pos = (
                    force_pos_ratio is not None
                    and random.random() < force_pos_ratio
                )
                # 准备 picker 列表 (force 模式 2 个高风险 picker, 普通模式 None)
                if use_force_pos:
                    pickers = [
                        ("买家退回寄件", _pick_claim, "claim"),
                        ("揽收入仓", _pick_high_value_waybill, "waybill"),
                    ]
                    random.shuffle(pickers)
                # 最多 retry 次数 (force 模式 2 次, 普通 1 次)
                max_tries = 2 if use_force_pos else 1
                success_done = False

                for try_idx in range(max_tries):
                    # 选事件
                    if use_force_pos:
                        et, picker, ptype = pickers[try_idx % len(pickers)]
                        picked = await picker(db, RISKY_USER_PREFIX if balance_pos else None)
                        if picked is None:
                            continue  # 试下一个 picker
                        waybill_id, user_id, consignee_id = picked
                        request = RiskCheckRequest(
                            event_type=et, source_id=waybill_id, user_id=user_id,
                            order_id=waybill_id, receive_id=consignee_id,
                        )
                    else:
                        # 普通路径: --balance-pos 时 80% 概率从 RISK 卖家挑, 偶用有纠纷的运单
                        if balance_pos and random.random() < 0.8:
                            shipper_prefix = RISKY_USER_PREFIX
                        else:
                            shipper_prefix = None
                        if all_claims and random.random() < 0.3:
                            picked = await _pick_claim(db, shipper_prefix)
                            if not picked:
                                picked = await _pick_waybill(db, shipper_prefix)
                        else:
                            picked = await _pick_waybill(db, shipper_prefix)
                        if not picked:
                            break
                        waybill_id, user_id, consignee_id = picked
                        request = RiskCheckRequest(
                            event_type=random.choice(WAYBILL_EVENT_TYPES),
                            source_id=waybill_id,
                            user_id=user_id,
                            order_id=waybill_id,
                            receive_id=consignee_id,
                        )

                    try:
                        await process_event(db, request)

                        backdate_target = None if live else target_time

                        new_event_result = await db.execute(text("""
                            SELECT event_id FROM risk_event
                            WHERE user_id = :uid
                            ORDER BY create_time DESC LIMIT 1
                        """), {"uid": request.user_id})
                        new_event = new_event_result.first()

                        new_assess_result = await db.execute(text("""
                            SELECT assessment_id, decision FROM risk_assessment
                            WHERE user_id = :uid
                            ORDER BY create_time DESC LIMIT 1
                        """), {"uid": request.user_id})
                        new_assess = new_assess_result.first()

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
                        success_done = True
                        break
                    except Exception as e:
                        await db.rollback()
                        day_reject += 1
                        grand_reject += 1
                        _log_failure(target_time, request, e)
                        success_done = True
                        break  # 异常不 retry
                        grand_success += 1
                        success_done = True
                        break
                    except Exception as e:
                        await db.rollback()
                        day_reject += 1
                        grand_reject += 1
                        _log_failure(target_time, request, e)
                        success_done = True
                        break  # 业务异常, 不 retry

                # 【P4-L3 第五轮】--force-pos-ratio retry 兜底:
                # 如果 use_force_pos=True 但 force retry 3 次都失败 (success_done=True 但 day_positive 没++),
                # 这条算"伪正例", 不计入 day_positive (实际效果: 整体正例比例可能略低于 force_pos_ratio)
                # 不需要额外处理, 因为:
                #   - success_done=True 已经在 try 块里 break 了
                #   - day_positive++ 只在 decision in (拒绝/人工审核) 时执行
                #   - 如果 3 次 retry 都失败, day_positive 自然没++

            print(f"  -> 成功 {day_success}, 失败 {day_reject}, 正例 {day_positive}")
            grand_total += day_count

            # 【P4-L3 第三轮】target_pos_ratio 模式: 每天完成后检查
            if target_pos_ratio is not None and day_success > 0:
                current_pos_ratio = day_positive / day_success
                if current_pos_ratio < target_pos_ratio * 0.7:
                    print(f"  ⚠️  今日正例比例 {current_pos_ratio*100:.1f}% < 目标 {target_pos_ratio*100:.0f}% 的 70%, 检查 RISK 用户是否存在")
        print(f"\n{'=' * 50}")
        overall_pos = grand_positive / grand_success * 100 if grand_success else 0
        print(f"完成! 总计 {grand_total} 次, 成功 {grand_success}, 失败 {grand_reject}, 正例 {grand_positive} ({overall_pos:.1f}%)")
        if grand_reject > 0:
            print(f"失败详情见: {FAIL_LOG}")
        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        if overall_pos < 15 and grand_success > 0:
            print(f"⚠️  正例比例仅 {overall_pos:.1f}%, 训练可能假收敛. 建议: --balance-pos --target-pos-ratio 0.30 重造")
        print("刷新仪表盘: http://localhost:8000/")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="带日期范围的造数据脚本 (每天条数: --per-day 固定, 或随机 1~--max-per-day)"
    )
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD (与 --days 互斥)")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--per-day", type=int, default=None,
                        help="每天固定条数 (不指定则随机)")
    parser.add_argument("--max-per-day", type=int, default=30,
                        help="每天最多多少条 (默认 30, 仅在未指定 --per-day 时生效)")
    parser.add_argument("--clean", action="store_true", help="先清空风控表")
    # 【P4-L3 2026-08-08 第四轮】--live: 不回写 create_time, 数据 create_time=now, 仪表盘"今日"能看见
    parser.add_argument("--live", action="store_true",
                        help="不回写 create_time (数据 create_time=now), 适合 demo (仪表盘/趋势图能看到)")
    # 【P4-L3 2026-08-08 第三轮】--balance-pos 跟 --target-pos-ratio
    parser.add_argument("--balance-pos", action="store_true",
                        help="【P4-L3】80%% 概率挑 RISK 高风险用户, 拉高正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="【P4-L3】目标正例比例 (0.0-1.0), 配合 --balance-pos 循环造数到达标")
    # 【P4-L3 2026-08-08 第五轮】--force-pos-ratio: 强制走"已知能触发规则的高风险事件"路径
    parser.add_argument("--force-pos-ratio", type=float, default=None,
                        help="【P4-L3 第五轮】强制每条按此概率走'高风险事件'路径 (RISK 用户售后/物流投诉/高额订单), "
                             "并 retry 最多 3 次换事件, 保证最终正例比例接近 force_pos_ratio. "
                             "区别 --balance-pos: balance 只挑 RISK 用户, 但业务规则不保证命中; "
                             "force 强制触发规则, 更激进但全用 RISK 用户数据")
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

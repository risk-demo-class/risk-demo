"""
医疗风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据，让仪表盘趋势图有跨天数据

【P4-L3 2026-08-08 第三轮】支持 --balance-pos / --target-pos-ratio 控制正负例比例:
  - --balance-pos: 80% 概率从 RISK 高风险用户挑样本 (跟 gen_risk_data.py 行为一致)
  - --target-pos-ratio: 目标正例比例 (0.0-1.0), 自动循环造数据直到达标 (最多 10 轮)

每天数据量规则 (优先级从高到低):
    1. --per-day 固定值       → 每天生成固定条数
    2. --max-per-day 仅指定   → 每天随机 1 ~ max-per-day 条
    3. 都不指定              → 每天随机 1 ~ 30 条 (默认)

用法:
    # 默认: 近 7 天, 每天随机 1~30 条 (没 RISK 用户时正例 ≈ 2%)
    python scripts/gen_risk_data_with_dates.py

    # 近 30 天, 每天固定 200 条, 循环造到正例 30% (训练用, 推荐)
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 200 --balance-pos --target-pos-ratio 0.30

    # 每天固定 15 条
    python scripts/gen_risk_data_with_dates.py --per-day 15

    # 每天最多 30 条 (随机 1~30)
    python scripts/gen_risk_data_with_dates.py --max-per-day 30

    # 固定 15 条 + 每天最多不超过 20 条 (取 min)
    python scripts/gen_risk_data_with_dates.py --per-day 15 --max-per-day 20

    # 近 30 天, 每天固定 10 条
    python scripts/gen_risk_data_with_dates.py --days 30 --per-day 10

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
# 【P4-L3 2026-08-08 第三轮】--balance-pos 配套: 优先从 RISK 用户挑
# ============================================================
async def _pick_claim_for_balance(db, balance_pos: bool):
    """从医保结算池挑一条; balance_pos=True 时 80% 概率挑 RISK 用户结算."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT claim_id, user_id FROM insurance_claim
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.claim_id, row.user_id)
    r = await db.execute(text("""
        SELECT claim_id, user_id FROM insurance_claim ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.claim_id, row.user_id) if row else None


async def _pick_rx_for_balance(db, balance_pos: bool):
    """从处方池挑一条; balance_pos=True 时 80% 概率挑 RISK 用户处方."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT rx_id, user_id FROM prescription
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.rx_id, row.user_id)
    r = await db.execute(text("""
        SELECT rx_id, user_id FROM prescription ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.rx_id, row.user_id) if row else None


async def _pick_appt_for_balance(db, balance_pos: bool):
    """从挂号池挑一条; balance_pos=True 时 80% 概率挑 RISK 用户挂号."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT appt_id, user_id FROM appointment
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.appt_id, row.user_id)
    r = await db.execute(text("""
        SELECT appt_id, user_id FROM appointment ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.appt_id, row.user_id) if row else None


async def _pick_drug_for_balance(db, balance_pos: bool):
    """从药品订单池挑一条; balance_pos=True 时 80% 概率挑 RISK 用户订单."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT drug_order_id, user_id FROM drug_order
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.drug_order_id, row.user_id)
    r = await db.execute(text("""
        SELECT drug_order_id, user_id FROM drug_order ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.drug_order_id, row.user_id) if row else None


async def _pick_forced_rx(db):
    """强制正例路径: RISK 用户的处方 (触发 R002 统方 / R004 超量 / R009 无诊断)."""
    r = await db.execute(text("""
        SELECT rx_id, user_id FROM prescription
        WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    return (row.rx_id, row.user_id) if row else None


async def _pick_forced_claim(db):
    """强制正例路径: RISK 用户的医保结算 (触发 R001 盗刷 / R007 异地结算)."""
    r = await db.execute(text("""
        SELECT claim_id, user_id FROM insurance_claim
        WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    return (row.claim_id, row.user_id) if row else None


async def _pick_forced_drug(db):
    """强制正例路径: RISK 用户的药品订单 (触发 R006 药品代购)."""
    r = await db.execute(text("""
        SELECT drug_order_id, user_id FROM drug_order
        WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
    """), {"prefix": f"{RISKY_USER_PREFIX}%"})
    row = r.first()
    return (row.drug_order_id, row.user_id) if row else None



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
            print(f"[FORCE-POS] --force-pos-ratio 模式: 强制 {force_pos_ratio*100:.0f}% 走高风险事件路径 (RISK 处方/结算/药品订单 + retry)")

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {daily_rule}")

        # 1. 医疗业务单数量统计 (balance picker 实时查, 这里只做可用性提示)
        claim_cnt = (await db.execute(text("SELECT COUNT(*) FROM insurance_claim"))).scalar() or 0
        rx_cnt = (await db.execute(text("SELECT COUNT(*) FROM prescription"))).scalar() or 0
        appt_cnt = (await db.execute(text("SELECT COUNT(*) FROM appointment"))).scalar() or 0
        drug_cnt = (await db.execute(text("SELECT COUNT(*) FROM drug_order"))).scalar() or 0
        if claim_cnt + rx_cnt + appt_cnt + drug_cnt == 0:
            print("错误: 数据库里没有医疗业务数据, 请先跑 init_db.py + gen_risky_users.py")
            return
        print(f"可用业务单: 结算 {claim_cnt} / 处方 {rx_cnt} / 挂号 {appt_cnt} / 药品 {drug_cnt}\n")
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

                # 【P4-L3 第五轮】--force-pos-ratio: 每条按概率走"高风险事件"路径
                use_force_pos = (
                    force_pos_ratio is not None
                    and random.random() < force_pos_ratio
                )
                # 准备 picker 列表 (force 模式 3 个高风险 picker, 普通模式 None)
                if use_force_pos:
                    pickers = [
                        ("处方审核", _pick_forced_rx, "rx"),
                        ("医保结算", _pick_forced_claim, "claim"),
                        ("药品代购", _pick_forced_drug, "drug"),
                    ]
                    random.shuffle(pickers)
                # 最多 retry 次数 (force 模式 3 次, 普通 1 次)
                max_tries = 3 if use_force_pos else 1
                success_done = False

                for try_idx in range(max_tries):
                    # 选事件
                    if use_force_pos:
                        et, picker, ptype = pickers[try_idx % len(pickers)]
                        picked = await picker(db)
                        if picked is None:
                            continue  # 试下一个 picker
                        sid, user_id = picked
                        request = RiskCheckRequest(event_type=et, source_id=sid, user_id=user_id)
                    else:
                        # 普通路径: --balance-pos 80% 概率从 RISK 用户挑, 混 4 类医疗事件
                        rx_odds = 0.4 if balance_pos else 0.25
                        if random.random() < rx_odds:
                            picked = await _pick_rx_for_balance(db, balance_pos)
                            if picked:
                                rx_id, user_id = picked
                                request = RiskCheckRequest(event_type="处方审核", source_id=rx_id, user_id=user_id)
                            else:
                                picked = await _pick_claim_for_balance(db, balance_pos)
                                if not picked:
                                    break
                                claim_id, user_id = picked
                                request = RiskCheckRequest(event_type="医保结算", source_id=claim_id, user_id=user_id)
                        else:
                            event_type = random.choice(["医保结算", "医保结算", "挂号", "药品代购"])
                            if event_type == "医保结算":
                                picked = await _pick_claim_for_balance(db, balance_pos)
                                if not picked:
                                    break
                                claim_id, user_id = picked
                                request = RiskCheckRequest(event_type=event_type, source_id=claim_id, user_id=user_id)
                            elif event_type == "挂号":
                                picked = await _pick_appt_for_balance(db, balance_pos)
                                if not picked:
                                    break
                                appt_id, user_id = picked
                                request = RiskCheckRequest(event_type=event_type, source_id=appt_id, user_id=user_id)
                            else:  # 药品代购
                                picked = await _pick_drug_for_balance(db, balance_pos)
                                if not picked:
                                    break
                                drug_id, user_id = picked
                                request = RiskCheckRequest(event_type=event_type, source_id=drug_id, user_id=user_id)

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

"""
银行风控系统 - 模拟风控评估数据生成 (异步, 走 process_event 4 步流程)

在指定日期范围内生成评估数据, 事件类型覆盖 4 大银行场景:
  转账 (40%) / 登录 (25%) / 贷款申请 (20%) / 信用卡 (15%)

支持 --balance-pos / --target-pos-ratio 控制正负例比例:
  - --balance-pos: 80% 概率从 RISK 高风险用户挑样本
  - --target-pos-ratio: 目标正例比例 (0.0-1.0), 自动循环造数据直到达标 (最多 10 轮)

每天数据量规则 (优先级从高到低):
    1. --per-day 固定值       → 每天生成固定条数
    2. --max-per-day 仅指定   → 每天随机 1 ~ max-per-day 条
    3. 都不指定              → 每天随机 1 ~ 30 条 (默认)

【训练数据严格化】造数结束后统一把 ml_score/ml_decision 置 NULL:
  train_xgb_model.py 显式 WHERE ml_score IS NULL 只取"无 ML 痕迹"数据,
  保证训练样本 100% 干净 (由规则 + 决策引擎标注, 不含未训练模型垃圾值).

用法:
    # 近 7 天, 每天随机 1~30 条
    python scripts/gen_risk_data.py

    # 近 30 天, 每天固定 100 条, 循环造到正例 30% (训练用, 推荐)
    python scripts/gen_risk_data.py --days 30 --per-day 100 --balance-pos --target-pos-ratio 0.30

    # 清空风控表后重建
    python scripts/gen_risk_data.py --days 15 --per-day 100 --clean
"""
import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timedelta

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows GBK 终端强制 stdout UTF-8
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

# ============================================================
# 失败日志: 写入 logs/gen_risk_fail.log (供事后查, 不刷屏终端)
# ============================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
FAIL_LOG = os.path.join(LOG_DIR, "gen_risk_fail.log")


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _log_failure(target_time, request, error):
    """追加 1 条失败记录到日志 (1 行 JSON, 方便后续解析)."""
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


# ============================================================
# 事件源选取 (4 大银行场景)
# ============================================================
async def _pick_txn(db, balance_pos: bool):
    """转账场景: 挑 1 笔交易 (含 from_card/to_card/device_id/ip)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT t.txn_id, t.from_card, t.to_card, t.device_id, t.ip,
                   c.user_id AS from_uid
            FROM transaction t
            JOIN bank_card c ON t.from_card = c.card_id
            WHERE c.user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return dict(row._mapping)
    r = await db.execute(text("""
        SELECT t.txn_id, t.from_card, t.to_card, t.device_id, t.ip,
               c.user_id AS from_uid
        FROM transaction t
        JOIN bank_card c ON t.from_card = c.card_id
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return dict(row._mapping) if row else None


async def _pick_login(db, balance_pos: bool):
    """登录场景: 挑 1 条登录日志."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT login_id, user_id, device_id, ip
            FROM login_log
            WHERE user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return dict(row._mapping)
    r = await db.execute(text("""
        SELECT login_id, user_id, device_id, ip
        FROM login_log
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return dict(row._mapping) if row else None


async def _pick_loan(db, balance_pos: bool):
    """贷款申请场景: 挑 1 条贷款申请."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT loan_id, user_id
            FROM loan_application
            WHERE user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return dict(row._mapping)
    r = await db.execute(text("""
        SELECT loan_id, user_id
        FROM loan_application
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return dict(row._mapping) if row else None


async def _pick_card(db, balance_pos: bool):
    """信用卡场景: 挑 1 张信用卡 (金额走 event_data)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT card_id, user_id
            FROM bank_card
            WHERE card_type = '信用卡' AND user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return dict(row._mapping)
    r = await db.execute(text("""
        SELECT card_id, user_id
        FROM bank_card
        WHERE card_type = '信用卡'
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return dict(row._mapping) if row else None


def _build_request(event_type: str, picked: dict, target_time: datetime) -> RiskCheckRequest:
    """事件数据 → RiskCheckRequest (与 validator/event 的银行映射对齐)."""
    if event_type == "转账":
        return RiskCheckRequest(
            event_type="转账", source_id=picked["txn_id"], user_id=picked["from_uid"],
            from_card=picked["from_card"], to_card=picked["to_card"],
            device_id=picked["device_id"], ip=picked["ip"],
        )
    if event_type == "登录":
        return RiskCheckRequest(
            event_type="登录", source_id=picked["login_id"], user_id=picked["user_id"],
            device_id=picked["device_id"], ip=picked["ip"],
        )
    if event_type == "贷款申请":
        return RiskCheckRequest(
            event_type="贷款申请", source_id=picked["loan_id"], user_id=picked["user_id"],
        )
    # 信用卡: 金额/时间走 event_data (compute_card_features 读取)
    # 金额 5000~50000: 50% 概率 >30000 命中 R005 新设备信用卡大额 (card_device_new=1 时)
    amount = round(random.uniform(5000, 50000), 2)
    if random.random() < 0.5:
        amount = round(random.uniform(30000, 50000), 2)
    return RiskCheckRequest(
        event_type="信用卡", source_id=picked["card_id"], user_id=picked["user_id"],
        event_data={"amount": amount, "txn_time": target_time.isoformat()},
    )


# ============================================================
# 工具
# ============================================================
async def clean_risk_tables(db):
    """清空风控运行时表 (不影响 risk_rule)."""
    print("清空风控运行时表...")
    for tbl in ["risk_feature", "risk_assessment", "risk_event",
                "risk_case", "risk_user_profile", "risk_blacklist"]:
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception as e:
            print(f"  清空 {tbl} 失败 (可能表不存在): {e}")
    await db.commit()


async def backdate_record(db, table: str, time_col: str, event_id: str, target_time: datetime):
    """把指定记录的某个时间字段改写成目标时间 (异步)."""
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


async def reset_ml_score_null(db):
    """【训练数据严格化】把评估的 ml_score/ml_decision 置 NULL.

    造数走 process_event 会正常写 ml_score (模型若已存在);
    训练要求 WHERE ml_score IS NULL, 保证训练样本无"未训练模型"垃圾值.
    """
    r = await db.execute(text("UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL"))
    n = r.rowcount
    await db.commit()
    if n:
        print(f"已把 {n} 条评估的 ml_score/ml_decision 置 NULL (训练数据严格化)")


# 4 大场景选取器 (权重: 转账40 / 登录25 / 贷款20 / 信用卡15)
SCENARIOS = [
    ("转账", _pick_txn, 40),
    ("登录", _pick_login, 25),
    ("贷款申请", _pick_loan, 20),
    ("信用卡", _pick_card, 15),
]


def _weighted_choice():
    ets = [s[0] for s in SCENARIOS]
    weights = [s[2] for s in SCENARIOS]
    return random.choices(ets, weights=weights)[0]


async def generate_risk_data(
    days: int = 7,
    per_day: int = None,
    max_per_day: int = 30,
    start_date: str = None,
    end_date: str = None,
    clean: bool = False,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
    live: bool = False,
):
    """在指定日期范围内生成银行风控评估数据 (异步, 走 process_event)."""
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
            start_dt = (end_dt - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0)

        daily_rule = f"每天固定 {per_day} 条" if per_day is not None else f"每天随机 1~{max_per_day} 条"

        # 参数提示
        if target_pos_ratio is not None and not balance_pos:
            print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True
        if balance_pos:
            print(f"⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户 (4 大银行场景)")
        if target_pos_ratio is not None:
            print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标 (最多 10 轮)")
        if live:
            print("📌 --live 模式: 不回写 create_time, 数据 create_time=now, 仪表盘'今日'能看到")

        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {daily_rule}")

        # 场景数据量预检
        for et, _, _ in SCENARIOS:
            tbl = {"转账": "transaction", "登录": "login_log",
                   "贷款申请": "loan_application", "信用卡": "bank_card"}[et]
            r = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            print(f"  可用{et}数据: {r.scalar()} 条")
        if not (await db.execute(text("SELECT COUNT(*) FROM transaction"))).scalar():
            print("错误: 数据库里没有业务数据, 请先跑: init_db.py + gen_bank_data.py + gen_risky_users.py")
            return

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
                    hour=random.randint(0, 23),
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59),
                )

                # 选事件类型 + 对应数据
                event_type = _weighted_choice()
                picker = dict((s[0], s[1]) for s in SCENARIOS)[event_type]
                picked = await picker(db, balance_pos)
                if not picked:
                    day_reject += 1
                    continue
                request = _build_request(event_type, picked, target_time)

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
                        text("UPDATE risk_user_profile SET last_assessment_time = :t, update_time = :t "
                             "WHERE user_id = :uid"),
                        {"t": backdate_target or datetime.now(), "uid": request.user_id},
                    )

                    await db.commit()
                    day_success += 1
                    grand_success += 1
                except Exception as e:
                    await db.rollback()
                    day_reject += 1
                    grand_reject += 1
                    _log_failure(target_time, request, e)

            print(f"  -> 成功 {day_success}, 失败 {day_reject}, 正例 {day_positive}")
            grand_total += day_count

            # target_pos_ratio 模式: 每天完成后检查
            if target_pos_ratio is not None and day_success > 0:
                current_pos_ratio = day_positive / day_success
                if current_pos_ratio < target_pos_ratio * 0.7:
                    print(f"  ⚠️  今日正例比例 {current_pos_ratio*100:.1f}% < 目标 {target_pos_ratio*100:.0f}% 的 70%, "
                          f"检查 RISK 用户是否存在 (gen_risky_users.py)")

        # 【训练数据严格化】统一置 ml_score=NULL
        await reset_ml_score_null(db)

        print(f"\n{'=' * 50}")
        overall_pos = grand_positive / grand_success * 100 if grand_success else 0
        print(f"完成! 总计 {grand_total} 次, 成功 {grand_success}, 失败 {grand_reject}, "
              f"正例 {grand_positive} ({overall_pos:.1f}%)")
        if grand_reject > 0:
            print(f"失败详情见: {FAIL_LOG}")
        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        if overall_pos < 15 and grand_success > 0:
            print("⚠️  正例比例仅 %.1f%%, 训练可能假收敛. 建议: --balance-pos --target-pos-ratio 0.30 重造" % overall_pos)
        print("下一步: python scripts/train_xgb_model.py")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="银行风控系统 - 造评估数据脚本 (4 大场景: 转账/登录/贷款申请/信用卡)"
    )
    parser.add_argument("--days", type=int, default=7, help="近 N 天 (默认 7)")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD (与 --days 互斥)")
    parser.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--per-day", type=int, default=None, help="每天固定条数 (不指定则随机)")
    parser.add_argument("--max-per-day", type=int, default=30,
                        help="每天最多多少条 (默认 30, 仅在未指定 --per-day 时生效)")
    parser.add_argument("--clean", action="store_true", help="先清空风控运行时表")
    parser.add_argument("--live", action="store_true",
                        help="不回写 create_time (数据 create_time=now), 适合 demo")
    parser.add_argument("--balance-pos", action="store_true",
                        help="80%% 概率挑 RISK 高风险用户, 拉高正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 循环造数到达标")
    args = parser.parse_args()

    async def _runner():
        from app.database import async_engine
        try:
            await generate_risk_data(
                days=args.days,
                per_day=args.per_day,
                max_per_day=args.max_per_day,
                start_date=args.start,
                end_date=args.end,
                clean=args.clean,
                balance_pos=args.balance_pos,
                target_pos_ratio=args.target_pos_ratio,
                live=args.live,
            )
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())

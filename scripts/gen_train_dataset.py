"""
银行信贷风控系统 - 训练数据集生成 (PD 违约标签)

【目的】造一份严格标注的 XGBoost 训练数据集:
  1. 正例: 逾期客户 (loan_status='逾期' 或存在逾期记录) → PD 标签 1
  2. 负例: 正常履约客户 → PD 标签 0
  默认规模: 60 逾期 × 25 + 60 正常 × 25 = 3000 条
  3. 事件: 贷款申请 (银行 4 事件), 特征真实从 DB 查
  4. ml_score 强制 NULL (训练 SQL 显式 WHERE ml_score IS NULL)

【标签语义 (Q5 决策)】XGBoost 输出 PD 违约概率:
  0 = 正常履约, 1 = 逾期违约 (positives from overdue customers)

【用法】
  python scripts/gen_train_dataset.py --n-overdue 60 --n-normal 60 --per-user 25
  python scripts/gen_train_dataset.py --reset     # 先清空 risk_event/feature/assessment
  python scripts/gen_train_dataset.py --dry-run   # 只统计不写入
"""
import argparse
import asyncio
import os
import random
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def _pick_overdue_customers(db, n: int) -> list[str]:
    """PD 正例: 有逾期记录的客户 (逾期→分期→申请→客户)."""
    r = await db.execute(text("""
        SELECT DISTINCT la.customer_id
        FROM overdue_record ov
        JOIN loan_installment ins ON ov.installment_id = ins.installment_id
        JOIN loan_application la ON ins.loan_id = la.loan_id
        ORDER BY la.customer_id
        LIMIT :n
    """), {"n": n})
    return [row.customer_id for row in r.fetchall() if isinstance(row.customer_id, str)]


async def _pick_normal_customers(db, n: int) -> list[str]:
    """PD 负例: 有申请记录但无逾期记录的客户 (履约客户)."""
    r = await db.execute(text("""
        SELECT c.customer_id
        FROM customer_info c
        JOIN loan_application la ON c.customer_id = la.customer_id
        WHERE c.customer_id NOT IN (
            SELECT DISTINCT la2.customer_id
            FROM overdue_record ov
            JOIN loan_installment ins ON ov.installment_id = ins.installment_id
            JOIN loan_application la2 ON ins.loan_id = la2.loan_id
        )
        GROUP BY c.customer_id
        ORDER BY c.customer_id
        LIMIT :n
    """), {"n": n})
    return [row.customer_id for row in r.fetchall() if isinstance(row.customer_id, str)]


async def _pick_loan_for_customer(db, customer_id: str) -> tuple | None:
    """挑该客户的一条贷款申请 (loan_id, customer_id)."""
    r = await db.execute(text("""
        SELECT loan_id, customer_id
        FROM loan_application
        WHERE customer_id = :cid
        ORDER BY RAND() LIMIT 1
    """), {"cid": customer_id})
    row = r.first()
    return (row.loan_id, row.customer_id) if row else None


async def gen_train_dataset(
    n_overdue: int = 60,
    n_normal: int = 60,
    per_user: int = 25,
    reset: bool = False,
    dry_run: bool = False,
):
    """造训练数据集: n_overdue × per_user 正例 + n_normal × per_user 负例."""
    total_target = (n_overdue + n_normal) * per_user
    print("=" * 60)
    mode = "[DRY-RUN] 预演 (不写库)" if dry_run else "训练数据集生成 (PD 违约标签)"
    print(mode)
    print(f"目标: {n_overdue} 逾期客户 × {per_user} + {n_normal} 正常 × {per_user} = {total_target} 条")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        if reset and not dry_run:
            print("\n[0] 清空训练用表 (risk_event / risk_feature / risk_assessment / risk_case)...")
            for tbl in ("risk_case", "risk_assessment", "risk_feature", "risk_event", "risk_user_profile"):
                await db.execute(text(f"DELETE FROM {tbl}"))
            await db.commit()
            print("  清空完成")

        print(f"\n[1] 选 {n_overdue} 逾期 + {n_normal} 正常客户...")
        overdue_users = await _pick_overdue_customers(db, n_overdue)
        normal_users = await _pick_normal_customers(db, n_normal)
        if not overdue_users:
            print("  [FAIL] 没有逾期客户, 先跑: python scripts/gen_10w_data.py")
            return
        actual_o, actual_n = len(overdue_users), len(normal_users)
        print(f"  逾期: {actual_o} 个 ({overdue_users[0]} ~ {overdue_users[-1]})")
        print(f"  正常: {actual_n} 个 ({normal_users[0]} ~ {normal_users[-1]})")

        if dry_run:
            print(f"\n[DRY-RUN] 预演完成. 真跑去掉 --dry-run")
            return

        plan = [(uid, True) for uid in overdue_users[:n_overdue]] * 1
        plan += [(uid, False) for uid in normal_users[:n_normal]] * 1
        plan = [(uid, is_pos) for uid, is_pos in plan for _ in range(per_user)]
        random.shuffle(plan)

        print(f"\n[2] 造 {len(plan)} 条贷款申请事件 (乱序)...")
        success = pos_count = failed = 0
        for idx, (uid, is_pos) in enumerate(plan, 1):
            try:
                picked = await _pick_loan_for_customer(db, uid)
                if not picked:
                    failed += 1
                    continue
                loan_id, customer_id = picked
                request = RiskCheckRequest(
                    event_type="贷款申请", source_id=loan_id, user_id=customer_id,
                    order_id=loan_id,
                )
                result = await process_event(db, request)
                success += 1
                if result.decision in ("拒绝", "人工审核"):
                    pos_count += 1
                if idx % 100 == 0 or idx == len(plan):
                    print(f"  进度 {idx}/{len(plan)}: 成功 {success}, 拒绝/审核 {pos_count}")
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"  [失败 #{failed}] 客户={uid}: {e}")

        print(f"\n[3] 强制 ml_score = NULL (训练数据无 ml 痕迹)...")
        await db.execute(text("""
            UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL
            WHERE ml_score IS NOT NULL
        """))
        await db.commit()

    print("\n" + "=" * 60)
    print("训练数据集生成完成!")
    print(f"  目标:     {total_target} 条")
    print(f"  实际成功: {success} 条")
    print(f"  拒绝/审核正例: {pos_count} ({100 * pos_count / max(success, 1):.1f}%)")
    print(f"  失败:     {failed} 条")
    print(f"  ml_score: 全部 NULL")
    print(f"  PD 标签:  由 train_xgb_model.py 从客户逾期事实推导 (0=履约, 1=违约)")
    print("=" * 60)
    print("下一步: python scripts/train_xgb_model.py")


async def _runner():
    from app.database import async_engine
    try:
        await gen_train_dataset(
            n_overdue=args.overdue, n_normal=args.normal,
            per_user=args.per_user, reset=args.reset, dry_run=args.dry_run,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="造 PD 训练数据集 (逾期客户正例, ml_score=NULL)")
    parser.add_argument("--overdue", type=int, default=60, help="逾期(正例)客户数 (默认 60)")
    parser.add_argument("--normal", type=int, default=60, help="正常(负例)客户数 (默认 60)")
    parser.add_argument("--per-user", type=int, default=25, help="每个客户造几条 (默认 25)")
    parser.add_argument("--reset", action="store_true", help="先清空训练用表")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    # 兼容旧参数名
    parser.add_argument("--n-risk", dest="overdue", type=int, default=60)
    parser.add_argument("--n-normal", dest="normal", type=int, default=60)
    args = parser.parse_args()
    asyncio.run(_runner())
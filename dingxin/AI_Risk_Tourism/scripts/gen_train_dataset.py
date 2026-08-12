"""
旅游风控系统 - 训练数据集生成 (强标注, 数据为合成业务数据)
默认 30 RISK 用户 × 25 高风险事件 + 30 普通用户 × 25 正常事件 = 1500 条
标签由 12 条旅游规则真实跑出 (decision 字段), 特征 25 维真实从 DB 查
ml_score 字段强制 NULL (避免"未训练模型"垃圾值), 训完用 backfill 回填

用法:
  python scripts/gen_train_dataset.py
  python scripts/gen_train_dataset.py --reset
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402

RISKY_USER_PREFIX = "RISK"


async def _pick_risk_users(db, n: int) -> list[str]:
    r = await db.execute(text("""
        SELECT user_id FROM user_info
        WHERE user_id LIKE :prefix ORDER BY user_id LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.user_id for row in r.fetchall()]


async def _pick_normal_users(db, n: int) -> list[str]:
    r = await db.execute(text("""
        SELECT user_id FROM user_info
        WHERE user_id NOT LIKE :prefix AND user_id LIKE 'U%'
        ORDER BY user_id LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.user_id for row in r.fetchall()]


async def _pick_refund_for_user(db, user_id: str) -> tuple | None:
    r = await db.execute(text("""
        SELECT refund_id FROM order_refund
        WHERE user_id = :uid ORDER BY RAND() LIMIT 1
    """), {"uid": user_id})
    row = r.first()
    return (row.refund_id,) if row else None


async def _pick_visa_for_user(db, user_id: str) -> tuple | None:
    r = await db.execute(text("""
        SELECT visa_id FROM visa_application
        WHERE user_id = :uid ORDER BY RAND() LIMIT 1
    """), {"uid": user_id})
    row = r.first()
    return (row.visa_id,) if row else None


async def _pick_order_for_user(db, user_id: str) -> tuple | None:
    r = await db.execute(text("""
        SELECT order_id FROM order_info
        WHERE user_id = :uid ORDER BY RAND() LIMIT 1
    """), {"uid": user_id})
    row = r.first()
    return (row.order_id,) if row else None


async def gen_train_dataset(
    n_risk: int = 30,
    n_normal: int = 30,
    per_user: int = 25,
    reset: bool = False,
    dry_run: bool = False,
):
    """造训练数据集: n_risk × per_user 高风险 + n_normal × per_user 正常."""
    total_target = (n_risk + n_normal) * per_user
    print("=" * 60)
    print(f"旅游训练数据集生成 (强标注, ml_score=NULL): 目标 {total_target} 条")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        if reset and not dry_run:
            print("\n[0] 清空训练用表 (risk_event/feature/assessment/case/profile)...")
            for tbl in ("risk_case", "risk_assessment", "risk_feature", "risk_event", "risk_user_profile"):
                await db.execute(text(f"DELETE FROM {tbl}"))
            await db.commit()
            print("  清空完成")

        print(f"\n[1] 选 {n_risk} RISK + {n_normal} 普通用户...")
        risk_users = await _pick_risk_users(db, n_risk)
        normal_users = await _pick_normal_users(db, n_normal)
        if not risk_users:
            print("  [FAIL] 没找到 RISK 用户, 先跑: python scripts/gen_risky_users.py --count 30")
            return
        if not normal_users:
            print("  [FAIL] 没找到普通用户, 先跑: python scripts/gen_business_data.py --users 40")
            return
        n_risk = min(n_risk, len(risk_users))
        n_normal = min(n_normal, len(normal_users))
        print(f"  RISK: {len(risk_users)} 个 | 普通: {len(normal_users)} 个")

        if dry_run:
            print("\n[DRY-RUN] 预演完成. 真跑去掉 --dry-run")
            return

        plan = []
        for uid in risk_users:
            for _ in range(per_user):
                # 高风险用户优先走 退改申请 / 签证申请 (规则命中率高)
                plan.append((uid, random.choice(["退改申请", "退改申请", "签证申请", "预订下单"])))
        for uid in normal_users:
            for _ in range(per_user):
                plan.append((uid, "预订下单"))
        random.shuffle(plan)

        print(f"\n[2] 造 {len(plan)} 条事件 (乱序)...")
        success = 0
        pos_count = 0
        failed = 0
        for idx, (uid, event_type) in enumerate(plan, 1):
            try:
                if event_type == "退改申请":
                    picked = await _pick_refund_for_user(db, uid)
                    if picked:
                        request = RiskCheckRequest(event_type="退改申请", source_id=picked[0], user_id=uid)
                    else:
                        # 该用户没有退改单, 兜底走预订下单
                        picked = await _pick_order_for_user(db, uid)
                        if not picked:
                            failed += 1
                            continue
                        request = RiskCheckRequest(event_type="预订下单", source_id=picked[0],
                                                   user_id=uid, order_id=picked[0])
                elif event_type == "签证申请":
                    picked = await _pick_visa_for_user(db, uid)
                    if picked:
                        request = RiskCheckRequest(event_type="签证申请", source_id=picked[0], user_id=uid)
                    else:
                        # 该用户没有签证记录, 兜底走预订下单
                        picked = await _pick_order_for_user(db, uid)
                        if not picked:
                            failed += 1
                            continue
                        request = RiskCheckRequest(event_type="预订下单", source_id=picked[0],
                                                   user_id=uid, order_id=picked[0])
                else:
                    picked = await _pick_order_for_user(db, uid)
                    if not picked:
                        failed += 1
                        continue
                    order_id = picked[0]
                    request = RiskCheckRequest(event_type="预订下单", source_id=order_id,
                                               user_id=uid, order_id=order_id)

                result = await process_event(db, request)
                success += 1
                if result.decision in ("拒绝", "人工审核"):
                    pos_count += 1
                if idx % 200 == 0 or idx == len(plan):
                    print(f"  进度 {idx}/{len(plan)}: 成功 {success}, 正例 {pos_count} ({100*pos_count/max(success,1):.1f}%)")
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"  [失败 #{failed}] 用户={uid}, 事件={event_type}: {e}")

        # 3. 强制 ml_score = NULL
        await db.execute(text("UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL WHERE ml_score IS NOT NULL"))
        await db.commit()

    print("\n" + "=" * 60)
    print("训练数据集生成完成!")
    print(f"  实际成功: {success} 条 | 正例: {pos_count} 条 ({100*pos_count/max(success,1):.1f}%) | 失败: {failed}")
    print("  下一步: python scripts/train_xgb_model.py")
    print("=" * 60)


async def _runner():
    from app.database import async_engine
    try:
        await gen_train_dataset(
            n_risk=args.n_risk, n_normal=args.n_normal,
            per_user=args.per_user, reset=args.reset, dry_run=args.dry_run,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="造旅游训练数据集 (强标注, ml_score=NULL)")
    parser.add_argument("--n-risk", type=int, default=30)
    parser.add_argument("--n-normal", type=int, default=30)
    parser.add_argument("--per-user", type=int, default=25)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(_runner())

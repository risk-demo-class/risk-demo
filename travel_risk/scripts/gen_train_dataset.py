"""
旅游风控系统 - 严格标注训练数据集生成

【目的】
  造一份严格标注的 XGBoost 训练数据集, 满足:
    1. 数量: 1500 条 (30 RISK 用户 × 25 条高风险事件 + 30 普通用户 × 25 条正常事件)
    2. 标签: 真实由 30 规则跑出 (decision 字段), 不是随机
    3. 特征: 28 维真实从 DB 查 (feature.py), 不是捏造
    4. ml_score 字段: 写库后强制 NULL (干净, 训练 SQL 显式 WHERE ml_score IS NULL)

【用法】
  python scripts/gen_train_dataset.py --reset
  python scripts/gen_train_dataset.py --n-risk 50 --n-normal 50 --per-user 25
  python scripts/gen_train_dataset.py --dry-run
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal, rebuild_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def _pick_risk_users(db, n: int) -> list[str]:
    """从 RISK00X 高风险用户里选 N 个."""
    r = await db.execute(text(
        "SELECT user_id FROM user_info WHERE user_id LIKE 'RISK%' ORDER BY user_id LIMIT :n"
    ), {"n": n})
    return [row.user_id for row in r.fetchall()]


async def _pick_normal_users(db, n: int) -> list[str]:
    """从普通用户里选 N 个 (排除 RISK 和 RISKB 用户)."""
    r = await db.execute(text("""
        SELECT user_id FROM user_info
        WHERE user_id NOT LIKE 'RISK%'
        AND user_id NOT LIKE 'U1%'
        ORDER BY user_id
        LIMIT :n
    """), {"n": n})
    return [row.user_id for row in r.fetchall()]


async def _pick_booking(db, user_id: str) -> str | None:
    """挑该用户的一笔旅游订单."""
    r = await db.execute(text(
        "SELECT booking_id FROM booking_info WHERE user_id=:uid ORDER BY RAND() LIMIT 1"
    ), {"uid": user_id})
    row = r.first()
    return row[0] if row else None


async def _pick_claim(db, user_id: str) -> str | None:
    """挑该用户的一条理赔申请."""
    r = await db.execute(text(
        "SELECT claim_id FROM claim_info WHERE user_id=:uid ORDER BY RAND() LIMIT 1"
    ), {"uid": user_id})
    row = r.first()
    return row[0] if row else None


async def _pick_complaint(db, user_id: str) -> str | None:
    """挑该用户的一条投诉."""
    r = await db.execute(text(
        "SELECT complaint_id FROM complaint_info WHERE user_id=:uid ORDER BY RAND() LIMIT 1"
    ), {"uid": user_id})
    row = r.first()
    return row[0] if row else None


async def gen_train_dataset(
    n_risk: int = 30,
    n_normal: int = 30,
    per_user: int = 25,
    reset: bool = False,
    dry_run: bool = False,
):
    random.seed(42)
    async with AsyncSessionLocal() as db:
        if reset:
            print("[reset] 清空 risk_event / risk_feature / risk_assessment / risk_case ...")
            for table in ("risk_feature", "risk_assessment", "risk_case", "risk_event"):
                await db.execute(text(f"DELETE FROM {table}"))
            await db.commit()

        risk_users = await _pick_risk_users(db, n_risk)
        normal_users = await _pick_normal_users(db, n_normal)
        if len(risk_users) < n_risk:
            print(f"[WARN] RISK 用户只有 {len(risk_users)} 个 (< {n_risk}), 建议先跑 gen_risky_users.py")
        if len(normal_users) < n_normal:
            print(f"[WARN] 普通用户只有 {len(normal_users)} 个 (< {n_normal}), 建议先跑 gen_10w_data.py")
        if dry_run:
            print(f"[dry-run] RISK {len(risk_users)} 个, 普通 {len(normal_users)} 个, 每用户 {per_user} 条")
            return

        total = 0
        positive = 0

        # 高风险用户: 理赔/投诉 + 下单事件 (目标: 拒绝/审核)
        for uid in risk_users:
            claims = []
            complaints = []
            bookings = []
            for _ in range(per_user):
                claim_id = await _pick_claim(db, uid)
                if claim_id:
                    claims.append(claim_id)
                complaint_id = await _pick_complaint(db, uid)
                if complaint_id:
                    complaints.append(complaint_id)
                booking_id = await _pick_booking(db, uid)
                if booking_id:
                    bookings.append(booking_id)

            # 用理赔申请 + 投诉 + 下单混合凑 per_user 条
            sources = []
            for c in claims:
                sources.append(("理赔申请", c))
            for c in complaints:
                sources.append(("投诉", c))
            for b in bookings:
                sources.append(("下单", b))
            sources = sources[:per_user]
            while len(sources) < per_user and bookings:
                sources.append(("下单", random.choice(bookings)))

            for event_type, source_id in sources:
                try:
                    resp = await process_event(db, RiskCheckRequest(
                        event_type=event_type,
                        source_id=source_id,
                        user_id=uid,
                        event_data={event_type: source_id},
                    ))
                    total += 1
                    if resp.decision in ("人工审核", "拒绝"):
                        positive += 1
                    # 强制 ml_score=NULL (训练数据纯净)
                    await db.execute(text(
                        "UPDATE risk_assessment SET ml_score=NULL, ml_decision=NULL "
                        "WHERE assessment_id=:aid"
                    ), {"aid": resp.assessment_id})
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    print(f"  [跳过] {uid} {event_type} {source_id}: {type(e).__name__} {str(e)[:60]}")

        # 普通用户: 下单事件 (目标: 通过/标记)
        for uid in normal_users:
            bookings = []
            for _ in range(per_user):
                booking_id = await _pick_booking(db, uid)
                if booking_id:
                    bookings.append(booking_id)
            sources = [(b, b) for b in bookings][:per_user]
            while len(sources) < per_user and bookings:
                sources.append(("下单", random.choice(bookings)))
            for event_type, source_id in sources:
                try:
                    resp = await process_event(db, RiskCheckRequest(
                        event_type="下单",
                        source_id=source_id,
                        user_id=uid,
                        event_data={"booking_id": source_id},
                    ))
                    total += 1
                    if resp.decision in ("人工审核", "拒绝"):
                        positive += 1
                    await db.execute(text(
                        "UPDATE risk_assessment SET ml_score=NULL, ml_decision=NULL "
                        "WHERE assessment_id=:aid"
                    ), {"aid": resp.assessment_id})
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    print(f"  [跳过] {uid}: {type(e).__name__} {str(e)[:60]}")

        print("\n" + "=" * 60)
        print(f"训练数据集生成完成: 共 {total} 条, 正例 {positive} 条 ({100 * positive / total:.1f}%)")
        print("下一步: python scripts/train_xgb_model.py")
        print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成严格标注训练数据集")
    parser.add_argument("--n-risk", type=int, default=30)
    parser.add_argument("--n-normal", type=int, default=30)
    parser.add_argument("--per-user", type=int, default=25)
    parser.add_argument("--reset", action="store_true", help="先清空风控评估数据")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()
    rebuild_engine()

    async def _main():
        try:
            await gen_train_dataset(args.n_risk, args.n_normal, args.per_user, args.reset, args.dry_run)
        finally:
            from app.database import dispose_engine
            await dispose_engine()

    asyncio.run(_main())

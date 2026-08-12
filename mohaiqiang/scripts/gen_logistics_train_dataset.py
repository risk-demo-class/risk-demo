"""
物流风控系统 - 严格标注训练数据集生成 (异步)

目的:
  1. 数量: (RISK 寄件人 + 普通寄件人) × per_user 条
  2. 标签: 真实由 24 条物流规则跑出 (decision 字段)
  3. 特征: 30 维真实从 DB 查 (feature.py 三大特征族)
  4. ml_score 字段: 强制 NULL, 避免"未训练模型"垃圾值

用法:
  python scripts/gen_logistics_train_dataset.py                        # 默认 30 RISK + 30 普通 × 25
  python scripts/gen_logistics_train_dataset.py --n-risk 50 --n-normal 50 --per-user 25
  python scripts/gen_logistics_train_dataset.py --reset
  python scripts/gen_logistics_train_dataset.py --dry-run
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event

RISKY_USER_PREFIX = "RISK"


async def _pick_risk_users(db, n: int) -> list[str]:
    r = await db.execute(text("""
        SELECT sender_id FROM logistics_sender
        WHERE sender_id LIKE :prefix
        ORDER BY sender_id LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.sender_id for row in r.fetchall()]


async def _pick_normal_users(db, n: int) -> list[str]:
    r = await db.execute(text("""
        SELECT sender_id FROM logistics_sender
        WHERE sender_id NOT LIKE :prefix
        ORDER BY sender_id LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.sender_id for row in r.fetchall()]


async def _pick_risk_waybill_for_user(db, uid: str) -> tuple | None:
    """挑该寄件人的高风险运单 (未实名/危险品/跨境/COD拒收/异常状态)."""
    r = await db.execute(text("""
        SELECT w.waybill_no, w.sender_id
        FROM logistics_waybill w
        LEFT JOIN logistics_sender s ON s.sender_id = w.sender_id
        LEFT JOIN logistics_cod_settlement c
               ON c.waybill_no = w.waybill_no AND c.collect_status = '拒收'
        WHERE w.sender_id = :uid
          AND (s.is_real_name_verified = 0 OR s.verify_fail_count >= 3
               OR w.item_category IN ('电池', '化学品') OR w.is_cross_border = 1
               OR c.cod_id IS NOT NULL OR w.status IN ('拒收', '退回', '异常'))
        ORDER BY RAND() LIMIT 1
    """), {"uid": uid})
    row = r.first()
    if row:
        return (row.waybill_no, row.sender_id)
    # fallback: 该寄件人任意运单
    row = (await db.execute(text("""
        SELECT waybill_no, sender_id FROM logistics_waybill
        WHERE sender_id = :uid ORDER BY RAND() LIMIT 1
    """), {"uid": uid})).first()
    return (row.waybill_no, row.sender_id) if row else None


async def _pick_normal_waybill_for_user(db, uid: str) -> tuple | None:
    """挑该寄件人的正常运单 (实名+非危险品+非跨境+无COD+正常状态)."""
    r = await db.execute(text("""
        SELECT w.waybill_no, w.sender_id
        FROM logistics_waybill w
        JOIN logistics_sender s ON s.sender_id = w.sender_id
        WHERE w.sender_id = :uid
          AND s.is_real_name_verified = 1
          AND w.item_category NOT IN ('电池', '化学品')
          AND w.is_cross_border = 0
          AND w.cod_amount = 0
          AND w.status NOT IN ('拒收', '退回', '异常')
        ORDER BY RAND() LIMIT 1
    """), {"uid": uid})
    row = r.first()
    if row:
        return (row.waybill_no, row.sender_id)
    row = (await db.execute(text("""
        SELECT waybill_no, sender_id FROM logistics_waybill
        WHERE sender_id = :uid ORDER BY RAND() LIMIT 1
    """), {"uid": uid})).first()
    return (row.waybill_no, row.sender_id) if row else None


async def _pick_risk_special(db, uid: str, event_type: str) -> tuple | None:
    """投诉/理赔/COD 专用 picker."""
    if event_type == "投诉":
        table, id_col = "logistics_complaint_record", "complaint_id"
    elif event_type == "理赔申请":
        table, id_col = "logistics_claim", "claim_id"
    else:  # COD结算
        table, id_col = "logistics_cod_settlement", "cod_id"
    r = await db.execute(text(f"""
        SELECT c.{id_col}, w.sender_id
        FROM {table} c
        JOIN logistics_waybill w ON w.waybill_no = c.waybill_no
        WHERE w.sender_id = :uid
        ORDER BY RAND() LIMIT 1
    """), {"uid": uid})
    row = r.first()
    return (row[0], row[1]) if row else None


async def gen_logistics_train_dataset(
    n_risk: int = 30,
    n_normal: int = 30,
    per_user: int = 25,
    reset: bool = False,
    dry_run: bool = False,
) -> None:
    total_target = (n_risk + n_normal) * per_user
    print("=" * 60)
    print(f"训练数据集生成 (目标 {total_target} 条, ml_score=NULL)")
    print(f"目标: {n_risk} RISK × {per_user} + {n_normal} 普通 × {per_user} = {total_target} 条")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        if reset and not dry_run:
            print("\n[0] 清空训练用表...")
            for tbl in ("risk_case", "risk_assessment", "risk_feature", "risk_event", "risk_user_profile"):
                await db.execute(text(f"DELETE FROM {tbl}"))
            await db.commit()
            print("  清空完成")

        print(f"\n[1] 选 {n_risk} RISK + {n_normal} 普通寄件人...")
        risk_users = await _pick_risk_users(db, n_risk)
        normal_users = await _pick_normal_users(db, n_normal)
        if not risk_users:
            print(f"  [FAIL] 没找到 RISK 寄件人, 先跑: python scripts/gen_logistics_risky_senders.py --count {n_risk}")
            return
        if not normal_users:
            print("  [FAIL] 没找到普通寄件人, 先跑: python scripts/gen_logistics_data.py")
            return
        n_risk = min(n_risk, len(risk_users))
        n_normal = min(n_normal, len(normal_users))
        print(f"  RISK: {len(risk_users)} 个 ({risk_users[0]} ~ {risk_users[-1]})")
        print(f"  普通: {len(normal_users)} 个 ({normal_users[0]} ~ {normal_users[-1]})")

        if dry_run:
            print("\n[DRY-RUN] 预演完成. 真跑去掉 --dry-run")
            return

        success = 0
        pos_count = 0
        neg_count = 0
        failed = 0
        plan = []
        for uid in risk_users:
            for _ in range(per_user):
                plan.append((uid, random.choice(["寄件下单", "揽收", "投诉", "理赔申请", "COD结算"])))
        for uid in normal_users:
            for _ in range(per_user):
                plan.append((uid, "寄件下单"))
        random.shuffle(plan)

        print(f"\n[2] 造 {len(plan)} 条事件 (乱序)...")
        for idx, (uid, event_type) in enumerate(plan, 1):
            try:
                if event_type in ("投诉", "理赔申请", "COD结算"):
                    picked = await _pick_risk_special(db, uid, event_type)
                    if not picked:
                        picked = await _pick_risk_waybill_for_user(db, uid)
                        event_type = "揽收"
                    if not picked:
                        failed += 1
                        continue
                    source_id, sender_id = picked
                else:
                    if uid.startswith(RISKY_USER_PREFIX):
                        picked = await _pick_risk_waybill_for_user(db, uid)
                    else:
                        picked = await _pick_normal_waybill_for_user(db, uid)
                    if not picked:
                        failed += 1
                        continue
                    source_id, sender_id = picked
                result = await process_event(db, RiskCheckRequest(
                    event_type=event_type, source_id=source_id, user_id=sender_id,
                ))
                success += 1
                if result.decision in ("人工审核", "拒绝"):
                    pos_count += 1
                else:
                    neg_count += 1
                if idx % 100 == 0 or idx == len(plan):
                    print(f"  进度 {idx}/{len(plan)}: 成功 {success}, 正例 {pos_count} "
                          f"({100 * pos_count / max(success, 1):.1f}%)")
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"  [失败 #{failed}] 寄件人={uid}, 事件={event_type}: {e}")

        print("\n[3] 强制 ml_score = NULL (训练数据无 ml 痕迹)...")
        await db.execute(text("""
            UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL
            WHERE ml_score IS NOT NULL
        """))
        await db.commit()

    print("\n" + "=" * 60)
    print(f"训练数据集生成完成!")
    print(f"  实际成功:   {success} 条")
    print(f"  正例:       {pos_count} 条 ({100 * pos_count / max(success, 1):.1f}%)")
    print(f"  负例:       {neg_count} 条 ({100 * neg_count / max(success, 1):.1f}%)")
    print(f"  失败:       {failed} 条")
    print(f"  ml_score:   全部 NULL (无未训练模型垃圾值)")
    print("=" * 60)
    print("下一步: python scripts/train_xgb_model.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="物流严格标注训练数据集生成")
    parser.add_argument("--n-risk", type=int, default=30, help="RISK 高风险寄件人数 (默认 30)")
    parser.add_argument("--n-normal", type=int, default=30, help="普通寄件人数 (默认 30)")
    parser.add_argument("--per-user", type=int, default=25, help="每个寄件人造几条 (默认 25)")
    parser.add_argument("--reset", action="store_true", help="先清空训练用表")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    async def _runner() -> None:
        try:
            await gen_logistics_train_dataset(
                n_risk=args.n_risk,
                n_normal=args.n_normal,
                per_user=args.per_user,
                reset=args.reset,
                dry_run=args.dry_run,
            )
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()

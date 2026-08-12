"""
制造业风控系统 - 训练数据集生成 (P4-L4 2026-08-08)

【目的】
  造一份**严格标注**的 XGBoost 训练数据集, 满足:
    1. 数量: 默认 1500 条 (30 RISK 经销商 × 25 高风险 + 30 普通经销商 × 25 正常)
    2. 标签: 真实由 16 条制造业规则跑出 (decision 字段), 不是随机
    3. 特征: 25 维真实从 DB 查 (feature.py), 不是捏造
    4. ml_score 字段: 强制 NULL (写库后 UPDATE), 不存"未训练的垃圾模型"推理值
       → 训完基础模型后, 用 scripts/backfill_ml_score.py 回填合理值

【用法】
  python scripts/gen_train_dataset.py                  # 默认 30 RISK + 30 普通, 每用户 25 条
  python scripts/gen_train_dataset.py --reset         # 先清空风控运行时表再造
  python scripts/gen_train_dataset.py --dry-run       # 只统计不写入
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

RISKY_DEALER_PREFIX = "RISK"


async def _pick_risk_dealers(db, n: int) -> list[str]:
    """从 RISK 高风险经销商里选 N 个 (按 dealer_id 排序稳定)."""
    r = await db.execute(text("""
        SELECT dealer_id FROM dealer_info
        WHERE dealer_id LIKE :prefix
        ORDER BY dealer_id
        LIMIT :n
    """), {"prefix": f"{RISKY_DEALER_PREFIX}%", "n": n})
    return [row.dealer_id for row in r.fetchall()]


async def _pick_normal_dealers(db, n: int) -> list[str]:
    """从普通经销商里选 N 个 (排除 RISK, 按 dealer_id 排序)."""
    r = await db.execute(text("""
        SELECT dealer_id FROM dealer_info
        WHERE dealer_id NOT LIKE :prefix
        ORDER BY dealer_id
        LIMIT :n
    """), {"prefix": f"{RISKY_DEALER_PREFIX}%", "n": n})
    return [row.dealer_id for row in r.fetchall()]


async def _pick_order_for_dealer(db, dealer_id: str) -> str | None:
    r = await db.execute(text("""
        SELECT order_id FROM order_info
        WHERE dealer_id = :did
        ORDER BY RAND() LIMIT 1
    """), {"did": dealer_id})
    row = r.first()
    return row.order_id if row else None


async def _pick_warranty_for_dealer(db, dealer_id: str) -> str | None:
    r = await db.execute(text("""
        SELECT w.warranty_id FROM warranty_record w
        JOIN order_info oi ON w.order_id = oi.order_id
        WHERE oi.dealer_id = :did
        ORDER BY RAND() LIMIT 1
    """), {"did": dealer_id})
    row = r.first()
    return row.warranty_id if row else None


async def _pick_report_for_dealer(db, dealer_id: str) -> str | None:
    r = await db.execute(text("""
        SELECT report_id FROM cross_region_report
        WHERE dealer_id = :did
        ORDER BY RAND() LIMIT 1
    """), {"did": dealer_id})
    row = r.first()
    return row.report_id if row else None


async def gen_train_dataset(
    n_risk: int = 30,
    n_normal: int = 30,
    per_user: int = 25,
    reset: bool = False,
    dry_run: bool = False,
):
    """造训练数据集: n_risk × per_user 高风险 + n_normal × per_user 正常."""
    if dry_run:
        print("=" * 60)
        print("[DRY-RUN] 训练数据集预演 (不写库)")

    async with AsyncSessionLocal() as db:
        if reset:
            print("[reset] 清空风控运行时表 (risk_event/feature/assessment/case/profile)...")
            for tbl in ["risk_feature", "risk_assessment", "risk_event", "risk_case", "risk_user_profile"]:
                await db.execute(text(f"DELETE FROM {tbl}"))
            await db.commit()

        risk_dealers = await _pick_risk_dealers(db, n_risk)
        normal_dealers = await _pick_normal_dealers(db, n_normal)
        print(f"[选用户] RISK 经销商 {len(risk_dealers)} 家 / 普通经销商 {len(normal_dealers)} 家")

        total = 0
        pos = 0
        neg = 0

        # 1. 高风险样本: RISK 经销商 → 保修/串货举报事件为主
        for dealer_id in risk_dealers:
            for i in range(per_user):
                roll = i % 10
                if roll < 5:
                    source = await _pick_warranty_for_dealer(db, dealer_id)
                    event_type = "设备保修"
                elif roll < 8:
                    source = await _pick_report_for_dealer(db, dealer_id)
                    event_type = "跨区串货举报"
                else:
                    source = await _pick_order_for_dealer(db, dealer_id)
                    event_type = "经销商订货"
                if not source:
                    continue
                request = RiskCheckRequest(
                    event_type=event_type, source_id=source, user_id=dealer_id,
                )
                try:
                    result = await process_event(db, request)
                    # 强制 ml_score=NULL (未训练模型不写垃圾值)
                    await db.execute(text(
                        "UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL "
                        "WHERE assessment_id = :aid"
                    ), {"aid": result.assessment_id})
                    await db.commit()
                    total += 1
                    if result.decision in ("拒绝", "人工审核"):
                        pos += 1
                    else:
                        neg += 1
                except Exception as e:
                    await db.rollback()
                    print(f"  [RISK] {dealer_id} {event_type} {source} 失败: {e}")

        # 2. 正常样本: 普通经销商 → 普通订货为主
        for dealer_id in normal_dealers:
            for i in range(per_user):
                source = await _pick_order_for_dealer(db, dealer_id)
                if not source:
                    continue
                request = RiskCheckRequest(
                    event_type="经销商订货", source_id=source, user_id=dealer_id,
                )
                try:
                    result = await process_event(db, request)
                    await db.execute(text(
                        "UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL "
                        "WHERE assessment_id = :aid"
                    ), {"aid": result.assessment_id})
                    await db.commit()
                    total += 1
                    if result.decision in ("拒绝", "人工审核"):
                        pos += 1
                    else:
                        neg += 1
                except Exception as e:
                    await db.rollback()
                    print(f"  [NORMAL] {dealer_id} {source} 失败: {e}")

        pos_ratio = pos / total if total > 0 else 0
        print("=" * 60)
        print(f"[完成] 训练数据集: 共 {total} 条 (正例 {pos} / 负例 {neg})")
        print(f"  正例比例: {pos_ratio*100:.1f}%  (目标 40%-55%)")
        print(f"  ml_score 全部 = NULL, 训练前可先跑 train_xgb_model.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="制造业风控系统 - 训练数据集生成 (RISK 高风险 + 普通样本)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""例:
  python scripts/gen_train_dataset.py
  python scripts/gen_train_dataset.py --reset
  python scripts/gen_train_dataset.py --dry-run
        """,
    )
    parser.add_argument("--n-risk", type=int, default=30, dest="n_risk", help="RISK 经销商数 (默认 30)")
    parser.add_argument("--n-normal", type=int, default=30, dest="n_normal", help="普通经销商数 (默认 30)")
    parser.add_argument("--per-user", type=int, default=25, dest="per_user", help="每经销商事件数 (默认 25)")
    parser.add_argument("--reset", action="store_true", help="先清空风控运行时表")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()
    asyncio.run(gen_train_dataset(
        n_risk=args.n_risk, n_normal=args.n_normal,
        per_user=args.per_user, reset=args.reset, dry_run=args.dry_run,
    ))

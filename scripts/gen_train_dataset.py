"""
制造业风控系统 - 训练数据集生成

【目的】
  造一份严格标注的 XGBoost 训练数据集:
    1. RISK 高风险经销商 → 保修/维修事件 (触发 R008/R015/R018 等 → 拒绝/人工审核)
    2. 普通经销商 → 经销商订货事件 (正常 → 通过/标记)
    3. 特征: 25 维真实从 DB 查 (feature.py)
    4. ml_score 字段强制 NULL (训练 SQL 显式 WHERE ml_score IS NULL)
   默认规模: 30 RISK × 25 + 30 普通 × 25 = 1500 条 (普通经销商不足时按实际数量)

【用法】
  python scripts/gen_train_dataset.py                  # 默认 1500 条 (30 RISK + 30 普通 × 25)
  python scripts/gen_train_dataset.py --n-risk 10 --n-normal 12 --per-user 20
  python scripts/gen_train_dataset.py --reset          # 先清空风控运行时表
"""
import argparse
import asyncio
import os
import random
import sys

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.service.event import process_event
from scripts.mfg_pickers import build_request, pick_order, pick_warranty

RISKY_USER_PREFIX = "RISK"


async def _pick_risk_users(db, n: int) -> list[str]:
    """从 RISK00X 高风险经销商里选 N 个."""
    r = await db.execute(text("""
        SELECT user_id FROM user_info
        WHERE user_id LIKE :prefix
        ORDER BY user_id LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.user_id for row in r.fetchall()]


async def _pick_normal_users(db, n: int) -> list[str]:
    """从普通经销商 (非 RISK) 里选 N 个."""
    r = await db.execute(text("""
        SELECT user_id FROM user_info
        WHERE user_id NOT LIKE :prefix AND role = '经销商'
        ORDER BY user_id LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.user_id for row in r.fetchall()]


async def _pick_risky_warranty_for_user(db, user_id: str) -> tuple | None:
    """挑该经销商的一条保修/维修工单."""
    issue_type = random.choice(["保修", "维修"])
    return await pick_warranty(db, user_id=user_id, issue_type=issue_type)


async def gen_train_dataset(
    n_risk: int = 30,
    n_normal: int = 30,
    per_user: int = 25,
    reset: bool = False,
    dry_run: bool = False,
):
    total_target = (n_risk + n_normal) * per_user
    print("=" * 60)
    print("训练数据集生成 (强标注, ml_score=NULL)")
    print(f"目标: {n_risk} RISK × {per_user} + {n_normal} 普通 × {per_user} = {total_target} 条")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        if reset and not dry_run:
            print("\n[0] 清空风控运行时表...")
            for tbl in ["risk_case", "risk_assessment", "risk_feature",
                        "risk_event", "risk_user_profile"]:
                await db.execute(text(f"DELETE FROM {tbl}"))
            await db.commit()
            print("  清空完成")

        print(f"\n[1] 选 {n_risk} RISK + {n_normal} 普通经销商...")
        risk_users = await _pick_risk_users(db, n_risk)
        normal_users = await _pick_normal_users(db, n_normal)
        if not risk_users:
            print("  [FAIL] 没找到 RISK 经销商, 先跑: python scripts/gen_risky_users.py")
            return
        if not normal_users:
            print("  [FAIL] 没找到普通经销商, 先跑 init_db.py 初始化业务数据")
            return
        n_risk, n_normal = len(risk_users), len(normal_users)
        print(f"  RISK: {len(risk_users)} 个, 普通: {len(normal_users)} 个")

        if dry_run:
            print("\n[DRY-RUN] 预演完成.")
            return

        plan = []
        for uid in risk_users:
            for _ in range(per_user):
                plan.append((uid, "risky"))
        for uid in normal_users:
            for _ in range(per_user):
                plan.append((uid, "normal"))
        random.shuffle(plan)

        print(f"\n[2] 造 {len(plan)} 条事件 (乱序)...")
        success = 0
        pos_count = 0
        neg_count = 0
        failed = 0
        for idx, (uid, kind) in enumerate(plan, 1):
            try:
                if kind == "risky":
                    # 交替用保修/维修工单 与 订货单, 避免样本不足
                    if random.random() < 0.5:
                        picked = await _pick_risky_warranty_for_user(db, uid)
                        if not picked:
                            picked = await pick_order(db, user_id=uid)
                            if not picked:
                                failed += 1
                                continue
                            oid, _, _ = picked
                            request = build_request("经销商订货", oid, uid, oid)
                        else:
                            wid, _, issue_type = picked
                            event_type = "保修申请" if issue_type == "保修" else "售后维修"
                            request = build_request(event_type, wid, uid)
                    else:
                        picked = await pick_order(db, user_id=uid)
                        if not picked:
                            failed += 1
                            continue
                        oid, _, _ = picked
                        request = build_request("经销商订货", oid, uid, oid)
                else:
                    picked = await pick_order(db, user_id=uid)
                    if not picked:
                        failed += 1
                        continue
                    oid, _, _ = picked
                    request = build_request("经销商订货", oid, uid, oid)

                result = await process_event(db, request)
                success += 1
                if result.decision in ("拒绝", "人工审核"):
                    pos_count += 1
                else:
                    neg_count += 1
                if idx % 100 == 0 or idx == len(plan):
                    print(f"  进度 {idx}/{len(plan)}: 成功 {success}, 正例 {pos_count} ({100*pos_count/max(success,1):.1f}%)")
            except Exception as e:
                await db.rollback()
                failed += 1
                if failed <= 5:
                    print(f"  [失败 #{failed}] 用户={uid}: {e}")

        print(f"\n[3] 强制 ml_score = NULL (训练数据无 ml 痕迹)...")
        await db.execute(text("""
            UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL
            WHERE ml_score IS NOT NULL
        """))
        await db.commit()

    print("\n" + "=" * 60)
    print("训练数据集生成完成!")
    print(f"  实际成功: {success} 条")
    print(f"  正例:     {pos_count} 条 ({100*pos_count/max(success,1):.1f}%)")
    print(f"  负例:     {neg_count} 条 ({100*neg_count/max(success,1):.1f}%)")
    print(f"  失败:     {failed} 条")
    print("  ml_score: 全部 NULL (无未训练模型垃圾值)")
    print("=" * 60)
    if pos_count / max(success, 1) < 0.25:
        print("[WARN] 正例比例 < 25% 推荐值, 模型可能假收敛")
    print("\n下一步: python scripts/train_xgb_model.py")


async def _runner():
    from app.database import async_engine
    try:
        await gen_train_dataset(
            n_risk=args.n_risk,
            n_normal=args.n_normal,
            per_user=args.per_user,
            reset=args.reset,
            dry_run=args.dry_run,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造训练数据集 (强标注, ml_score=NULL, 训练 SQL 显式 WHERE ml_score IS NULL)"
    )
    parser.add_argument("--n-risk", type=int, default=30, help="RISK 高风险经销商数 (默认 30)")
    parser.add_argument("--n-normal", type=int, default=30, help="普通经销商数 (默认 30)")
    parser.add_argument("--per-user", type=int, default=25, help="每个经销商造几条 (默认 25)")
    parser.add_argument("--reset", action="store_true", help="先清空训练用表")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()
    asyncio.run(_runner())

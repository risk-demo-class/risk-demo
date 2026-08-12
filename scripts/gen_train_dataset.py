"""
物流风控系统 - 训练数据集生成 (500 条默认: 5 RISK × 20 + 20 普通 × 20)

【目的】造一份**严格标注**的 XGBoost 训练数据集:
  1. 标签: 真实 30 规则跑出的 decision 字段
  2. 特征: 25 维真实从 DB 查 (feature.py)
  3. ml_score = NULL, 训练 SQL 显式 WHERE ml_score IS NULL

【RISK 用户倾向事件】极高概率产生正例:
  - RISK001(高频+大额+夜间) → 寄件下单 (命中 L002/L003/L013 极高)
  - RISK002(80% 到付拒收) → 到付签收 (命中 L022 极高)
  - RISK003(危险品瞒报模式) → 寄件下单 (命中 L011 大额零保价/L007/L008)
  - RISK004(跨境低申报+6地址) → 跨境申报 (命中 L017/L018 极高/L020 多地址)
  - RISK005(7 条投诉) → 投诉申诉 (命中 L025 30 天 3 次)
【普通用户 → 普通寄件下单】极低概率触发规则 = 负例
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

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event

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
        WHERE user_id NOT LIKE :prefix
        ORDER BY user_id LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.user_id for row in r.fetchall()]


async def _pick_shipment_user(db, user_id: str, prefer_cod: bool = False):
    where = "s.sender_user_id = :uid"
    params: dict = {"uid": user_id}
    if prefer_cod:
        where += " AND s.payment_method = '到付'"
    row = (await db.execute(text(f"""
        SELECT s.shipment_id, s.sender_user_id, s.receiver_address_id
        FROM shipment s
        WHERE {where}
        ORDER BY RAND() LIMIT 1
    """), params)).first()
    return (row.shipment_id, row.sender_user_id, row.receiver_address_id) if row else None


async def _pick_declaration_user(db, user_id: str):
    row = (await db.execute(text("""
        SELECT d.declaration_id, s.sender_user_id
        FROM customs_declaration d
        JOIN shipment s ON d.shipment_id = s.shipment_id
        WHERE s.sender_user_id = :uid
        ORDER BY RAND() LIMIT 1
    """), {"uid": user_id})).first()
    return (row.declaration_id, row.sender_user_id) if row else None


async def _pick_complaint_user(db, user_id: str):
    row = (await db.execute(text("""
        SELECT cr.record_id, cr.user_id
        FROM complaint_record cr WHERE cr.user_id = :uid
        ORDER BY RAND() LIMIT 1
    """), {"uid": user_id})).first()
    if row:
        return (str(row.record_id), row.user_id)
    return None


def _user_preferred_event(user_id: str) -> str:
    if user_id == "RISK001":
        return random.choice(["寄件下单", "寄件下单", "寄件下单", "到付签收"])
    elif user_id == "RISK002":
        return "到付签收"
    elif user_id == "RISK003":
        return "寄件下单"
    elif user_id == "RISK004":
        return "跨境申报"
    elif user_id == "RISK005":
        return random.choice(["投诉申诉", "投诉申诉", "寄件下单"])
    else:
        return random.choice(["寄件下单", "寄件下单", "寄件下单", "到付签收"])


async def gen_train_dataset(n_risk=30, n_normal=30, per_user=25, reset=False, dry_run=False):
    print("=" * 60)
    print("[物流风控] 训练数据集生成 (强标注, ml_score=NULL)")
    total_target = (n_risk + n_normal) * per_user
    print(f"目标: {n_risk} RISK × {per_user} + {n_normal} 普通 × {per_user} = {total_target} 条")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        if reset and not dry_run:
            print("\n[0] 清空训练用表 (risk_case/assessment/feature/event/user_profile)...")
            await db.execute(text("DELETE FROM risk_case"))
            await db.execute(text("DELETE FROM risk_assessment"))
            await db.execute(text("DELETE FROM risk_feature"))
            await db.execute(text("DELETE FROM risk_event"))
            await db.execute(text("DELETE FROM risk_user_profile"))
            await db.commit()
            print("  清空完成")

        print(f"\n[1] 选 {n_risk} RISK + {n_normal} 普通用户...")
        risk_users = await _pick_risk_users(db, n_risk)
        normal_users = await _pick_normal_users(db, n_normal)
        if not risk_users:
            print(f"  [FAIL] 没 RISK 用户, 先跑 gen_business_data.py (有 5 个)")
            return
        if not normal_users:
            print("  [FAIL] 没普通用户, 先跑 gen_business_data.py (有 50 个)")
            return
        if len(risk_users) < n_risk:
            print(f"  [WARN] RISK 实际 {len(risk_users)} 个, 降规模")
            n_risk = len(risk_users)
        if len(normal_users) < n_normal:
            print(f"  [WARN] 普通用户实际 {len(normal_users)} 个, 降规模")
            n_normal = len(normal_users)
        print(f"  RISK: {len(risk_users)} 个: {risk_users}")
        print(f"  普通: {len(normal_users)} 个 ({normal_users[0]} ~ {normal_users[-1]})")

        if dry_run:
            print(f"\n[DRY-RUN] 预演完成, 真跑去掉 --dry-run")
            return

        success = 0
        pos_count = 0
        neg_count = 0
        failed = 0
        plan: list[tuple[str, str]] = []
        for uid in risk_users:
            for _ in range(per_user):
                plan.append((uid, _user_preferred_event(uid)))
        for uid in normal_users:
            for _ in range(per_user):
                plan.append((uid, "寄件下单"))
        random.shuffle(plan)
        print(f"\n[2] 造 {len(plan)} 条事件 (乱序)...")
        risk_pos = 0
        normal_pos = 0
        for idx, (uid, event_type) in enumerate(plan, 1):
            try:
                if event_type == "寄件下单":
                    picked = await _pick_shipment_user(db, uid)
                    if not picked:
                        failed += 1
                        continue
                    sid, _, rid = picked
                    request = RiskCheckRequest(
                        event_type="寄件下单", source_id=sid, user_id=uid,
                        order_id=sid, receive_id=str(rid),
                    )
                elif event_type == "到付签收":
                    picked = await _pick_shipment_user(db, uid, prefer_cod=True)
                    if not picked:
                        picked = await _pick_shipment_user(db, uid)
                    if not picked:
                        failed += 1
                        continue
                    sid, _, rid = picked
                    request = RiskCheckRequest(
                        event_type="到付签收", source_id=sid, user_id=uid,
                        order_id=sid, receive_id=str(rid),
                    )
                elif event_type == "跨境申报":
                    picked = await _pick_declaration_user(db, uid)
                    if not picked:
                        picked = await _pick_shipment_user(db, uid)
                        if not picked:
                            failed += 1
                            continue
                        sid, _, rid = picked
                        request = RiskCheckRequest(
                            event_type="寄件下单", source_id=sid, user_id=uid,
                            order_id=sid, receive_id=str(rid),
                        )
                    else:
                        did, _ = picked
                        request = RiskCheckRequest(event_type="跨境申报", source_id=did, user_id=uid)
                elif event_type == "投诉申诉":
                    picked = await _pick_complaint_user(db, uid)
                    if not picked:
                        picked = await _pick_shipment_user(db, uid)
                        if not picked:
                            failed += 1
                            continue
                        sid, _, rid = picked
                        request = RiskCheckRequest(
                            event_type="寄件下单", source_id=sid, user_id=uid,
                            order_id=sid, receive_id=str(rid),
                        )
                    else:
                        rid_c, _ = picked
                        request = RiskCheckRequest(event_type="投诉申诉", source_id=rid_c, user_id=uid)
                else:
                    failed += 1
                    continue

                result = await process_event(db, request)
                success += 1
                if result.decision in ("拒绝", "人工审核"):
                    pos_count += 1
                    if uid.startswith(RISKY_USER_PREFIX):
                        risk_pos += 1
                    else:
                        normal_pos += 1
                else:
                    neg_count += 1
                if idx % 100 == 0 or idx == len(plan):
                    print(f"  进度 {idx}/{len(plan)}: 成功 {success}, 正例 {pos_count} ({100*pos_count/max(success,1):.1f}%)")
            except Exception as e:
                failed += 1
                if failed <= 10:
                    print(f"  [失败#{failed}] uid={uid}, ev={event_type}: {type(e).__name__}: {e}")

        print(f"\n[3] 强制 ml_score = NULL (训练数据无 ml 推理痕迹)...")
        await db.execute(text("UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL WHERE ml_score IS NOT NULL"))
        nc = (await db.execute(text("SELECT COUNT(*) FROM risk_assessment WHERE ml_score IS NULL"))).scalar()
        nn = (await db.execute(text("SELECT COUNT(*) FROM risk_assessment WHERE ml_score IS NOT NULL"))).scalar()
        await db.commit()
        print(f"  总 {nc+nn} 条, NULL: {nc}, 非 NULL: {nn}")

    print("\n" + "=" * 60)
    print("训练数据集生成完成!")
    print(f"  目标:       {total_target} 条 ({n_risk} RISK × {per_user} + {n_normal} 普通 × {per_user})")
    print(f"  实际成功:   {success} 条")
    print(f"  正例:       {pos_count} 条 ({100*pos_count/max(success,1):.1f}%)")
    print(f"  负例:       {neg_count} 条 ({100*neg_count/max(success,1):.1f}%)")
    print(f"  失败:       {failed} 条")
    print(f"  RISK 正例:  {risk_pos}/{n_risk*per_user} = {100*risk_pos/max(n_risk*per_user,1):.1f}%")
    print(f"  普通正例:   {normal_pos}/{n_normal*per_user} = {100*normal_pos/max(n_normal*per_user,1):.1f}%")
    print(f"  ml_score:   全部 NULL")
    print("=" * 60)
    ratio = pos_count / max(success, 1)
    if ratio < 0.25:
        print(f"[WARN] 正例比例 {100*ratio:.1f}% < 25%, 模型可能假收敛, 建议扩大 RISK 用户 per_user")
    elif ratio > 0.70:
        print(f"[WARN] 正例比例 {100*ratio:.1f}% > 70%, 正负极不平衡可能过拟合")
    print("\n下一步: python scripts/train_xgb_model.py")


async def _runner():
    try:
        await gen_train_dataset(
            n_risk=args.n_risk, n_normal=args.n_normal,
            per_user=args.per_user, reset=args.reset, dry_run=args.dry_run,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="物流风控训练数据集 (强标注, ml_score=NULL)")
    parser.add_argument("--n-risk", type=int, default=5, help="RISK 用户 (默认 5)")
    parser.add_argument("--n-normal", type=int, default=20, help="普通用户 (默认 20)")
    parser.add_argument("--per-user", type=int, default=20, help="每用户条数 (默认 20)")
    parser.add_argument("--reset", action="store_true", help="先清空风控评估/事件/特征/画像/案件表")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()
    asyncio.run(_runner())

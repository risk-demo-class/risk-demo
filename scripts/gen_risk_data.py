"""
物流风控系统 - 模拟风控评估数据生成 (异步)
从现有物流业务数据中随机选取运单/申报/投诉，调用风控引擎生成评估记录
支持 --balance-pos 优先用 RISK00X 系列高风险用户，拉高训练正例比例 >= 20%
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event

RISKY_USER_PREFIX = "RISK"


async def _pick_shipment(db, balance_pos: bool, prefer_cod: bool = False):
    """挑运单用于"寄件下单/到付签收"事件.
    返回: (shipment_id, user_id, receiver_address_id)
    """
    where_extra = ""
    params = {}
    if balance_pos and random.random() < 0.8:
        where_extra = " AND s.sender_user_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    if prefer_cod:
        where_extra += " AND s.payment_method = '到付'"

    sql = f"""
        SELECT s.shipment_id, s.sender_user_id, s.receiver_address_id
        FROM shipment s
        WHERE 1=1 {where_extra}
        ORDER BY RAND() LIMIT 1
    """
    row = (await db.execute(text(sql), params)).first()
    return (row.shipment_id, row.sender_user_id, row.receiver_address_id) if row else None


async def _pick_declaration(db, balance_pos: bool):
    """挑跨境申报单用于"跨境申报"事件."""
    where_extra = ""
    params = {}
    if balance_pos and random.random() < 0.8:
        where_extra = " AND s.sender_user_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    sql = f"""
        SELECT d.declaration_id, s.sender_user_id
        FROM customs_declaration d
        JOIN shipment s ON d.shipment_id = s.shipment_id
        WHERE 1=1 {where_extra}
        ORDER BY RAND() LIMIT 1
    """
    row = (await db.execute(text(sql), params)).first()
    return (row.declaration_id, row.sender_user_id) if row else None


async def _pick_complaint(db, balance_pos: bool):
    """挑投诉记录用于"投诉申诉"事件."""
    where_extra = ""
    params = {}
    if balance_pos and random.random() < 0.8:
        where_extra = " AND cr.user_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    sql = f"""
        SELECT cr.record_id, cr.user_id
        FROM complaint_record cr
        WHERE 1=1 {where_extra}
        ORDER BY RAND() LIMIT 1
    """
    row = (await db.execute(text(sql), params)).first()
    if row:
        return (str(row.record_id), row.user_id)
    return None


async def generate_risk_data(count: int = 30, balance_pos: bool = False, target_pos_ratio: float | None = None):
    """生成 {count} 条风控评估记录 (异步)."""
    if target_pos_ratio is not None and not balance_pos:
        print(f"⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
        balance_pos = True
    if target_pos_ratio is not None:
        print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标")

    max_rounds = 10
    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            if balance_pos and round_idx == 0:
                print(f"⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户, 拉高训练正例比例")
            success = 0
            pos_count = 0
            for i in range(count):
                # 事件类型概率: 寄件60% / 到付20% / 跨境12% / 投诉8%
                r = random.random()
                if r < 0.60:
                    picked = await _pick_shipment(db, balance_pos, prefer_cod=False)
                    if not picked:
                        if target_pos_ratio: continue
                        print(f"  [{i+1}/{count}] 没有可用运单, 跳过")
                        continue
                    shipment_id, user_id, recv_addr_id = picked
                    req = RiskCheckRequest(
                        event_type="寄件下单",
                        source_id=shipment_id,
                        user_id=user_id,
                        order_id=shipment_id,
                        receive_id=str(recv_addr_id),
                    )
                    tag = "寄件下单"
                elif r < 0.80:
                    picked = await _pick_shipment(db, balance_pos, prefer_cod=True)
                    if not picked:
                        picked = await _pick_shipment(db, balance_pos)
                    if not picked:
                        if target_pos_ratio: continue
                        print(f"  [{i+1}/{count}] 没有可用到付运单, 跳过")
                        continue
                    shipment_id, user_id, recv_addr_id = picked
                    req = RiskCheckRequest(
                        event_type="到付签收",
                        source_id=shipment_id,
                        user_id=user_id,
                        order_id=shipment_id,
                        receive_id=str(recv_addr_id),
                    )
                    tag = "到付签收"
                elif r < 0.92:
                    picked = await _pick_declaration(db, balance_pos)
                    if not picked:
                        if target_pos_ratio: continue
                        print(f"  [{i+1}/{count}] 没有可用跨境申报, 跳过")
                        continue
                    decl_id, user_id = picked
                    req = RiskCheckRequest(
                        event_type="跨境申报",
                        source_id=decl_id,
                        user_id=user_id,
                    )
                    tag = "跨境申报"
                else:
                    picked = await _pick_complaint(db, balance_pos)
                    if not picked:
                        if target_pos_ratio: continue
                        print(f"  [{i+1}/{count}] 没有可用投诉记录, 跳过")
                        continue
                    rec_id, user_id = picked
                    req = RiskCheckRequest(
                        event_type="投诉申诉",
                        source_id=rec_id,
                        user_id=user_id,
                    )
                    tag = "投诉申诉"
                try:
                    result = await process_event(db, req)
                    success += 1
                    if result.decision in ("拒绝", "人工审核"):
                        pos_count += 1
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] {tag} 用户={user_id}, "
                              f"评分={result.final_score}, 决策={result.decision}, 命中={result.rule_count}条")
                except Exception as e:
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] 失败: {type(e).__name__}: {e}")

        current_ratio = pos_count / success if success else 0.0
        print(f"\n[第 {round_idx+1}/{max_rounds} 轮] 成功 {success} 条, 正例 {pos_count} 条 ({current_ratio*100:.1f}%)")

        if target_pos_ratio is not None:
            if current_ratio >= target_pos_ratio:
                print(f"✅ 正例比例 {current_ratio*100:.1f}% >= 目标 {target_pos_ratio*100:.0f}%, 达标!")
                break
            elif round_idx < max_rounds - 1:
                print(f"⚠️  正例比例 {current_ratio*100:.1f}% < 目标 {target_pos_ratio*100:.0f}%, 继续造数据...")
                continue
            else:
                print(f"❌ 跑完 {max_rounds} 轮仍未达标, 最后比例 {current_ratio*100:.1f}%")
                break
        else:
            break
    print(
        f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 "
        + (f"({pos_count / success * 100:.1f}%)" if success else "")
    )


async def _runner():
    try:
        await generate_risk_data(
            count=args.count,
            balance_pos=args.balance_pos,
            target_pos_ratio=args.target_pos_ratio,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造物流风控评估数据. --balance-pos 优先挑 RISK 高风险用户."
    )
    parser.add_argument("--count", type=int, default=80, help="评估条数 (默认 80)")
    parser.add_argument("--balance-pos", action="store_true", help="优先 RISK 用户, 正例 >= 20%")
    parser.add_argument("--target-pos-ratio", type=float, default=None, help="目标正例比例 (0.0-1.0)")
    args = parser.parse_args()
    asyncio.run(_runner())

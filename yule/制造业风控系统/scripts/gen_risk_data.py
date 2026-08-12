"""
制造业风控系统 - 模拟风控评估数据生成 (异步)
从现有业务数据中随机选取订货订单/保修单/串货举报, 调用风控引擎生成评估记录
用于填充仪表盘和案件管理页面的初始数据

P4-L3 2026-08-08 新增 --balance-pos:
    XGBoost 训练是 2 分类, 需要关注正负样本比. 业务上"高风险评估"只占 5%~10%.
    --balance-pos 启用时: 优先挑 RISK 高风险经销商, 把正例比例拉到 25%~35%.
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

RISKY_DEALER_PREFIX = "RISK"


async def _pick_order(db, balance_pos: bool) -> tuple | None:
    """挑一张订货订单; balance_pos=True 时优先从 RISK 高风险经销商里选."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT order_id, dealer_id
            FROM order_info
            WHERE dealer_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_DEALER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.order_id, row.dealer_id)
    r = await db.execute(text("""
        SELECT order_id, dealer_id
        FROM order_info
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.order_id, row.dealer_id) if row else None


async def _pick_warranty(db, balance_pos: bool) -> tuple | None:
    """挑一条保修单; balance_pos=True 时优先从 RISK 高风险经销商里选."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT w.warranty_id, oi.dealer_id
            FROM warranty_record w
            JOIN order_info oi ON w.order_id = oi.order_id
            WHERE oi.dealer_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_DEALER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.warranty_id, row.dealer_id)
    r = await db.execute(text("""
        SELECT w.warranty_id, oi.dealer_id
        FROM warranty_record w
        JOIN order_info oi ON w.order_id = oi.order_id
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.warranty_id, row.dealer_id) if row else None


async def _pick_report(db, balance_pos: bool) -> tuple | None:
    """挑一条跨区串货举报; balance_pos=True 时优先从 RISK 高风险经销商里选."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT report_id, dealer_id
            FROM cross_region_report
            WHERE dealer_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_DEALER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.report_id, row.dealer_id)
    r = await db.execute(text("""
        SELECT report_id, dealer_id
        FROM cross_region_report
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.report_id, row.dealer_id) if row else None


async def generate_risk_data(count: int = 30, balance_pos: bool = False,
                             target_pos_ratio: float | None = None):
    """随机从现有业务数据中选取事件, 对每条执行风控检查 (异步)."""
    if target_pos_ratio is not None and not balance_pos:
        print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
        balance_pos = True
    if target_pos_ratio is not None:
        print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标")

    max_rounds = 10
    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            if balance_pos and round_idx == 0:
                print("⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险经销商, 拉高训练正例比例")
            success = 0
            pos_count = 0
            for i in range(count):
                # balance_pos 时更倾向用保修 (套保/维修费异常样本多)
                wr_odds = 0.5 if balance_pos else 0.3
                roll = random.random()
                if roll < wr_odds:
                    picked = await _pick_warranty(db, balance_pos)
                    if not picked:
                        picked = await _pick_order(db, balance_pos)
                    if not picked:
                        if target_pos_ratio is not None:
                            continue
                        print(f"  [{i+1}/{count}] 没有可用保修/订单, 跳过")
                        continue
                    wid, dealer_id = picked
                    request = RiskCheckRequest(
                        event_type="设备保修", source_id=wid, user_id=dealer_id,
                    )
                    tag = "保修"
                elif roll < wr_odds + 0.15:
                    picked = await _pick_report(db, balance_pos)
                    if not picked:
                        if target_pos_ratio is not None:
                            continue
                        print(f"  [{i+1}/{count}] 没有可用串货举报, 跳过")
                        continue
                    rid, dealer_id = picked
                    request = RiskCheckRequest(
                        event_type="跨区串货举报", source_id=rid, user_id=dealer_id,
                    )
                    tag = "串货"
                else:
                    picked = await _pick_order(db, balance_pos)
                    if not picked:
                        if target_pos_ratio is not None:
                            continue
                        print(f"  [{i+1}/{count}] 没有可用订单, 跳过")
                        continue
                    order_id, dealer_id = picked
                    request = RiskCheckRequest(
                        event_type="经销商订货",
                        source_id=order_id,
                        user_id=dealer_id,
                        order_id=order_id,
                    )
                    tag = "订货"
                try:
                    result = await process_event(db, request)
                    success += 1
                    if result.decision in ("拒绝", "人工审核"):
                        pos_count += 1
                    if i % 10 == 0 or result.decision in ("拒绝", "人工审核"):
                        print(f"  [{i+1}/{count}] {tag} source={request.source_id} "
                              f"user={dealer_id} → {result.decision} ({result.final_score})")
                except Exception as e:
                    print(f"  [{i+1}/{count}] {tag} source={request.source_id} 失败: {type(e).__name__}: {e}")

            pos_ratio = pos_count / success if success > 0 else 0
            print(f"\n本轮完成: 成功 {success} 条, 正例 {pos_count} 条, 正例比例 {pos_ratio*100:.1f}%")

            # target_pos_ratio 模式: 达标或满轮退出
            if target_pos_ratio is not None:
                if pos_ratio >= target_pos_ratio:
                    print(f"✅ 正例比例达标 ({pos_ratio*100:.1f}% >= {target_pos_ratio*100:.0f}%), 退出")
                    break
                if round_idx == max_rounds - 1:
                    print("⚠️ 达到最大轮数仍未达标, 可调大 --count 或先造更多 RISK 数据")
            else:
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="从现有订货/保修/举报数据生成风控评估记录 (制造业)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""例:
  python scripts/gen_risk_data.py --count 30
  python scripts/gen_risk_data.py --balance-pos --target-pos-ratio 0.30 --count 200
        """,
    )
    parser.add_argument("--count", type=int, default=30, help="评估条数 (默认 30)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="优先挑 RISK 高风险经销商, 拉高正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0-1), 循环造数据直到达标")
    args = parser.parse_args()
    asyncio.run(generate_risk_data(
        count=args.count, balance_pos=args.balance_pos,
        target_pos_ratio=args.target_pos_ratio,
    ))

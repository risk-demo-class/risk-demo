"""
旅游风控系统 - 模拟风控评估数据生成 (异步)
从旅游业务数据中随机选取 订单/退改/签证, 调用风控引擎生成评估记录
用于填充仪表盘和案件管理页面的初始数据

--balance-pos: 优先挑 RISK 高风险用户, 拉高训练正例比例 (XGBoost 训练推荐)
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


async def _pick_order(db, balance_pos: bool) -> tuple | None:
    """挑一条旅游订单, 返回 (order_id, user_id)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT order_id, user_id FROM order_info
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.order_id, row.user_id)
    r = await db.execute(text(
        "SELECT order_id, user_id FROM order_info ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return (row.order_id, row.user_id) if row else None


async def _pick_refund(db, balance_pos: bool) -> tuple | None:
    """挑一条退改单, 返回 (refund_id, user_id)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT refund_id, user_id FROM order_refund
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.refund_id, row.user_id)
    r = await db.execute(text(
        "SELECT refund_id, user_id FROM order_refund ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return (row.refund_id, row.user_id) if row else None


async def _pick_visa(db, balance_pos: bool) -> tuple | None:
    """挑一条签证申请, 返回 (visa_id, user_id)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT visa_id, user_id FROM visa_application
            WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.visa_id, row.user_id)
    r = await db.execute(text(
        "SELECT visa_id, user_id FROM visa_application ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return (row.visa_id, row.user_id) if row else None


async def generate_risk_data(count: int = 30, balance_pos: bool = False, target_pos_ratio: float | None = None):
    """随机从旅游业务数据中选取, 对每条执行风控检查."""
    if target_pos_ratio is not None and not balance_pos:
        print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
        balance_pos = True

    max_rounds = 10
    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            success = 0
            pos_count = 0
            for i in range(count):
                # 事件混合: 60% 预订下单 / 30% 退改申请 / 10% 签证申请
                evt = random.choices(
                    ["预订下单", "退改申请", "签证申请"],
                    weights=[60, 30, 10],
                )[0]
                if evt == "预订下单":
                    picked = await _pick_order(db, balance_pos)
                    if not picked:
                        continue
                    order_id, user_id = picked
                    request = RiskCheckRequest(
                        event_type="预订下单", source_id=order_id, user_id=user_id,
                        order_id=order_id,
                    )
                elif evt == "退改申请":
                    picked = await _pick_refund(db, balance_pos)
                    if not picked:
                        picked = await _pick_order(db, balance_pos)
                        if not picked:
                            continue
                        order_id, user_id = picked
                        request = RiskCheckRequest(
                            event_type="预订下单", source_id=order_id, user_id=user_id,
                            order_id=order_id,
                        )
                    else:
                        refund_id, user_id = picked
                        request = RiskCheckRequest(
                            event_type="退改申请", source_id=refund_id, user_id=user_id,
                        )
                else:
                    picked = await _pick_visa(db, balance_pos)
                    if not picked:
                        continue
                    visa_id, user_id = picked
                    request = RiskCheckRequest(
                        event_type="签证申请", source_id=visa_id, user_id=user_id,
                    )

                try:
                    result = await process_event(db, request)
                    success += 1
                    if result.decision in ("拒绝", "人工审核"):
                        pos_count += 1
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] {evt} 用户={user_id}, "
                              f"评分={result.final_score}, 决策={result.decision}, "
                              f"命中={result.rule_count}条规则")
                except Exception as e:
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] 失败: {e}")

        current_ratio = pos_count / success if success else 0.0
        print(f"\n[第 {round_idx+1}/{max_rounds} 轮] 成功 {success} 条, 正例 {pos_count} 条 ({current_ratio*100:.1f}%)")

        if target_pos_ratio is not None:
            if current_ratio >= target_pos_ratio:
                print(f"✅ 正例比例 {current_ratio*100:.1f}% >= 目标 {target_pos_ratio*100:.0f}%, 达标!")
                break
            if round_idx >= max_rounds - 1:
                print(f"❌ 跑完 {max_rounds} 轮仍未达标, 建议 gen_risky_users.py --count 30 扩大样本")
                break
        else:
            break

    print(f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 ({pos_count/max(success,1)*100:.1f}%)")


async def _runner():
    from app.database import async_engine
    try:
        await generate_risk_data(
            count=args.count,
            balance_pos=args.balance_pos,
            target_pos_ratio=args.target_pos_ratio,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="造旅游风控评估数据.")
    parser.add_argument("--count", type=int, default=30, help="评估条数 (默认 30)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="优先挑 RISK 高风险用户, 拉高训练正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 使用")
    args = parser.parse_args()
    asyncio.run(_runner())

"""
旅游风控系统 - 模拟风控评估数据生成 (异步)

从行业业务表随机选取 订单/签证申请, 调用风控引擎生成评估记录,
用于填充仪表盘、案件管理、评估历史, 并为 XGBoost 训练提供数据.

事件类型: 预订 / 支付 / 签证申请 / 退改签

P4-L3: --balance-pos 优先挑 RISK 高风险用户, 拉高正例比例;
       --target-pos-ratio 循环造数据直到正例比例达标 (训练推荐 25%-35%).
"""
import argparse
import asyncio
import os
import random
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

RISKY_USER_PREFIX = "RISK"


async def _pick_order(db, balance_pos: bool) -> tuple | None:
    """挑一条订单; balance_pos=True 时优先从 RISK 高风险用户里选."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT order_id, user_id
            FROM order_info
            WHERE user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.order_id, row.user_id)
    r = await db.execute(text("""
        SELECT order_id, user_id
        FROM order_info
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.order_id, row.user_id) if row else None


async def _pick_refund_order(db, balance_pos: bool) -> tuple | None:
    """挑一条退改签订单 (状态=已退订/已取消)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT order_id, user_id
            FROM order_info
            WHERE user_id LIKE :prefix AND order_status IN ('已退订', '已取消')
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.order_id, row.user_id)
    r = await db.execute(text("""
        SELECT order_id, user_id
        FROM order_info
        WHERE order_status IN ('已退订', '已取消')
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.order_id, row.user_id) if row else None


async def _pick_visa(db, balance_pos: bool) -> tuple | None:
    """挑一条签证申请; balance_pos=True 时优先 RISK 用户."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT visa_id, user_id
            FROM visa_application
            WHERE user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.visa_id, row.user_id)
    r = await db.execute(text("""
        SELECT visa_id, user_id
        FROM visa_application
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.visa_id, row.user_id) if row else None


async def generate_risk_data(
    count: int = 30,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
) -> None:
    """随机选取业务记录执行风控检查, 生成评估数据."""
    if target_pos_ratio is not None and not balance_pos:
        print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
        balance_pos = True
    if target_pos_ratio is not None:
        print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标")

    max_rounds = 10
    success = 0
    pos_count = 0
    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            if balance_pos and round_idx == 0:
                print("⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户, 拉高训练正例比例")
            for i in range(count):
                # 事件类型分布: 预订 50% / 支付 15% / 签证申请 20% / 退改签 15%
                et = random.choices(
                    ["预订", "预订", "预订", "支付", "支付", "签证申请", "签证申请", "退改签"],
                    k=1,
                )[0]
                if et == "签证申请":
                    picked = await _pick_visa(db, balance_pos)
                    if not picked:
                        continue
                    visa_id, user_id = picked
                    request = RiskCheckRequest(
                        event_type="签证申请",
                        source_id=visa_id,
                        user_id=user_id,
                    )
                    tag = "签证"
                elif et == "退改签":
                    picked = await _pick_refund_order(db, balance_pos)
                    if not picked:
                        continue
                    order_id, user_id = picked
                    request = RiskCheckRequest(
                        event_type="退改签",
                        source_id=order_id,
                        user_id=user_id,
                        order_id=order_id,
                    )
                    tag = "退改签"
                else:
                    picked = await _pick_order(db, balance_pos)
                    if not picked:
                        continue
                    order_id, user_id = picked
                    request = RiskCheckRequest(
                        event_type=et,
                        source_id=order_id,
                        user_id=user_id,
                        order_id=order_id,
                        event_data={
                            "device_id": random.choice(["DEV_A", "DEV_B", "DEV_RISK_BOT", "DEV_C"]),
                            "ip": random.choice(["1.2.3.4", "45.155.204.101", "8.8.8.8"]),
                        },
                    )
                    tag = "订单" if et == "预订" else "支付"
                try:
                    result = await process_event(db, request)
                    success += 1
                    if result.decision in ("拒绝", "人工审核"):
                        pos_count += 1
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] {tag} 用户={user_id}, "
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
                print(f"❌ 跑完 {max_rounds} 轮仍未达标, 最后比例 {current_ratio*100:.1f}%")
                break
            print(f"⚠️  正例比例 {current_ratio*100:.1f}% < 目标 {target_pos_ratio*100:.0f}%, 继续造数据...")
        else:
            break

    print(f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 ({pos_count/success*100:.1f}%)")


async def _runner(args) -> None:
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
    parser = argparse.ArgumentParser(
        description="造风控评估数据 (旅游版). --balance-pos 优先挑 RISK 高风险用户."
    )
    parser.add_argument("--count", type=int, default=30, help="评估条数 (默认 30)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="优先挑 RISK 高风险用户, 拉高训练正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 使用")
    args = parser.parse_args()
    asyncio.run(_runner(args))

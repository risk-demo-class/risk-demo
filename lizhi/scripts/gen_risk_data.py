"""
旅游风控系统 - 模拟风控评估数据生成 (异步)

从旅游业务数据中随机选取订单/签证申请, 调用 process_event 生成评估记录,
用于填充仪表盘、案件管理页面和 XGBoost 训练数据.

事件类型 (对应 1-业务说明.md):
  - 订单类: 预订下单 / 支付成功 / 出票确认 / 出行核销 / 退改签申请 / 索赔投诉 / 评价发布
  - 签证类: 签证申请 (source_id=visa_id)

【P4-L3】--balance-pos: 优先挑 RISK 高风险用户, 把正例 (人工审核/拒绝) 比例拉到 >= 20%.
【训练取数】写完评估后强制 UPDATE ml_score=NULL: 训练脚本只取"无 ml 痕迹"的数据
(避免未训练模型写入的 0.0 垃圾值).

用法:
  python scripts/gen_risk_data.py                        # 默认 30 条
  python scripts/gen_risk_data.py --count 300 --balance-pos
  python scripts/gen_risk_data.py --count 400 --balance-pos --target-pos-ratio 0.30
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

RISKY_USER_PREFIX = "RISK"

# 订单类事件池 (预订下单为主, 退改签申请留给高风险用户拉正例)
ORDER_EVENT_TYPES = ["预订下单", "预订下单", "预订下单", "支付成功", "出票确认",
                     "出行核销", "退改签申请", "索赔投诉", "评价发布"]


async def _pick_order(db, balance_pos: bool) -> tuple | None:
    """挑一条订单, 返回 (order_id, user_id)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT order_id, user_id FROM order_info
            WHERE user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.order_id, row.user_id)
    r = await db.execute(text("""
        SELECT order_id, user_id FROM order_info
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.order_id, row.user_id) if row else None


async def _pick_visa(db, balance_pos: bool) -> tuple | None:
    """挑一条签证申请, 返回 (visa_id, user_id)."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT v.visa_id, v.user_id
            FROM visa_application v
            WHERE v.user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.visa_id, row.user_id)
    r = await db.execute(text("""
        SELECT visa_id, user_id FROM visa_application
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.visa_id, row.user_id) if row else None


async def generate_risk_data(count: int = 30, balance_pos: bool = False,
                             target_pos_ratio: float | None = None):
    """随机选订单/签证 → process_event → 评估记录 (ml_score 置 NULL)."""
    if target_pos_ratio is not None and not balance_pos:
        print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
        balance_pos = True

    max_rounds = 10
    success = 0
    pos_count = 0

    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            if balance_pos and round_idx == 0:
                print("⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户, 拉高正例比例")
            for i in range(count):
                use_visa = random.random() < (0.35 if balance_pos else 0.20)
                if use_visa:
                    picked = await _pick_visa(db, balance_pos)
                    if not picked:
                        continue
                    visa_id, user_id = picked
                    request = RiskCheckRequest(
                        event_type="签证申请", source_id=visa_id, user_id=user_id,
                    )
                    tag = "签证"
                else:
                    picked = await _pick_order(db, balance_pos)
                    if not picked:
                        continue
                    order_id, user_id = picked
                    event_type = random.choice(ORDER_EVENT_TYPES)
                    request = RiskCheckRequest(
                        event_type=event_type, source_id=order_id, user_id=user_id,
                        order_id=order_id,
                    )
                    tag = "订单"
                try:
                    result = await process_event(db, request)
                    # 训练取数: 显式置 ml_score=NULL (见脚本 docstring)
                    await db.execute(
                        text("UPDATE risk_assessment SET ml_score=NULL WHERE event_id=:eid"),
                        {"eid": result.event_id},
                    )
                    await db.commit()
                    success += 1
                    if result.decision in ("拒绝", "人工审核"):
                        pos_count += 1
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] {tag} 用户={user_id}, "
                              f"评分={result.final_score}, 决策={result.decision}, "
                              f"命中={result.rule_count}条规则")
                except Exception as e:
                    await db.rollback()
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] 失败: {e}")

        current_ratio = pos_count / success if success else 0.0
        print(f"\n[第 {round_idx+1}/{max_rounds} 轮] 成功 {success} 条, "
              f"正例 {pos_count} 条 ({current_ratio*100:.1f}%)")

        if target_pos_ratio is not None:
            if current_ratio >= target_pos_ratio:
                print(f"✅ 正例比例 {current_ratio*100:.1f}% >= 目标 {target_pos_ratio*100:.0f}%, 达标!")
                break
            if round_idx >= max_rounds - 1:
                print(f"❌ 跑完 {max_rounds} 轮仍未达标, 最后比例 {current_ratio*100:.1f}%")
                break
        else:
            break

    print(f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 "
          f"({pos_count/max(1, success)*100:.1f}%)")


async def _runner():
    from app.database import async_engine
    try:
        await generate_risk_data(
            count=args.count, balance_pos=args.balance_pos,
            target_pos_ratio=args.target_pos_ratio,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="旅游风控 - 造评估数据. --balance-pos 优先挑 RISK 高风险用户拉高正例比例."
    )
    parser.add_argument("--count", type=int, default=30, help="每轮评估条数 (默认 30)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="优先挑 RISK00X 高风险用户, 让正例比例 >= 20%")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos, 循环造数据直到达标")
    args = parser.parse_args()
    asyncio.run(_runner())

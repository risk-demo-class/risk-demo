"""
制造业风控系统 - 模拟风控评估数据生成 (异步)
从业务表 (订货单/保修工单/串货举报) 随机选取事件, 调用风控引擎生成评估记录.

支持:
  --balance-pos      80% 概率从 RISK 高风险经销商挑样本, 拉高训练正例比例
  --target-pos-ratio 目标正例比例, 循环造数据直到达标 (最多 10 轮)

用法:
  python scripts/gen_risk_data.py                          # 随机 30 条
  python scripts/gen_risk_data.py --count 200 --balance-pos --target-pos-ratio 0.30
"""
import argparse
import asyncio
import os
import random
import sys

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event
from scripts.mfg_pickers import build_request, pick_random_event


async def generate_risk_data(
    count: int = 30,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
):
    """随机从业务表选取事件执行风控检查.

    Args:
        count: 评估条数
        balance_pos: True 时优先从 RISK 高风险经销商挑样本
        target_pos_ratio: 目标正例比例 (0.0-1.0), 循环造数据直到达标
    """
    if target_pos_ratio is not None and not balance_pos:
        print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
        balance_pos = True
    if target_pos_ratio is not None:
        print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标")

    max_rounds = 10
    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            if balance_pos and round_idx == 0:
                print("⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险经销商")
            success = 0
            pos_count = 0
            for i in range(count):
                picked = await pick_random_event(db, balance_pos)
                if not picked:
                    if target_pos_ratio is not None:
                        continue
                    print(f"  [{i+1}/{count}] 没有可用事件, 跳过")
                    continue
                event_type, source_id, user_id, order_id = picked
                request = build_request(event_type, source_id, user_id, order_id)
                try:
                    result = await process_event(db, request)
                    success += 1
                    if result.decision in ("拒绝", "人工审核"):
                        pos_count += 1
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] {event_type} 经销商={user_id}, "
                              f"评分={result.final_score}, 决策={result.decision}, "
                              f"命中={result.rule_count}条规则")
                except Exception as e:
                    await db.rollback()
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] 失败: {e}")

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
                print(f"❌ 跑完 {max_rounds} 轮仍未达标")
                break
        else:
            break

    print(f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 "
          f"({pos_count/max(success,1)*100:.1f}%)")


async def _runner():
    """包装函数: 跑完后显式 dispose engine."""
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
        description="造风控评估数据 (制造业). --balance-pos 优先挑 RISK 经销商拉高正例比例."
    )
    parser.add_argument("--count", type=int, default=30, help="评估条数 (默认 30)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="优先挑 RISK00X 高风险经销商, 让训练时正例比例 >= 20%")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 循环造数据直到达标")
    args = parser.parse_args()
    asyncio.run(_runner())

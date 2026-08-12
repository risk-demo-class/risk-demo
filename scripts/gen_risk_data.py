"""
医疗风控系统 - 模拟风控评估数据生成 (异步)
从现有业务数据中随机选取 挂号/处方/结算/药品订单, 调用风控引擎生成评估记录
用于填充仪表盘和案件管理页面的初始数据, 以及 XGBoost 训练数据

--balance-pos:
    XGBoost 训练是 2 分类, 需要关注正负样本比. 业务上"高风险评估"只占 5%~10%,
    想要好训练效果, 应保证正例 (拒绝/人工审核) 占比 >= 20%.
    --balance-pos 启用时: 优先挑 RISK00X 系列高风险患者, 把正例比例拉到 25%~35%.
"""
import argparse
import asyncio
import os
import random
import sys

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

# --balance-pos 用 RISK 前缀的预置高风险患者 (gen_risky_users.py 造过)
RISKY_USER_PREFIX = "RISK"


async def _pick_document(db, balance_pos: bool) -> tuple | None:
    """随机挑一条诊疗单据. 返回 (event_type, source_id, user_id) 或 None.

    4 种单据等权重随机; balance_pos=True 时 80% 概率优先从 RISK 高风险患者里挑.
    """
    pickers = [
        # (event_type, 表, 主键列)
        ("挂号", "appointment", "appt_id"),
        ("处方开具", "prescription", "rx_id"),
        ("医保结算", "insurance_claim", "claim_id"),
        ("药品下单", "drug_order", "drug_order_id"),
    ]
    random.shuffle(pickers)

    for event_type, table, pk in pickers:
        if balance_pos and random.random() < 0.8:
            r = await db.execute(text(f"""
                SELECT {pk} AS sid, user_id FROM {table}
                WHERE user_id LIKE :prefix
                ORDER BY RAND() LIMIT 1
            """), {"prefix": f"{RISKY_USER_PREFIX}%"})
            row = r.first()
            if row:
                return (event_type, row.sid, row.user_id)
        r = await db.execute(text(f"""
            SELECT {pk} AS sid, user_id FROM {table}
            ORDER BY RAND() LIMIT 1
        """))
        row = r.first()
        if row:
            return (event_type, row.sid, row.user_id)
    return None


async def generate_risk_data(count: int = 30, balance_pos: bool = False, target_pos_ratio: float | None = None):
    """
    随机从现有诊疗单据中选取, 对每条执行风控检查 (异步).

    Args:
        count: 评估条数
        balance_pos: True 时优先从 RISK 高风险患者挑样本, 拉高正例比例
        target_pos_ratio: 目标正例比例 (0.0-1.0), 设置后自动循环造数据直到达标
    """
    if target_pos_ratio is not None and not balance_pos:
        print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
        balance_pos = True
    if target_pos_ratio is not None:
        print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标")

    max_rounds = 10  # 最多循环 10 轮, 避免无限循环
    success = 0
    pos_count = 0
    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            if balance_pos and round_idx == 0:
                print("⚠️  --balance-pos 模式: 优先挑 RISK 高风险患者, 拉高训练正例比例")
            success = 0
            pos_count = 0
            for i in range(count):
                picked = await _pick_document(db, balance_pos)
                if not picked:
                    if target_pos_ratio is not None:
                        continue
                    print(f"  [{i+1}/{count}] 没有可用诊疗单据, 跳过 (先跑 init_db.py)")
                    continue
                event_type, source_id, user_id = picked
                request = RiskCheckRequest(
                    event_type=event_type,
                    source_id=source_id,
                    user_id=user_id,
                )
                try:
                    result = await process_event(db, request)
                    success += 1
                    # 决策是"拒绝"或"人工审核"= 正例
                    if result.decision in ("拒绝", "人工审核"):
                        pos_count += 1
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] {event_type} 患者={user_id}, "
                              f"评分={result.final_score}, 决策={result.decision}, "
                              f"命中={result.rule_count}条规则")
                except Exception as e:
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] 失败: {e}")

        current_ratio = pos_count / success if success else 0.0
        print(f"\n[第 {round_idx+1}/{max_rounds} 轮] 成功 {success} 条, 正例 {pos_count} 条 ({current_ratio*100:.1f}%)")

        # target 模式: 检查正例比例是否达标
        if target_pos_ratio is not None:
            if current_ratio >= target_pos_ratio:
                print(f"✅ 正例比例 {current_ratio*100:.1f}% >= 目标 {target_pos_ratio*100:.0f}%, 达标!")
                break
            elif round_idx < max_rounds - 1:
                print(f"⚠️  正例比例 {current_ratio*100:.1f}% < 目标 {target_pos_ratio*100:.0f}%, 继续造数据...")
                continue
            else:
                print(f"❌ 跑完 {max_rounds} 轮仍未达标, 最后比例 {current_ratio*100:.1f}%")
                print("   建议: 跑 scripts/gen_risky_users.py 扩大 RISK 患者规模 (默认只 5 个不够)")
                break
        else:
            # 非 target 模式: 跑完就退出
            break

    ratio = pos_count / success * 100 if success else 0.0
    print(f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 ({ratio:.1f}%)")


async def _runner():
    """包装函数: 业务跑完后显式 dispose engine, 避免 Event loop is closed 警告"""
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
        description="造医疗风控评估数据. --balance-pos 优先挑 RISK 高风险患者, 拉高训练正例比例."
    )
    parser.add_argument("--count", type=int, default=30, help="评估条数 (默认 30)")
    parser.add_argument(
        "--balance-pos", action="store_true",
        help="优先挑 RISK00X 高风险患者, 让训练时正例比例 >= 20% (XGBoost 推荐值)",
    )
    parser.add_argument(
        "--target-pos-ratio", type=float, default=None,
        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 使用, 循环造数据直到达标. 例: --target-pos-ratio 0.30",
    )
    args = parser.parse_args()
    asyncio.run(_runner())

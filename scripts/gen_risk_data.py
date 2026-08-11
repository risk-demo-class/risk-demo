"""
医疗风控系统 - 模拟风控评估数据生成 (异步)
从现有业务数据中随机选取结算/处方/挂号/药品订单, 调用风控引擎生成评估记录
用于填充仪表盘 / 案件管理页面 / XGBoost 训练数据

数据规模加大 (用户要求): 默认 --count 10000 条评估, 高风险种子用户 100 个 (gen_risky_users.py --count 100).
--balance-pos 启用时优先挑 RISK 前缀高风险用户, 把正例比例拉到目标值.
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

# 4 类事件 → (业务表, 业务单ID字段)
EVENT_POOL = [
    ("医保结算", "insurance_claim", "claim_id"),
    ("处方审核", "prescription", "rx_id"),
    ("挂号", "appointment", "appt_id"),
    ("药品代购", "drug_order", "drug_order_id"),
]


async def _pick_event(db, balance_pos: bool) -> tuple | None:
    """随机挑一类事件的一条业务单, 返回 (event_type, source_id, user_id)."""
    event_type, table, id_col = random.choice(EVENT_POOL)
    if balance_pos and random.random() < 0.8:
        # 80% 概率从高风险用户 (RISK 前缀) 里挑, 触发更多非通过决策
        r = await db.execute(text(
            f"SELECT {id_col}, user_id FROM {table} WHERE user_id LIKE :prefix ORDER BY RAND() LIMIT 1"
        ), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (event_type, row[0], row[1])
    r = await db.execute(text(f"SELECT {id_col}, user_id FROM {table} ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return (event_type, row[0], row[1]) if row else None


async def generate_risk_data(
    count: int = 10000,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
):
    """随机选取业务单执行风控检查, 生成 count 条评估记录.

    target_pos_ratio: 目标正例比例 (0.0-1.0), 设置后循环直到达标为止 (不超 count).
    """
    results = {"通过": 0, "标记": 0, "人工审核": 0, "拒绝": 0}
    async with AsyncSessionLocal() as db:
        generated = 0
        while generated < count:
            picked = await _pick_event(db, balance_pos)
            if picked is None:
                print("业务数据不足, 先跑 init_db + gen_risky_users")
                break
            event_type, source_id, user_id = picked
            request = RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=user_id)
            try:
                resp = await process_event(db, request)
                await db.commit()
            except Exception as e:
                await db.rollback()
                print(f"跳过异常: {event_type} {source_id} -> {e}")
                continue
            results[resp.decision] = results.get(resp.decision, 0) + 1
            generated += 1
            if target_pos_ratio is not None and generated % 100 == 0:
                pos = results["人工审核"] + results["拒绝"]
                if generated > 0 and pos / generated >= target_pos_ratio:
                    break

    total = sum(results.values())
    pos = results["人工审核"] + results["拒绝"]
    print(f"[OK] 生成 {total} 条评估: {results}")
    if total:
        print(f"  正例比例 (人工审核+拒绝) = {pos / total:.1%}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成医疗风控评估数据")
    parser.add_argument("--count", type=int, default=10000, help="评估条数 (默认 10000)")
    parser.add_argument("--balance-pos", action="store_true", help="优先挑 RISK 高风险用户, 拉高正例比例")
    parser.add_argument("--target-pos-ratio", type=float, default=None, help="目标正例比例 (如 0.25)")
    args = parser.parse_args()
    asyncio.run(generate_risk_data(
        count=args.count, balance_pos=args.balance_pos, target_pos_ratio=args.target_pos_ratio,
    ))
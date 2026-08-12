"""
物流行业风控系统 - 模拟风控评估数据生成 (异步)
从现有 shipment / shipment_complaint / user_info 中随机选取运单, 调用风控引擎
生成 risk_event / risk_feature / risk_assessment / risk_case / risk_user_profile 记录
用于填充仪表盘和案件管理页面的初始数据

事件类型 (物流域): shipment_create / shipment_cancel / shipment_receive / id_verification
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


async def _pick_shipment(db, balance_pos: bool):
    """随机挑一张运单; balance_pos=True 时优先从高频寄件用户里挑."""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT shipment_id, sender_id, dest_address_id
            FROM shipment
            WHERE sender_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.shipment_id, row.sender_id, row.dest_address_id)
        r = await db.execute(text("""
            SELECT s.shipment_id, s.sender_id, s.dest_address_id
            FROM shipment s
            JOIN (
                SELECT sender_id, COUNT(*) AS cnt
                FROM shipment GROUP BY sender_id ORDER BY cnt DESC LIMIT 10
            ) top ON top.sender_id = s.sender_id
            ORDER BY RAND() LIMIT 1
        """))
        row = r.first()
        if row:
            return (row.shipment_id, row.sender_id, row.dest_address_id)
    r = await db.execute(text("""
        SELECT shipment_id, sender_id, dest_address_id
        FROM shipment ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.shipment_id, row.sender_id, row.dest_address_id) if row else None


async def _pick_user(db):
    r = await db.execute(text("SELECT user_id FROM user_info ORDER BY RAND() LIMIT 1"))
    row = r.first()
    return row.user_id if row else None


async def generate_risk_data(count: int = 30, balance_pos: bool = False):
    """
    随机从运单中选取, 对每条执行风控检查 (异步).

    Args:
        count: 评估条数
        balance_pos: True 时优先从高频寄件用户挑样本, 拉高正例比例
    """
    async with AsyncSessionLocal() as db:
        if balance_pos:
            print("⚠️  --balance-pos 模式: 80% 概率挑高频寄件用户, 拉高正例比例")
        success = 0
        pos_count = 0
        for i in range(count):
            roll = random.random()
            if roll < 0.15:
                picked = await _pick_shipment(db, balance_pos)
                if not picked:
                    print(f"  [{i+1}/{count}] 没有可用运单, 跳过")
                    continue
                tag = "取消运单"
                shipment_id, user_id, receive_id = picked
                request = RiskCheckRequest(
                    event_type="shipment_cancel",
                    source_id=shipment_id,
                    user_id=user_id,
                    order_id=shipment_id,
                    receive_id=receive_id,
                )
            elif roll < 0.30:
                picked = await _pick_shipment(db, balance_pos)
                if not picked:
                    print(f"  [{i+1}/{count}] 没有可用运单, 跳过")
                    continue
                tag = "签收"
                shipment_id, user_id, receive_id = picked
                request = RiskCheckRequest(
                    event_type="shipment_receive",
                    source_id=shipment_id,
                    user_id=user_id,
                    order_id=shipment_id,
                    receive_id=receive_id,
                )
            elif roll < 0.45:
                user_id = await _pick_user(db)
                if not user_id:
                    print(f"  [{i+1}/{count}] 没有可用用户, 跳过")
                    continue
                tag = "实名认证"
                request = RiskCheckRequest(
                    event_type="id_verification", source_id=user_id, user_id=user_id,
                )
            else:
                picked = await _pick_shipment(db, balance_pos)
                if not picked:
                    print(f"  [{i+1}/{count}] 没有可用运单, 跳过")
                    continue
                tag = "寄件"
                shipment_id, user_id, receive_id = picked
                request = RiskCheckRequest(
                    event_type="shipment_create",
                    source_id=shipment_id,
                    user_id=user_id,
                    order_id=shipment_id,
                    receive_id=receive_id,
                )

            try:
                result = await process_event(db, request)
                success += 1
                if result.decision in ("拒绝", "人工审核"):
                    pos_count += 1
                print(f"  [{i+1}/{count}] {tag} 用户={user_id}, "
                      f"评分={result.final_score}, 决策={result.decision}, "
                      f"命中={result.rule_count}条规则")
            except Exception as e:
                print(f"  [{i+1}/{count}] 失败: {e}")

        print(f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 ({pos_count/success*100:.1f}%)")


async def _runner():
    """包装函数: 业务跑完后显式 dispose engine, 避免 Event loop is closed 警告"""
    from app.database import async_engine
    try:
        await generate_risk_data(count=args.count, balance_pos=args.balance_pos)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="物流风控 - 造评估数据 (--balance-pos 优先挑高频寄件用户, 拉高正例比例)."
    )
    parser.add_argument("--count", type=int, default=30, help="评估条数 (默认 30)")
    parser.add_argument(
        "--balance-pos", action="store_true",
        help="优先从高频寄件用户挑样本, 让正例比例 >= 20%",
    )
    args = parser.parse_args()
    asyncio.run(_runner())

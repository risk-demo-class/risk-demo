"""
教育风控系统 - 模拟风控评估数据生成 (异步)
从现有教育业务数据中随机选取订单/退费/课程观看等，调用风控引擎生成评估记录
用于填充仪表盘和案件管理页面，以及 XGBoost 训练数据

P4-L3 2026-08-08 新增 --balance-pos:
    XGBoost 训练是 2 分类, 需要关注正负样本比. 业务上"高风险评估"只占 5%~10%.
    训练时正负样本比 1:20 太极端, scale_pos_weight 会截断到上限 10.
    想要好训练效果, 应保证正例 (拒绝/人工审核) 占比 >= 20%.
    --balance-pos 启用时: 优先挑 RISK00X 系列高风险用户, 把正例比例拉到 25%~35%.
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


async def _pick_order(db, balance_pos: bool) -> tuple | None:
    """挑一条教育订单; balance_pos=True 时优先从 RISK 高风险用户里选.
    返回: (order_id, user_id, course_id)
    """
    if balance_pos:
        if random.random() < 0.8:
            r = await db.execute(text("""
                SELECT order_id, user_id, course_id
                FROM order_info
                WHERE user_id LIKE :prefix
                ORDER BY RAND() LIMIT 1
            """), {"prefix": f"{RISKY_USER_PREFIX}%"})
            row = r.first()
            if row:
                return (row.order_id, row.user_id, row.course_id)
    r = await db.execute(text("""
        SELECT order_id, user_id, course_id
        FROM order_info
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.order_id, row.user_id, row.course_id) if row else None


async def _pick_refund(db, balance_pos: bool) -> tuple | None:
    """挑一条退费申请; balance_pos=True 时优先从 RISK 高风险用户里选.
    返回: (refund_id, user_id)
    """
    if balance_pos:
        if random.random() < 0.8:
            r = await db.execute(text("""
                SELECT rr.refund_id, rr.user_id
                FROM refund_request rr
                WHERE rr.user_id LIKE :prefix
                ORDER BY RAND() LIMIT 1
            """), {"prefix": f"{RISKY_USER_PREFIX}%"})
            row = r.first()
            if row:
                return (row.refund_id, row.user_id)
    r = await db.execute(text("""
        SELECT refund_id, user_id
        FROM refund_request
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.refund_id, row.user_id) if row else None


async def generate_risk_data(count: int = 30, balance_pos: bool = False, target_pos_ratio: float | None = None):
    """
    随机从现有教育业务数据中选取，调用风控引擎生成评估记录.

    Args:
        count: 评估条数
        balance_pos: True 时优先从 RISK 高风险用户挑样本, 拉高正例比例
        target_pos_ratio: 目标正例比例 (0.0-1.0), 循环造数据直到达标
    """
    if target_pos_ratio is not None and not balance_pos:
        print("⚠️  --target-pos-ratio 必须配合 --balance-pos, 已自动启用")
        balance_pos = True
    if target_pos_ratio is not None:
        print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标")

    max_rounds = 10
    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            if balance_pos and round_idx == 0:
                print("⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户, 拉高训练正例比例")
            success = 0
            pos_count = 0
            for i in range(count):
                # 随机挑选事件类型
                event_pool = ["purchase", "course_watch", "refund_apply", "complaint"]
                event_type = random.choice(event_pool)

                if event_type == "refund_apply":
                    use_refund = True
                elif event_type == "complaint":
                    use_refund = False
                else:
                    use_refund = False  # purchase / course_watch

                if use_refund:
                    picked = await _pick_refund(db, balance_pos)
                    if not picked:
                        if target_pos_ratio is not None:
                            continue
                        print(f"  [{i+1}/{count}] 没有可用退费, 跳过")
                        continue
                    refund_id, user_id = picked
                    request = RiskCheckRequest(
                        event_type="refund_apply",
                        source_id=refund_id,
                        user_id=user_id,
                    )
                    tag = "退费"
                else:
                    picked = await _pick_order(db, balance_pos)
                    if not picked:
                        if target_pos_ratio is not None:
                            continue
                        print(f"  [{i+1}/{count}] 没有可用订单, 跳过")
                        continue
                    order_id, user_id, course_id = picked
                    if event_type == "course_watch":
                        request = RiskCheckRequest(
                            event_type="course_watch",
                            source_id=order_id,
                            user_id=user_id,
                            order_id=order_id,
                            course_id=course_id,
                        )
                        tag = "看课"
                    else:
                        request = RiskCheckRequest(
                            event_type=event_type,
                            source_id=order_id,
                            user_id=user_id,
                            order_id=order_id,
                            course_id=course_id,
                        )
                        tag = "报名"
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
            print(f"[第 {round_idx+1}/{max_rounds} 轮] 成功 {success} 条, 正例 {pos_count} 条 ({current_ratio*100:.1f}%)")

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

    print(f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 ({pos_count/success*100:.1f}%)")


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
    # Windows asyncio 兼容: 避免 Event loop is closed
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    parser = argparse.ArgumentParser(
        description="造教育风控评估数据. --balance-pos 优先挑 RISK 高风险用户."
    )
    parser.add_argument("--count", type=int, default=30, help="评估条数 (默认 30)")
    parser.add_argument(
        "--balance-pos", action="store_true",
        help="优先挑 RISK00X 高风险用户, 让训练时正例比例 >= 20%",
    )
    parser.add_argument(
        "--target-pos-ratio", type=float, default=None,
        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 使用",
    )
    args = parser.parse_args()
    asyncio.run(_runner())
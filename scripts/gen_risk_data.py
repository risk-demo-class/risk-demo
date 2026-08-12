"""
物流风控系统 - 模拟风控评估数据生成 (异步)
从现有业务数据中随机选取包裹/危险品申报/COD，调用风控引擎生成评估记录
用于填充仪表盘和案件管理页面的初始数据

【物流版】覆盖 4 类物流事件 (跟 validator.py 的 _EVENT_SOURCE_VALIDATORS 对齐):
  - parcel_pickup    揽收:      source_id = parcel_id  (随机包裹)
  - cross_border_ship 跨境发运: source_id = parcel_id  (优先国际件)
  - dangerous_declare 危险品申报: source_id = decl_id  (从 dangerous_declaration 挑)
  - cod_settlement    COD结算:   source_id = cod_id    (从 cod_transaction 挑)

验收标准 (requirements.md §9): 生成 500-2000 条且 ≥15% 正样本, 覆盖全部 4 种事件类型.
默认 --count 800 (区间内).

--balance-pos:
    XGBoost 训练是 2 分类, 需要关注正负样本比. 业务上"高风险评估"只占 5%~10%,
    训练时正负样本比 1:20 太极端. 想要好训练效果, 应保证正例 (拒绝/人工审核) 占比 >= 20%.
    --balance-pos 启用时: 80% 概率挑 RISK00X 系列高风险用户, 把正例比例拉到 25%~35%.
"""
import argparse
import asyncio
import os
import random
import sys

# UTF-8 stdout (Windows GBK 终端兼容)
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

# RISK 高风险用户前缀 (gen_risky_users.py 造过)
RISKY_USER_PREFIX = "RISK"

# 4 类物流事件 + 采样权重 (保证 4 种事件类型都覆盖)
EVENT_TYPES = ["parcel_pickup", "cross_border_ship", "dangerous_declare", "cod_settlement"]
EVENT_WEIGHTS = [4, 2, 2, 2]


# ============================================================
# 事件源 picker (balance_pos=True 时 80% 概率从 RISK 高风险用户挑)
# ============================================================

async def _pick_parcel(db, balance_pos: bool, international_only: bool = False) -> tuple | None:
    """挑一个包裹; international_only=True 时只挑国际件 (跨境发运事件).

    返回: (parcel_id, user_id) 元组或 None
    """
    intl_sql = "AND is_international = 1" if international_only else ""
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text(f"""
            SELECT parcel_id, user_id FROM parcel
            WHERE user_id LIKE :prefix {intl_sql}
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.parcel_id, row.user_id)
    r = await db.execute(text(f"""
        SELECT parcel_id, user_id FROM parcel
        WHERE 1=1 {intl_sql}
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.parcel_id, row.user_id) if row else None


async def _pick_declaration(db, balance_pos: bool) -> tuple | None:
    """挑一条危险品申报 (dangerous_declare 事件源).

    返回: (decl_id, user_id) 元组或 None
    """
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT d.decl_id, p.user_id
            FROM dangerous_declaration d
            JOIN parcel p ON d.parcel_id = p.parcel_id
            WHERE p.user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.decl_id, row.user_id)
    r = await db.execute(text("""
        SELECT d.decl_id, p.user_id
        FROM dangerous_declaration d
        JOIN parcel p ON d.parcel_id = p.parcel_id
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.decl_id, row.user_id) if row else None


async def _pick_cod(db, balance_pos: bool) -> tuple | None:
    """挑一条 COD 流水 (cod_settlement 事件源).

    返回: (cod_id, user_id) 元组或 None
    """
    if balance_pos and random.random() < 0.8:
        r = await db.execute(text("""
            SELECT c.cod_id, p.user_id
            FROM cod_transaction c
            JOIN parcel p ON c.parcel_id = p.parcel_id
            WHERE p.user_id LIKE :prefix
            ORDER BY RAND() LIMIT 1
        """), {"prefix": f"{RISKY_USER_PREFIX}%"})
        row = r.first()
        if row:
            return (row.cod_id, row.user_id)
    r = await db.execute(text("""
        SELECT c.cod_id, p.user_id
        FROM cod_transaction c
        JOIN parcel p ON c.parcel_id = p.parcel_id
        ORDER BY RAND() LIMIT 1
    """))
    row = r.first()
    return (row.cod_id, row.user_id) if row else None


async def _pick_and_build_request(db, balance_pos: bool) -> RiskCheckRequest | None:
    """按权重随机挑 1 类事件并构造 RiskCheckRequest.

    事件类型 → source_id 语义 (跟 validator.py / event.py 的补全逻辑一致):
      parcel_pickup / cross_border_ship → source_id = parcel_id
      dangerous_declare                 → source_id = decl_id
      cod_settlement                    → source_id = cod_id
    """
    evt = random.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0]

    if evt == "parcel_pickup":
        picked = await _pick_parcel(db, balance_pos)
        if not picked:
            return None
        pid, uid = picked
        return RiskCheckRequest(event_type="parcel_pickup", source_id=pid, user_id=uid)

    if evt == "cross_border_ship":
        # 优先国际件; 没有国际件时兜底任意包裹 (保证事件类型能跑通)
        picked = await _pick_parcel(db, balance_pos, international_only=True)
        if not picked:
            picked = await _pick_parcel(db, balance_pos)
        if not picked:
            return None
        pid, uid = picked
        return RiskCheckRequest(event_type="cross_border_ship", source_id=pid, user_id=uid)

    if evt == "dangerous_declare":
        picked = await _pick_declaration(db, balance_pos)
        if not picked:
            return None
        did, uid = picked
        return RiskCheckRequest(event_type="dangerous_declare", source_id=did, user_id=uid)

    # cod_settlement
    picked = await _pick_cod(db, balance_pos)
    if not picked:
        return None
    cid, uid = picked
    return RiskCheckRequest(event_type="cod_settlement", source_id=cid, user_id=uid)


# ============================================================
# 主流程
# ============================================================

async def generate_risk_data(count: int = 800, balance_pos: bool = False,
                             target_pos_ratio: float | None = None):
    """
    随机从现有业务数据中选取事件, 对每条执行风控检查 (异步).

    Args:
        count: 评估条数 (默认 800, 满足验收 500-2000)
        balance_pos: True 时 80% 概率从 RISK 高风险用户挑样本, 拉高正例比例
        target_pos_ratio: 目标正例比例 (0.0-1.0), 设置后自动循环造数据直到达标
    """
    # --target-pos-ratio 必须配合 --balance-pos (自动启用)
    if target_pos_ratio is not None and not balance_pos:
        print(f"⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
        balance_pos = True
    if target_pos_ratio is not None:
        print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标")

    max_rounds = 10  # 最多循环 10 轮, 避免无限循环
    for round_idx in range(max_rounds):
        async with AsyncSessionLocal() as db:
            if balance_pos and round_idx == 0:
                print(f"⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户, 拉高训练正例比例")
            success = 0
            pos_count = 0
            for i in range(count):
                request = await _pick_and_build_request(db, balance_pos)
                if not request:
                    if target_pos_ratio is not None:
                        continue  # target 模式下继续造
                    print(f"  [{i+1}/{count}] 没有可用包裹/申报/COD, 跳过")
                    continue
                try:
                    result = await process_event(db, request)
                    success += 1
                    # 决策是"拒绝"或"人工审核" = 正例
                    if result.decision in ("拒绝", "人工审核"):
                        pos_count += 1
                    if target_pos_ratio is None:
                        print(f"  [{i+1}/{count}] {request.event_type} 用户={request.user_id}, "
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
                print(f"   建议: 跑 scripts/gen_risky_users.py 扩大 RISK 用户规模 (默认 24 个不够)")
                break
        else:
            break  # 非 target 模式: 跑完就退出

    print(f"\n完成! 成功生成 {success} 条风控评估记录, 正例 {pos_count} 条 ({pos_count/max(success,1)*100:.1f}%)")


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
        description="造风控评估数据 (物流版, 覆盖 4 类事件). --balance-pos 优先挑 RISK 高风险用户, 拉高训练正例比例."
    )
    parser.add_argument("--count", type=int, default=800, help="评估条数 (默认 800, 验收区间 500-2000)")
    parser.add_argument(
        "--balance-pos", action="store_true",
        help="优先挑 RISK 高风险用户, 让训练时正例比例 >= 20% (XGBoost 推荐值)",
    )
    parser.add_argument(
        "--target-pos-ratio", type=float, default=None,
        help="目标正例比例 (0.0-1.0), 配合 --balance-pos 使用, 循环造数据直到达标. 例: --target-pos-ratio 0.30",
    )
    args = parser.parse_args()
    asyncio.run(_runner())

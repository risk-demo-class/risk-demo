"""
物流风控系统 - 训练数据集生成 (物流版)

【目的】
  造一份**严格标注**的 XGBoost 训练数据集, 满足:
    1. 数量: 目标 (30 RISK × 25) + (30 普通 × 25) = 1500 条 (argparse 默认);
             现有 RISK 用户不足自动截断 — 默认 gen_risky_users 造 24 个 → 实际 ≈ 800 条
    2. 标签: 真实由 8 条物流规则跑出 (decision 字段), 不是随机
    3. 特征: 25 维物流特征真实从 DB 查 (feature.py compute_all_features), 不是捏造
    4. ml_score 字段: 强制 NULL (写库后 UPDATE), 不存"未训练的垃圾模型"推理值
       → 训完基础模型后, 用 scripts/backfill_ml_score.py 回填合理值

【跟 gen_risk_data.py 的区别】
  - gen_risk_data.py: 全局随机挑包裹/申报/COD → 覆盖 4 类事件 + 固定比例正负样本
  - gen_train_dataset.py: **按用户**造事件. RISK 用户先"探测"候选事件 (哪些实际触发
    物流规则 → 强正例池), 采样时 60% 从强正例池 + 40% 从全候选 (保留 context 对照包裹
    当负例), 让正例率稳定在 40%~60%; 普通用户 (U0001-U0008 种子) 只走正常包裹 → 通过.

【RISK 用户事件源】对每个 RISK 用户, 从"该用户"可用事件里探测:
  - 每个包裹  → parcel_pickup    (R001 未实名 / R012 同地址高频 / R018 改派 / R025 大额低报 / R030 黑地址)
  - 国际件    → cross_border_ship (R005 跨境违禁品)
  - 危险品申报 → dangerous_declare (R002 危险品瞒报)
  - COD 流水  → cod_settlement   (R008 COD 卷款)

【用法】
  python scripts/gen_train_dataset.py                  # 默认 30 RISK + 30 普通 (不够自动截断)
  python scripts/gen_train_dataset.py --n-risk 24      # 用全部 24 个 RISK 用户
  python scripts/gen_train_dataset.py --n-normal 8     # 只用 8 个种子普通用户
  python scripts/gen_train_dataset.py --per-user 20    # 每个用户 20 条
  python scripts/gen_train_dataset.py --reset          # 先清空 risk_event/feature/assessment/case 再造
  python scripts/gen_train_dataset.py --dry-run        # 只统计不写入 (验证数据够不够)
"""
import argparse
import asyncio
import os
import random
import sys

# UTF-8 stdout (Windows GBK 兼容)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

# RISK 高风险用户前缀 (跟 gen_risky_users.py 一致)
RISKY_USER_PREFIX = "RISK"

# RISK 用户采样时, 从"强正例池"采样的比例 (其余从全候选, 保留对照包裹当负例)
STRONG_POOL_RATIO = 0.6


# ============================================================
# 选用户
# ============================================================

async def _pick_risk_users(db, n: int) -> list[str]:
    """从 RISK 高风险用户里选 N 个 (按 user_id 排序稳定)."""
    r = await db.execute(text("""
        SELECT user_id FROM user_info
        WHERE user_id LIKE :prefix
        ORDER BY user_id
        LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.user_id for row in r.fetchall()]


async def _pick_normal_users(db, n: int) -> list[str]:
    """从普通用户里选 N 个 (非 RISK 前缀, 物流版种子用户是 U0001-U0008)."""
    r = await db.execute(text("""
        SELECT user_id FROM user_info
        WHERE user_id NOT LIKE :prefix
        ORDER BY user_id
        LIMIT :n
    """), {"prefix": f"{RISKY_USER_PREFIX}%", "n": n})
    return [row.user_id for row in r.fetchall()]


# ============================================================
# 挑事件 (按用户)
# ============================================================

async def _risk_event_options(db, user_id: str) -> list[tuple]:
    """返回该用户的所有可用事件选项: [(event_type, source_id), ...].

    把所有可评估的事件源都收集起来:
      - 每个包裹   → parcel_pickup     (揽收)
      - 国际件     → cross_border_ship (跨境发运, 专触 R005)
      - 危险品申报  → dangerous_declare (专触 R002)
      - COD 流水   → cod_settlement    (专触 R008)
    """
    options: list[tuple] = []

    # 包裹 (普通揽收事件源; 含风险包裹 / context 对照包裹 / R012 共享收件包裹)
    r = await db.execute(text("""
        SELECT parcel_id FROM parcel WHERE user_id = :uid
    """), {"uid": user_id})
    for row in r.fetchall():
        options.append(("parcel_pickup", row.parcel_id))

    # 国际件 (跨境发运事件源)
    r = await db.execute(text("""
        SELECT parcel_id FROM parcel
        WHERE user_id = :uid AND is_international = 1
    """), {"uid": user_id})
    for row in r.fetchall():
        options.append(("cross_border_ship", row.parcel_id))

    # 危险品申报 (dangerous_declare 事件源)
    r = await db.execute(text("""
        SELECT d.decl_id FROM dangerous_declaration d
        JOIN parcel p ON d.parcel_id = p.parcel_id
        WHERE p.user_id = :uid
    """), {"uid": user_id})
    for row in r.fetchall():
        options.append(("dangerous_declare", row.decl_id))

    # COD 流水 (cod_settlement 事件源)
    r = await db.execute(text("""
        SELECT c.cod_id FROM cod_transaction c
        JOIN parcel p ON c.parcel_id = p.parcel_id
        WHERE p.user_id = :uid
    """), {"uid": user_id})
    for row in r.fetchall():
        options.append(("cod_settlement", row.cod_id))

    return options


async def _pick_normal_event_for_user(db, user_id: str) -> tuple | None:
    """为普通用户随机挑 1 个正常包裹 (parcel_pickup). 返回 (event_type, source_id) 或 None."""
    r = await db.execute(text("""
        SELECT parcel_id FROM parcel
        WHERE user_id = :uid
        ORDER BY RAND() LIMIT 1
    """), {"uid": user_id})
    row = r.first()
    return ("parcel_pickup", row.parcel_id) if row else None


# ============================================================
# 主流程
# ============================================================

async def gen_train_dataset(
    n_risk: int = 30,
    n_normal: int = 30,
    per_user: int = 25,
    reset: bool = False,
    dry_run: bool = False,
):
    """造训练数据集: n_risk × per_user 高风险 + n_normal × per_user 正常 (物流版)."""
    if dry_run:
        print("=" * 60)
        print("[DRY-RUN] 训练数据集预演 (不写库)")
    else:
        print("=" * 60)
        print("训练数据集生成 (物流版, 强标注, ml_score=NULL)")

    total_target = (n_risk + n_normal) * per_user
    print(f"目标: {n_risk} RISK × {per_user} + {n_normal} 普通 × {per_user} = {total_target} 条")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # 0. (可选) 清空训练用表 (注意 FK 顺序: case → assessment → feature → event)
        if reset and not dry_run:
            print("\n[0] 清空训练用表 (risk_event / risk_feature / risk_assessment / risk_case / risk_user_profile)...")
            await db.execute(text("DELETE FROM risk_case"))
            await db.execute(text("DELETE FROM risk_assessment"))
            await db.execute(text("DELETE FROM risk_feature"))
            await db.execute(text("DELETE FROM risk_event"))
            await db.execute(text("DELETE FROM risk_user_profile"))
            await db.commit()
            print("  清空完成")

        # 1. 选用户
        print(f"\n[1] 选 {n_risk} RISK + {n_normal} 普通用户...")
        risk_users = await _pick_risk_users(db, n_risk)
        normal_users = await _pick_normal_users(db, n_normal)
        if not risk_users:
            print(f"  [FAIL] 没找到 RISK 用户, 先跑: python scripts/gen_risky_users.py --count {n_risk}")
            return
        if not normal_users:
            print("  [FAIL] 没找到普通用户, 先跑 init_business_data.sql 初始化业务数据")
            return
        if len(risk_users) < n_risk:
            print(f"  [WARN] RISK 用户只 {len(risk_users)} 个 < 目标 {n_risk}, 用现有数量")
            n_risk = len(risk_users)
        if len(normal_users) < n_normal:
            print(f"  [WARN] 普通用户只 {len(normal_users)} 个 < 目标 {n_normal}, 用现有数量")
            n_normal = len(normal_users)
        print(f"  RISK: {len(risk_users)} 个 ({risk_users[0]} ~ {risk_users[-1]})")
        print(f"  普通: {len(normal_users)} 个 ({normal_users[0]} ~ {normal_users[-1]})")

        if dry_run:
            # 预演: 统计每个 RISK 用户可用事件数, 验证事件够不够
            print("\n[DRY-RUN] 检查 RISK 用户可用事件...")
            total_opts = 0
            for uid in risk_users[:5]:
                opts = await _risk_event_options(db, uid)
                total_opts += len(opts)
                print(f"  {uid}: {len(opts)} 个可用事件")
            print(f"[DRY-RUN] 预演完成 (前 5 个用户共 {total_opts} 个事件). 真跑去掉 --dry-run")
            return

        # 2. 造事件
        success = 0
        pos_count = 0
        neg_count = 0
        failed = 0
        risk_pos = 0
        normal_pos = 0

        async def _run_request(request, is_risk: bool):
            """跑一次事件并统计 (返回 decision)."""
            nonlocal success, pos_count, neg_count, risk_pos, normal_pos
            result = await process_event(db, request)
            success += 1
            if result.decision in ("拒绝", "人工审核"):
                pos_count += 1
                if is_risk:
                    risk_pos += 1
                else:
                    normal_pos += 1
            else:
                neg_count += 1
            return result.decision

        # 2.1 RISK 用户: 探测候选事件 → 强正例池 → 采样补足到 per_user
        print(f"\n[2] 造 {n_risk * per_user + n_normal * per_user} 条事件...")
        print(f"    RISK 用户策略: 探测候选事件找'实际触发规则'的事件源 (强正例池), "
              f"采样 {STRONG_POOL_RATIO:.0%} 强正例 + {(1-STRONG_POOL_RATIO):.0%} 全候选")
        for uid in risk_users:
            options = await _risk_event_options(db, uid)
            if not options:
                failed += per_user
                print(f"  [跳过] {uid} 无任何可用事件")
                continue

            # 探测: 把该用户所有候选事件跑一遍, 收集实际触发规则的 (强正例池)
            strong = []
            for event_type, source_id in options:
                request = RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=uid)
                decision = await _run_request(request, is_risk=True)
                if decision in ("拒绝", "人工审核"):
                    strong.append((event_type, source_id))

            # 一个都没触发? 兜底: 强正例池 = 全部候选 (至少保证有样本)
            if not strong:
                strong = list(options)

            # 补足到 per_user (探测已产出 len(options) 条)
            produced = len(options)
            while produced < per_user:
                # 60% 从强正例池, 40% 从全候选 (保留对照包裹当负例)
                if random.random() < STRONG_POOL_RATIO:
                    event_type, source_id = random.choice(strong)
                else:
                    event_type, source_id = random.choice(options)
                request = RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=uid)
                await _run_request(request, is_risk=True)
                produced += 1

        # 2.2 普通用户: 只走正常包裹 (通过 = 负例)
        for uid in normal_users:
            produced = 0
            while produced < per_user:
                picked = await _pick_normal_event_for_user(db, uid)
                if not picked:
                    failed += 1
                    break
                event_type, source_id = picked
                request = RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=uid)
                await _run_request(request, is_risk=False)
                produced += 1

        # 3. 强制 ml_score = NULL (训练数据无 ml 痕迹)
        print(f"\n[3] 强制 ml_score = NULL (训练数据无 ml 痕迹)...")
        await db.execute(text("""
            UPDATE risk_assessment
            SET ml_score = NULL, ml_decision = NULL
            WHERE ml_score IS NOT NULL
        """))
        null_count = (await db.execute(text("""
            SELECT COUNT(*) FROM risk_assessment WHERE ml_score IS NULL
        """))).scalar()
        non_null = (await db.execute(text("""
            SELECT COUNT(*) FROM risk_assessment WHERE ml_score IS NOT NULL
        """))).scalar()
        await db.commit()
        print(f"  risk_assessment 总 {null_count + non_null} 条, ml_score=NULL: {null_count}, 非 NULL: {non_null}")

    # 4. 汇总
    print("\n" + "=" * 60)
    print("训练数据集生成完成!")
    print(f"  目标:       {total_target} 条 ({n_risk} RISK × {per_user} + {n_normal} 普通 × {per_user})")
    print(f"  实际成功:   {success} 条")
    print(f"  正例:       {pos_count} 条 ({100*pos_count/max(success,1):.1f}%)")
    print(f"  负例:       {neg_count} 条 ({100*neg_count/max(success,1):.1f}%)")
    print(f"  失败:       {failed} 条")
    print(f"  标签分布:   RISK 正例 {risk_pos} / RISK 总 {n_risk*per_user} = {100*risk_pos/max(n_risk*per_user,1):.1f}%")
    print(f"              普通 正例 {normal_pos} / 普通 总 {n_normal*per_user} = {100*normal_pos/max(n_normal*per_user,1):.1f}%")
    print(f"  ml_score:   全部 NULL (无未训练模型垃圾值)")
    print("=" * 60)
    if pos_count / max(success, 1) < 0.25:
        print(f"[WARN] 正例比例 {100*pos_count/max(success,1):.1f}% < 25% 推荐值, 模型可能假收敛")
    if pos_count / max(success, 1) > 0.65:
        print(f"[WARN] 正例比例 {100*pos_count/max(success,1):.1f}% > 65% 上限, 业务上不正常")
    print("\n下一步: python scripts/train_xgb_model.py")


async def _runner():
    """包装函数: 业务跑完后显式 dispose engine, 避免 Event loop is closed 警告"""
    from app.database import async_engine

    # 【关键】训练集标签必须反映"纯规则决策", 不能被旧的/未训练的 ML 模型污染.
    # 原因: ML_WEIGHT_RULE=0.5 双轨融合, 旧电商模型 predict 兜底 score=0 时,
    #       规则分被稀释一半 (R001 70 分 → 35 → '标记'), 决策降级, 训练标签失真.
    #       禁用 ML 后走纯规则: R001(70)→人工审核, R025(80)→拒绝, R012(65)→人工审核.
    #       等训出物流模型 (train_demo_model.py) 后, 线上决策再启用 ML 融合.
    from app.engine import ml_model as _ml
    _ml._LOADED = False
    _ml._MODEL = None

    try:
        await gen_train_dataset(
            n_risk=args.n_risk,
            n_normal=args.n_normal,
            per_user=args.per_user,
            reset=args.reset,
            dry_run=args.dry_run,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造训练数据集 (物流版: RISK 用户触物流规则=正例, 普通用户正常包裹=负例, ml_score=NULL)"
    )
    parser.add_argument("--n-risk", type=int, default=30, help="RISK 高风险用户数 (默认 30, 不够自动截断)")
    parser.add_argument("--n-normal", type=int, default=30, help="普通用户数 (默认 30, 种子用户 U0001-U0008, 不够自动截断)")
    parser.add_argument("--per-user", type=int, default=25, help="每个用户造几条 (默认 25)")
    parser.add_argument("--reset", action="store_true", help="先清空训练用表 (risk_event/feature/assessment/case)")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()
    asyncio.run(_runner())

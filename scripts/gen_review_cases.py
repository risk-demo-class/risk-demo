"""
生成"人工审核"事件 / 待审核案件 (2026-08-11).

背景:
  RISK_REVIEW_ML_EXEMPT=True (2026-08-11 P2) 之后, 命中 action=人工审核 的规则
  会保持"人工审核"决策, ML 只作展示参考 → 本脚本直接跑 RISK 用户事件即可
  稳定产出"待审核"案件, 且案件自带真实 ML 评分.

历史: 之前版本强制 XGB_ENABLED=false (纯规则) 造人工审核, 但案件 ML 分全为 0;
      方案 B 后不再需要, 已移除.

用法:
  python scripts/gen_review_cases.py                # 目标 40 个待审核案件
  python scripts/gen_review_cases.py --target 80    # 目标 80 个
  python scripts/gen_review_cases.py --per-user 3   # 每用户每类事件最多取 3 条
"""
import argparse
import asyncio
import os
import sys

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event


# 4 类事件 → RISK 用户业务记录查询 (只取 RISK 高风险用户的记录)
_CANDIDATE_SQL = {
    "处方审核": """
        SELECT rx_id AS sid, user_id FROM prescription
        WHERE user_id LIKE 'RISK%'
        ORDER BY user_id, rx_id
    """,
    "医保结算": """
        SELECT claim_id AS sid, user_id FROM insurance_claim
        WHERE user_id LIKE 'RISK%'
        ORDER BY user_id, claim_id
    """,
    "挂号": """
        SELECT appt_id AS sid, user_id FROM appointment
        WHERE user_id LIKE 'RISK%'
        ORDER BY user_id, appt_id
    """,
    "药品代购": """
        SELECT drug_order_id AS sid, user_id FROM drug_order
        WHERE user_id LIKE 'RISK%'
        ORDER BY user_id, drug_order_id
    """,
}


async def _collect_candidates(db, per_user: int) -> list[tuple[str, str, str]]:
    """按事件类型收集 (event_type, source_id, user_id), 每用户每类最多 per_user 条."""
    out: list[tuple[str, str, str]] = []
    for event_type, sql in _CANDIDATE_SQL.items():
        rows = (await db.execute(text(sql))).fetchall()
        per_user_count: dict[str, int] = {}
        for r in rows:
            if per_user_count.get(r.user_id, 0) >= per_user:
                continue
            per_user_count[r.user_id] = per_user_count.get(r.user_id, 0) + 1
            out.append((event_type, r.sid, r.user_id))
    return out


async def gen_review_cases(target: int = 40, per_user: int = 5) -> dict:
    """跑事件直到攒够 target 个"人工审核"决策 (或候选耗尽), 返回统计."""
    stats = {
        "ran": 0, "review": 0,
        "通过": 0, "标记": 0, "人工审核": 0, "拒绝": 0,
        "cases": [],   # [(assessment_id, user_id, event_type, source_id)]
    }
    async with AsyncSessionLocal() as db:
        candidates = await _collect_candidates(db, per_user)
        print(f"候选事件: {len(candidates)} 条 (每用户每类最多 {per_user} 条)")
        for event_type, source_id, user_id in candidates:
            if stats["review"] >= target:
                break
            try:
                res = await process_event(
                    db,
                    RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=user_id),
                )
            except Exception as e:  # 单条失败不中断 (校验/数据问题)
                print(f"  [跳过] {event_type} {source_id}: {e}")
                continue
            stats["ran"] += 1
            stats[res.decision] = stats.get(res.decision, 0) + 1
            if res.decision == "人工审核":
                stats["review"] += 1
                stats["cases"].append((res.assessment_id, user_id, event_type, source_id))
    return stats


async def _runner():
    """包装: 业务跑完后显式 dispose engine, 避免 Event loop is closed 警告."""
    from app.database import async_engine
    try:
        stats = await gen_review_cases(target=args.target, per_user=args.per_user)
    finally:
        await async_engine.dispose()

    print("\n" + "=" * 60)
    print(f"生成完成: 运行 {stats['ran']} 条事件")
    print(f"决策分布: 通过={stats['通过']} 标记={stats['标记']} "
          f"人工审核={stats['人工审核']} 拒绝={stats['拒绝']}")
    print(f"待审核案件: {stats['review']} 个")
    print("=" * 60)
    if stats["cases"]:
        print("示例 (前 5 条):")
        for aid, uid, evt, sid in stats["cases"][:5]:
            print(f"  {aid} | {uid} | {evt} | {sid}")
    print("\n刷新页面: http://localhost:8000/cases (案件管理 → 待审核)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成人工审核事件/待审核案件 (纯规则模式)")
    parser.add_argument("--target", type=int, default=40, help="目标待审核案件数 (默认 40)")
    parser.add_argument("--per-user", type=int, default=5, help="每用户每类事件最多取几条 (默认 5)")
    args = parser.parse_args()
    asyncio.run(_runner())

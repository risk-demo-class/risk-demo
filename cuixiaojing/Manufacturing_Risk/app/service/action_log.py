"""
操作审计日志.
任何规则/案件/黑名单的变更都调 record_action() 写一行.
教学价值: 学员能讲"我设计的系统有完整审计日志" (合规要求).

注意: 函数不 commit, 跟调用方合并成 1 个事务.
"""
import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskActionLog

logger = logging.getLogger(__name__)


async def record_action(
    db: AsyncSession,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    *,
    before_value: Optional[dict] = None,
    after_value: Optional[dict] = None,
    ip: Optional[str] = None,
    remark: Optional[str] = None,
) -> None:
    """写 1 行操作审计日志 (不 commit, 由调用方 commit)."""
    log = RiskActionLog(
        operator=operator,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        before_value=json.dumps(before_value, ensure_ascii=False) if before_value else None,
        after_value=json.dumps(after_value, ensure_ascii=False) if after_value else None,
        ip=ip,
        remark=remark,
    )
    db.add(log)
    logger.info("action_log: %s by %s on %s(%s)", action_type, operator, target_type, target_id)


def orm_to_dict(obj: Any, fields: list[str]) -> dict:
    """ORM 对象 → dict (只取 fields 指定字段). 比 obj.__dict__ 安全."""
    return {f: getattr(obj, f, None) for f in fields}


# ============================================================
# Demo: 演练 record_action 写审计 + orm_to_dict — 用 mock DB
# 跑法: python -m app.service.action_log
# ============================================================
if __name__ == "__main__":
    import asyncio

    print("=" * 60)
    print("Service ActionLog — 审计层 (2 个核心子函数)")
    print("=" * 60)

    class _FakeRule:
        def __init__(self):
            self.rule_id = "R001"
            self.rule_name = "跨区串货举报"
            self.risk_score = 95
            self._sa_instance_state = "<SQLAlchemy 内部状态>"

    rule = _FakeRule()
    safe = orm_to_dict(rule, ["rule_id", "rule_name", "risk_score"])
    unsafe = dict(rule.__dict__)
    print(f"\n[1] orm_to_dict: {safe}")
    print(f"    __dict__ 含 {len(unsafe)} 字段 (含 SQLAlchemy 内部状态) → orm_to_dict 更安全")

    class _FakeDB:
        def __init__(self):
            self.added = []
        def add(self, obj):
            self.added.append(obj)

    async def demo():
        db = _FakeDB()
        await record_action(
            db, operator="admin", action_type="CREATE_RULE",
            target_type="rule", target_id="R025",
            after_value={"rule_name": "经销商资质过期", "risk_score": 50},
            remark="新增 R025",
        )
        await record_action(
            db, operator="system", action_type="AUTO_REJECT_CASE",
            target_type="case", target_id="cas_xxx",
            after_value={"case_status": "已拒绝", "final_score": 95},
            remark="系统自动拒绝",
        )
        for log in db.added:
            print(f"\n[2] [{log.action_type}] {log.operator} → {log.target_type}({log.target_id})")
            print(f"    after = {log.after_value}")

    asyncio.run(demo())

    print("\n[3] action_type 完整列表:")
    valid_types = [
        "CREATE_RULE", "UPDATE_RULE", "TOGGLE_RULE", "DELETE_RULE",
        "REVIEW_CASE", "AUTO_REJECT_CASE",
        "ADD_BLACKLIST", "REMOVE_BLACKLIST",
    ]
    for t in valid_types:
        print(f"  - {t}")

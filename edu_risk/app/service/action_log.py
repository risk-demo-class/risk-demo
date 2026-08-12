"""
审计日志 — 记录所有风控操作(案件流转/黑名单/规则变更)
design: record_action(db, operator, action_type, before, after)
"""
from datetime import datetime


async def record_action(db, operator: str, action_type: str,
                        before: dict | None = None, after: dict | None = None,
                        remark: str = ""):
    """
    写一条审计日志到 risk_event 的 event_data? 不,审计独立记录。
    教学版用轻量方案: 直接打印 + 可选落库(未来扩展 audit_log 表)。
    生产环境建议单独 audit_log 表。
    """
    entry = {
        "time": datetime.now().isoformat(),
        "operator": operator,
        "action_type": action_type,
        "before": before or {},
        "after": after or {},
        "remark": remark,
    }
    # 教学版: 日志即审计;生产环境换 DB 表
    import logging
    logging.getLogger("audit").info("AUDIT %s", entry)
    return entry

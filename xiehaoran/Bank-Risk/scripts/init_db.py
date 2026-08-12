"""银行风控系统 - 数据库初始化 (建表 + 种子数据).

用法:
  python scripts/init_db.py --yes         # 建 9 张风控表 + 种子规则/黑名单
  python scripts/init_db.py --reset        # 先 DROP 再建 (危险)

建表基于 app.models_risk.Base.metadata.create_all.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.database import async_engine, Base  # noqa: E402
from app.models_risk import (  # noqa: E402
    RiskBlacklist, RiskRule,
)
from app.config import settings  # noqa: E402


# ============================================================
# 种子规则: 对齐 Bank-Risk DISPATCH_TABLE 的 8 条银行规则
# 条件字段对应 11 维特征名 (见 app/engine/feature.FEATURE_ORDER)
# ============================================================
SEED_RULES = [
    {
        "rule_id": "R001", "rule_name": "黑名单命中", "rule_category": "账户风险",
        "event_type": "通用", "risk_level": "极高", "risk_score": 95, "action": "freeze",
        "priority": 100, "description": "账户/设备/IP/证件/商户/受益人任一命中即一票否决冻结",
        "rule_condition": {"field": "multi_loan_index", "op": ">=", "value": 0.0},  # 占位, 实际由 service/event 撞黑短路
    },
    {
        "rule_id": "R002", "rule_name": "转账大额报送", "rule_category": "交易风险",
        "event_type": "transfer", "risk_level": "高", "risk_score": 80, "action": "reject",
        "priority": 90, "description": "单笔 >=20万大额报送",
        "rule_condition": {"field": "large_amt_flag", "op": ">=", "value": 1},
    },
    {
        "rule_id": "R003", "rule_name": "分散转入对手数", "rule_category": "反洗钱",
        "event_type": "transfer", "risk_level": "中", "risk_score": 60, "action": "review",
        "priority": 80, "description": "近1h对手数>=10疑似资金归集",
        "rule_condition": {"field": "disperse_peer_cnt", "op": ">=", "value": 0.28},
    },
    {
        "rule_id": "R004", "rule_name": "地理/IP突变", "rule_category": "设备风险",
        "event_type": "通用", "risk_level": "中", "risk_score": 60, "action": "review",
        "priority": 70, "description": "异地登录或盗卡",
        "rule_condition": {"field": "geo_deviation", "op": ">=", "value": 1},
    },
    {
        "rule_id": "R005", "rule_name": "多头借贷过度查询", "rule_category": "信贷风险",
        "event_type": "loan_apply", "risk_level": "高", "risk_score": 75, "action": "reject",
        "priority": 85, "description": "征信查询>=10或平台数>=5借名骗贷",
        "rule_condition": {"field": "multi_loan_index", "op": ">=", "value": 0.5},
    },
    {
        "rule_id": "R006", "rule_name": "登录失败频控", "rule_category": "登录风险",
        "event_type": "login", "risk_level": "中", "risk_score": 60, "action": "freeze",
        "priority": 75, "description": "5分钟失败>=5疑似撞库",
        "rule_condition": {"field": "login_brute_freq", "op": ">=", "value": 0.5},
    },
    {
        "rule_id": "R007", "rule_name": "分散转入集中转出", "rule_category": "反洗钱",
        "event_type": "transfer", "risk_level": "中", "risk_score": 60, "action": "review",
        "priority": 65, "description": "对手数高+单笔中高金额疑似洗钱",
        "rule_condition": {"and": [
            {"field": "disperse_peer_cnt", "op": ">=", "value": 0.2},
            {"field": "amount_deviation", "op": ">=", "value": 0.5},
        ]},
    },
    {
        "rule_id": "R008", "rule_name": "异常时段交易", "rule_category": "交易风险",
        "event_type": "通用", "risk_level": "低", "risk_score": 40, "action": "review",
        "priority": 60, "description": "0~6点夜间交易高发盗卡/电诈",
        "rule_condition": {"field": "txn_time_anomaly", "op": ">=", "value": 1},
    },
]

SEED_BLACKLIST = [
    {"blacklist_type": "account", "blacklist_value": "C999999", "reason": "涉案失信账户(示例)"},
    {"blacklist_type": "device", "blacklist_value": "dev_fraud_001", "reason": "群控模拟器(示例)"},
    {"blacklist_type": "ip", "blacklist_value": "203.0.113.9", "reason": "境外跳板IP(示例)"},
]


async def create_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"[OK] 已创建/校验 {len(Base.metadata.tables)} 张表 (库: {settings.DB_NAME})")


async def seed_rules(db):
    from sqlalchemy import select
    for r in SEED_RULES:
        exists = (await db.execute(select(RiskRule).where(RiskRule.rule_id == r["rule_id"]))).scalar_one_or_none()
        if exists:
            continue
        db.add(RiskRule(
            rule_id=r["rule_id"], rule_name=r["rule_name"], rule_category=r["rule_category"],
            event_type=r["event_type"], risk_level=r["risk_level"], risk_score=r["risk_score"],
            action=r["action"], priority=r["priority"], description=r["description"],
            rule_condition=json.dumps(r["rule_condition"], ensure_ascii=False),
        ))
    await db.commit()
    print(f"[OK] 种子规则: {len(SEED_RULES)} 条")


async def seed_blacklist(db):
    from sqlalchemy import select
    for b in SEED_BLACKLIST:
        exists = (await db.execute(select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == b["blacklist_type"],
            RiskBlacklist.blacklist_value == b["blacklist_value"],
            RiskBlacklist.deleted_at.is_(None)))).scalar_one_or_none()
        if exists:
            continue
        db.add(RiskBlacklist(blacklist_type=b["blacklist_type"], blacklist_value=b["blacklist_value"], reason=b["reason"]))
    await db.commit()
    print(f"[OK] 种子黑名单: {len(SEED_BLACKLIST)} 条")


async def main(reset: bool = False):
    if reset:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        print("[WARN] 已 DROP 全部表 (reset)")
    await create_tables()
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await seed_rules(db)
        await seed_blacklist(db)
    await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bank-Risk 数据库初始化")
    parser.add_argument("--yes", action="store_true", help="确认执行")
    parser.add_argument("--reset", action="store_true", help="先 DROP 再建 (危险)")
    args = parser.parse_args()
    if not args.yes and not args.reset:
        print("预览模式: 加 --yes 执行建表 + 种子数据; 加 --reset 危险重建")
        print(f"目标库: {settings.DB_NAME}, 将创建 {len(Base.metadata.tables)} 张表")
        raise SystemExit(0)
    asyncio.run(main(reset=args.reset))

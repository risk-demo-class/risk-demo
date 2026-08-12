"""幂等写入 15 条结构化规则；MR016 由黑名单前置检查产生。"""
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine.rule_definitions import RULE_DEFINITIONS  # noqa: E402
from app.models_risk import RiskRule  # noqa: E402


async def seed_rules() -> tuple[int, int]:
    created = updated = 0
    async with AsyncSessionLocal() as db:
        try:
            for index, row in enumerate(RULE_DEFINITIONS):
                rule_id, name, category, event_type, condition, level, score, action = row
                rule = await db.get(RiskRule, rule_id)
                values = dict(
                    rule_name=name, rule_category=category, event_type=event_type,
                    rule_condition=json.dumps(condition, ensure_ascii=False),
                    risk_level=level, risk_score=score, action=action,
                    is_enabled=1, priority=100 - index,
                    description="系统预置阈值，可在规则管理中调整",
                    deleted_at=None,
                )
                if rule is None:
                    db.add(RiskRule(rule_id=rule_id, **values))
                    created += 1
                else:
                    for key, value in values.items():
                        setattr(rule, key, value)
                    updated += 1
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return created, updated


async def main_async():
    try:
        created, updated = await seed_rules()
        print(f"规则初始化完成: created={created}, updated={updated}, blacklist_runtime=1")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main_async())

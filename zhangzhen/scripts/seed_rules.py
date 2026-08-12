"""幂等写入第一版 20 条银行规则。"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine.rule_seed import PRESET_RULES  # noqa: E402
from app.models_risk import RiskRule  # noqa: E402


async def seed_rules(db: AsyncSession) -> int:
    for index, data in enumerate(PRESET_RULES):
        rule = await db.get(RiskRule, data["rule_id"])
        values = {
            **data,
            "is_enabled": True,
            "priority": data["risk_score"],
            "description": f"教学预置规则：{data['rule_name']}，阈值仅用于演示",
            "deleted_at": None,
        }
        if rule is None:
            db.add(RiskRule(**values))
        else:
            for key, value in values.items():
                setattr(rule, key, value)
    await db.flush()
    return len(PRESET_RULES)


async def run() -> None:
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                count = await seed_rules(db)
        print(f"规则初始化成功：{count} 条")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())


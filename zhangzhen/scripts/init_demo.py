"""在表已创建的前提下，一次写入规则和小规模演示数据。"""

import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from scripts.seed_demo_data import seed_demo_data  # noqa: E402
from scripts.seed_rules import seed_rules  # noqa: E402


async def run() -> None:
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                rule_count = await seed_rules(db)
                await seed_demo_data(db)
        print(f"演示初始化完成：{rule_count} 条规则 + 四类银行业务样本")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())


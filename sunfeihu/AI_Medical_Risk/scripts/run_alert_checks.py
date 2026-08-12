"""手工执行一次聚合告警检查。"""
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal  # noqa: E402
from app.service.alert import run_alert_checks  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await run_alert_checks(db)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

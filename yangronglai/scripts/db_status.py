"""Print portable table and row-count status for the configured database."""

import asyncio
import json

from sqlalchemy import func, inspect, select

import app.models  # noqa: F401
from app.database import close_database, get_engine, get_session_factory
from app.models_business import (
    BankCard,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)
from app.models_risk import (
    RiskActionLog,
    RiskAppeal,
    RiskAppealEvidence,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeatureSnapshot,
    RiskLabel,
    RiskRule,
    RiskRuleHit,
)


TABLE_MODELS = (
    UserInfo,
    BankCard,
    Transaction,
    LoanApplication,
    LoginLog,
    DeviceFingerprint,
    IpGeoLocation,
    BlacklistExtra,
    RiskRule,
    RiskEvent,
    RiskFeatureSnapshot,
    RiskRuleHit,
    RiskAssessment,
    RiskLabel,
    RiskCase,
    RiskAppeal,
    RiskAppealEvidence,
    RiskActionLog,
)


async def read_status() -> dict:
    async with get_engine().connect() as connection:
        table_names = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())
    counts: dict[str, int] = {}
    async with get_session_factory()() as session:
        for model in TABLE_MODELS:
            counts[model.__tablename__] = int(
                await session.scalar(select(func.count()).select_from(model)) or 0
            )
    return {"table_count": len(table_names), "counts": counts}


async def main() -> int:
    try:
        print(json.dumps(await read_status(), ensure_ascii=False, indent=2))
        return 0
    finally:
        await close_database()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

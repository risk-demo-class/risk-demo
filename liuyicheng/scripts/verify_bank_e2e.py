"""验证 17 张表和银行四场景在线决策链。会写入风控事件/评估/案件。"""
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import func, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.models import (  # noqa: E402
    BankCard, BankTransaction, BlacklistExtra, DeviceFingerprint,
    IpGeoLocation, LoanApplication, LoginLog, RiskRule, UserInfo,
)
from app.schemas import RiskCheckRequest  # noqa: E402
from app.service.event import process_event  # noqa: E402


SAMPLES = [
    ("转账", "U002", "TXN_GEO_001", "R001"),
    ("信用卡", "U010", "TXN_CC_RISK", "R003"),
    ("贷款", "U006", "LOAN_MULTI_1", "R012"),
    ("登录", "U008", "LOGIN_PROXY", "R025"),
    ("转账", "U011", "TXN_BLACK_CARD", "R030"),
]


async def verify() -> None:
    business_models = [
        UserInfo, BankCard, BankTransaction, LoanApplication, LoginLog,
        DeviceFingerprint, IpGeoLocation, BlacklistExtra,
    ]
    async with AsyncSessionLocal() as db:
        table_count = int((await db.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE()"
        ))).scalar() or 0)
        rule_count = int((await db.execute(
            select(func.count()).select_from(RiskRule).where(RiskRule.deleted_at.is_(None))
        )).scalar() or 0)
        business_rows = 0
        for model in business_models:
            business_rows += int((await db.execute(
                select(func.count()).select_from(model)
            )).scalar() or 0)
    assert table_count == 17, f"表数量应为17，实际{table_count}"
    assert rule_count == 12, f"规则数量应为12，实际{rule_count}"
    assert business_rows >= 100, f"业务样例应不少于100，实际{business_rows}"

    results = []
    for event_type, user_id, source_id, expected_rule in SAMPLES:
        async with AsyncSessionLocal() as db:
            response = await process_event(db, RiskCheckRequest(
                event_type=event_type,
                source_id=source_id,
                user_id=user_id,
                event_data={"verification": True},
            ))
        hit_ids = [item.rule_id for item in response.triggered_rules]
        assert expected_rule in hit_ids, (
            f"{event_type}/{source_id} 应命中 {expected_rule}，实际 {hit_ids}"
        )
        results.append({
            "event_type": event_type,
            "source_id": source_id,
            "decision": response.decision,
            "score": response.final_score,
            "rules": hit_ids,
            "ml_score": response.ml_score,
        })
    print(json.dumps({
        "tables": table_count,
        "business_rows": business_rows,
        "rules": rule_count,
        "samples": results,
    }, ensure_ascii=False, indent=2))


async def main() -> None:
    try:
        await verify()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

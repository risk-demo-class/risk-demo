import os

import pytest
from sqlalchemy import text

from fastapi.testclient import TestClient

from app.database import async_engine
from run_app import app


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MYSQL_TESTS") != "1",
        reason="设置 RUN_MYSQL_TESTS=1 后才运行真实 MySQL 集成测试",
    ),
]


@pytest.mark.asyncio
async def test_real_database_contains_18_tables_and_expected_data():
    try:
        async with async_engine.connect() as connection:
            tables = (await connection.execute(text("SHOW TABLES"))).all()
            assert len(tables) == 18
            patient_count = (await connection.execute(
                text("SELECT COUNT(*) FROM medical_patient")
            )).scalar_one()
            assert patient_count == 200
    finally:
        await async_engine.dispose()


def test_high_risk_samples_hit_six_distinct_rules():
    samples = [
        ("医保结算", "CLM0000001", "PAT000001", {"MR001"}),
        ("处方开立", "RX0000001", "PAT000001", {"MR005"}),
        ("处方开立", "RX0000500", "PAT000050", {"MR014"}),
        ("挂号申请", "REG0000001", "PAT000002", {"MR012"}),
        ("挂号退号", "REG0000001", "PAT000002", {"MR011"}),
    ]
    client = TestClient(app)
    login = client.post("/api/auth/login", json={
        "username": "admin",
        "password": os.getenv("TEST_ADMIN_PASSWORD", "admin"),
    })
    assert login.status_code == 200, login.text
    observed = set()
    for event_type, source_id, patient_id, expected in samples:
        response = client.post("/api/risk/check", json={
            "event_type": event_type,
            "source_id": source_id,
            "user_id": patient_id,
            "event_data": {},
        })
        assert response.status_code == 200, response.text
        rule_ids = {row["rule_id"] for row in response.json()["triggered_rules"]}
        assert expected <= rule_ids
        observed |= rule_ids
    assert {"MR001", "MR002", "MR005", "MR011", "MR012", "MR014"} <= observed

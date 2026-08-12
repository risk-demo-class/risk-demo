from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.service.validator import EVENT_SOURCE_MAP, ensure_source_matches_event_type


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, value):
        self.value = value
        self.execute_count = 0

    async def execute(self, statement):
        self.execute_count += 1
        return FakeResult(self.value)


def test_four_medical_event_mappings():
    assert set(EVENT_SOURCE_MAP) == {"挂号申请", "挂号退号", "处方开立", "医保结算"}
    assert EVENT_SOURCE_MAP["挂号申请"].id_attr == "registration_id"
    assert EVENT_SOURCE_MAP["挂号退号"].id_attr == "registration_id"
    assert EVENT_SOURCE_MAP["处方开立"].id_attr == "prescription_id"
    assert EVENT_SOURCE_MAP["医保结算"].id_attr == "claim_id"


@pytest.mark.asyncio
async def test_matching_patient_is_accepted_with_one_query():
    db = FakeSession(SimpleNamespace(patient_id="PAT000001"))
    await ensure_source_matches_event_type(db, "处方开立", "RX0000001", "PAT000001")
    assert db.execute_count == 1


@pytest.mark.asyncio
async def test_wrong_patient_is_rejected():
    db = FakeSession(SimpleNamespace(patient_id="PAT000002"))
    with pytest.raises(HTTPException) as error:
        await ensure_source_matches_event_type(db, "医保结算", "CLM0000001", "PAT000001")
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_missing_source_is_404():
    db = FakeSession(None)
    with pytest.raises(HTTPException) as error:
        await ensure_source_matches_event_type(db, "挂号申请", "REG404", "PAT000001")
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_unknown_event_is_400_without_query():
    db = FakeSession(None)
    with pytest.raises(HTTPException) as error:
        await ensure_source_matches_event_type(db, "未知事件", "X", "PAT000001")
    assert error.value.status_code == 400
    assert db.execute_count == 0

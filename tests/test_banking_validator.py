"""业务校验器测试: 事件类型派发 + 防越权归属校验"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import LoanApplication, LoanContract, LoginLog, RepaymentRecord, Transaction
from app.service.validator import (
    _EVENT_SOURCE_VALIDATORS,
    ensure_entity_belongs_to_user,
    ensure_source_matches_event_type,
)
from app.schemas import RiskCheckRequest


def test_event_source_dispatch_covers_5_banking_events():
    """5 类银行业务事件都必须有来源实体映射"""
    expected = {
        "贷款申请": LoanApplication,
        "放款": LoanContract,
        "还款": RepaymentRecord,
        "转账": Transaction,
        "登录": LoginLog,
    }
    for evt, model in expected.items():
        assert any(
            evt in evt_types and info[0] is model
            for evt_types, info in _EVENT_SOURCE_VALIDATORS.items()
        ), f"{evt} 未映射到 {model.__name__}"


class _CountDB:
    def __init__(self, found: int):
        self.found = found

    async def execute(self, stmt):
        class _R:
            def __init__(self, n):
                self.n = n

            def scalar(self):
                return self.n

        return _R(self.found)


def test_source_matches_event_type_ok():
    req = RiskCheckRequest(event_type="贷款申请", source_id="LA0001", user_id="U0001")
    asyncio.run(ensure_source_matches_event_type(_CountDB(1), req))  # 存在 → 不抛


def test_source_matches_event_type_missing():
    req = RiskCheckRequest(event_type="贷款申请", source_id="LA9999", user_id="U0001")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ensure_source_matches_event_type(_CountDB(0), req))
    assert exc.value.status_code == 400


class _OwnerDB:
    def __init__(self, owner):
        self.owner = owner

    async def execute(self, stmt):
        class _R:
            def __init__(self, o):
                self.o = o

            def scalar_one_or_none(self):
                return self.o

        return _R(self.owner)


def test_ownership_mismatch_forbidden():
    db = _OwnerDB("U0002")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ensure_entity_belongs_to_user(
            db, LoanApplication, "application_id", "user_id",
            "LA0001", "U0001", "贷款申请",
        ))
    assert exc.value.status_code == 403


def test_ownership_match_ok():
    db = _OwnerDB("U0001")
    asyncio.run(ensure_entity_belongs_to_user(
        db, LoanApplication, "application_id", "user_id",
        "LA0001", "U0001", "贷款申请",
    ))  # 归属一致 → 不抛

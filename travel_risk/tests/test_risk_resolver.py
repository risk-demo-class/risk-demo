"""风控检查入参解析单测: 用户ID/业务ID/设备ID 任一即可"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.schemas import RiskCheckRequest
from app.service.event import _resolve_request


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDB:
    """按调用顺序返回固定行."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.idx = 0

    async def execute(self, stmt):
        row = self.rows[self.idx] if self.idx < len(self.rows) else None
        self.idx += 1
        return _FakeResult(row)


def _run(db, request: RiskCheckRequest):
    return asyncio.run(_resolve_request(db, request))


def test_only_user_id():
    req = RiskCheckRequest(user_id="U003")
    out = _run(_FakeDB([]), req)
    assert out.user_id == "U003"
    assert out.event_type == "通用"
    assert out.source_id == "U003"


def test_only_device_id():
    req = RiskCheckRequest(device_id="DEV001")
    db = _FakeDB([("U001",)])  # 设备 DEV001 最近绑定 U001
    out = _run(db, req)
    assert out.user_id == "U001"
    assert out.event_type == "通用"
    assert out.source_id == "DEV001"


def test_device_not_bound():
    req = RiskCheckRequest(device_id="DEV999")
    with pytest.raises(HTTPException) as e:
        _run(_FakeDB([None]), req)
    assert e.value.status_code == 404


def test_only_booking_id():
    req = RiskCheckRequest(source_id="B001")
    db = _FakeDB([("U003",)])  # booking B001 属于 U003
    out = _run(db, req)
    assert out.user_id == "U003"
    assert out.event_type == "下单"
    assert out.source_id == "B001"


def test_only_payment_id():
    req = RiskCheckRequest(source_id="PAY0001")
    db = _FakeDB([
        None,  # booking 未命中
        ("U001",),  # payment 命中
    ])
    out = _run(db, req)
    assert out.user_id == "U001"
    assert out.event_type == "支付"


def test_unknown_source_without_device():
    req = RiskCheckRequest(source_id="GHOST_ID")
    db = _FakeDB([None, None, None, None, None, None])  # 6 张表全部未命中
    with pytest.raises(HTTPException) as e:
        _run(db, req)
    assert e.value.status_code == 404


def test_no_identifier_raises_400():
    req = RiskCheckRequest()
    with pytest.raises(HTTPException) as e:
        _run(_FakeDB([]), req)
    assert e.value.status_code == 400


def test_explicit_event_type_kept():
    req = RiskCheckRequest(source_id="RF001", event_type="退改申请")
    db = _FakeDB([("U001",)])  # 只查退改表
    out = _run(db, req)
    assert out.event_type == "退改申请"
    assert out.user_id == "U001"

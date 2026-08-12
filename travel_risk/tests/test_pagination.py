"""通用分页单测"""
import asyncio
from types import SimpleNamespace

from app.service.case import paginate


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def scalars(self):
        return SimpleNamespace(all=lambda: self._value)


class _FakeDB:
    def __init__(self, total, items):
        self.total = total
        self.items = items
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        # 第一次调用是 count_stmt, 第二次是列表 stmt
        value = self.total if self.calls == 1 else self.items
        return _FakeResult(value)


class _FakeStmt:
    """模拟 SQLAlchemy stmt: offset/limit 链式调用."""

    def offset(self, n):
        return self

    def limit(self, n):
        return self


def test_paginate_basic():
    db = _FakeDB(25, list(range(10)))
    items, total, page, page_size = asyncio.run(
        paginate(db, _FakeStmt(), _FakeStmt(), page=1, page_size=10),
    )
    assert total == 25
    assert page == 1
    assert page_size == 10
    assert len(items) == 10


def test_paginate_clamps():
    db = _FakeDB(3, [1, 2, 3])
    items, total, page, page_size = asyncio.run(
        paginate(db, _FakeStmt(), _FakeStmt(), page=0, page_size=999),
    )
    assert page == 1
    assert page_size == 100

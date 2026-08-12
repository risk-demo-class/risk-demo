"""
联想搜索接口测试 (DB-free)
覆盖: 用户联想 / 业务ID联想 (type 切换 + user_id 过滤) / LIKE 转义 / 路由注册
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.routers.suggest import _escape_like, api_suggest_biz, api_suggest_users, suggest_router


def _db_with_rows(rows):
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    return db


class TestEscapeLike:
    def test_escapes_wildcards(self):
        assert _escape_like("a%b_c") == "a\\%b\\_c"
        assert _escape_like("100%") == "100\\%"
        assert _escape_like("plain") == "plain"


class TestSuggestUsers:
    @pytest.mark.asyncio
    async def test_empty_q_returns_empty(self):
        db = _db_with_rows([])
        resp = await api_suggest_users(q="", db=db)
        assert resp == {"items": []}
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_prefix_match_returns_fields(self):
        rows = [SimpleNamespace(
            user_id="U1001", name="张三",
            real_name_status=1, vip_level=2, account_age_days=400,
        )]
        resp = await api_suggest_users(q="U1", limit=10, db=_db_with_rows(rows))
        item = resp["items"][0]
        assert item["user_id"] == "U1001"
        assert item["name"] == "张三"
        assert item["real_name_status"] == 1
        assert item["vip_level"] == 2

    @pytest.mark.asyncio
    async def test_whitespace_stripped(self):
        resp = await api_suggest_users(q="  U1  ", limit=10, db=_db_with_rows([]))
        assert "items" in resp


class TestSuggestBiz:
    @pytest.mark.asyncio
    async def test_invalid_type_400(self):
        with pytest.raises(HTTPException) as exc:
            await api_suggest_biz(type="xxx", q="A", db=_db_with_rows([]))
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_q_returns_empty(self):
        resp = await api_suggest_biz(type="order", q="", db=_db_with_rows([]))
        assert resp == {"items": []}

    @pytest.mark.asyncio
    async def test_order_suggest(self):
        rows = [SimpleNamespace(
            order_id="ORD_T001", user_id="U1001", order_type="机票",
            total_amount=Decimal("5200.00"), dest_country="日本",
        )]
        resp = await api_suggest_biz(type="order", q="ORD", limit=10, db=_db_with_rows(rows))
        item = resp["items"][0]
        assert item["source_id"] == "ORD_T001"
        assert item["user_id"] == "U1001"
        assert "机票" in item["label"] and "日本" in item["label"]

    @pytest.mark.asyncio
    async def test_refund_suggest(self):
        rows = [SimpleNamespace(
            refund_id="RFD_001", user_id="U1001", order_id="ORD_T001",
            refund_type="退款", refund_amount=Decimal("1000"), refund_status="处理中",
        )]
        resp = await api_suggest_biz(type="refund", q="RFD", limit=10, db=_db_with_rows(rows))
        item = resp["items"][0]
        assert item["source_id"] == "RFD_001"
        assert "退款" in item["label"]

    @pytest.mark.asyncio
    async def test_visa_suggest(self):
        rows = [SimpleNamespace(
            visa_id="VISA_001", user_id="U1001", dest_country="日本",
            visa_type="旅游签证", submit_time=None,
        )]
        resp = await api_suggest_biz(type="visa", q="VISA", limit=10, db=_db_with_rows(rows))
        item = resp["items"][0]
        assert item["source_id"] == "VISA_001"
        assert "旅游签证" in item["label"]

    @pytest.mark.asyncio
    async def test_user_filter_accepted(self):
        """传 user_id 时接口正常 (过滤逻辑在 SQL 层, mock 只验证响应)."""
        resp = await api_suggest_biz(type="order", q="ORD", user_id="U1001", limit=10, db=_db_with_rows([]))
        assert "items" in resp


class TestRouterRegistration:
    def test_suggest_routes_registered(self):
        paths = [r.path for r in suggest_router.routes]
        assert "/api/suggest/users" in paths
        assert "/api/suggest/biz" in paths

    def test_static_paths_before_dynamic(self):
        """suggest 路由全是静态路径, 不存在被 /{user_id} 吞参的问题."""
        for r in suggest_router.routes:
            assert "{" not in r.path, f"suggest 路由不应有动态参数: {r.path}"

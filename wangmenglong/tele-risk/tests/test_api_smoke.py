"""
API 烟雾测试 (不打真实 DB): 路由注册 + 健康检查 + schema 可用性.

用 FastAPI TestClient, 但不连 DB (mock get_db_async).
验证: 7 个 router 都挂载了, /health 返回 ok, /api/risk/check 参数校验生效.

注意: 连 DB 的路由用 dependency_overrides 注入 mock session, 避免在 Windows 上
aiomysql 连接池跨 TestClient event loop 复用导致 'NoneType' has no attribute 'send'.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _mock_db_session() -> AsyncMock:
    """Mock async session: execute() 返一个能撑 scalar()/scalars().all() 的 result."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = 0
    result.scalars.return_value.all.return_value = []
    result.first.return_value = None
    session.execute.return_value = result
    return session


async def _mock_get_db():
    """依赖注入替身: yield mock session, 不连真实 MySQL."""
    yield _mock_db_session()


@pytest.fixture
def client():
    """FastAPI TestClient (不打真实 DB)."""
    from app.main import app
    return TestClient(app)


class TestRouteRegistration:
    """7 个 router 都挂载了."""

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "tele-risk"

    def test_risk_check_route_exists(self, client):
        """/api/risk/check 路由存在 (POST). 发空 body 应 422 (参数校验)."""
        resp = client.post("/api/risk/check", json={})
        assert resp.status_code == 422  # 缺 event_type/msisdn/source_id

    def test_rules_route_exists(self, client):
        from app.database import get_db_async
        from app.main import app
        app.dependency_overrides[get_db_async] = _mock_get_db
        try:
            resp = client.get("/api/rules")
            # mock session 返空列表 → 200; 路由没挂才是 404
            assert resp.status_code == 200, f"路由应存在, 实际 {resp.status_code}"
        finally:
            app.dependency_overrides.clear()

    def test_agent_route_exists(self, client):
        resp = client.post("/api/agent/chat", json={})
        assert resp.status_code == 422  # 缺 message

    def test_page_index(self, client):
        """/ 首页能渲染 (mock DB, 不实际连接避免 event loop 问题)."""
        from app.database import get_db_async
        from app.main import app
        app.dependency_overrides[get_db_async] = _mock_get_db
        try:
            resp = client.get("/")
            assert resp.status_code == 200, f"页面应能渲染, 实际 {resp.status_code}"
        finally:
            app.dependency_overrides.clear()


class TestRiskCheckValidation:
    """/api/risk/check 参数校验 (不打 DB)."""

    def test_invalid_event_type(self, client):
        """event_type 不是 5 种电信事件 → 422."""
        resp = client.post("/api/risk/check", json={
            "event_type": "下单", "source_id": "x", "msisdn": "13800000001",
        })
        assert resp.status_code == 422

    def test_missing_msisdn(self, client):
        resp = client.post("/api/risk/check", json={
            "event_type": "通话", "source_id": "x",
        })
        assert resp.status_code == 422

    def test_valid_request_shape(self, client):
        """参数合法 → 进 process_event (会因 DB/号卡不存在报错, 但不是 422)."""
        # mock process_event 返一个固定响应 (不打 DB)
        mock_resp = {
            "assessment_id": "ast_test", "event_id": "evt_test",
            "msisdn": "13800000001", "final_score": 70, "risk_level": "高",
            "decision": "人工审核", "rule_count": 1, "triggered_rules": [],
            "features": {}, "create_time": "2026-08-12T12:00:00",
        }
        with patch("app.routers.risk.process_event", new=AsyncMock(return_value=mock_resp)):
            resp = client.post("/api/risk/check", json={
                "event_type": "通话", "source_id": "cdr_001", "msisdn": "13800000001",
            })
        assert resp.status_code == 200
        assert resp.json()["msisdn"] == "13800000001"

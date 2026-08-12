from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.agent_api as agent_api
from app.auth import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Role, StaffUser, StaffUserRole


def test_agent_is_administrator_only_and_does_not_require_history(monkeypatch) -> None:
    suffix = uuid4().hex[:8]
    username = f"agent_viewer_{suffix}"
    password = "123456"
    user_id: int | None = None

    with SessionLocal.begin() as db:
        reviewer_role = db.scalar(select(Role).where(Role.role_code == "RISK_REVIEWER"))
        assert reviewer_role is not None
        now = datetime.now()
        user = StaffUser(
            username=username,
            password_hash=hash_password(password),
            display_name="Agent权限测试员工",
            is_active=True,
            session_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        user_id = user.staff_user_id
        db.add(
            StaffUserRole(
                staff_user_id=user.staff_user_id,
                role_id=reviewer_role.role_id,
                assigned_at=now,
                assigned_by=None,
            )
        )

    try:
        with TestClient(app) as reviewer:
            response = reviewer.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )
            assert response.status_code == 200
            assert reviewer.get("/agent").status_code == 403
            assert reviewer.get("/api/agent/capabilities").status_code == 403
            assert reviewer.post("/api/agent/run", json={"message": "查询风险概览"}).status_code == 403

        captured: dict[str, str] = {}

        def fake_run_agent(message, db, staff):
            captured["message"] = message
            captured["username"] = staff.username
            return {
                "answer": "当前风险概览读取完成。",
                "tools": [{"name": "get_risk_overview", "status": "success"}],
                "model": "test-model",
            }

        monkeypatch.setattr(agent_api, "run_agent", fake_run_agent)
        with TestClient(app) as admin:
            response = admin.post(
                "/api/auth/login",
                json={"username": "administer", "password": "123456"},
            )
            assert response.status_code == 200
            assert admin.get("/agent").status_code == 200
            capabilities = admin.get("/api/agent/capabilities")
            assert capabilities.status_code == 200
            assert capabilities.json()["history_enabled"] is False
            result = admin.post("/api/agent/run", json={"message": "查询风险概览"})
            assert result.status_code == 200
            assert result.json()["tools"][0]["name"] == "get_risk_overview"
            assert captured == {"message": "查询风险概览", "username": "administer"}
    finally:
        if user_id is not None:
            with SessionLocal.begin() as db:
                user = db.get(StaffUser, user_id)
                if user is not None:
                    db.delete(user)


def test_agent_tool_schemas_are_strict_and_deep_agent_is_restricted() -> None:
    from app.agent_service import AGENT_TOOLS, DEEP_AGENT_EXCLUDED_TOOLS, SYSTEM_PROMPT

    assert len(AGENT_TOOLS) >= 10
    assert "只服务于当前 OTA 旅游风控项目" in SYSTEM_PROMPT
    assert "没有历史对话" in SYSTEM_PROMPT
    assert {"read_file", "write_file", "execute", "task"} <= DEEP_AGENT_EXCLUDED_TOOLS
    for tool in AGENT_TOOLS:
        assert tool["strict"] is True
        parameters = tool["parameters"]
        assert parameters["additionalProperties"] is False
        assert set(parameters["properties"]) == set(parameters["required"])


def test_agent_message_is_limited_to_200_characters() -> None:
    from app.agent_api import AgentRequest
    from pydantic import ValidationError

    assert len(AgentRequest(message="风" * 200).message) == 200
    try:
        AgentRequest(message="风" * 201)
    except ValidationError:
        pass
    else:
        raise AssertionError("201-character Agent input should be rejected")


def test_deep_agent_is_stateless_and_executes_database_tools(monkeypatch) -> None:
    import app.agent_service as service
    from app.auth import AuthenticatedStaff

    model_options: dict = {}
    agent_options: dict = {}
    invocations: list[tuple[dict, dict]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            model_options.update(kwargs)

    class FakeAgent:
        def __init__(self, tools):
            self.tools = tools

        def invoke(self, input_data, config):
            invocations.append((input_data, config))
            overview_tool = next(tool for tool in self.tools if tool.name == "get_risk_overview")
            overview_result = overview_tool.invoke({})
            assert '"ok": true' in overview_result
            return {"messages": [service.AIMessage(content="风险概览查询完成。")]}

    def fake_create_deep_agent(**kwargs):
        agent_options.update(kwargs)
        return FakeAgent(kwargs["tools"])

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://model-gateway.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr(service, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(service, "create_deep_agent", fake_create_deep_agent)
    staff = AuthenticatedStaff(
        staff_user_id=1,
        username="administer",
        display_name="系统管理员",
        session_version=1,
        permissions=frozenset(),
    )
    with SessionLocal() as db:
        result = service.run_agent("查询风险概览", db, staff)

    assert result["answer"] == "风险概览查询完成。"
    assert model_options["api_key"] == "test-key"
    assert model_options["base_url"] == "https://model-gateway.example/v1"
    assert model_options["store"] is False
    assert model_options["use_previous_response_id"] is False
    assert result["tools"] == [{"name": "get_risk_overview", "status": "success"}]
    assert agent_options["system_prompt"] == service.SYSTEM_PROMPT
    assert agent_options["subagents"] == []
    assert agent_options["memory"] is None
    assert agent_options["checkpointer"] is None
    assert agent_options["store"] is None
    assert {tool.name for tool in agent_options["tools"]} == {
        tool["name"] for tool in service.AGENT_TOOLS
    }
    assert invocations == [
        (
            {"messages": [{"role": "user", "content": "查询风险概览"}]},
            {"recursion_limit": 24},
        )
    ]

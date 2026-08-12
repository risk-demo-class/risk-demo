"""Eight executable Agent tools with an explicit approval boundary."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.database import get_session_factory
from app.engine.graph import graph_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event
from app.service.operations import (
    assessment_detail,
    customer_360,
    dashboard_stats,
    list_cases,
    request_case_review,
    rule_effectiveness,
)


TOOL_MANIFEST = [
    {
        "name": "risk_check",
        "mode": "execute",
        "approval": False,
        "description": "对信用卡、贷款、转账或登录事件执行三层风险评估。",
        "parameters": {"type": "object", "properties": {"scenario": {"type": "string"}, "source_id": {"type": "string"}, "user_id": {"type": "string"}, "event_data": {"type": "object"}}, "required": ["scenario", "source_id", "user_id"]},
    },
    {
        "name": "explain_decision",
        "mode": "read",
        "approval": False,
        "description": "查询评估详情、三层分数、命中规则和证据。",
        "parameters": {"type": "object", "properties": {"assessment_id": {"type": "string"}}, "required": ["assessment_id"]},
    },
    {
        "name": "query_cases",
        "mode": "read",
        "approval": False,
        "description": "查询人工审核案件。",
        "parameters": {"type": "object", "properties": {"status": {"type": "string"}, "page": {"type": "integer"}, "page_size": {"type": "integer"}}},
    },
    {
        "name": "query_customer_360",
        "mode": "read",
        "approval": False,
        "description": "查询客户、银行卡、交易、贷款、登录和历史风险。",
        "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]},
    },
    {
        "name": "query_graph_relations",
        "mode": "read",
        "approval": False,
        "description": "查询客户二度设备、IP、卡片和资金关系。",
        "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}, "depth": {"type": "integer"}}, "required": ["user_id"]},
    },
    {
        "name": "query_dashboard_stats",
        "mode": "read",
        "approval": False,
        "description": "查询评估、案件、风险分布和高频规则统计。",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "analyze_rule_effectiveness",
        "mode": "read",
        "approval": False,
        "description": "分析规则命中次数和命中率。",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "submit_review_request",
        "mode": "request",
        "approval": True,
        "description": "经人工批准后将案件提交审核队列，不直接给出审核结论。",
        "parameters": {"type": "object", "properties": {"case_id": {"type": "string"}, "operator": {"type": "string"}, "reason": {"type": "string"}, "approval_token": {"type": "string"}}, "required": ["case_id", "operator", "reason"]},
    },
]


async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    manifest = next((item for item in TOOL_MANIFEST if item["name"] == name), None)
    if manifest is None:
        return {"ok": False, "error": f"unknown tool: {name}"}
    if manifest["approval"] and (
        not settings.AGENT_APPROVAL_TOKEN
        or arguments.get("approval_token") != settings.AGENT_APPROVAL_TOKEN
    ):
        return {
            "ok": False,
            "approval_required": True,
            "tool": name,
            "message": "该请求会改变案件状态，需要审批系统提供有效 approval_token。",
        }
    async with get_session_factory()() as session:
        if name == "risk_check":
            request = RiskCheckRequest.model_validate(arguments)
            result = await process_event(request, session)
            return {"ok": True, "data": result.model_dump(mode="json")}
        if name == "explain_decision":
            result = await assessment_detail(session, arguments["assessment_id"])
        elif name == "query_cases":
            result = await list_cases(
                session,
                status=arguments.get("status"),
                page=max(1, int(arguments.get("page", 1))),
                page_size=min(100, max(1, int(arguments.get("page_size", 20)))),
            )
        elif name == "query_customer_360":
            result = await customer_360(session, arguments["user_id"])
        elif name == "query_graph_relations":
            result = await graph_engine.neighborhood(
                arguments["user_id"], session, depth=min(3, max(1, int(arguments.get("depth", 2))))
            )
        elif name == "query_dashboard_stats":
            result = await dashboard_stats(session)
        elif name == "analyze_rule_effectiveness":
            result = await rule_effectiveness(session)
        else:
            result = await request_case_review(
                session,
                arguments["case_id"],
                operator=arguments["operator"],
                reason=arguments["reason"],
            )
        if result is None:
            return {"ok": False, "error": "target not found"}
        return {"ok": True, "data": result}


def openai_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["parameters"],
            },
        }
        for item in TOOL_MANIFEST
    ]

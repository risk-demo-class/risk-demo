"""两角色、案件分配与审核闭环回归测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth import AuthUser
from app.schemas import CaseAssignRequest, CaseReviewRequest


@pytest.mark.asyncio
async def test_assignment_moves_pending_case_to_reviewing(monkeypatch):
    from app.service import case as case_service

    risk_case = SimpleNamespace(
        case_id="case-001", case_status="待审核", assignee_id=None, assign_time=None,
    )
    reviewer = SimpleNamespace(user_id=2, username="reviewer")
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=risk_case)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=reviewer)),
        ]),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(case_service, "record_action", AsyncMock())
    expected = SimpleNamespace(case_id="case-001", case_status="审核中")
    monkeypatch.setattr(case_service, "get_case_detail", AsyncMock(return_value=expected))

    result = await case_service.assign_case(
        db, "case-001", CaseAssignRequest(assignee_id=2), "admin",
    )

    assert result is expected
    assert risk_case.assignee_id == 2
    assert risk_case.case_status == "审核中"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_can_review_any_open_case(monkeypatch):
    from app.routers import case as case_router_module

    detail = SimpleNamespace(assignee_id=None)
    expected = SimpleNamespace(case_id="case-001", case_status="已通过")
    monkeypatch.setattr(case_router_module, "get_case_detail", AsyncMock(return_value=detail))
    review_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(case_router_module, "review_case", review_mock)

    admin = AuthUser(1, "admin", "管理员", "ADMIN")
    result = await case_router_module.api_review_case(
        "case-001",
        CaseReviewRequest(decision="已通过", reviewer="伪造值", review_comment="管理员兜底审核"),
        SimpleNamespace(),
        admin,
    )

    assert result is expected
    sent_request = review_mock.await_args.args[2]
    assert sent_request.reviewer == "admin"


@pytest.mark.asyncio
async def test_reviewer_cannot_review_another_reviewers_case(monkeypatch):
    from app.routers import case as case_router_module

    monkeypatch.setattr(
        case_router_module, "get_case_detail", AsyncMock(return_value=SimpleNamespace(assignee_id=99)),
    )
    reviewer = AuthUser(2, "reviewer", "审核员", "REVIEWER")

    with pytest.raises(Exception) as exc_info:
        await case_router_module.api_review_case(
            "case-002",
            CaseReviewRequest(decision="已拒绝", reviewer="reviewer"),
            SimpleNamespace(),
            reviewer,
        )

    assert getattr(exc_info.value, "status_code", None) == 403


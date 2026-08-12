from pathlib import Path

from app.schemas import AssessmentItem


ROOT = Path(__file__).resolve().parents[1]


def test_blacklist_page_has_explicit_manual_add_workflow():
    source = (ROOT / "templates/blacklist.html").read_text(encoding="utf-8")
    assert "手动添加黑名单" in source
    assert "无需先拒绝案件" in source
    assert "showAddModal()" in source
    assert "method: 'POST'" in source
    assert "'/api/blacklist'" in source


def test_assessment_list_contract_contains_source_id_for_recheck():
    item = AssessmentItem(
        assessment_id="A1",
        event_id="E1",
        user_id="U1",
        event_type="转账",
        event_source_id="T1",
        final_score=80,
        risk_level="高",
        decision="人工审核",
        rule_count=1,
        create_time="2026-08-12T12:00:00",
    )
    assert item.event_source_id == "T1"


def test_assessment_history_can_prefill_risk_check():
    assessments = (ROOT / "templates/assessments.html").read_text(encoding="utf-8")
    service = (ROOT / "app/service/case.py").read_text(encoding="utf-8")
    assert "recheckAssessment" in assessments
    assert "risk_check_prefill" in assessments
    assert "event_source_id" in assessments
    assert "RiskEvent.event_source_id" in service


def test_risk_check_draft_survives_navigation_and_can_be_cleared():
    source = (ROOT / "templates/risk_check.html").read_text(encoding="utf-8")
    assert "risk_check_draft_v1" in source
    assert "localStorage.setItem" in source
    assert "localStorage.getItem" in source
    assert "clearRiskCheckDraft" in source
    assert "输入会自动保存" in source

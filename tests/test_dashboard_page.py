from fastapi.testclient import TestClient
from pathlib import Path


def test_dashboard_page_uses_the_source_project_navigation_structure():
    from app.main import app

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "教育风控仪表盘" in response.text
    assert "规则管理" in response.text
    assert "案件管理" in response.text


def test_dashboard_template_inherits_the_shared_source_style_shell():
    template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")

    assert '{% extends "base.html" %}' in template


def test_shared_shell_does_not_double_count_the_fixed_sidebar_grid_width():
    template = Path("app/templates/base.html").read_text(encoding="utf-8")

    assert 'class="col-md-10 main-content"' not in template
    assert 'class="col-md-2 sidebar' not in template


def test_risk_check_page_uses_the_source_project_form_route():
    from app.main import app

    response = TestClient(app).get("/risk-check")

    assert response.status_code == 200
    assert 'id="checkForm"' in response.text
    assert "发起课程报名风险检查" in response.text
    assert '<option value="退费申请">退费申请</option>' in response.text

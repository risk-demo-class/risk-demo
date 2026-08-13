"""Goal 3 银行前端关键路由、文案、绑定与静态资源测试。"""

from pathlib import Path

from fastapi.testclient import TestClient

from scripts.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_six_core_bank_pages_render_and_load_shared_stylesheet():
    client = TestClient(app)
    expected = {
        "/": "银行风险运营总览",
        "/risk-check": "银行事件风险检查",
        "/rules": "银行风险规则",
        "/blacklist": "银行风险黑名单",
        "/cases": "银行风险案件",
        "/assessments": "银行风险评估流水",
    }
    for path, heading in expected.items():
        response = client.get(path)
        assert response.status_code == 200
        assert heading in response.text
        assert '/static/app.css?v=' in response.text
        assert "银行风险运营工作台" in response.text


def test_shared_bank_css_and_javascript_are_served():
    client = TestClient(app)
    css = client.get("/static/app.css")
    javascript = client.get("/static/app.js")
    assert css.status_code == 200
    assert javascript.status_code == 200
    assert "--brand-900: #0B1F3A" in css.text
    assert '"order_event_amount"' in javascript.text
    assert '"本次事件金额"' in javascript.text


def test_frontend_has_no_obsolete_ecommerce_event_options():
    for filename in ("risk_check.html", "rules.html", "assessments.html"):
        content = (ROOT / "templates" / filename).read_text(encoding="utf-8")
        for event_type in ("下单", "支付", "售后申请", "物流投诉"):
            assert f'value="{event_type}"' not in content


def test_risk_check_request_has_only_external_bank_fields():
    content = (ROOT / "templates" / "risk_check.html").read_text(encoding="utf-8")
    request_block = content.split("body: JSON.stringify(", 1)[1].split("})", 1)[0]
    for field in ("event_type", "user_id", "source_id", "event_data"):
        assert field in request_block
    assert "order_id" not in request_block
    assert "receive_id" not in request_block


def test_loading_empty_error_success_and_blacklist_feedback_exist():
    dashboard = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
    risk_check = (ROOT / "templates" / "risk_check.html").read_text(encoding="utf-8")
    for marker in ("正在加载真实统计", "暂无规则命中", "总览数据暂时不可用", "重新加载"):
        assert marker in dashboard
    for marker in ("决策流水线执行中", "等待风险事件", "风险检查未完成", "最终决策", "黑名单短路"):
        assert marker in risk_check

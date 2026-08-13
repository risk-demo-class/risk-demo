"""实时检查页必须把决策引擎使用的规则分和模型分显式展示。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_risk_check_page_renders_complete_score_breakdown() -> None:
    html = (ROOT / "templates" / "risk_check.html").read_text(encoding="utf-8")
    for element_id in (
        "rule-score", "ml-probability", "ml-risk-score", "score-weights",
        "fusion-score", "veto-status", "score-formula", "model-status",
    ):
        assert f'id="{element_id}"' in html
    assert "renderScoreBreakdown(lastResult)" in html
    assert "规则与模型融合决策完成" in html


def test_score_breakdown_has_responsive_styles() -> None:
    css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
    assert ".score-breakdown" in css
    assert ".score-formula" in css

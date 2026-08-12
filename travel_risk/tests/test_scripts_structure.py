"""脚本结构单测: 关键脚本存在且含主入口"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_SCRIPTS = [
    "init_db.py",
    "gen_10w_data.py",
    "gen_risky_users.py",
    "gen_risk_data.py",
    "gen_risk_data_with_dates.py",
    "gen_train_dataset.py",
    "train_xgb_model.py",
    "train_demo_model.py",
    "backfill_ml_score.py",
    "one_command.py",
    "main.py",
]


def test_scripts_exist():
    for name in REQUIRED_SCRIPTS:
        path = os.path.join(PROJECT_ROOT, "scripts", name)
        assert os.path.exists(path), f"缺少脚本: {name}"


def test_sql_files_exist():
    for name in ("init_business_tables.sql", "init_business_data.sql",
                 "init_risk_tables.sql", "init_risk_data.sql"):
        path = os.path.join(PROJECT_ROOT, "sql", name)
        assert os.path.exists(path), f"缺少 SQL: {name}"


def test_risk_data_has_30_rules():
    path = os.path.join(PROJECT_ROOT, "sql", "init_risk_data.sql")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert content.count("INSERT INTO risk_rule") == 30


def test_models_importable():
    from app.models import (  # noqa: F401
        BookingInfo,
        RiskAssessment,
        RiskRule,
        TravelerInfo,
    )
    assert BookingInfo.__tablename__ == "booking_info"
    assert RiskRule.__tablename__ == "risk_rule"


def test_rules_page_has_condition_column():
    """规则管理页必须包含"规则条件"表头和渲染函数 (防止回归丢失条件列)."""
    path = os.path.join(PROJECT_ROOT, "templates", "rules.html")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "规则条件" in content
    assert "ruleConditionHtml" in content


def test_rules_page_filter_interactions():
    """分类/事件下拉必须切换即刷新 (onchange), 且提供重置与筛选状态提示."""
    path = os.path.join(PROJECT_ROOT, "templates", "rules.html")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert 'onchange="loadRules(1)"' in content
    assert "resetRuleFilters" in content
    assert "rule-filter-state" in content


def test_cases_page_has_risk_detail_modal():
    """案件审核弹窗必须展示风控检查详细结果 (评分/规则/特征)."""
    path = os.path.join(PROJECT_ROOT, "templates", "cases.html")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "renderRiskDetail" in content
    assert "c-risk-detail" in content
    assert "28 维特征快照" in content
    assert 'modal-xl' in content

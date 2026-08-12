"""任务 2 验收入口：python -m app.service.validator。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import inspect, select

from app.database import SessionLocal, engine
from app.engine.feature import ACCOUNT_FEATURES, BEHAVIOR_FEATURES, ENROLLMENT_FEATURES
from app.engine.ml_model import FEATURE_COLUMNS
from app.engine.decision import calculate_decision
from app.engine.rule import RULE_MATCHERS, load_enabled_rules, match_rules, validate_condition
from app.schemas import UserCreate


def validate_static_contracts() -> None:
    assert len(FEATURE_COLUMNS) == 25
    assert len(ACCOUNT_FEATURES) == 8
    assert len(ENROLLMENT_FEATURES) == 8
    assert len(BEHAVIOR_FEATURES) == 9
    assert len(RULE_MATCHERS) == 8
    UserCreate(
        user_id="VALIDATOR", name="校验用户", role="学生",
        student_id="VALIDATOR-ST", register_at=datetime.now(),
    )


def validate_database() -> None:
    expected_tables = {
        "user_info", "user_device", "course", "order_info", "learning_progress",
        "refund_request", "blacklist_extra", "education_credential", "live_reward",
        "risk_rule", "risk_event", "risk_feature", "risk_assessment", "risk_case",
    }
    actual = set(inspect(engine).get_table_names())
    assert expected_tables <= actual, f"缺表: {expected_tables - actual}"
    with SessionLocal() as db:
        rules = load_enabled_rules(db)
        assert len(rules) == 8, f"启用规则应为8条，实际{len(rules)}条"
        assert all(rule.enabled for rule in rules)
        for rule in rules:
            validate_condition(rule.rule_condition)
        r002 = next(rule for rule in rules if rule.rule_id == "R002")
        hits = match_rules([r002], {"study_minutes_before_refund": 2})
        result = calculate_decision(hits)
        assert (result.score, result.risk_level, result.decision) == (80, "高", "人工审核")
        assert db.scalar(select(r002.__class__.enabled).where(r002.__class__.rule_id == "R002")) is True


def main() -> None:
    validate_static_contracts()
    validate_database()
    print("validator OK")
    print("  tables=14, rules=8(enabled=True), features=25 (8+8+9)")
    print("  demo: R002 study_minutes=2 -> 高/人工审核/80分")


if __name__ == "__main__":
    main()

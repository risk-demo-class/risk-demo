from __future__ import annotations

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import OrderInfo, RiskRule
from app.risk_engine import recalculate_all_assessments


def test_full_recalculation_covers_every_order_and_is_idempotent() -> None:
    with SessionLocal() as session:
        order_count = session.scalar(select(func.count()).select_from(OrderInfo)) or 0
        result = recalculate_all_assessments(
            session,
            operator="test_runner",
            trigger="test_idempotent",
        )
        assert result.total_orders == order_count
        assert sum(result.decisions.values()) == order_count
        assert result.changed_assessments == 0
        assert result.generated_hits > 0
        session.rollback()


def test_disabling_every_rule_recalculates_all_orders_to_pass() -> None:
    with SessionLocal() as session:
        rules = list(session.scalars(select(RiskRule)))
        for rule in rules:
            rule.is_enabled = False
        result = recalculate_all_assessments(
            session,
            operator="test_runner",
            trigger="test_rules_disabled",
            use_model=False,
        )
        assert result.decisions == {"PASS": result.total_orders}
        assert result.generated_hits == 0
        session.rollback()

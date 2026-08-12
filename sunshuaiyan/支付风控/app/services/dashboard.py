from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ml.model import model_metrics
from app.services.rule_engine import load_rules_from_db


def dashboard_stats(db: Session) -> dict[str, Any]:
    summary = db.execute(text("""
        SELECT
          COUNT(*) AS inbound_count,
          ROUND(SUM(amount_usd), 2) AS inbound_amount_usd,
          SUM(inbound_status IN ('REJECTED','REFUNDED')) AS high_risk_count,
          ROUND(100 * SUM(inbound_status IN ('REJECTED','REFUNDED')) / COUNT(*), 2) AS high_risk_rate,
          COUNT(DISTINCT customer_id) AS active_customers,
          COUNT(DISTINCT payer_counterparty_id) AS distinct_payers
        FROM inbound_payments
    """)).mappings().one()
    cases = db.execute(text("""
        SELECT
          SUM(status <> 'CLOSED') AS open_cases,
          SUM(priority IN ('P0','P1') AND status <> 'CLOSED') AS urgent_cases,
          COALESCE(ROUND(SUM(loss_amount_usd), 2), 0) AS labeled_loss_usd
        FROM risk_cases
    """)).mappings().one()
    payouts = db.execute(text("""
        SELECT COUNT(*) AS payout_count,
               SUM(status = 'RISK_HOLD') AS payout_holds,
               SUM(seconds_since_inbound < 3600) AS rapid_payouts
        FROM payouts
    """)).mappings().one()
    return {**dict(summary), **dict(cases), **dict(payouts), "model": model_metrics()}


def risk_trend(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(text("""
        SELECT DATE_FORMAT(received_date, '%Y-%m-%d') AS day,
               COUNT(*) AS total,
               SUM(inbound_status IN ('REJECTED','REFUNDED')) AS high_risk,
               ROUND(SUM(amount_usd), 2) AS amount_usd
        FROM inbound_payments
        GROUP BY received_date
        ORDER BY received_date DESC
        LIMIT 30
    """)).mappings().all()
    return [dict(row) for row in reversed(rows)]


def recent_inbounds(db: Session, limit: int = 30) -> list[dict[str, Any]]:
    rows = db.execute(text("""
        SELECT ip.id, ip.transaction_id, c.client_id, c.legal_name AS customer_name,
               ip.amount_usd, ip.currency, ip.origin_country, ip.business_type,
               ip.inbound_status, ip.received_at, ip.risk_score,
               cp.legal_name AS payer_name, cp.external_risk_label
        FROM inbound_payments ip
        JOIN customers c ON c.id = ip.customer_id
        JOIN counterparties cp ON cp.id = ip.payer_counterparty_id
        ORDER BY ip.received_at DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()
    return [dict(row) for row in rows]


def recent_payouts(db: Session, limit: int = 30) -> list[dict[str, Any]]:
    rows = db.execute(text("""
        SELECT po.id, po.payout_id, po.pay_amount, po.pay_currency, po.target_amount,
               po.target_currency, po.status, po.requested_at, po.risk_score,
               c.client_id, c.legal_name AS customer_name,
               ba.account_ref AS beneficiary_account_ref, ba.holder_name AS beneficiary_name,
               ba.bank_country
        FROM payouts po
        JOIN customers c ON c.id = po.customer_id
        JOIN bank_accounts ba ON ba.id = po.beneficiary_bank_account_id
        ORDER BY po.requested_at DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()
    return [dict(row) for row in rows]


def case_queue(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.execute(text("""
        SELECT rc.id, rc.case_id, rc.case_type, rc.priority, rc.status, rc.title,
               rc.opened_at, rc.due_at, rc.assignee, rc.disposition,
               c.client_id, c.legal_name AS customer_name
        FROM risk_cases rc
        LEFT JOIN customers c ON c.id = rc.customer_id
        ORDER BY FIELD(rc.status, 'INVESTIGATING', 'PENDING', 'CLOSED'),
                 FIELD(rc.priority, 'P0', 'P1', 'P2', 'P3'), rc.opened_at DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()
    return [dict(row) for row in rows]


def rule_catalog(db: Session) -> list[dict[str, Any]]:
    return load_rules_from_db(db)

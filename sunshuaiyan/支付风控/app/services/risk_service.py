from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import engine
from app.ml.model import model_metrics, predict_probability
from app.services.blacklist import check_blacklist_candidates
from app.services.features import feature_record, payout_feature_record
from app.services.rule_engine import aggregate_rule_score, evaluate_rules
from models import (
    BankAccount,
    Counterparty,
    Customer,
    InboundPayment,
    Payout,
    RiskDecision,
    RiskEvent,
    VirtualAccount,
)


def _decision(score: float, veto: bool = False) -> str:
    if veto or score >= 80:
        return "REJECT"
    if score >= 60:
        return "MANUAL_REVIEW"
    if score >= 30:
        return "FLAG"
    return "ALLOW"


def _inbound_blacklist_hits(db: Session, payment: InboundPayment, record_hit: bool) -> list[dict[str, Any]]:
    customer = db.get(Customer, payment.customer_id)
    payer = db.get(Counterparty, payment.payer_counterparty_id)
    virtual_account = db.get(VirtualAccount, payment.virtual_account_id)
    payer_account = db.get(BankAccount, payment.payer_bank_account_id) if payment.payer_bank_account_id else None
    return check_blacklist_candidates(
        db,
        [
            ("CUSTOMER", customer.client_id if customer else None, customer.legal_name if customer else None),
            ("COUNTERPARTY", payer.counterparty_ref if payer else None, payer.legal_name if payer else None),
            ("VIRTUAL_ACCOUNT", virtual_account.va_id if virtual_account else None, virtual_account.account_holder_name if virtual_account else None),
            ("BANK_ACCOUNT", payer_account.account_ref if payer_account else None, payer_account.holder_name if payer_account else None),
            ("COUNTRY", payment.origin_country, payment.origin_country),
        ],
        record_hit=record_hit,
    )


def _payout_blacklist_hits(
    db: Session, payout: Payout, record_hit: bool
) -> list[dict[str, Any]]:
    customer = db.get(Customer, payout.customer_id)
    beneficiary = db.get(BankAccount, payout.beneficiary_bank_account_id)
    return check_blacklist_candidates(
        db,
        [
            ("CUSTOMER", customer.client_id if customer else None, customer.legal_name if customer else None),
            ("BANK_ACCOUNT", beneficiary.account_ref if beneficiary else None, beneficiary.holder_name if beneficiary else None),
            ("COUNTRY", beneficiary.bank_country if beneficiary else None, beneficiary.bank_country if beneficiary else None),
        ],
        record_hit=record_hit,
    )


def assess_inbound(db: Session, inbound_payment_id: int, persist: bool = True) -> dict[str, Any]:
    payment = db.get(InboundPayment, inbound_payment_id)
    if payment is None:
        raise LookupError(f"inbound payment {inbound_payment_id} not found")
    features = feature_record(engine, inbound_payment_id)
    blacklist_hits = _inbound_blacklist_hits(db, payment, record_hit=persist)
    hits = evaluate_rules(features, "INBOUND", db)
    rule_score = aggregate_rule_score(hits)
    probability, model_loaded = predict_probability(features)
    ml_score = 100.0 * (1.0 - math.exp(-3.0 * probability)) if model_loaded else 0.0
    veto = bool(blacklist_hits) or any(hit.veto for hit in hits)
    final_score = 100.0 if blacklist_hits else (max(90.0, rule_score) if veto else 0.55 * rule_score + 0.45 * ml_score)
    decision = _decision(final_score, veto)
    event_id = None
    decision_id = None

    if persist:
        now = datetime.now()
        event = RiskEvent(
            event_id=f"EVT-RISK-{uuid.uuid4().hex[:20]}",
            event_type="inbound.risk.assessed.v1",
            event_version=1,
            risk_domain="FRAUD",
            partner_id=int(features["partner_id"]),
            customer_id=int(features["customer_id"]),
            subject_type="INBOUND_PAYMENT",
            subject_id=str(features["transaction_id"]),
            actor_type="SYSTEM",
            actor_id="risk-api",
            occurred_at=now,
            received_at=now,
            correlation_id=f"CORR-{uuid.uuid4().hex[:20]}",
            causation_id=None,
            idempotency_key=f"ASSESS-{inbound_payment_id}-{uuid.uuid4().hex[:12]}",
            source_system="pingpong-risk-app",
            risk_score=round(final_score, 4),
            labels=[hit.category for hit in hits] + (["BLACKLIST"] if blacklist_hits else []),
            payload={
                "features": {name: features.get(name) for name in model_metrics().get("feature_columns", [])},
                "blacklist_hits": [item["blacklist_id"] for item in blacklist_hits],
            },
        )
        event.partner_id = payment.partner_id
        db.add(event)
        db.flush()
        decision_row = RiskDecision(
            decision_id=f"RDEC-{uuid.uuid4().hex[:20]}",
            risk_event_id=event.id,
            partner_id=payment.partner_id,
            customer_id=payment.customer_id,
            subject_type="INBOUND_PAYMENT",
            subject_id=payment.transaction_id,
            risk_domain="FRAUD",
            decision=decision,
            risk_score=round(final_score, 4),
            rule_hits=[hit.id for hit in hits],
            model_outputs={"probability": round(probability, 6), "ml_score": round(ml_score, 4), "loaded": model_loaded},
            reason_codes=[f"BLACKLIST_{item['entity_type']}" for item in blacklist_hits] + [hit.category for hit in hits],
            engine_version="pingpong-risk-1.0.0",
            decided_at=now,
            manual_override=False,
        )
        db.add(decision_row)
        db.commit()
        event_id = event.event_id
        decision_id = decision_row.decision_id

    return {
        "inbound_payment_id": inbound_payment_id,
        "transaction_id": features["transaction_id"],
        "customer_id": features["customer_id"],
        "decision": decision,
        "final_score": round(final_score, 4),
        "rule_score": rule_score,
        "ml_probability": round(probability, 6),
        "ml_score": round(ml_score, 4),
        "model_loaded": model_loaded,
        "veto": veto,
        "blacklist_match": bool(blacklist_hits),
        "blacklist_hits": blacklist_hits,
        "rule_hits": [hit.as_dict() for hit in hits],
        "features": features,
        "risk_event_id": event_id,
        "risk_decision_id": decision_id,
    }


def assess_payout(db: Session, payout_id: int, persist: bool = True) -> dict[str, Any]:
    features = payout_feature_record(engine, payout_id)
    payout = db.get(Payout, payout_id)
    if payout is None:
        raise LookupError(f"payout {payout_id} not found")
    blacklist_hits = _payout_blacklist_hits(db, payout, record_hit=persist)
    hits = evaluate_rules(features, "PAYOUT", db)
    score = aggregate_rule_score(hits)
    veto = bool(blacklist_hits) or any(hit.veto for hit in hits)
    final_score = 100 if blacklist_hits else score
    decision = _decision(final_score, veto)
    event_id = None
    decision_id = None

    if persist:
        now = datetime.now()
        event = RiskEvent(
            event_id=f"EVT-RISK-{uuid.uuid4().hex[:20]}",
            event_type="payout.risk.assessed.v1",
            event_version=1,
            risk_domain="FRAUD",
            partner_id=payout.partner_id,
            customer_id=payout.customer_id,
            subject_type="PAYOUT",
            subject_id=payout.payout_id,
            actor_type="SYSTEM",
            actor_id="risk-api",
            occurred_at=now,
            received_at=now,
            correlation_id=f"CORR-{uuid.uuid4().hex[:20]}",
            causation_id=None,
            idempotency_key=f"ASSESS-PAYOUT-{payout_id}-{uuid.uuid4().hex[:12]}",
            source_system="pingpong-risk-app",
            risk_score=round(final_score, 4),
            labels=[hit.category for hit in hits] + (["BLACKLIST"] if blacklist_hits else []),
            payload={
                "features": features,
                "blacklist_hits": [item["blacklist_id"] for item in blacklist_hits],
            },
        )
        db.add(event)
        db.flush()
        decision_row = RiskDecision(
            decision_id=f"RDEC-{uuid.uuid4().hex[:20]}",
            risk_event_id=event.id,
            partner_id=payout.partner_id,
            customer_id=payout.customer_id,
            subject_type="PAYOUT",
            subject_id=payout.payout_id,
            risk_domain="FRAUD",
            decision=decision,
            risk_score=round(final_score, 4),
            rule_hits=[hit.id for hit in hits],
            model_outputs={"probability": 0.0, "loaded": False},
            reason_codes=[f"BLACKLIST_{item['entity_type']}" for item in blacklist_hits]
            + [hit.category for hit in hits],
            engine_version="pingpong-risk-1.0.0",
            decided_at=now,
            manual_override=False,
        )
        db.add(decision_row)
        db.commit()
        event_id = event.event_id
        decision_id = decision_row.decision_id

    return {
        "payout_id": payout_id,
        "business_id": payout.payout_id,
        "decision": decision,
        "final_score": final_score,
        "rule_score": score,
        "ml_probability": 0.0,
        "model_loaded": False,
        "veto": veto,
        "blacklist_match": bool(blacklist_hits),
        "blacklist_hits": blacklist_hits,
        "rule_hits": [hit.as_dict() for hit in hits],
        "features": features,
        "risk_event_id": event_id,
        "risk_decision_id": decision_id,
    }


def assess_business_id(db: Session, event_type: str, business_id: str, persist: bool = True) -> dict[str, Any]:
    raw_id = business_id.strip()
    if event_type == "INBOUND":
        payment_id = int(raw_id) if raw_id.isdigit() else db.scalar(
            select(InboundPayment.id).where(InboundPayment.transaction_id == raw_id)
        )
        if payment_id is None:
            raise LookupError(f"inbound payment {raw_id} not found")
        result = assess_inbound(db, int(payment_id), persist)
        result["event_type"] = "INBOUND"
        result["business_id"] = result["transaction_id"]
        return result
    payout_id = int(raw_id) if raw_id.isdigit() else db.scalar(
        select(Payout.id).where(Payout.payout_id == raw_id)
    )
    if payout_id is None:
        raise LookupError(f"payout {raw_id} not found")
    result = assess_payout(db, int(payout_id), persist)
    result["event_type"] = "PAYOUT"
    return result

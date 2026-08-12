from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text


INBOUND_FEATURE_COLUMNS = [
    "amount_usd",
    "amount_log",
    "expected_volume_ratio",
    "customer_age_days",
    "customer_risk_tier",
    "partner_risk_tier",
    "payer_risk_score",
    "payer_external_risk_flag",
    "payer_sanctions_flag",
    "payer_name_match_score",
    "order_risk_score",
    "order_is_new_buyer",
    "is_third_party_payment",
    "is_first_payer",
    "payer_buyer_country_mismatch",
    "payer_buyer_identity_mismatch",
    "origin_buyer_country_mismatch",
    "purpose_mismatch",
    "currency_unexpected",
    "allocation_amount_ratio",
    "max_doc_tamper_score",
    "failed_doc_count",
    "duplicate_doc_hash_count",
    "recent_auth_risk_max_7d",
    "recent_auth_failed_count_7d",
    "recent_new_device_count_30d",
    "prior_inbound_count_24h",
    "prior_inbound_amount_usd_24h",
    "prior_distinct_payers_30d",
    "prior_rejected_count_30d",
    "payer_prior_customer_count",
    "shared_device_customer_count",
    "store_auth_failed",
    "shared_store_credential_count",
    "store_va_link_missing",
    "declaration_customer_count",
    "business_ecommerce_flag",
    "business_b2b_flag",
    "business_service_flag",
    "rail_swift_flag",
    "rail_local_flag",
]


INBOUND_DATASET_SQL = """
SELECT
    ip.id AS inbound_payment_id,
    ip.transaction_id,
    ip.partner_id,
    ip.customer_id,
    c.client_id,
    c.legal_name AS customer_name,
    p.partner_name,
    ip.received_at,
    ip.inbound_status,
    ip.currency,
    ip.origin_country,
    ip.rail,
    ip.business_type,
    ip.amount_usd,
    LN(1 + ip.amount_usd) AS amount_log,
    COALESCE(ip.amount_usd / NULLIF(c.expected_monthly_volume_usd, 0), 0) AS expected_volume_ratio,
    GREATEST(DATEDIFF(ip.received_at, c.incorporation_date), 0) AS customer_age_days,
    CASE c.risk_tier WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 1 ELSE 0 END AS customer_risk_tier,
    CASE p.risk_tier WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 1 ELSE 0 END AS partner_risk_tier,
    cp.risk_score AS payer_risk_score,
    (cp.external_risk_label IS NOT NULL) AS payer_external_risk_flag,
    (cp.sanctions_status <> 'CLEAR') AS payer_sanctions_flag,
    COALESCE(pba.name_match_score, 0) AS payer_name_match_score,
    COALESCE(tord.risk_score, 0) AS order_risk_score,
    COALESCE(tord.is_new_buyer, 0) AS order_is_new_buyer,
    ip.is_third_party_payment,
    (ip.third_party_reason IS NOT NULL) AS third_party_reason_valid,
    ip.is_first_payer,
    (cp.country_code <> tord.buyer_country_snapshot) AS payer_buyer_country_mismatch,
    (ip.payer_counterparty_id <> tord.buyer_counterparty_id) AS payer_buyer_identity_mismatch,
    (ip.origin_country <> tord.buyer_country_snapshot) AS origin_buyer_country_mismatch,
    (va.purpose_code <> CASE c.declared_business_type
        WHEN 'ECOMMERCE_PLATFORM' THEN '01'
        WHEN 'SELF_STATION' THEN '01'
        WHEN 'B2B_COMMERCE' THEN '02'
        WHEN 'SERVICE_TRADE' THEN '06'
        ELSE va.purpose_code END) AS purpose_mismatch,
    (JSON_CONTAINS(c.expected_currencies, JSON_QUOTE(ip.currency)) = 0) AS currency_unexpected,
    COALESCE(ioa.allocated_amount / NULLIF(tord.total_amount, 0), 0) AS allocation_amount_ratio,
    COALESCE((SELECT MAX(td.tamper_score) FROM trade_documents td WHERE td.trade_order_id = tord.id), 0) AS max_doc_tamper_score,
    COALESCE((SELECT COUNT(*) FROM trade_documents td WHERE td.trade_order_id = tord.id AND td.verification_status = 'FAILED'), 0) AS failed_doc_count,
    COALESCE((SELECT MAX((SELECT COUNT(DISTINCT td2.customer_id) FROM trade_documents td2 WHERE td2.file_hash = td.file_hash)) FROM trade_documents td WHERE td.trade_order_id = tord.id), 0) AS duplicate_doc_hash_count,
    COALESCE((SELECT MAX(ae.risk_score) FROM auth_events ae WHERE ae.customer_id = ip.customer_id AND ae.event_time < ip.received_at AND ae.event_time >= ip.received_at - INTERVAL 7 DAY), 0) AS recent_auth_risk_max_7d,
    COALESCE((SELECT COUNT(*) FROM auth_events ae WHERE ae.customer_id = ip.customer_id AND ae.result <> 'SUCCESS' AND ae.event_time < ip.received_at AND ae.event_time >= ip.received_at - INTERVAL 7 DAY), 0) AS recent_auth_failed_count_7d,
    COALESCE((SELECT COUNT(*) FROM auth_events ae WHERE ae.customer_id = ip.customer_id AND ae.is_new_device = 1 AND ae.event_time < ip.received_at AND ae.event_time >= ip.received_at - INTERVAL 30 DAY), 0) AS recent_new_device_count_30d,
    COALESCE((SELECT COUNT(*) FROM inbound_payments ip2 WHERE ip2.customer_id = ip.customer_id AND ip2.received_at < ip.received_at AND ip2.received_at >= ip.received_at - INTERVAL 24 HOUR), 0) AS prior_inbound_count_24h,
    COALESCE((SELECT SUM(ip2.amount_usd) FROM inbound_payments ip2 WHERE ip2.customer_id = ip.customer_id AND ip2.received_at < ip.received_at AND ip2.received_at >= ip.received_at - INTERVAL 24 HOUR), 0) AS prior_inbound_amount_usd_24h,
    COALESCE((SELECT COUNT(DISTINCT ip2.payer_counterparty_id) FROM inbound_payments ip2 WHERE ip2.customer_id = ip.customer_id AND ip2.received_at < ip.received_at AND ip2.received_at >= ip.received_at - INTERVAL 30 DAY), 0) AS prior_distinct_payers_30d,
    COALESCE((SELECT COUNT(*) FROM inbound_payments ip2 WHERE ip2.customer_id = ip.customer_id AND ip2.inbound_status IN ('REJECTED','REFUNDED') AND ip2.received_at < ip.received_at AND ip2.received_at >= ip.received_at - INTERVAL 30 DAY), 0) AS prior_rejected_count_30d,
    COALESCE((SELECT COUNT(DISTINCT ip2.customer_id) FROM inbound_payments ip2 WHERE ip2.payer_counterparty_id = ip.payer_counterparty_id AND ip2.received_at < ip.received_at), 0) AS payer_prior_customer_count,
    COALESCE((SELECT MAX(shared.cnt) FROM (
        SELECT ae0.customer_id, d0.fingerprint_hash, COUNT(DISTINCT ae1.customer_id) AS cnt
        FROM auth_events ae0
        JOIN devices d0 ON d0.id = ae0.device_id
        JOIN devices d1 ON d1.fingerprint_hash = d0.fingerprint_hash
        JOIN auth_events ae1 ON ae1.device_id = d1.id
        GROUP BY ae0.customer_id, d0.fingerprint_hash
    ) shared WHERE shared.customer_id = ip.customer_id), 1) AS shared_device_customer_count,
    (COALESCE(s.auth_status, 'SUCCESS') <> 'SUCCESS' OR (s.auth_expires_at IS NOT NULL AND s.auth_expires_at < ip.received_at)) AS store_auth_failed,
    COALESCE((SELECT COUNT(DISTINCT s2.customer_id) FROM stores s2 WHERE s.auth_credential_fingerprint IS NOT NULL AND s2.auth_credential_fingerprint = s.auth_credential_fingerprint), 0) AS shared_store_credential_count,
    (ip.store_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM store_virtual_account_links sval WHERE sval.store_id = ip.store_id AND sval.virtual_account_id = ip.virtual_account_id AND sval.status = 'ACTIVE')) AS store_va_link_missing,
    COALESCE((SELECT COUNT(DISTINCT t2.customer_id) FROM trade_orders t2 WHERE tord.declaration_no IS NOT NULL AND t2.declaration_no = tord.declaration_no), 0) AS declaration_customer_count,
    (ip.business_type = 'ECOMMERCE_PLATFORM') AS business_ecommerce_flag,
    (ip.business_type = 'B2B_COMMERCE') AS business_b2b_flag,
    (ip.business_type = 'SERVICE_TRADE') AS business_service_flag,
    (ip.rail = 'SWIFT') AS rail_swift_flag,
    (ip.rail = 'LOCAL') AS rail_local_flag,
    CASE
      WHEN ip.inbound_status IN ('REJECTED','REFUNDED') THEN 1
      WHEN ip.inbound_status = 'APPROVED' THEN 0
      ELSE NULL
    END AS label
FROM inbound_payments ip
JOIN customers c ON c.id = ip.customer_id
JOIN partners p ON p.id = ip.partner_id
JOIN virtual_accounts va ON va.id = ip.virtual_account_id
JOIN counterparties cp ON cp.id = ip.payer_counterparty_id
LEFT JOIN bank_accounts pba ON pba.id = ip.payer_bank_account_id
LEFT JOIN stores s ON s.id = ip.store_id
LEFT JOIN inbound_order_allocations ioa ON ioa.inbound_payment_id = ip.id
LEFT JOIN trade_orders tord ON tord.id = ioa.trade_order_id
ORDER BY ip.received_at, ip.id
"""


def load_inbound_dataset(engine: Engine, labeled_only: bool = False) -> pd.DataFrame:
    frame = pd.read_sql(text(INBOUND_DATASET_SQL), engine)
    for column in INBOUND_FEATURE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    if labeled_only:
        frame = frame[frame["label"].notna()].copy()
        frame["label"] = frame["label"].astype(int)
    return frame


def feature_record(engine: Engine, inbound_payment_id: int) -> dict[str, Any]:
    frame = load_inbound_dataset(engine, labeled_only=False)
    selected = frame.loc[frame["inbound_payment_id"] == inbound_payment_id]
    if selected.empty:
        raise LookupError(f"inbound payment {inbound_payment_id} not found")
    record = selected.iloc[0].to_dict()
    for key, value in list(record.items()):
        if isinstance(value, np.generic):
            record[key] = value.item()
        elif pd.isna(value):
            record[key] = None
    record["platform_business_flag"] = record.get("business_ecommerce_flag", 0)
    return record


PAYOUT_FEATURE_SQL = """
SELECT
  po.id AS payout_db_id,
  po.payout_id,
  po.customer_id,
  po.seconds_since_inbound,
  po.is_new_beneficiary,
  po.recent_security_event_flag,
  po.balance_drain_ratio,
  po.pay_amount * CASE po.pay_currency
    WHEN 'USD' THEN 1 WHEN 'EUR' THEN 1.09 WHEN 'GBP' THEN 1.28
    WHEN 'JPY' THEN 0.0068 WHEN 'SGD' THEN 0.75 WHEN 'CNY' THEN 0.139 ELSE 1 END AS pay_amount_usd,
  (ba.ownership_check_result NOT IN ('MATCH','CLOSE_MATCH')) AS beneficiary_ownership_mismatch,
  COALESCE((SELECT COUNT(DISTINCT po2.customer_id) FROM payouts po2 WHERE po2.beneficiary_bank_account_id = po.beneficiary_bank_account_id AND po2.requested_at < po.requested_at), 0) AS beneficiary_customer_count,
  0 AS beneficiary_changed_24h,
  0 AS out_of_band_verified,
  COALESCE((SELECT COUNT(*) FROM payouts po2 WHERE po2.customer_id = po.customer_id AND po2.status = 'FAILED' AND po2.requested_at < po.requested_at AND po2.requested_at >= po.requested_at - INTERVAL 1 HOUR), 0) AS failed_payout_count_1h,
  (ba.bank_country IN ('IR','KP','SY')) AS high_risk_corridor_flag
FROM payouts po
JOIN bank_accounts ba ON ba.id = po.beneficiary_bank_account_id
WHERE po.id = :payout_id
"""


def payout_feature_record(engine: Engine, payout_id: int) -> dict[str, Any]:
    frame = pd.read_sql(text(PAYOUT_FEATURE_SQL), engine, params={"payout_id": payout_id})
    if frame.empty:
        raise LookupError(f"payout {payout_id} not found")
    return frame.iloc[0].fillna(0).to_dict()

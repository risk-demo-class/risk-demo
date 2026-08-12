-- Example feature queries for MySQL 8.0.
-- Composite indexes in schema.sql are designed to support these access paths.

USE `pingpong`;

-- 1. Per-inbound 24-hour customer velocity.
SELECT
    p1.id AS inbound_payment_id,
    p1.customer_id,
    p1.received_at,
    COUNT(p2.id) AS inbound_count_24h,
    SUM(p2.amount_usd) AS inbound_amount_usd_24h,
    COUNT(DISTINCT p2.payer_counterparty_id) AS payer_count_24h
FROM inbound_payments p1
JOIN inbound_payments p2
  ON p2.customer_id = p1.customer_id
 AND p2.received_at BETWEEN p1.received_at - INTERVAL 24 HOUR AND p1.received_at
GROUP BY p1.id, p1.customer_id, p1.received_at;

-- 2. Rapid payout after an approved inbound payment.
SELECT
    po.id AS payout_id,
    po.customer_id,
    ip.transaction_id,
    po.payout_type,
    po.pay_amount,
    po.pay_currency,
    TIMESTAMPDIFF(SECOND, ip.available_at, po.requested_at) AS seconds_after_available,
    po.balance_drain_ratio,
    po.is_new_beneficiary,
    po.recent_security_event_flag,
    po.risk_score
FROM payouts po
JOIN inbound_payments ip ON ip.id = po.source_inbound_payment_id
WHERE ip.available_at IS NOT NULL
  AND po.requested_at <= ip.available_at + INTERVAL 24 HOUR
ORDER BY seconds_after_available;

-- 3. Shared device fingerprints across customers (graph seed feature).
SELECT
    d.fingerprint_hash,
    COUNT(DISTINCT ae.customer_id) AS linked_customer_count,
    COUNT(*) AS auth_event_count,
    MAX(ae.risk_score) AS max_auth_risk_score,
    MIN(ae.event_time) AS first_event_at,
    MAX(ae.event_time) AS last_event_at
FROM auth_events ae
JOIN devices d ON d.id = ae.device_id
GROUP BY d.fingerprint_hash
HAVING COUNT(DISTINCT ae.customer_id) > 1
ORDER BY linked_customer_count DESC, auth_event_count DESC;

-- 4. Reused trade-document hashes across different customers.
SELECT
    td.file_hash,
    COUNT(*) AS document_count,
    COUNT(DISTINCT td.customer_id) AS customer_count,
    COUNT(DISTINCT td.trade_order_id) AS order_count,
    MAX(td.tamper_score) AS max_tamper_score
FROM trade_documents td
GROUP BY td.file_hash
HAVING COUNT(DISTINCT td.customer_id) > 1
ORDER BY customer_count DESC, document_count DESC;

-- 5. Partner portfolio quality by business date.
SELECT
    ip.partner_id,
    ip.received_date,
    COUNT(*) AS inbound_count,
    SUM(ip.amount_usd) AS amount_usd,
    AVG(ip.risk_score) AS avg_risk_score,
    SUM(ip.inbound_status = 'APPROVED') / COUNT(*) AS approved_rate,
    SUM(ip.inbound_status = 'DECLINED') / COUNT(*) AS declined_rate,
    SUM(ip.inbound_status IN ('REJECTED', 'REFUNDED')) / COUNT(*) AS reject_refund_rate,
    SUM(ip.is_third_party_payment = 1) / COUNT(*) AS third_party_rate
FROM inbound_payments ip
GROUP BY ip.partner_id, ip.received_date
ORDER BY ip.received_date DESC, ip.partner_id;

-- 6. Customer 30-day payer concentration and first-payer ratio.
WITH customer_payer AS (
    SELECT
        customer_id,
        payer_counterparty_id,
        SUM(amount_usd) AS payer_amount_usd,
        COUNT(*) AS payer_payment_count
    FROM inbound_payments
    WHERE received_at >= UTC_TIMESTAMP(6) - INTERVAL 30 DAY
    GROUP BY customer_id, payer_counterparty_id
),
customer_total AS (
    SELECT customer_id, SUM(payer_amount_usd) AS total_amount_usd
    FROM customer_payer
    GROUP BY customer_id
)
SELECT
    cp.customer_id,
    COUNT(*) AS distinct_payers,
    MAX(cp.payer_amount_usd) / NULLIF(ct.total_amount_usd, 0) AS top1_payer_amount_ratio,
    ct.total_amount_usd
FROM customer_payer cp
JOIN customer_total ct ON ct.customer_id = cp.customer_id
GROUP BY cp.customer_id, ct.total_amount_usd;

-- 7. State and ledger reconciliation for approved inbound payments.
SELECT
    ip.transaction_id,
    ip.customer_id,
    ip.currency,
    ip.amount,
    ip.inbound_status,
    SUM(le.direction = 'CR' AND la.account_type = 'TEMP_ACCOUNT') AS temp_credit_count,
    SUM(le.direction = 'DR' AND la.account_type = 'TEMP_ACCOUNT') AS temp_debit_count,
    SUM(le.direction = 'CR' AND la.account_type = 'AVAIL_ACCOUNT') AS avail_credit_count
FROM inbound_payments ip
LEFT JOIN ledger_entries le ON le.fund_source_transaction_id = ip.id
LEFT JOIN ledger_accounts la ON la.id = le.ledger_account_id
WHERE ip.inbound_status = 'APPROVED'
GROUP BY ip.id, ip.transaction_id, ip.customer_id, ip.currency, ip.amount, ip.inbound_status
HAVING temp_credit_count <> 1 OR temp_debit_count <> 1 OR avail_credit_count < 1;

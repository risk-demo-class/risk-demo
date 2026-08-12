-- Generated from models.py; do not edit by hand.

-- Target: MySQL 8.0+

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `pingpong` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

USE `pingpong`;

SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE counterparties (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	counterparty_ref VARCHAR(64) NOT NULL,
	counterparty_type VARCHAR(24) NOT NULL,
	legal_name VARCHAR(255) NOT NULL,
	normalized_name VARCHAR(255) NOT NULL,
	country_code VARCHAR(2) NOT NULL,
	registration_or_id_hash VARCHAR(64),
	industry_code VARCHAR(32),
	sanctions_status VARCHAR(16) NOT NULL,
	external_risk_label VARCHAR(32),
	risk_score NUMERIC(8, 4) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_counterparties PRIMARY KEY (id),
	CONSTRAINT uq_counterparties_counterparty_ref UNIQUE (counterparty_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_counterparty_label_score ON counterparties (external_risk_label, risk_score);

CREATE INDEX ix_counterparty_name_country ON counterparties (normalized_name, country_code);

CREATE INDEX ix_counterparty_reg_hash ON counterparties (registration_or_id_hash);

CREATE TABLE devices (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	device_id VARCHAR(64) NOT NULL,
	fingerprint_hash VARCHAR(64) NOT NULL,
	device_type VARCHAR(16) NOT NULL,
	os_name VARCHAR(32),
	browser_name VARCHAR(32),
	is_emulator BOOL NOT NULL,
	is_rooted BOOL NOT NULL,
	first_seen_at DATETIME(6) NOT NULL,
	last_seen_at DATETIME(6) NOT NULL,
	risk_score NUMERIC(8, 4) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_devices PRIMARY KEY (id),
	CONSTRAINT uq_devices_device_id UNIQUE (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_devices_fingerprint_hash ON devices (fingerprint_hash);

CREATE TABLE entity_relations (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	src_entity_type VARCHAR(32) NOT NULL,
	src_entity_id VARCHAR(64) NOT NULL,
	dst_entity_type VARCHAR(32) NOT NULL,
	dst_entity_id VARCHAR(64) NOT NULL,
	relation_type VARCHAR(32) NOT NULL,
	valid_from DATETIME(6) NOT NULL,
	valid_to DATETIME(6),
	source VARCHAR(32) NOT NULL,
	confidence NUMERIC(8, 4) NOT NULL,
	attributes JSON,
	CONSTRAINT pk_entity_relations PRIMARY KEY (id),
	CONSTRAINT uq_entity_relations_src_entity_type UNIQUE (src_entity_type, src_entity_id, dst_entity_type, dst_entity_id, relation_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_relation_dst ON entity_relations (dst_entity_type, dst_entity_id, relation_type);

CREATE INDEX ix_relation_src ON entity_relations (src_entity_type, src_entity_id, relation_type);

CREATE INDEX ix_relation_type_time ON entity_relations (relation_type, valid_from);

CREATE TABLE partners (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	partner_code VARCHAR(32) NOT NULL,
	partner_name VARCHAR(128) NOT NULL,
	partner_type VARCHAR(32) NOT NULL,
	country_code VARCHAR(2) NOT NULL,
	risk_tier VARCHAR(16) NOT NULL,
	status VARCHAR(16) NOT NULL,
	api_enabled BOOL NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_partners PRIMARY KEY (id),
	CONSTRAINT ck_partners_risk_tier CHECK (risk_tier IN ('LOW','MEDIUM','HIGH')),
	CONSTRAINT uq_partners_partner_code UNIQUE (partner_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_partners_type_status ON partners (partner_type, status);

CREATE TABLE persons (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	person_ref VARCHAR(64) NOT NULL,
	full_name VARCHAR(255) NOT NULL,
	full_name_en VARCHAR(255),
	normalized_name VARCHAR(255) NOT NULL,
	date_of_birth DATE,
	nationality VARCHAR(2),
	residence_country VARCHAR(2),
	id_type VARCHAR(32),
	id_country VARCHAR(2),
	id_number_hash VARCHAR(64),
	phone_hash VARCHAR(64),
	email_hash VARCHAR(64),
	pep_status VARCHAR(16) NOT NULL,
	sanctions_status VARCHAR(16) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_persons PRIMARY KEY (id),
	CONSTRAINT uq_persons_person_ref UNIQUE (person_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_persons_email_hash ON persons (email_hash);

CREATE INDEX ix_persons_id_number_hash ON persons (id_number_hash);

CREATE INDEX ix_persons_name_dob ON persons (normalized_name, date_of_birth);

CREATE INDEX ix_persons_phone_hash ON persons (phone_hash);

CREATE INDEX ix_persons_screening ON persons (sanctions_status, pep_status);

CREATE TABLE risk_blacklist (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	blacklist_id VARCHAR(64) NOT NULL,
	entity_type VARCHAR(32) NOT NULL,
	entity_value VARCHAR(255) NOT NULL,
	normalized_value VARCHAR(255) NOT NULL,
	display_name VARCHAR(255),
	reason_code VARCHAR(48) NOT NULL,
	reason_detail VARCHAR(512),
	severity VARCHAR(16) NOT NULL,
	source VARCHAR(24) NOT NULL,
	source_refs JSON,
	is_active BOOL NOT NULL,
	effective_from DATETIME(6) NOT NULL,
	expires_at DATETIME(6),
	hit_count BIGINT NOT NULL,
	last_hit_at DATETIME(6),
	created_by VARCHAR(64) NOT NULL,
	removed_at DATETIME(6),
	removed_by VARCHAR(64),
	removed_reason VARCHAR(255),
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_risk_blacklist PRIMARY KEY (id),
	CONSTRAINT uq_blacklist_entity_value UNIQUE (entity_type, normalized_value),
	CONSTRAINT ck_risk_blacklist_entity_type CHECK (entity_type IN ('CUSTOMER','COUNTERPARTY','BANK_ACCOUNT','VIRTUAL_ACCOUNT','DEVICE','DOCUMENT_HASH','COUNTRY')),
	CONSTRAINT ck_risk_blacklist_severity CHECK (severity IN ('MEDIUM','HIGH','CRITICAL')),
	CONSTRAINT ck_risk_blacklist_source CHECK (source IN ('MANUAL','CASE','SCREENING','EXTERNAL')),
	CONSTRAINT ck_risk_blacklist_hit_count_non_negative CHECK (hit_count >= 0),
	CONSTRAINT uq_risk_blacklist_blacklist_id UNIQUE (blacklist_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_blacklist_active_lookup ON risk_blacklist (entity_type, normalized_value, is_active);

CREATE INDEX ix_blacklist_reason_created ON risk_blacklist (reason_code, created_at);

CREATE INDEX ix_blacklist_status_expiry ON risk_blacklist (is_active, expires_at, severity);

CREATE TABLE risk_cases (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	case_id VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED,
	case_type VARCHAR(32) NOT NULL,
	priority VARCHAR(8) NOT NULL,
	status VARCHAR(24) NOT NULL,
	title VARCHAR(255) NOT NULL,
	opened_at DATETIME(6) NOT NULL,
	due_at DATETIME(6),
	closed_at DATETIME(6),
	assignee VARCHAR(64),
	disposition VARCHAR(32),
	label_confidence NUMERIC(8, 4),
	loss_amount_usd NUMERIC(20, 4) NOT NULL,
	recovered_amount_usd NUMERIC(20, 4) NOT NULL,
	summary TEXT,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_risk_cases PRIMARY KEY (id),
	CONSTRAINT uq_risk_cases_case_id UNIQUE (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_case_customer_status ON risk_cases (customer_id, status);

CREATE INDEX ix_case_disposition ON risk_cases (disposition, closed_at);

CREATE INDEX ix_case_partner_priority ON risk_cases (partner_id, priority, opened_at);

CREATE TABLE risk_rules (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	rule_id VARCHAR(32) NOT NULL,
	rule_name VARCHAR(128) NOT NULL,
	stage VARCHAR(24) NOT NULL,
	category VARCHAR(48) NOT NULL,
	fraud_scenario VARCHAR(255) NOT NULL,
	rule_condition JSON NOT NULL,
	severity VARCHAR(16) NOT NULL,
	risk_score INTEGER NOT NULL,
	action VARCHAR(24) NOT NULL,
	is_veto BOOL NOT NULL,
	priority INTEGER NOT NULL,
	is_enabled BOOL NOT NULL,
	version INTEGER NOT NULL,
	source_refs JSON,
	effective_from DATETIME(6) NOT NULL,
	effective_to DATETIME(6),
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_risk_rules PRIMARY KEY (id),
	CONSTRAINT ck_risk_rules_score_range CHECK (risk_score BETWEEN 0 AND 100),
	CONSTRAINT uq_risk_rules_rule_id UNIQUE (rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_risk_rule_category_severity ON risk_rules (category, severity);

CREATE INDEX ix_risk_rule_stage_enabled ON risk_rules (stage, is_enabled, priority);

CREATE TABLE case_entities (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	risk_case_id BIGINT UNSIGNED NOT NULL,
	entity_type VARCHAR(32) NOT NULL,
	entity_id VARCHAR(64) NOT NULL,
	relation_type VARCHAR(32) NOT NULL,
	added_at DATETIME(6) NOT NULL,
	evidence JSON,
	CONSTRAINT pk_case_entities PRIMARY KEY (id),
	CONSTRAINT uq_case_entities_risk_case_id UNIQUE (risk_case_id, entity_type, entity_id, relation_type),
	CONSTRAINT fk_case_entities_risk_case_id_risk_cases FOREIGN KEY(risk_case_id) REFERENCES risk_cases (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_case_entity_lookup ON case_entities (entity_type, entity_id);

CREATE TABLE customers (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	client_id VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_location VARCHAR(2) NOT NULL,
	customer_type VARCHAR(16) NOT NULL,
	legal_name VARCHAR(255) NOT NULL,
	legal_name_en VARCHAR(255),
	normalized_name VARCHAR(255) NOT NULL,
	registration_number_hash VARCHAR(64) NOT NULL,
	incorporation_date DATE,
	company_url VARCHAR(512),
	declared_business_type VARCHAR(32) NOT NULL,
	declared_industry_code VARCHAR(32),
	export_country_list JSON,
	expected_currencies JSON,
	expected_monthly_volume_usd NUMERIC(20, 4),
	expected_monthly_count INTEGER,
	kyc_status VARCHAR(16) NOT NULL,
	risk_tier VARCHAR(16) NOT NULL,
	account_status VARCHAR(16) NOT NULL,
	first_approved_at DATETIME(6),
	last_reviewed_at DATETIME(6),
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_customers PRIMARY KEY (id),
	CONSTRAINT uq_customers_partner_id UNIQUE (partner_id, registration_number_hash),
	CONSTRAINT ck_customers_customer_type CHECK (customer_type IN ('ENTERPRISE','INDIVIDUAL')),
	CONSTRAINT ck_customers_kyc_status CHECK (kyc_status IN ('PENDING','APPROVED','DECLINED')),
	CONSTRAINT uq_customers_client_id UNIQUE (client_id),
	CONSTRAINT fk_customers_partner_id_partners FOREIGN KEY(partner_id) REFERENCES partners (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_customers_business_type ON customers (declared_business_type);

CREATE INDEX ix_customers_partner_kyc ON customers (partner_id, kyc_status);

CREATE INDEX ix_customers_reg_hash ON customers (registration_number_hash);

CREATE INDEX ix_customers_risk_status ON customers (risk_tier, account_status);

CREATE TABLE auth_events (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	event_id VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	person_id BIGINT UNSIGNED,
	device_id BIGINT UNSIGNED,
	event_type VARCHAR(48) NOT NULL,
	event_time DATETIME(6) NOT NULL,
	event_date DATE GENERATED ALWAYS AS (DATE(event_time)) STORED NOT NULL,
	result VARCHAR(16) NOT NULL,
	session_id VARCHAR(64),
	ip_address VARCHAR(45),
	ip_country VARCHAR(2),
	asn INTEGER,
	vpn_proxy_tor_flag BOOL NOT NULL,
	is_new_device BOOL NOT NULL,
	risk_score NUMERIC(8, 4) NOT NULL,
	raw_payload JSON,
	CONSTRAINT pk_auth_events PRIMARY KEY (id),
	CONSTRAINT uq_auth_events_event_id UNIQUE (event_id),
	CONSTRAINT fk_auth_events_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
	CONSTRAINT fk_auth_events_person_id_persons FOREIGN KEY(person_id) REFERENCES persons (id) ON DELETE SET NULL,
	CONSTRAINT fk_auth_events_device_id_devices FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_auth_customer_time ON auth_events (customer_id, event_time);

CREATE INDEX ix_auth_device_time ON auth_events (device_id, event_time);

CREATE INDEX ix_auth_partner_date ON auth_events (partner_id, event_date);

CREATE INDEX ix_auth_type_time ON auth_events (event_type, event_time);

CREATE TABLE bank_accounts (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	account_ref VARCHAR(64) NOT NULL,
	owner_type VARCHAR(24) NOT NULL,
	customer_id BIGINT UNSIGNED,
	counterparty_id BIGINT UNSIGNED,
	holder_name VARCHAR(255) NOT NULL,
	normalized_holder_name VARCHAR(255) NOT NULL,
	holder_type VARCHAR(16) NOT NULL,
	bank_name VARCHAR(255) NOT NULL,
	bank_country VARCHAR(2) NOT NULL,
	currency VARCHAR(3),
	account_number_token VARCHAR(128) NOT NULL,
	account_fingerprint VARCHAR(64) NOT NULL,
	ownership_check_result VARCHAR(16) NOT NULL,
	name_match_score NUMERIC(8, 4),
	status VARCHAR(16) NOT NULL,
	first_used_at DATETIME(6),
	risk_score NUMERIC(8, 4) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_bank_accounts PRIMARY KEY (id),
	CONSTRAINT ck_bank_accounts_single_owner CHECK ((customer_id IS NOT NULL) <> (counterparty_id IS NOT NULL)),
	CONSTRAINT uq_bank_accounts_account_ref UNIQUE (account_ref),
	CONSTRAINT fk_bank_accounts_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
	CONSTRAINT fk_bank_accounts_counterparty_id_counterparties FOREIGN KEY(counterparty_id) REFERENCES counterparties (id) ON DELETE CASCADE,
	CONSTRAINT uq_bank_accounts_account_number_token UNIQUE (account_number_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_bank_accounts_account_fingerprint ON bank_accounts (account_fingerprint);

CREATE INDEX ix_bank_accounts_counterparty ON bank_accounts (counterparty_id);

CREATE INDEX ix_bank_accounts_country_risk ON bank_accounts (bank_country, risk_score);

CREATE INDEX ix_bank_accounts_customer_status ON bank_accounts (customer_id, status);

CREATE TABLE customer_person_roles (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	customer_id BIGINT UNSIGNED NOT NULL,
	person_id BIGINT UNSIGNED NOT NULL,
	role_type VARCHAR(24) NOT NULL,
	ownership_percent NUMERIC(7, 4),
	control_type VARCHAR(32),
	is_primary BOOL NOT NULL,
	valid_from DATE,
	valid_to DATE,
	source VARCHAR(32) NOT NULL,
	CONSTRAINT pk_customer_person_roles PRIMARY KEY (id),
	CONSTRAINT uq_customer_person_roles_customer_id UNIQUE (customer_id, person_id, role_type),
	CONSTRAINT fk_customer_person_roles_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
	CONSTRAINT fk_customer_person_roles_person_id_persons FOREIGN KEY(person_id) REFERENCES persons (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_customer_person_role_customer ON customer_person_roles (customer_id, role_type);

CREATE INDEX ix_customer_person_role_person ON customer_person_roles (person_id, role_type);

CREATE TABLE ledger_accounts (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	ledger_account_no VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	account_type VARCHAR(16) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	available_balance NUMERIC(20, 4) NOT NULL,
	frozen_balance NUMERIC(20, 4) NOT NULL,
	status VARCHAR(16) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_ledger_accounts PRIMARY KEY (id),
	CONSTRAINT uq_ledger_accounts_customer_id UNIQUE (customer_id, account_type, currency),
	CONSTRAINT uq_ledger_accounts_ledger_account_no UNIQUE (ledger_account_no),
	CONSTRAINT fk_ledger_accounts_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_ledger_account_partner_type ON ledger_accounts (partner_id, account_type);

CREATE TABLE risk_events (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	event_id VARCHAR(64) NOT NULL,
	event_type VARCHAR(96) NOT NULL,
	event_version INTEGER NOT NULL,
	risk_domain VARCHAR(24) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED,
	subject_type VARCHAR(32) NOT NULL,
	subject_id VARCHAR(64) NOT NULL,
	actor_type VARCHAR(24),
	actor_id VARCHAR(64),
	occurred_at DATETIME(6) NOT NULL,
	event_date DATE GENERATED ALWAYS AS (DATE(occurred_at)) STORED NOT NULL,
	received_at DATETIME(6) NOT NULL,
	correlation_id VARCHAR(64),
	causation_id VARCHAR(64),
	idempotency_key VARCHAR(128),
	source_system VARCHAR(48) NOT NULL,
	risk_score NUMERIC(8, 4) NOT NULL,
	labels JSON,
	payload JSON,
	CONSTRAINT pk_risk_events PRIMARY KEY (id),
	CONSTRAINT uq_risk_events_event_id UNIQUE (event_id),
	CONSTRAINT fk_risk_events_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_risk_event_correlation ON risk_events (correlation_id);

CREATE INDEX ix_risk_event_customer_time ON risk_events (customer_id, occurred_at);

CREATE INDEX ix_risk_event_domain_time ON risk_events (risk_domain, occurred_at);

CREATE INDEX ix_risk_event_partner_date ON risk_events (partner_id, event_date);

CREATE INDEX ix_risk_event_subject_time ON risk_events (subject_type, subject_id, occurred_at);

CREATE INDEX ix_risk_event_type_time ON risk_events (event_type, occurred_at);

CREATE TABLE stores (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	store_id VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	platform VARCHAR(32) NOT NULL,
	seller_id VARCHAR(128),
	store_name VARCHAR(255) NOT NULL,
	store_url VARCHAR(512),
	category_code VARCHAR(32),
	auth_type VARCHAR(16),
	auth_status VARCHAR(16) NOT NULL,
	auth_credential_fingerprint VARCHAR(64),
	authorized_at DATETIME(6),
	auth_expires_at DATETIME(6),
	last_order_sync_at DATETIME(6),
	ownership_match_score NUMERIC(8, 4),
	risk_tier VARCHAR(16) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_stores PRIMARY KEY (id),
	CONSTRAINT uq_stores_platform UNIQUE (platform, seller_id),
	CONSTRAINT uq_stores_store_id UNIQUE (store_id),
	CONSTRAINT fk_stores_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_stores_auth_fingerprint ON stores (auth_credential_fingerprint);

CREATE INDEX ix_stores_customer_platform ON stores (customer_id, platform);

CREATE INDEX ix_stores_partner_auth ON stores (partner_id, auth_status);

CREATE TABLE virtual_accounts (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	va_id VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	purpose_code VARCHAR(4) NOT NULL,
	purpose_domain VARCHAR(32) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	bank_country VARCHAR(2) NOT NULL,
	rail VARCHAR(24) NOT NULL,
	account_holder_name VARCHAR(255) NOT NULL,
	account_number_token VARCHAR(128) NOT NULL,
	account_fingerprint VARCHAR(64) NOT NULL,
	status VARCHAR(16) NOT NULL,
	opened_at DATETIME(6) NOT NULL,
	first_credit_at DATETIME(6),
	last_credit_at DATETIME(6),
	risk_tier VARCHAR(16) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_virtual_accounts PRIMARY KEY (id),
	CONSTRAINT uq_virtual_accounts_va_id UNIQUE (va_id),
	CONSTRAINT fk_virtual_accounts_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
	CONSTRAINT uq_virtual_accounts_account_number_token UNIQUE (account_number_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_va_customer_currency ON virtual_accounts (customer_id, currency);

CREATE INDEX ix_va_partner_purpose ON virtual_accounts (partner_id, purpose_code);

CREATE INDEX ix_va_status_country ON virtual_accounts (status, bank_country);

CREATE INDEX ix_virtual_accounts_account_fingerprint ON virtual_accounts (account_fingerprint);

CREATE TABLE inbound_payments (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	transaction_id VARCHAR(64) NOT NULL,
	partner_reference VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	virtual_account_id BIGINT UNSIGNED NOT NULL,
	store_id BIGINT UNSIGNED,
	payer_counterparty_id BIGINT UNSIGNED NOT NULL,
	payer_bank_account_id BIGINT UNSIGNED,
	business_type VARCHAR(32) NOT NULL,
	purpose_code VARCHAR(16) NOT NULL,
	amount NUMERIC(20, 4) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	amount_usd NUMERIC(20, 4) NOT NULL,
	received_at DATETIME(6) NOT NULL,
	received_date DATE GENERATED ALWAYS AS (DATE(received_at)) STORED NOT NULL,
	value_date DATE,
	end_to_end_id VARCHAR(64),
	uetr VARCHAR(64),
	origin_country VARCHAR(2) NOT NULL,
	rail VARCHAR(24) NOT NULL,
	remittance_text VARCHAR(512),
	is_third_party_payment BOOL NOT NULL,
	third_party_reason VARCHAR(32),
	is_first_payer BOOL NOT NULL,
	inbound_status VARCHAR(24) NOT NULL,
	temp_posted_at DATETIME(6),
	available_at DATETIME(6),
	refunded_at DATETIME(6),
	risk_score NUMERIC(8, 4) NOT NULL,
	risk_tier_snapshot VARCHAR(16) NOT NULL,
	data_quality_flags JSON,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_inbound_payments PRIMARY KEY (id),
	CONSTRAINT uq_inbound_payments_partner_id UNIQUE (partner_id, partner_reference),
	CONSTRAINT ck_inbound_payments_positive_amount CHECK (amount > 0),
	CONSTRAINT ck_inbound_payments_positive_amount_usd CHECK (amount_usd > 0),
	CONSTRAINT uq_inbound_payments_transaction_id UNIQUE (transaction_id),
	CONSTRAINT fk_inbound_payments_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
	CONSTRAINT fk_inbound_payments_virtual_account_id_virtual_accounts FOREIGN KEY(virtual_account_id) REFERENCES virtual_accounts (id) ON DELETE RESTRICT,
	CONSTRAINT fk_inbound_payments_store_id_stores FOREIGN KEY(store_id) REFERENCES stores (id) ON DELETE SET NULL,
	CONSTRAINT fk_inbound_payments_payer_counterparty_id_counterparties FOREIGN KEY(payer_counterparty_id) REFERENCES counterparties (id) ON DELETE RESTRICT,
	CONSTRAINT fk_inbound_payments_payer_bank_account_id_bank_accounts FOREIGN KEY(payer_bank_account_id) REFERENCES bank_accounts (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_inbound_business_date ON inbound_payments (business_type, received_date);

CREATE INDEX ix_inbound_customer_status_time ON inbound_payments (customer_id, inbound_status, received_at);

CREATE INDEX ix_inbound_customer_time ON inbound_payments (customer_id, received_at);

CREATE INDEX ix_inbound_origin_date ON inbound_payments (origin_country, received_date);

CREATE INDEX ix_inbound_partner_date ON inbound_payments (partner_id, received_date);

CREATE INDEX ix_inbound_payer_time ON inbound_payments (payer_counterparty_id, received_at);

CREATE INDEX ix_inbound_uetr ON inbound_payments (uetr);

CREATE INDEX ix_inbound_va_time ON inbound_payments (virtual_account_id, received_at);

CREATE TABLE risk_decisions (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	decision_id VARCHAR(64) NOT NULL,
	risk_event_id BIGINT UNSIGNED,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED,
	subject_type VARCHAR(32) NOT NULL,
	subject_id VARCHAR(64) NOT NULL,
	risk_domain VARCHAR(24) NOT NULL,
	decision VARCHAR(24) NOT NULL,
	risk_score NUMERIC(8, 4) NOT NULL,
	rule_hits JSON,
	model_outputs JSON,
	reason_codes JSON,
	engine_version VARCHAR(32) NOT NULL,
	decided_at DATETIME(6) NOT NULL,
	expires_at DATETIME(6),
	manual_override BOOL NOT NULL,
	override_by VARCHAR(64),
	override_reason VARCHAR(255),
	CONSTRAINT pk_risk_decisions PRIMARY KEY (id),
	CONSTRAINT uq_risk_decisions_decision_id UNIQUE (decision_id),
	CONSTRAINT fk_risk_decisions_risk_event_id_risk_events FOREIGN KEY(risk_event_id) REFERENCES risk_events (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_decision_action_time ON risk_decisions (decision, decided_at);

CREATE INDEX ix_decision_customer_time ON risk_decisions (customer_id, decided_at);

CREATE INDEX ix_decision_subject ON risk_decisions (subject_type, subject_id, decided_at);

CREATE TABLE store_virtual_account_links (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	store_id BIGINT UNSIGNED NOT NULL,
	virtual_account_id BIGINT UNSIGNED NOT NULL,
	linked_at DATETIME(6) NOT NULL,
	unlinked_at DATETIME(6),
	status VARCHAR(16) NOT NULL,
	CONSTRAINT pk_store_virtual_account_links PRIMARY KEY (id),
	CONSTRAINT uq_store_virtual_account_links_store_id UNIQUE (store_id, virtual_account_id),
	CONSTRAINT fk_store_virtual_account_links_store_id_stores FOREIGN KEY(store_id) REFERENCES stores (id) ON DELETE CASCADE,
	CONSTRAINT fk_store_virtual_account_links_virtual_account_id_virtua_5276 FOREIGN KEY(virtual_account_id) REFERENCES virtual_accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_store_va_va_status ON store_virtual_account_links (virtual_account_id, status);

CREATE TABLE trade_orders (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	trade_order_no VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	store_id BIGINT UNSIGNED,
	buyer_counterparty_id BIGINT UNSIGNED NOT NULL,
	business_type VARCHAR(32) NOT NULL,
	settlement_type VARCHAR(16) NOT NULL,
	trade_code VARCHAR(16) NOT NULL,
	total_amount NUMERIC(20, 4) NOT NULL,
	reserved_amount NUMERIC(20, 4) NOT NULL,
	approved_amount NUMERIC(20, 4) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	order_time DATETIME(6) NOT NULL,
	order_date DATE GENERATED ALWAYS AS (DATE(order_time)) STORED NOT NULL,
	payment_method VARCHAR(16) NOT NULL,
	trading_terms VARCHAR(16),
	declaration_no VARCHAR(128),
	is_new_buyer BOOL NOT NULL,
	category_code VARCHAR(32),
	consignee_country_code VARCHAR(2),
	buyer_name_snapshot VARCHAR(255) NOT NULL,
	buyer_country_snapshot VARCHAR(2) NOT NULL,
	status VARCHAR(16) NOT NULL,
	risk_score NUMERIC(8, 4) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_trade_orders PRIMARY KEY (id),
	CONSTRAINT uq_trade_orders_partner_id UNIQUE (partner_id, trade_order_no),
	CONSTRAINT ck_trade_orders_positive_total CHECK (total_amount > 0),
	CONSTRAINT ck_trade_orders_nonnegative_reserved CHECK (reserved_amount >= 0),
	CONSTRAINT ck_trade_orders_nonnegative_approved CHECK (approved_amount >= 0),
	CONSTRAINT fk_trade_orders_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
	CONSTRAINT fk_trade_orders_store_id_stores FOREIGN KEY(store_id) REFERENCES stores (id) ON DELETE SET NULL,
	CONSTRAINT fk_trade_orders_buyer_counterparty_id_counterparties FOREIGN KEY(buyer_counterparty_id) REFERENCES counterparties (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_trade_order_business_date ON trade_orders (business_type, order_date);

CREATE INDEX ix_trade_order_buyer_time ON trade_orders (buyer_counterparty_id, order_time);

CREATE INDEX ix_trade_order_customer_time ON trade_orders (customer_id, order_time);

CREATE INDEX ix_trade_order_declaration ON trade_orders (declaration_no);

CREATE TABLE fx_orders (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	fx_order_id VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	sell_currency VARCHAR(3) NOT NULL,
	sell_amount NUMERIC(20, 4) NOT NULL,
	buy_currency VARCHAR(3) NOT NULL,
	buy_amount NUMERIC(20, 4) NOT NULL,
	fx_rate NUMERIC(20, 10) NOT NULL,
	quote_id VARCHAR(64) NOT NULL,
	source_inbound_payment_id BIGINT UNSIGNED,
	status VARCHAR(16) NOT NULL,
	requested_at DATETIME(6) NOT NULL,
	executed_at DATETIME(6),
	risk_score NUMERIC(8, 4) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_fx_orders PRIMARY KEY (id),
	CONSTRAINT ck_fx_orders_positive_amounts CHECK (sell_amount > 0 AND buy_amount > 0),
	CONSTRAINT uq_fx_orders_fx_order_id UNIQUE (fx_order_id),
	CONSTRAINT fk_fx_orders_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
	CONSTRAINT fk_fx_orders_source_inbound_payment_id_inbound_payments FOREIGN KEY(source_inbound_payment_id) REFERENCES inbound_payments (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_fx_customer_time ON fx_orders (customer_id, requested_at);

CREATE INDEX ix_fx_pair_time ON fx_orders (sell_currency, buy_currency, requested_at);

CREATE TABLE inbound_audits (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	audit_id VARCHAR(64) NOT NULL,
	inbound_payment_id BIGINT UNSIGNED NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	attempt_no INTEGER NOT NULL,
	submitted_business_type VARCHAR(32) NOT NULL,
	status VARCHAR(16) NOT NULL,
	reason_code VARCHAR(64),
	fail_reason VARCHAR(255),
	submitted_by_type VARCHAR(16) NOT NULL,
	submitted_by_id VARCHAR(64),
	submitted_at DATETIME(6) NOT NULL,
	completed_at DATETIME(6),
	evidence_snapshot JSON,
	rule_hits JSON,
	decision_score NUMERIC(8, 4) NOT NULL,
	CONSTRAINT pk_inbound_audits PRIMARY KEY (id),
	CONSTRAINT uq_inbound_audits_inbound_payment_id UNIQUE (inbound_payment_id, attempt_no),
	CONSTRAINT uq_inbound_audits_audit_id UNIQUE (audit_id),
	CONSTRAINT fk_inbound_audits_inbound_payment_id_inbound_payments FOREIGN KEY(inbound_payment_id) REFERENCES inbound_payments (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_audit_customer_time ON inbound_audits (customer_id, submitted_at);

CREATE INDEX ix_audit_partner_status_time ON inbound_audits (partner_id, status, submitted_at);

CREATE INDEX ix_audit_reason ON inbound_audits (reason_code);

CREATE TABLE inbound_order_allocations (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	inbound_payment_id BIGINT UNSIGNED NOT NULL,
	trade_order_id BIGINT UNSIGNED NOT NULL,
	allocated_amount NUMERIC(20, 4) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	allocation_status VARCHAR(16) NOT NULL,
	reserved_at DATETIME(6) NOT NULL,
	released_at DATETIME(6),
	CONSTRAINT pk_inbound_order_allocations PRIMARY KEY (id),
	CONSTRAINT uq_inbound_order_allocations_inbound_payment_id UNIQUE (inbound_payment_id, trade_order_id),
	CONSTRAINT ck_inbound_order_allocations_positive_amount CHECK (allocated_amount > 0),
	CONSTRAINT fk_inbound_order_allocations_inbound_payment_id_inbound_payments FOREIGN KEY(inbound_payment_id) REFERENCES inbound_payments (id) ON DELETE CASCADE,
	CONSTRAINT fk_inbound_order_allocations_trade_order_id_trade_orders FOREIGN KEY(trade_order_id) REFERENCES trade_orders (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_allocation_order_status ON inbound_order_allocations (trade_order_id, allocation_status);

CREATE TABLE ledger_entries (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	entry_id VARCHAR(64) NOT NULL,
	entry_group_id VARCHAR(64) NOT NULL,
	ledger_account_id BIGINT UNSIGNED NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	direction VARCHAR(2) NOT NULL,
	amount NUMERIC(20, 4) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	business_type VARCHAR(24) NOT NULL,
	business_ref_type VARCHAR(24) NOT NULL,
	business_ref_id VARCHAR(64) NOT NULL,
	fund_source_transaction_id BIGINT UNSIGNED,
	booked_at DATETIME(6) NOT NULL,
	booked_date DATE GENERATED ALWAYS AS (DATE(booked_at)) STORED NOT NULL,
	balance_after NUMERIC(20, 4) NOT NULL,
	reversal_of_entry_id BIGINT UNSIGNED,
	CONSTRAINT pk_ledger_entries PRIMARY KEY (id),
	CONSTRAINT ck_ledger_entries_direction CHECK (direction IN ('DR','CR')),
	CONSTRAINT ck_ledger_entries_positive_amount CHECK (amount > 0),
	CONSTRAINT uq_ledger_entries_entry_id UNIQUE (entry_id),
	CONSTRAINT fk_ledger_entries_ledger_account_id_ledger_accounts FOREIGN KEY(ledger_account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
	CONSTRAINT fk_ledger_entries_fund_source_transaction_id_inbound_payments FOREIGN KEY(fund_source_transaction_id) REFERENCES inbound_payments (id) ON DELETE SET NULL,
	CONSTRAINT fk_ledger_entries_reversal_of_entry_id_ledger_entries FOREIGN KEY(reversal_of_entry_id) REFERENCES ledger_entries (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_ledger_account_time ON ledger_entries (ledger_account_id, booked_at);

CREATE INDEX ix_ledger_business_ref ON ledger_entries (business_ref_type, business_ref_id);

CREATE INDEX ix_ledger_customer_time ON ledger_entries (customer_id, booked_at);

CREATE INDEX ix_ledger_group ON ledger_entries (entry_group_id);

CREATE INDEX ix_ledger_partner_date ON ledger_entries (partner_id, booked_date);

CREATE TABLE trade_documents (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	document_id VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	trade_order_id BIGINT UNSIGNED,
	document_type VARCHAR(24) NOT NULL,
	document_number VARCHAR(128),
	file_hash VARCHAR(64) NOT NULL,
	issued_at DATE,
	issuer_name VARCHAR(255),
	amount NUMERIC(20, 4),
	currency VARCHAR(3),
	ocr_fields JSON,
	tamper_score NUMERIC(8, 4) NOT NULL,
	verification_status VARCHAR(16) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_trade_documents PRIMARY KEY (id),
	CONSTRAINT uq_trade_documents_document_id UNIQUE (document_id),
	CONSTRAINT fk_trade_documents_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
	CONSTRAINT fk_trade_documents_trade_order_id_trade_orders FOREIGN KEY(trade_order_id) REFERENCES trade_orders (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_trade_doc_customer_hash ON trade_documents (customer_id, file_hash);

CREATE INDEX ix_trade_doc_number_type ON trade_documents (document_number, document_type);

CREATE INDEX ix_trade_doc_order_type ON trade_documents (trade_order_id, document_type);

CREATE INDEX ix_trade_documents_file_hash ON trade_documents (file_hash);

CREATE TABLE payouts (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	payout_id VARCHAR(64) NOT NULL,
	partner_order_id VARCHAR(64) NOT NULL,
	partner_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT UNSIGNED NOT NULL,
	beneficiary_bank_account_id BIGINT UNSIGNED NOT NULL,
	source_inbound_payment_id BIGINT UNSIGNED,
	fx_order_id BIGINT UNSIGNED,
	payout_type VARCHAR(16) NOT NULL,
	pay_currency VARCHAR(3) NOT NULL,
	pay_amount NUMERIC(20, 4) NOT NULL,
	fee_amount NUMERIC(20, 4) NOT NULL,
	target_currency VARCHAR(3) NOT NULL,
	target_amount NUMERIC(20, 4) NOT NULL,
	fx_rate NUMERIC(20, 10),
	payer_name VARCHAR(255),
	charges_indicator VARCHAR(3),
	trade_code VARCHAR(16),
	remark VARCHAR(255),
	requested_at DATETIME(6) NOT NULL,
	requested_date DATE GENERATED ALWAYS AS (DATE(requested_at)) STORED NOT NULL,
	accepted_at DATETIME(6),
	completed_at DATETIME(6),
	status VARCHAR(24) NOT NULL,
	failure_reason VARCHAR(128),
	is_new_beneficiary BOOL NOT NULL,
	recent_security_event_flag BOOL NOT NULL,
	seconds_since_inbound BIGINT,
	balance_drain_ratio NUMERIC(8, 6),
	risk_score NUMERIC(8, 4) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
	CONSTRAINT pk_payouts PRIMARY KEY (id),
	CONSTRAINT uq_payouts_partner_id UNIQUE (partner_id, partner_order_id),
	CONSTRAINT ck_payouts_payout_type CHECK (payout_type IN ('WITHDRAW','PAY')),
	CONSTRAINT ck_payouts_positive_amounts CHECK (pay_amount > 0 AND target_amount > 0),
	CONSTRAINT uq_payouts_payout_id UNIQUE (payout_id),
	CONSTRAINT fk_payouts_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
	CONSTRAINT fk_payouts_beneficiary_bank_account_id_bank_accounts FOREIGN KEY(beneficiary_bank_account_id) REFERENCES bank_accounts (id) ON DELETE RESTRICT,
	CONSTRAINT fk_payouts_source_inbound_payment_id_inbound_payments FOREIGN KEY(source_inbound_payment_id) REFERENCES inbound_payments (id) ON DELETE SET NULL,
	CONSTRAINT fk_payouts_fx_order_id_fx_orders FOREIGN KEY(fx_order_id) REFERENCES fx_orders (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX ix_payout_beneficiary_time ON payouts (beneficiary_bank_account_id, requested_at);

CREATE INDEX ix_payout_customer_status_time ON payouts (customer_id, status, requested_at);

CREATE INDEX ix_payout_customer_time ON payouts (customer_id, requested_at);

CREATE INDEX ix_payout_partner_date ON payouts (partner_id, requested_date);

CREATE INDEX ix_payout_source_inbound ON payouts (source_inbound_payment_id);

SET FOREIGN_KEY_CHECKS = 1;

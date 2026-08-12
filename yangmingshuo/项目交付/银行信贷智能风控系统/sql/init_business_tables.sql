CREATE TABLE user_info (user_id VARCHAR(32) PRIMARY KEY, name VARCHAR(40) NOT NULL, id_card_hash VARCHAR(64) UNIQUE, credit_score INTEGER, register_at DATETIME, kyc_level INTEGER, monthly_income FLOAT);
CREATE TABLE bank_card (card_id VARCHAR(32) PRIMARY KEY, user_id VARCHAR(32) NOT NULL, card_no_hash VARCHAR(64) UNIQUE, bank_code VARCHAR(20), card_type VARCHAR(16), credit_limit FLOAT, FOREIGN KEY(user_id) REFERENCES user_info(user_id));
CREATE TABLE bank_transaction (txn_id VARCHAR(32) PRIMARY KEY, from_card VARCHAR(32), to_card VARCHAR(32), amount FLOAT, channel VARCHAR(20), device_id VARCHAR(32), ip VARCHAR(45), geo VARCHAR(40), created_at DATETIME);
CREATE TABLE loan_application (loan_id VARCHAR(32) PRIMARY KEY, user_id VARCHAR(32), amount FLOAT, term_months INTEGER, purpose VARCHAR(40), monthly_income FLOAT, debt_ratio FLOAT, created_at DATETIME);
CREATE TABLE login_log (login_id VARCHAR(32) PRIMARY KEY, user_id VARCHAR(32), device_id VARCHAR(32), ip VARCHAR(45), geo VARCHAR(40), success BOOLEAN, login_at DATETIME);
CREATE TABLE device_fingerprint (device_id VARCHAR(32) PRIMARY KEY, user_id VARCHAR(32), fingerprint_hash VARCHAR(64), first_seen DATETIME, last_seen DATETIME, os VARCHAR(20), browser VARCHAR(20));
CREATE TABLE ip_geolocation (ip VARCHAR(45) PRIMARY KEY, country VARCHAR(30), province VARCHAR(30), city VARCHAR(30), isp VARCHAR(40), is_proxy BOOLEAN, is_tor BOOLEAN);
CREATE TABLE blacklist_extra (entry_id VARCHAR(32) PRIMARY KEY, type VARCHAR(20), value VARCHAR(80), reason VARCHAR(200), expire_at DATETIME);


CREATE DATABASE IF NOT EXISTS ecs CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE ecs;
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS bank_blacklist_extra, ip_geo_location, device_fingerprint, login_log, loan_application, bank_transaction, bank_card, bank_user_info;
CREATE TABLE bank_user_info (
 user_id VARCHAR(50) PRIMARY KEY, name VARCHAR(80) NOT NULL, id_card_hash VARCHAR(128) NOT NULL,
 credit_score INT DEFAULT 600, register_at DATETIME NOT NULL, kyc_level VARCHAR(20) DEFAULT '标准',
 account_status VARCHAR(20) DEFAULT '正常', usual_city VARCHAR(50) DEFAULT '上海'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE bank_card (
 card_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, card_no_hash VARCHAR(128) NOT NULL,
 bank_code VARCHAR(20) NOT NULL, card_type VARCHAR(20) DEFAULT '借记卡', credit_limit DECIMAL(12,2) DEFAULT 0,
 card_status VARCHAR(20) DEFAULT '正常', open_at DATETIME NOT NULL, INDEX idx_card_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE bank_transaction (
 txn_id VARCHAR(50) PRIMARY KEY, from_card VARCHAR(50) NOT NULL, to_card VARCHAR(50) NOT NULL,
 user_id VARCHAR(50) NOT NULL, amount DECIMAL(14,2) NOT NULL, channel VARCHAR(20) DEFAULT '手机银行',
 device_id VARCHAR(80) NOT NULL, ip VARCHAR(64) NOT NULL, geo VARCHAR(80) NOT NULL,
 txn_status VARCHAR(20) DEFAULT '成功', txn_time DATETIME NOT NULL,
 INDEX idx_txn_user(user_id), INDEX idx_txn_time(txn_time), INDEX idx_txn_device(device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE loan_application (
 loan_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, amount DECIMAL(14,2) NOT NULL,
 term_months INT NOT NULL, purpose VARCHAR(100) NOT NULL, monthly_income DECIMAL(14,2) NOT NULL,
 debt_ratio DECIMAL(6,4) DEFAULT 0, application_channel VARCHAR(20) DEFAULT 'APP',
 application_at DATETIME NOT NULL, application_status VARCHAR(20) DEFAULT '申请中', INDEX idx_loan_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE login_log (
 login_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, device_id VARCHAR(80) NOT NULL,
 ip VARCHAR(64) NOT NULL, geo VARCHAR(80) NOT NULL, success TINYINT DEFAULT 1,
 login_at DATETIME NOT NULL, login_channel VARCHAR(20) DEFAULT 'APP', INDEX idx_login_user(user_id), INDEX idx_login_at(login_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE device_fingerprint (
 fingerprint_id BIGINT AUTO_INCREMENT PRIMARY KEY, device_id VARCHAR(80) NOT NULL, user_id VARCHAR(50) NOT NULL,
 fingerprint_hash VARCHAR(128) NOT NULL, first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL,
 os VARCHAR(40) DEFAULT 'Android', browser VARCHAR(40) DEFAULT 'AppWebView', is_emulator TINYINT DEFAULT 0,
 INDEX idx_device(device_id), INDEX idx_device_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ip_geo_location (
 ip VARCHAR(64) PRIMARY KEY, country VARCHAR(40) DEFAULT '中国', province VARCHAR(40) NOT NULL,
 city VARCHAR(40) NOT NULL, isp VARCHAR(80) DEFAULT '运营商', is_proxy TINYINT DEFAULT 0, is_tor TINYINT DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE bank_blacklist_extra (
 entry_id BIGINT AUTO_INCREMENT PRIMARY KEY, blacklist_type VARCHAR(20) NOT NULL,
 blacklist_value VARCHAR(200) NOT NULL, reason VARCHAR(500), expire_at DATETIME NULL,
 UNIQUE KEY uk_bank_blacklist(blacklist_type, blacklist_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SET FOREIGN_KEY_CHECKS=1;

-- 银行风控业务表：8 张。风控核心 9 张表由 init_risk_tables.sql 创建。
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS blacklist_extra;
DROP TABLE IF EXISTS ip_geo_location;
DROP TABLE IF EXISTS device_fingerprint;
DROP TABLE IF EXISTS login_log;
DROP TABLE IF EXISTS loan_application;
DROP TABLE IF EXISTS bank_transaction;
DROP TABLE IF EXISTS bank_card;
DROP TABLE IF EXISTS user_info;

CREATE TABLE user_info (
    user_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    id_card_hash VARCHAR(128) NOT NULL UNIQUE,
    credit_score INT NOT NULL DEFAULT 600,
    register_at DATETIME NOT NULL,
    kyc_level TINYINT NOT NULL DEFAULT 1,
    home_city VARCHAR(50) NOT NULL,
    monthly_income DECIMAL(14,2) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT '正常',
    INDEX idx_user_credit_score (credit_score),
    INDEX idx_user_register_at (register_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行客户KYC主档';

CREATE TABLE bank_card (
    card_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    card_no_hash VARCHAR(128) NOT NULL UNIQUE,
    bank_code VARCHAR(20) NOT NULL,
    card_type VARCHAR(20) NOT NULL,
    credit_limit DECIMAL(14,2) NOT NULL DEFAULT 0,
    current_balance DECIMAL(14,2) NOT NULL DEFAULT 0,
    opened_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT '正常',
    INDEX idx_card_user (user_id),
    INDEX idx_card_type (card_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡';

CREATE TABLE bank_transaction (
    txn_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    txn_type VARCHAR(20) NOT NULL COMMENT '信用卡/转账',
    from_card VARCHAR(50) NOT NULL,
    to_card VARCHAR(50) DEFAULT NULL,
    amount DECIMAL(14,2) NOT NULL,
    channel VARCHAR(30) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    ip VARCHAR(45) NOT NULL,
    geo VARCHAR(50) NOT NULL,
    merchant_category VARCHAR(50) DEFAULT NULL,
    success TINYINT NOT NULL DEFAULT 1,
    txn_at DATETIME NOT NULL,
    INDEX idx_txn_user_time (user_id, txn_at),
    INDEX idx_txn_type_time (txn_type, txn_at),
    INDEX idx_txn_to_time (to_card, txn_at),
    INDEX idx_txn_device (device_id),
    INDEX idx_txn_ip (ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='信用卡与转账流水';

CREATE TABLE loan_application (
    loan_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    institution_code VARCHAR(30) NOT NULL,
    amount DECIMAL(14,2) NOT NULL,
    term_months INT NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    monthly_income DECIMAL(14,2) NOT NULL,
    debt_ratio DECIMAL(7,4) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    ip VARCHAR(45) NOT NULL,
    apply_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT '待审批',
    INDEX idx_loan_user_time (user_id, apply_at),
    INDEX idx_loan_institution (institution_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请';

CREATE TABLE login_log (
    login_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    ip VARCHAR(45) NOT NULL,
    geo VARCHAR(50) NOT NULL,
    success TINYINT NOT NULL,
    failure_reason VARCHAR(100) DEFAULT NULL,
    login_at DATETIME NOT NULL,
    INDEX idx_login_user_time (user_id, login_at),
    INDEX idx_login_device (device_id),
    INDEX idx_login_ip (ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='网银登录日志';

CREATE TABLE device_fingerprint (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    device_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    fingerprint_hash VARCHAR(128) NOT NULL,
    first_seen DATETIME NOT NULL,
    last_seen DATETIME NOT NULL,
    os VARCHAR(40) NOT NULL,
    browser VARCHAR(40) NOT NULL,
    trusted TINYINT NOT NULL DEFAULT 0,
    UNIQUE KEY uk_device_user (device_id, user_id),
    INDEX idx_device_user (user_id),
    INDEX idx_device_id (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹';

CREATE TABLE ip_geo_location (
    ip VARCHAR(45) PRIMARY KEY,
    country VARCHAR(50) NOT NULL,
    province VARCHAR(50) NOT NULL,
    city VARCHAR(50) NOT NULL,
    isp VARCHAR(80) NOT NULL,
    is_proxy TINYINT NOT NULL DEFAULT 0,
    is_tor TINYINT NOT NULL DEFAULT 0,
    risk_score INT NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL,
    INDEX idx_ip_risk (is_proxy, is_tor, risk_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP地理与代理情报';

CREATE TABLE blacklist_extra (
    entry_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    entry_type VARCHAR(30) NOT NULL COMMENT '设备指纹/IP/银行卡号/身份证号',
    entry_value VARCHAR(200) NOT NULL,
    reason TEXT NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT '内部名单',
    expire_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL,
    UNIQUE KEY uk_extra_type_value (entry_type, entry_value),
    INDEX idx_extra_expire (expire_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='外部银行威胁情报名单';

SET FOREIGN_KEY_CHECKS = 1;

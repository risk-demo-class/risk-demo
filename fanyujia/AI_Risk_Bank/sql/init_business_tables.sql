-- 银行风控业务表：8 张行业表，风控核心表保持独立。
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS bank_user_info (
  user_id VARCHAR(50) PRIMARY KEY, name VARCHAR(50) NOT NULL, id_card_hash VARCHAR(128) NOT NULL UNIQUE,
  credit_score INT NOT NULL DEFAULT 600, register_at DATETIME NOT NULL, kyc_level INT NOT NULL DEFAULT 1,
  monthly_income DECIMAL(14,2) NOT NULL DEFAULT 0, debt_ratio DECIMAL(6,4) NOT NULL DEFAULT 0,
  home_geo VARCHAR(100), status VARCHAR(20) NOT NULL DEFAULT '正常'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bank_card (
  card_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, card_no_hash VARCHAR(128) NOT NULL UNIQUE,
  bank_code VARCHAR(20) NOT NULL, card_type VARCHAR(20) NOT NULL, credit_limit DECIMAL(14,2) NOT NULL DEFAULT 0,
  open_at DATETIME NOT NULL, INDEX idx_card_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bank_transaction (
  txn_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, from_card_id VARCHAR(50), to_card_hash VARCHAR(128),
  payee_id VARCHAR(50), amount DECIMAL(14,2) NOT NULL, transaction_type VARCHAR(20) NOT NULL, channel VARCHAR(30) NOT NULL,
  device_id VARCHAR(80), ip VARCHAR(64), geo VARCHAR(100), txn_time DATETIME NOT NULL, status VARCHAR(20) NOT NULL DEFAULT '成功',
  INDEX idx_txn_user_time(user_id, txn_time), INDEX idx_txn_device(device_id), INDEX idx_txn_ip(ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS loan_application (
  loan_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, amount DECIMAL(14,2) NOT NULL, term_months INT NOT NULL,
  purpose VARCHAR(100) NOT NULL, monthly_income DECIMAL(14,2) NOT NULL, debt_ratio DECIMAL(6,4) NOT NULL,
  device_id VARCHAR(80), ip VARCHAR(64), apply_at DATETIME NOT NULL, status VARCHAR(20) NOT NULL DEFAULT '待审批',
  INDEX idx_loan_user_time(user_id, apply_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS login_log (
  login_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, device_id VARCHAR(80) NOT NULL,
  ip VARCHAR(64) NOT NULL, geo VARCHAR(100), success TINYINT(1) NOT NULL, login_at DATETIME NOT NULL,
  INDEX idx_login_user_time(user_id, login_at), INDEX idx_login_device(device_id), INDEX idx_login_ip(ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS device_fingerprint (
  record_id BIGINT AUTO_INCREMENT PRIMARY KEY, device_id VARCHAR(80) NOT NULL, user_id VARCHAR(50) NOT NULL,
  fingerprint_hash VARCHAR(128) NOT NULL, first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL,
  os VARCHAR(50), browser VARCHAR(50), UNIQUE KEY uq_device_user(device_id,user_id), INDEX idx_device_user(device_id,user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ip_geo_location (
  ip VARCHAR(64) PRIMARY KEY, country VARCHAR(50) NOT NULL DEFAULT '中国', province VARCHAR(50), city VARCHAR(50),
  isp VARCHAR(100), is_proxy TINYINT(1) NOT NULL DEFAULT 0, is_tor TINYINT(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS payee_relationship (
  relation_id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id VARCHAR(50) NOT NULL, payee_id VARCHAR(50) NOT NULL,
  payee_card_hash VARCHAR(128) NOT NULL, first_txn_at DATETIME NOT NULL, last_txn_at DATETIME NOT NULL,
  txn_count INT NOT NULL DEFAULT 0, total_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
  UNIQUE KEY uq_user_payee(user_id,payee_id), INDEX idx_payee_user(user_id,payee_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- 银行风控系统 - 业务表 DDL 初始化脚本
-- 创建 8 张银行业务表 (信用卡/贷款/转账/登录 4 大场景)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 用户与账户基础
-- ============================

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(100) NOT NULL COMMENT '姓名',
  `id_card_hash` varchar(64) DEFAULT NULL COMMENT '身份证号哈希',
  `credit_score` int DEFAULT 600 COMMENT '信用分',
  `register_at` datetime DEFAULT NULL COMMENT '注册时间',
  `kyc_level` int DEFAULT 0 COMMENT 'KYC等级(0-3)',
  `phone` varchar(20) DEFAULT NULL COMMENT '手机号',
  `email` varchar(100) DEFAULT NULL COMMENT '邮箱',
  `status` varchar(20) DEFAULT 'active' COMMENT '状态(active/frozen/closed)',
  PRIMARY KEY (`user_id`),
  KEY `idx_user_info_phone` (`phone`),
  KEY `idx_user_info_status` (`status`),
  KEY `idx_user_info_register_at` (`register_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 银行卡表
CREATE TABLE IF NOT EXISTS `bank_card` (
  `card_id` varchar(50) NOT NULL COMMENT '卡ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `card_no_hash` varchar(64) NOT NULL COMMENT '卡号哈希',
  `bank_code` varchar(20) NOT NULL COMMENT '银行编码',
  `card_type` varchar(20) DEFAULT 'debit' COMMENT '卡类型(debit/credit/savings)',
  `credit_limit` decimal(15,2) DEFAULT NULL COMMENT '信用额度',
  `balance` decimal(15,2) DEFAULT NULL COMMENT '余额',
  `status` varchar(20) DEFAULT 'active' COMMENT '状态',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`card_id`),
  KEY `idx_bank_card_user_id` (`user_id`),
  KEY `idx_bank_card_card_no_hash` (`card_no_hash`),
  KEY `idx_bank_card_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡表';

-- ============================
-- 第二层: 交易与贷款
-- ============================

-- 3. 交易记录表
CREATE TABLE IF NOT EXISTS `transaction` (
  `txn_id` varchar(50) NOT NULL COMMENT '交易ID',
  `from_card` varchar(50) NOT NULL COMMENT '转出卡ID',
  `to_card` varchar(50) DEFAULT NULL COMMENT '转入卡ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `amount` decimal(15,2) NOT NULL COMMENT '金额',
  `channel` varchar(20) DEFAULT 'online' COMMENT '渠道(online/atm/counter/mobile/pos)',
  `txn_type` varchar(20) DEFAULT 'transfer' COMMENT '交易类型(transfer/payment/withdrawal/deposit)',
  `device_id` varchar(64) DEFAULT NULL COMMENT '设备ID',
  `ip` varchar(45) DEFAULT NULL COMMENT 'IP地址',
  `geo` varchar(100) DEFAULT NULL COMMENT '地理位置',
  `status` varchar(20) DEFAULT 'pending' COMMENT '状态(pending/success/failed)',
  `txn_at` datetime DEFAULT NULL COMMENT '交易时间',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`txn_id`),
  KEY `idx_transaction_from_card` (`from_card`),
  KEY `idx_transaction_to_card` (`to_card`),
  KEY `idx_transaction_user_id` (`user_id`),
  KEY `idx_transaction_txn_at` (`txn_at`),
  KEY `idx_transaction_status` (`status`),
  KEY `idx_transaction_device_id` (`device_id`),
  KEY `idx_transaction_ip` (`ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交易记录表';

-- 4. 贷款申请表
CREATE TABLE IF NOT EXISTS `loan_application` (
  `loan_id` varchar(50) NOT NULL COMMENT '贷款申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `amount` decimal(15,2) NOT NULL COMMENT '申请金额',
  `term_months` int NOT NULL COMMENT '期限(月)',
  `purpose` varchar(200) DEFAULT NULL COMMENT '用途',
  `monthly_income` decimal(15,2) DEFAULT NULL COMMENT '月收入',
  `debt_ratio` decimal(5,4) DEFAULT NULL COMMENT '负债率',
  `status` varchar(20) DEFAULT 'pending' COMMENT '状态(pending/approved/rejected/disbursed)',
  `apply_at` datetime DEFAULT NULL COMMENT '申请时间',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`loan_id`),
  KEY `idx_loan_application_user_id` (`user_id`),
  KEY `idx_loan_application_status` (`status`),
  KEY `idx_loan_application_apply_at` (`apply_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请表';

-- ============================
-- 第三层: 登录与设备
-- ============================

-- 5. 登录日志表
CREATE TABLE IF NOT EXISTS `login_log` (
  `login_id` bigint NOT NULL AUTO_INCREMENT COMMENT '登录ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `device_id` varchar(64) DEFAULT NULL COMMENT '设备ID',
  `ip` varchar(45) DEFAULT NULL COMMENT 'IP地址',
  `geo` varchar(100) DEFAULT NULL COMMENT '地理位置',
  `success` int DEFAULT 1 COMMENT '是否成功(1/0)',
  `fail_reason` varchar(100) DEFAULT NULL COMMENT '失败原因',
  `login_at` datetime DEFAULT NULL COMMENT '登录时间',
  PRIMARY KEY (`login_id`),
  KEY `idx_login_log_user_id` (`user_id`),
  KEY `idx_login_log_device_id` (`device_id`),
  KEY `idx_login_log_ip` (`ip`),
  KEY `idx_login_log_login_at` (`login_at`),
  KEY `idx_login_log_success` (`success`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='登录日志表';

-- 6. 设备指纹表
CREATE TABLE IF NOT EXISTS `device_fingerprint` (
  `device_id` varchar(64) NOT NULL COMMENT '设备ID',
  `user_id` varchar(50) DEFAULT NULL COMMENT '用户ID',
  `fingerprint_hash` varchar(64) DEFAULT NULL COMMENT '指纹哈希',
  `first_seen` datetime DEFAULT NULL COMMENT '首次出现时间',
  `last_seen` datetime DEFAULT NULL COMMENT '最近出现时间',
  `os` varchar(50) DEFAULT NULL COMMENT '操作系统',
  `browser` varchar(50) DEFAULT NULL COMMENT '浏览器',
  `risk_score` int DEFAULT 0 COMMENT '风险评分(0-100)',
  PRIMARY KEY (`device_id`, `user_id`),
  KEY `idx_device_fingerprint_user_id` (`user_id`),
  KEY `idx_device_fingerprint_fingerprint_hash` (`fingerprint_hash`),
  KEY `idx_device_fingerprint_last_seen` (`last_seen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

-- ============================
-- 第四层: IP 库与扩展黑名单
-- ============================

-- 7. IP 地理位置库表
CREATE TABLE IF NOT EXISTS `ip_geo_location` (
  `ip` varchar(45) NOT NULL COMMENT 'IP地址',
  `country` varchar(50) DEFAULT NULL COMMENT '国家',
  `province` varchar(50) DEFAULT NULL COMMENT '省',
  `city` varchar(50) DEFAULT NULL COMMENT '市',
  `isp` varchar(100) DEFAULT NULL COMMENT 'ISP',
  `is_proxy` int DEFAULT 0 COMMENT '是否代理(1/0)',
  `is_tor` int DEFAULT 0 COMMENT '是否Tor(1/0)',
  `last_update` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`ip`),
  KEY `idx_ip_geo_is_proxy` (`is_proxy`),
  KEY `idx_ip_geo_is_tor` (`is_tor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP 地理位置库表';

-- 8. 扩展黑名单表
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `type` varchar(20) NOT NULL COMMENT '类型(user/device/ip/card/id_card)',
  `value` varchar(100) NOT NULL COMMENT '黑名单值',
  `reason` varchar(200) DEFAULT NULL COMMENT '加入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `uk_blacklist_extra_type_value` (`type`, `value`),
  KEY `idx_blacklist_extra_type` (`type`),
  KEY `idx_blacklist_extra_expire_at` (`expire_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='扩展黑名单表';

SET FOREIGN_KEY_CHECKS = 1;

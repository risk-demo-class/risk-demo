-- ============================================
-- 银行风控系统 - 业务表 DDL 初始化脚本 (8 张)
-- 在 risk_bank 数据库中创建银行业务核心表
-- 覆盖: 用户/银行卡/交易/贷款/登录/设备/IP/黑名单扩展
-- ============================================

USE risk_bank;

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `name` VARCHAR(50) DEFAULT NULL COMMENT '姓名',
    `id_card_hash` VARCHAR(64) DEFAULT NULL COMMENT '身份证号哈希(脱敏)',
    `credit_score` INT DEFAULT NULL COMMENT '人行信用分(300-850)',
    `register_at` DATETIME DEFAULT NULL COMMENT '注册时间',
    `kyc_level` INT DEFAULT 1 COMMENT 'KYC等级 (1=L1实名/2=L2人脸/3=L3面签/4=L4高级)',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行用户信息表';

-- 2. 银行卡表
CREATE TABLE IF NOT EXISTS `bank_card` (
    `card_id` VARCHAR(50) NOT NULL COMMENT '卡ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `card_no_hash` VARCHAR(64) NOT NULL COMMENT '卡号哈希(脱敏)',
    `bank_code` VARCHAR(20) DEFAULT NULL COMMENT '发卡行代码',
    `card_type` ENUM('借记卡','信用卡') DEFAULT NULL COMMENT '卡类型',
    `credit_limit` DECIMAL(12,2) DEFAULT 0 COMMENT '授信额度(信用卡), 借记卡为0',
    PRIMARY KEY (`card_id`),
    INDEX `idx_bank_card_user_id` (`user_id`),
    INDEX `idx_bank_card_type` (`card_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡表';

-- 3. 交易表 (转账/消费统一)
CREATE TABLE IF NOT EXISTS `transaction` (
    `txn_id` VARCHAR(50) NOT NULL COMMENT '交易ID',
    `from_card` VARCHAR(50) NOT NULL COMMENT '付款卡ID',
    `to_card` VARCHAR(50) DEFAULT NULL COMMENT '收款卡ID',
    `amount` DECIMAL(12,2) NOT NULL COMMENT '交易金额',
    `channel` ENUM('APP','网银','ATM','第三方') DEFAULT NULL COMMENT '交易渠道',
    `device_id` VARCHAR(64) DEFAULT NULL COMMENT '设备指纹ID',
    `ip` VARCHAR(50) DEFAULT NULL COMMENT 'IP地址',
    `geo` VARCHAR(100) DEFAULT NULL COMMENT '地理位置(省-市)',
    `txn_time` DATETIME DEFAULT NULL COMMENT '交易时间',
    PRIMARY KEY (`txn_id`),
    INDEX `idx_txn_from_card` (`from_card`),
    INDEX `idx_txn_to_card` (`to_card`),
    INDEX `idx_txn_time` (`txn_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交易表';

-- 4. 贷款申请表
CREATE TABLE IF NOT EXISTS `loan_application` (
    `loan_id` VARCHAR(50) NOT NULL COMMENT '贷款申请ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `amount` DECIMAL(12,2) NOT NULL COMMENT '申请金额',
    `term_months` INT DEFAULT NULL COMMENT '期限(月)',
    `purpose` VARCHAR(100) DEFAULT NULL COMMENT '贷款用途',
    `monthly_income` DECIMAL(12,2) DEFAULT NULL COMMENT '月收入',
    `debt_ratio` DECIMAL(5,4) DEFAULT NULL COMMENT '负债率(月还款/月收入)',
    `apply_time` DATETIME DEFAULT NULL COMMENT '申请时间',
    PRIMARY KEY (`loan_id`),
    INDEX `idx_loan_user_id` (`user_id`),
    INDEX `idx_loan_apply_time` (`apply_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请表';

-- 5. 登录日志表
CREATE TABLE IF NOT EXISTS `login_log` (
    `login_id` VARCHAR(50) NOT NULL COMMENT '登录ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `device_id` VARCHAR(64) DEFAULT NULL COMMENT '设备指纹ID',
    `ip` VARCHAR(50) DEFAULT NULL COMMENT 'IP地址',
    `geo` VARCHAR(100) DEFAULT NULL COMMENT '地理位置(省-市)',
    `success` INT DEFAULT 1 COMMENT '是否登录成功(1/0)',
    `login_at` DATETIME DEFAULT NULL COMMENT '登录时间',
    PRIMARY KEY (`login_id`),
    INDEX `idx_login_user_id` (`user_id`),
    INDEX `idx_login_device_id` (`device_id`),
    INDEX `idx_login_time` (`login_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='登录日志表';

-- 6. 设备指纹表
CREATE TABLE IF NOT EXISTS `device_fingerprint` (
    `device_id` VARCHAR(64) NOT NULL COMMENT '设备指纹ID',
    `user_id` VARCHAR(50) DEFAULT NULL COMMENT '归属用户(可能多人共用)',
    `fingerprint_hash` VARCHAR(64) DEFAULT NULL COMMENT '指纹哈希',
    `first_seen` DATETIME DEFAULT NULL COMMENT '首次出现时间',
    `last_seen` DATETIME DEFAULT NULL COMMENT '最近出现时间',
    `os` VARCHAR(50) DEFAULT NULL COMMENT '操作系统',
    `browser` VARCHAR(50) DEFAULT NULL COMMENT '浏览器',
    PRIMARY KEY (`device_id`),
    INDEX `idx_device_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

-- 7. IP 地理位置表
CREATE TABLE IF NOT EXISTS `ip_geo_location` (
    `ip` VARCHAR(50) NOT NULL COMMENT 'IP地址',
    `country` VARCHAR(50) DEFAULT NULL COMMENT '国家',
    `province` VARCHAR(50) DEFAULT NULL COMMENT '省',
    `city` VARCHAR(50) DEFAULT NULL COMMENT '市',
    `isp` VARCHAR(50) DEFAULT NULL COMMENT '运营商',
    `is_proxy` INT DEFAULT 0 COMMENT '是否代理IP(1/0)',
    `is_tor` INT DEFAULT 0 COMMENT '是否Tor出口(1/0)',
    PRIMARY KEY (`ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP地理位置表';

-- 8. 黑名单扩展表 (银行业专属类型)
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
    `entry_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '条目ID',
    `type` ENUM('设备指纹','IP','银行卡号','身份证号') NOT NULL COMMENT '黑名单类型',
    `value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` VARCHAR(500) DEFAULT NULL COMMENT '加入原因',
    `expire_at` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    PRIMARY KEY (`entry_id`),
    UNIQUE INDEX `idx_blacklist_extra_type_value` (`type`, `value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='黑名单扩展表';

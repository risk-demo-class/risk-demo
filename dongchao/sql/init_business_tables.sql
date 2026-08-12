-- ============================================
-- 银行风控系统 - 业务表 DDL (8 张)
-- 创建顺序: 从无外键到有外键 (FK 依赖排序)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 无外键依赖
-- ============================

CREATE TABLE IF NOT EXISTS `user_info` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `name` VARCHAR(100) NOT NULL COMMENT '姓名',
    `id_card_hash` VARCHAR(64) NOT NULL COMMENT '身份证号SHA256',
    `credit_score` INT DEFAULT 600 COMMENT '征信分(350-950)',
    `register_at` DATETIME NOT NULL COMMENT '注册时间',
    `kyc_level` ENUM('未认证','L1','L2','L3') DEFAULT '未认证' COMMENT 'KYC认证等级',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

CREATE TABLE IF NOT EXISTS `ip_geo_location` (
    `ip` VARCHAR(50) NOT NULL COMMENT 'IP地址',
    `country` VARCHAR(50) DEFAULT NULL COMMENT '国家',
    `province` VARCHAR(50) DEFAULT NULL COMMENT '省份',
    `city` VARCHAR(50) DEFAULT NULL COMMENT '城市',
    `isp` VARCHAR(50) DEFAULT NULL COMMENT '运营商',
    `is_proxy` TINYINT(1) DEFAULT 0 COMMENT '是否代理IP',
    `is_tor` TINYINT(1) DEFAULT 0 COMMENT '是否Tor出口',
    PRIMARY KEY (`ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP地理位置信息表';

-- ============================
-- 第二层: FK 依赖 user_info
-- ============================

CREATE TABLE IF NOT EXISTS `device_fingerprint` (
    `device_id` VARCHAR(50) NOT NULL COMMENT '设备ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `fingerprint_hash` VARCHAR(128) NOT NULL COMMENT '设备指纹Hash',
    `first_seen` DATETIME NOT NULL COMMENT '首次发现时间',
    `last_seen` DATETIME NOT NULL COMMENT '最后活跃时间',
    `os` VARCHAR(50) DEFAULT NULL COMMENT '操作系统',
    `browser` VARCHAR(50) DEFAULT NULL COMMENT '浏览器',
    PRIMARY KEY (`device_id`),
    INDEX `idx_df_user_id` (`user_id`),
    FOREIGN KEY (`user_id`) REFERENCES `user_info`(`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

CREATE TABLE IF NOT EXISTS `blacklist_extra` (
    `entry_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '条目ID',
    `type` ENUM('设备指纹','IP','银行卡号','身份证号') NOT NULL COMMENT '黑名单类型',
    `value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` TEXT COMMENT '加入原因',
    `expire_at` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    PRIMARY KEY (`entry_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务黑名单扩展表';

CREATE TABLE IF NOT EXISTS `bank_card` (
    `card_id` VARCHAR(50) NOT NULL COMMENT '卡ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `card_no_hash` VARCHAR(64) NOT NULL COMMENT '卡号SHA256',
    `bank_code` VARCHAR(20) NOT NULL COMMENT '银行代码',
    `card_type` ENUM('借记卡','信用卡') NOT NULL COMMENT '卡类型',
    `credit_limit` DECIMAL(12,2) DEFAULT 0 COMMENT '信用额度(信用卡)',
    PRIMARY KEY (`card_id`),
    INDEX `idx_bc_user_id` (`user_id`),
    FOREIGN KEY (`user_id`) REFERENCES `user_info`(`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡表';

-- ============================
-- 第三层: FK 依赖 user_info
-- ============================

CREATE TABLE IF NOT EXISTS `login_log` (
    `login_id` VARCHAR(50) NOT NULL COMMENT '登录ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `device_id` VARCHAR(50) DEFAULT NULL COMMENT '设备ID',
    `ip` VARCHAR(50) DEFAULT NULL COMMENT '登录IP',
    `geo` VARCHAR(100) DEFAULT NULL COMMENT '登录地理位置',
    `success` TINYINT(1) NOT NULL COMMENT '是否成功(1=成功,0=失败)',
    `login_at` DATETIME NOT NULL COMMENT '登录时间',
    PRIMARY KEY (`login_id`),
    INDEX `idx_ll_user_id` (`user_id`),
    INDEX `idx_ll_login_at` (`login_at`),
    FOREIGN KEY (`user_id`) REFERENCES `user_info`(`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='登录日志表';

CREATE TABLE IF NOT EXISTS `loan_application` (
    `loan_id` VARCHAR(50) NOT NULL COMMENT '贷款申请ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `amount` DECIMAL(12,2) NOT NULL COMMENT '申请金额',
    `term_months` INT NOT NULL COMMENT '期限(月)',
    `purpose` VARCHAR(200) NOT NULL COMMENT '贷款用途',
    `monthly_income` DECIMAL(10,2) NOT NULL COMMENT '月收入',
    `debt_ratio` DECIMAL(5,2) DEFAULT 0 COMMENT '负债率(%)',
    `status` ENUM('待审核','通过','拒绝') DEFAULT '待审核' COMMENT '审核状态',
    `create_time` DATETIME NOT NULL COMMENT '申请时间',
    PRIMARY KEY (`loan_id`),
    INDEX `idx_la_user_id` (`user_id`),
    FOREIGN KEY (`user_id`) REFERENCES `user_info`(`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请表';

-- ============================
-- 第四层: FK 依赖 bank_card
-- ============================

CREATE TABLE IF NOT EXISTS `transaction` (
    `txn_id` VARCHAR(50) NOT NULL COMMENT '交易ID',
    `from_card` VARCHAR(50) NOT NULL COMMENT '发出卡ID',
    `to_card` VARCHAR(50) NOT NULL COMMENT '接收卡ID(可为外行)',
    `amount` DECIMAL(12,2) NOT NULL COMMENT '交易金额',
    `channel` ENUM('网银','手机银行','ATM','柜台') NOT NULL COMMENT '交易渠道',
    `device_id` VARCHAR(50) DEFAULT NULL COMMENT '设备ID',
    `ip` VARCHAR(50) DEFAULT NULL COMMENT '交易IP',
    `geo` VARCHAR(100) DEFAULT NULL COMMENT '交易地理位置',
    `create_time` DATETIME NOT NULL COMMENT '交易时间',
    PRIMARY KEY (`txn_id`),
    INDEX `idx_txn_from_card` (`from_card`),
    INDEX `idx_txn_create_time` (`create_time`),
    FOREIGN KEY (`from_card`) REFERENCES `bank_card`(`card_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交易记录表(转账)';

SET FOREIGN_KEY_CHECKS = 1;
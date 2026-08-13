-- 银行风控教学系统 - 8 张业务表 DDL（不创建或修改核心风控表）

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(100) NOT NULL COMMENT '虚构用户标识名',
  `id_card_hash` varchar(64) NOT NULL COMMENT '虚构身份证号摘要',
  `credit_score` int NOT NULL DEFAULT 600 COMMENT '教学信用分',
  `register_at` datetime NOT NULL COMMENT '注册时间',
  `kyc_level` enum('基础','标准','增强') NOT NULL DEFAULT '基础' COMMENT 'KYC等级',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uq_user_id_card_hash` (`id_card_hash`),
  KEY `ix_user_credit_score` (`credit_score`),
  KEY `ix_user_register_at` (`register_at`),
  KEY `ix_user_kyc_credit` (`kyc_level`,`credit_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='虚构银行客户';

CREATE TABLE IF NOT EXISTS `ip_geo_location` (
  `ip` varchar(64) NOT NULL COMMENT '虚构IP标识',
  `country` varchar(50) NOT NULL COMMENT '国家或地区',
  `province` varchar(50) NOT NULL COMMENT '省级区域',
  `city` varchar(50) NOT NULL COMMENT '城市',
  `isp` varchar(100) NOT NULL COMMENT '虚构网络服务商',
  `is_proxy` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否代理',
  `is_tor` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否Tor出口',
  `updated_at` datetime NOT NULL COMMENT '环境更新时间',
  PRIMARY KEY (`ip`),
  KEY `ix_ip_geo` (`country`,`province`,`city`),
  KEY `ix_ip_proxy_tor` (`is_proxy`,`is_tor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='虚构IP地理环境';

CREATE TABLE IF NOT EXISTS `device_fingerprint` (
  `device_id` varchar(50) NOT NULL COMMENT '设备ID',
  `user_id` varchar(50) NOT NULL COMMENT '关联用户ID',
  `fingerprint_hash` varchar(64) NOT NULL COMMENT '设备指纹摘要',
  `first_seen` datetime NOT NULL COMMENT '首次出现时间',
  `last_seen` datetime NOT NULL COMMENT '最近出现时间',
  `os` varchar(50) NOT NULL COMMENT '操作系统枚举值',
  `browser` varchar(50) NOT NULL COMMENT '浏览器枚举值',
  PRIMARY KEY (`device_id`,`user_id`),
  KEY `ix_device_fingerprint_hash` (`fingerprint_hash`),
  KEY `ix_device_user_last_seen` (`user_id`,`last_seen`),
  CONSTRAINT `fk_device_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `ck_device_seen_order` CHECK (`last_seen` >= `first_seen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备与用户关联';

CREATE TABLE IF NOT EXISTS `bank_card` (
  `card_id` varchar(50) NOT NULL COMMENT '银行卡ID',
  `user_id` varchar(50) NOT NULL COMMENT '所属用户ID',
  `card_no_hash` varchar(64) NOT NULL COMMENT '虚构卡号摘要',
  `bank_code` varchar(20) NOT NULL COMMENT '虚构机构代码',
  `card_type` enum('借记卡','信用卡') NOT NULL COMMENT '卡类型',
  `credit_limit` decimal(14,2) NOT NULL DEFAULT 0.00 COMMENT '教学信用额度',
  `bind_at` datetime NOT NULL COMMENT '绑卡时间',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '卡关系是否有效',
  PRIMARY KEY (`card_id`),
  UNIQUE KEY `uq_bank_card_no_hash` (`card_no_hash`),
  KEY `ix_bank_card_user_active` (`user_id`,`is_active`),
  KEY `ix_bank_card_bank_type` (`bank_code`,`card_type`),
  CONSTRAINT `fk_bank_card_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `ck_bank_card_credit_limit` CHECK (`credit_limit` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡关系';

CREATE TABLE IF NOT EXISTS `bank_transaction` (
  `txn_id` varchar(50) NOT NULL COMMENT '交易ID',
  `from_card` varchar(50) NOT NULL COMMENT '付款卡ID',
  `to_card` varchar(50) NOT NULL COMMENT '收款卡ID',
  `amount` decimal(14,2) NOT NULL COMMENT '交易金额',
  `channel` enum('手机银行','网上银行','柜面','ATM','快捷支付') NOT NULL COMMENT '交易渠道',
  `device_id` varchar(50) NOT NULL COMMENT '逻辑关联设备ID',
  `ip` varchar(64) NOT NULL COMMENT '虚构IP标识',
  `geo` varchar(100) NOT NULL COMMENT '事件地理编码',
  `txn_at` datetime NOT NULL COMMENT '交易时间',
  `status` enum('成功','失败','处理中') NOT NULL DEFAULT '成功' COMMENT '交易状态',
  PRIMARY KEY (`txn_id`),
  KEY `ix_bank_transaction_from_time` (`from_card`,`txn_at`),
  KEY `ix_bank_transaction_to_time` (`to_card`,`txn_at`),
  KEY `ix_bank_transaction_device_time` (`device_id`,`txn_at`),
  KEY `ix_bank_transaction_ip_time` (`ip`,`txn_at`),
  KEY `ix_bank_transaction_time_amount` (`txn_at`,`amount`),
  CONSTRAINT `fk_transaction_from_card` FOREIGN KEY (`from_card`) REFERENCES `bank_card` (`card_id`),
  CONSTRAINT `fk_transaction_to_card` FOREIGN KEY (`to_card`) REFERENCES `bank_card` (`card_id`),
  CONSTRAINT `fk_transaction_ip` FOREIGN KEY (`ip`) REFERENCES `ip_geo_location` (`ip`),
  CONSTRAINT `ck_bank_transaction_amount` CHECK (`amount` > 0),
  CONSTRAINT `ck_bank_transaction_distinct_cards` CHECK (`from_card` <> `to_card`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行转账交易';

CREATE TABLE IF NOT EXISTS `loan_application` (
  `loan_id` varchar(50) NOT NULL COMMENT '贷款申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '申请用户ID',
  `amount` decimal(14,2) NOT NULL COMMENT '申请金额',
  `term_months` int NOT NULL COMMENT '期限（月）',
  `purpose` varchar(100) NOT NULL COMMENT '贷款用途',
  `monthly_income` decimal(14,2) NOT NULL COMMENT '月收入',
  `debt_ratio` decimal(6,4) NOT NULL COMMENT '负债率',
  `institution_code` varchar(32) NOT NULL COMMENT '虚构申请机构代码',
  `apply_at` datetime NOT NULL COMMENT '申请时间',
  `status` enum('待审核','已批准','已拒绝') NOT NULL DEFAULT '待审核' COMMENT '申请状态',
  PRIMARY KEY (`loan_id`),
  KEY `ix_loan_user_apply` (`user_id`,`apply_at`),
  KEY `ix_loan_institution_apply` (`institution_code`,`apply_at`),
  KEY `ix_loan_apply_amount` (`apply_at`,`amount`),
  CONSTRAINT `fk_loan_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `ck_loan_amount` CHECK (`amount` > 0),
  CONSTRAINT `ck_loan_term` CHECK (`term_months` > 0),
  CONSTRAINT `ck_loan_income` CHECK (`monthly_income` >= 0),
  CONSTRAINT `ck_loan_debt_ratio` CHECK (`debt_ratio` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请';

CREATE TABLE IF NOT EXISTS `login_log` (
  `login_id` varchar(50) NOT NULL COMMENT '登录记录ID',
  `user_id` varchar(50) NOT NULL COMMENT '登录用户ID',
  `device_id` varchar(50) NOT NULL COMMENT '设备ID',
  `ip` varchar(64) NOT NULL COMMENT '虚构IP标识',
  `geo` varchar(100) NOT NULL COMMENT '登录地理编码',
  `success` tinyint(1) NOT NULL COMMENT '是否登录成功',
  `login_at` datetime NOT NULL COMMENT '登录时间',
  PRIMARY KEY (`login_id`),
  KEY `ix_login_user_time` (`user_id`,`login_at`),
  KEY `ix_login_device_time` (`device_id`,`login_at`),
  KEY `ix_login_ip_time` (`ip`,`login_at`),
  CONSTRAINT `fk_login_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `fk_login_device_user` FOREIGN KEY (`device_id`,`user_id`) REFERENCES `device_fingerprint` (`device_id`,`user_id`),
  CONSTRAINT `fk_login_ip` FOREIGN KEY (`ip`) REFERENCES `ip_geo_location` (`ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='登录日志';

CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '扩展名单ID',
  `type` enum('用户','设备指纹','IP','银行卡号','身份证号') NOT NULL COMMENT '名单类型',
  `value` varchar(128) NOT NULL COMMENT '掩码或不可逆摘要',
  `reason` varchar(255) NOT NULL COMMENT '教学名单原因',
  `expire_at` datetime DEFAULT NULL COMMENT '到期时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `uq_blacklist_extra_type_value` (`type`,`value`),
  KEY `ix_blacklist_extra_expire` (`expire_at`),
  KEY `ix_blacklist_extra_type_created` (`type`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行扩展名单数据源';

SET FOREIGN_KEY_CHECKS = 1;

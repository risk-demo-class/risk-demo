-- ============================================
-- 银行工商风控系统 - 业务表 DDL (30 张)
-- 按外键依赖分层: L1 基础维度 -> L2 核心实体 -> L3 关联轨迹表
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- 第一层: 基础维度表 (无外键依赖)
-- ============================================================

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name_hash` varchar(128) NOT NULL COMMENT '姓名 SHA256 哈希',
  `id_card_hash` varchar(128) NOT NULL COMMENT '身份证号 SHA256 哈希',
  `phone_hash` varchar(128) NOT NULL COMMENT '手机号 SHA256 哈希',
  `email` varchar(100) DEFAULT NULL COMMENT '邮箱',
  `kyc_level` enum('L1','L2','L3','L4','L5') NOT NULL DEFAULT 'L1' COMMENT 'KYC 等级',
  `credit_score` int NOT NULL DEFAULT 600 COMMENT '行内信用评分 300-900',
  `reg_date` datetime NOT NULL COMMENT '注册日期',
  `status` enum('正常','冻结','销户') NOT NULL DEFAULT '正常' COMMENT '账户状态',
  `reg_ip` varchar(50) DEFAULT NULL COMMENT '注册 IP',
  `reg_city` varchar(30) DEFAULT NULL COMMENT '注册城市',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`user_id`),
  KEY `idx_user_id_card_hash` (`id_card_hash`),
  KEY `idx_user_phone_hash` (`phone_hash`),
  KEY `idx_user_kyc_level` (`kyc_level`),
  KEY `idx_user_credit_score` (`credit_score`),
  KEY `idx_user_reg_city` (`reg_city`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. IP 地理位置库
CREATE TABLE IF NOT EXISTS `ip_geo_location` (
  `ip_id` bigint NOT NULL AUTO_INCREMENT COMMENT 'IP 记录ID',
  `ip_cidr` varchar(50) NOT NULL COMMENT 'IP CIDR 段',
  `country` varchar(50) DEFAULT NULL COMMENT '国家',
  `province` varchar(30) DEFAULT NULL COMMENT '省份',
  `city` varchar(30) DEFAULT NULL COMMENT '城市',
  `isp` varchar(100) DEFAULT NULL COMMENT '运营商',
  `is_proxy` tinyint DEFAULT 0 COMMENT '是否代理 IP',
  `is_tor` tinyint DEFAULT 0 COMMENT '是否 Tor 出口节点',
  `is_data_center` tinyint DEFAULT 0 COMMENT '是否数据中心 IP',
  `risk_level` enum('低','中','高') DEFAULT '低' COMMENT 'IP 风险等级',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`ip_id`),
  KEY `idx_ip_cidr` (`ip_cidr`),
  KEY `idx_ip_risk_level` (`risk_level`),
  KEY `idx_ip_city` (`city`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP 地理位置库';

-- 3. 渠道风险权重配置表
CREATE TABLE IF NOT EXISTS `txn_channel_risk` (
  `channel` enum('网银','手机银行','快捷支付','柜面','ATM','POS') NOT NULL COMMENT '交易渠道',
  `risk_weight` decimal(5,2) NOT NULL COMMENT '风险权重 0-100',
  `max_single_limit` decimal(18,2) NOT NULL COMMENT '单笔限额',
  `max_daily_limit` decimal(18,2) NOT NULL COMMENT '日累计限额',
  `max_daily_count` int NOT NULL COMMENT '日笔数上限',
  `is_enabled` tinyint DEFAULT 1 COMMENT '是否启用',
  PRIMARY KEY (`channel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='渠道风险权重配置表';

-- 4. 高危地区名单表
CREATE TABLE IF NOT EXISTS `high_risk_region` (
  `region_id` bigint NOT NULL AUTO_INCREMENT COMMENT '地区ID',
  `province` varchar(30) NOT NULL COMMENT '省',
  `city` varchar(30) DEFAULT NULL COMMENT '市',
  `risk_level` enum('低','中','高','极高') NOT NULL COMMENT '风险等级',
  `risk_category` enum('电信诈骗','洗钱','赌博','非法集资','传销','其他') NOT NULL COMMENT '风险类型',
  `valid_from` date NOT NULL COMMENT '生效日期',
  `valid_to` date DEFAULT NULL COMMENT '失效日期 NULL=永久',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`region_id`),
  KEY `idx_region_city` (`province`,`city`),
  KEY `idx_region_level` (`risk_level`),
  KEY `idx_region_valid` (`valid_from`,`valid_to`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='高危地区名单表';

-- 5. 企业黑名单表
CREATE TABLE IF NOT EXISTS `enterprise_blacklist` (
  `enterprise_blacklist_id` bigint NOT NULL AUTO_INCREMENT COMMENT '企业黑名单ID',
  `enterprise_name` varchar(200) NOT NULL COMMENT '企业名称',
  `credit_code` varchar(50) NOT NULL COMMENT '统一社会信用代码',
  `legal_person_hash` varchar(128) DEFAULT NULL COMMENT '法定代表人身份证 SHA256',
  `black_reason` text NOT NULL COMMENT '列入原因',
  `black_source` enum('法院失信','工商吊销','公安通报','人行征信','行内风控') NOT NULL COMMENT '来源',
  `black_time` datetime NOT NULL COMMENT '列入时间',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`enterprise_blacklist_id`),
  KEY `idx_ent_blk_credit_code` (`credit_code`),
  KEY `idx_ent_blk_name` (`enterprise_name`),
  KEY `idx_ent_blk_legal` (`legal_person_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='企业黑名单表';

-- 6. 黑产收款账户特征库
CREATE TABLE IF NOT EXISTS `txn_black_account` (
  `account_id` bigint NOT NULL AUTO_INCREMENT COMMENT '黑账户ID',
  `account_number_hash` varchar(128) NOT NULL COMMENT '账号 SHA256',
  `account_name_hash` varchar(128) NOT NULL COMMENT '账户名 SHA256',
  `bank_name` varchar(100) DEFAULT NULL COMMENT '开户行',
  `hit_count` int DEFAULT 0 COMMENT '命中次数',
  `hit_date` datetime DEFAULT NULL COMMENT '最近命中时间',
  `risk_level` enum('低','中','高','极高') DEFAULT '中' COMMENT '风险等级',
  `source` varchar(50) DEFAULT NULL COMMENT '来源 公安/人行/行内',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`account_id`),
  KEY `idx_blk_acct_hash` (`account_number_hash`),
  KEY `idx_blk_acct_level` (`risk_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='黑产收款账户特征库';

-- ============================================================
-- 第二层: 依赖基础维度表
-- ============================================================

-- 7. 用户 KYC 审核记录表
CREATE TABLE IF NOT EXISTS `user_kyc_record` (
  `kyc_record_id` bigint NOT NULL AUTO_INCREMENT COMMENT 'KYC 记录ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `level_before` enum('L1','L2','L3','L4','L5') NOT NULL COMMENT '变更前 KYC 等级',
  `level_after` enum('L1','L2','L3','L4','L5') NOT NULL COMMENT '变更后 KYC 等级',
  `audit_status` enum('待审核','通过','驳回') DEFAULT '待审核' COMMENT '审核状态',
  `auditor` varchar(50) DEFAULT NULL COMMENT '审核人',
  `audit_remark` text COMMENT '审核备注',
  `audit_time` datetime DEFAULT NULL COMMENT '审核时间',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`kyc_record_id`),
  KEY `idx_kyc_user_id` (`user_id`),
  KEY `idx_kyc_audit_time` (`audit_time`),
  CONSTRAINT `fk_kyc_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户 KYC 审核记录表';

-- 8. 用户职业与收入信息表
CREATE TABLE IF NOT EXISTS `user_employment` (
  `employment_id` bigint NOT NULL AUTO_INCREMENT COMMENT '职业信息ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `company_name` varchar(200) NOT NULL COMMENT '公司名称',
  `position` varchar(100) DEFAULT NULL COMMENT '职位',
  `monthly_income` decimal(18,2) NOT NULL COMMENT '月收入',
  `annual_income` decimal(18,2) DEFAULT NULL COMMENT '年收入',
  `employment_status` enum('在职','离职','退休','自由职业') DEFAULT '在职' COMMENT '就业状态',
  `verify_status` enum('未验证','验证中','已验证','验证失败') DEFAULT '未验证' COMMENT '收入验证状态',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`employment_id`),
  KEY `idx_employment_user_id` (`user_id`),
  KEY `idx_employment_income` (`monthly_income`),
  CONSTRAINT `fk_employment_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户职业与收入信息表';

-- 9. 用户联系人信息表
CREATE TABLE IF NOT EXISTS `user_contact` (
  `contact_id` bigint NOT NULL AUTO_INCREMENT COMMENT '联系人ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `contact_name_hash` varchar(128) NOT NULL COMMENT '联系人姓名 SHA256',
  `contact_phone_hash` varchar(128) NOT NULL COMMENT '联系人手机号 SHA256',
  `relationship` enum('配偶','父母','子女','兄弟姐妹','朋友','同事') NOT NULL COMMENT '与用户关系',
  `is_emergency` tinyint DEFAULT 0 COMMENT '是否紧急联系人',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`contact_id`),
  KEY `idx_contact_user_id` (`user_id`),
  KEY `idx_contact_phone_hash` (`contact_phone_hash`),
  CONSTRAINT `fk_contact_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户联系人信息表';

-- 10. 企业对公信息表
CREATE TABLE IF NOT EXISTS `user_enterprise` (
  `enterprise_id` bigint NOT NULL AUTO_INCREMENT COMMENT '企业信息ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `enterprise_name` varchar(200) NOT NULL COMMENT '企业名称',
  `credit_code` varchar(50) NOT NULL COMMENT '统一社会信用代码',
  `legal_person_hash` varchar(128) NOT NULL COMMENT '法定代表人身份证 SHA256',
  `registered_capital` decimal(18,2) DEFAULT NULL COMMENT '注册资本万元',
  `business_scope` text COMMENT '经营范围',
  `establish_date` date DEFAULT NULL COMMENT '成立日期',
  `industry_category` varchar(50) DEFAULT NULL COMMENT '行业分类',
  `ubo_count` int DEFAULT 0 COMMENT '受益所有人数量',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`enterprise_id`),
  KEY `idx_ent_user_id` (`user_id`),
  KEY `idx_ent_credit_code` (`credit_code`),
  KEY `idx_ent_legal_person` (`legal_person_hash`),
  KEY `idx_ent_name` (`enterprise_name`),
  CONSTRAINT `fk_enterprise_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='企业对公信息表';

-- ============================================================
-- 第三层: 核心实体表 (依赖 L1-L2)
-- ============================================================

-- 11. 银行卡信息表
CREATE TABLE IF NOT EXISTS `bank_card` (
  `card_id` varchar(50) NOT NULL COMMENT '卡ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `card_number_hash` varchar(128) NOT NULL COMMENT '卡号 SHA256',
  `card_type` enum('借记卡','信用卡','II类户') NOT NULL COMMENT '卡类型',
  `bank_name` varchar(100) NOT NULL COMMENT '发卡行名称',
  `credit_limit` decimal(18,2) DEFAULT NULL COMMENT '授信额度',
  `available_limit` decimal(18,2) DEFAULT NULL COMMENT '可用额度',
  `open_date` date NOT NULL COMMENT '开卡日期',
  `card_status` enum('正常','冻结','挂失','注销') NOT NULL DEFAULT '正常' COMMENT '卡片状态',
  `is_virtual` tinyint DEFAULT 0 COMMENT '是否虚拟卡',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`card_id`),
  KEY `idx_card_user_id` (`user_id`),
  KEY `idx_card_number_hash` (`card_number_hash`),
  KEY `idx_card_type` (`card_type`),
  KEY `idx_card_status` (`card_status`),
  CONSTRAINT `fk_card_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡信息表';

-- 12. 设备指纹表
CREATE TABLE IF NOT EXISTS `device_fingerprint` (
  `device_id` varchar(50) NOT NULL COMMENT '设备指纹ID',
  `user_id` varchar(50) NOT NULL COMMENT '关联用户ID',
  `device_type` enum('iOS','Android','PC','Web','Other') NOT NULL COMMENT '设备类型',
  `os` varchar(50) DEFAULT NULL COMMENT '操作系统',
  `os_version` varchar(20) DEFAULT NULL COMMENT 'OS版本',
  `browser` varchar(50) DEFAULT NULL COMMENT '浏览器',
  `is_rooted` tinyint DEFAULT 0 COMMENT '是否Root越狱',
  `is_emulator` tinyint DEFAULT 0 COMMENT '是否模拟器',
  `fingerprint_hash` varchar(128) NOT NULL COMMENT '设备指纹哈希',
  `first_seen` datetime NOT NULL COMMENT '首次出现时间',
  `last_seen` datetime DEFAULT NULL COMMENT '最近出现时间',
  `associated_users` int DEFAULT 1 COMMENT '关联用户数',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`device_id`),
  KEY `idx_dev_user_id` (`user_id`),
  KEY `idx_dev_fingerprint_hash` (`fingerprint_hash`),
  KEY `idx_dev_associated_users` (`associated_users`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

-- 13. 交易对手方信息表
CREATE TABLE IF NOT EXISTS `txn_counterparty` (
  `counterparty_id` bigint NOT NULL AUTO_INCREMENT COMMENT '对手方ID',
  `counterparty_name_hash` varchar(128) NOT NULL COMMENT '对手方名称 SHA256',
  `counterparty_account_hash` varchar(128) NOT NULL COMMENT '对手方账号 SHA256',
  `counterparty_bank` varchar(100) DEFAULT NULL COMMENT '对手方开户行',
  `risk_flag` tinyint DEFAULT 0 COMMENT '风险标记',
  `risk_region` varchar(30) DEFAULT NULL COMMENT '对手方归属地',
  `first_seen` datetime DEFAULT NULL COMMENT '首次出现时间',
  `last_seen` datetime DEFAULT NULL COMMENT '最近出现时间',
  `txn_count` int DEFAULT 0 COMMENT '累计交易笔数',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`counterparty_id`),
  KEY `idx_cpty_account` (`counterparty_account_hash`),
  KEY `idx_cpty_risk_flag` (`risk_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交易对手方信息表';

-- 14. 交易流水表
CREATE TABLE IF NOT EXISTS `transaction` (
  `txn_id` varchar(50) NOT NULL COMMENT '交易ID',
  `from_card` varchar(50) NOT NULL COMMENT '付款卡号',
  `to_card` varchar(50) NOT NULL COMMENT '收款卡号',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `amount` decimal(18,2) NOT NULL COMMENT '交易金额',
  `txn_type` enum('转账','消费','取现','还款','退款') NOT NULL COMMENT '交易类型',
  `channel` enum('网银','手机银行','快捷支付','柜面','ATM','POS') NOT NULL COMMENT '交易渠道',
  `txn_time` datetime NOT NULL COMMENT '交易时间',
  `txn_status` enum('成功','失败','处理中','已冲正') DEFAULT '成功' COMMENT '交易状态',
  `ip` varchar(50) DEFAULT NULL COMMENT '交易IP',
  `city` varchar(30) DEFAULT NULL COMMENT '交易城市',
  `device_id` varchar(50) DEFAULT NULL COMMENT '设备指纹ID',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注附言',
  `is_international` tinyint DEFAULT 0 COMMENT '是否跨境交易',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`txn_id`),
  KEY `idx_txn_user_id` (`user_id`),
  KEY `idx_txn_from_card` (`from_card`),
  KEY `idx_txn_to_card` (`to_card`),
  KEY `idx_txn_time` (`txn_time`),
  KEY `idx_txn_user_time` (`user_id`,`txn_time`),
  KEY `idx_txn_to_card_time` (`to_card`,`txn_time`),
  KEY `idx_txn_amount` (`amount`),
  KEY `idx_txn_device` (`device_id`),
  KEY `idx_txn_city` (`city`),
  CONSTRAINT `fk_txn_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交易流水表';

-- 15. 登录日志表
CREATE TABLE IF NOT EXISTS `login_log` (
  `login_id` bigint NOT NULL AUTO_INCREMENT COMMENT '登录日志ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `login_time` datetime NOT NULL COMMENT '登录时间',
  `login_ip` varchar(50) NOT NULL COMMENT '登录IP',
  `login_city` varchar(30) DEFAULT NULL COMMENT '登录城市',
  `login_device_id` varchar(50) DEFAULT NULL COMMENT '设备指纹ID',
  `login_result` enum('成功','失败','锁定') NOT NULL COMMENT '登录结果',
  `fail_reason` varchar(100) DEFAULT NULL COMMENT '失败原因',
  `is_new_device` tinyint DEFAULT 0 COMMENT '是否新设备首次登录',
  `is_proxy_ip` tinyint DEFAULT 0 COMMENT '是否代理IP',
  `session_id` varchar(50) DEFAULT NULL COMMENT '会话ID',
  PRIMARY KEY (`login_id`),
  KEY `idx_login_user_id` (`user_id`),
  KEY `idx_login_time` (`login_time`),
  KEY `idx_login_device` (`login_device_id`),
  KEY `idx_login_ip` (`login_ip`),
  KEY `idx_login_user_time` (`user_id`,`login_time`),
  CONSTRAINT `fk_login_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='登录日志表';

-- 16. 贷款申请表
CREATE TABLE IF NOT EXISTS `loan_application` (
  `application_id` varchar(50) NOT NULL COMMENT '申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `loan_type` enum('个人消费贷','个人经营贷','住房按揭','汽车贷款','信用卡分期') NOT NULL COMMENT '贷款类型',
  `apply_amount` decimal(18,2) NOT NULL COMMENT '申请金额',
  `term_months` int NOT NULL COMMENT '贷款期限月',
  `purpose` varchar(200) NOT NULL COMMENT '资金用途',
  `debt_ratio` decimal(5,4) NOT NULL COMMENT '月负债收入比',
  `monthly_income` decimal(18,2) NOT NULL COMMENT '申报月收入',
  `credit_score` int NOT NULL COMMENT '申请时信用评分',
  `is_entrusted` tinyint DEFAULT 0 COMMENT '是否受托支付',
  `apply_status` enum('待审批','审批中','已通过','已拒绝','已放款') DEFAULT '待审批' COMMENT '申请状态',
  `apply_time` datetime NOT NULL COMMENT '申请时间',
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`application_id`),
  KEY `idx_loan_user_id` (`user_id`),
  KEY `idx_loan_apply_time` (`apply_time`),
  KEY `idx_loan_status` (`apply_status`),
  CONSTRAINT `fk_loan_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请表';

-- ============================================================
-- 第四层: 关联轨迹表 (依赖 L3)
-- ============================================================

-- 17. 贷款审批记录表
CREATE TABLE IF NOT EXISTS `loan_approval` (
  `approval_id` bigint NOT NULL AUTO_INCREMENT COMMENT '审批ID',
  `application_id` varchar(50) NOT NULL COMMENT '申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `approval_status` enum('通过','驳回','退回补充') NOT NULL COMMENT '审批结果',
  `approved_amount` decimal(18,2) DEFAULT NULL COMMENT '批准金额',
  `approved_term` int DEFAULT NULL COMMENT '批准期限月',
  `interest_rate` decimal(5,4) DEFAULT NULL COMMENT '批准利率',
  `reject_reason` text COMMENT '拒绝原因',
  `approver` varchar(50) NOT NULL COMMENT '审批人',
  `approval_time` datetime NOT NULL COMMENT '审批时间',
  PRIMARY KEY (`approval_id`),
  KEY `idx_appr_app_id` (`application_id`),
  KEY `idx_appr_user_id` (`user_id`),
  KEY `idx_appr_time` (`approval_time`),
  CONSTRAINT `fk_appr_app` FOREIGN KEY (`application_id`) REFERENCES `loan_application` (`application_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款审批记录表';

-- 18. 贷款合同表
CREATE TABLE IF NOT EXISTS `loan_contract` (
  `contract_id` varchar(50) NOT NULL COMMENT '合同ID',
  `application_id` varchar(50) NOT NULL COMMENT '申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `loan_amount` decimal(18,2) NOT NULL COMMENT '贷款金额',
  `term_months` int NOT NULL COMMENT '期限月',
  `interest_rate` decimal(5,4) NOT NULL COMMENT '年利率',
  `monthly_payment` decimal(18,2) DEFAULT NULL COMMENT '月还款额',
  `contract_status` enum('正常','关注','次级','可疑','损失','已结清') DEFAULT '正常' COMMENT '贷款五级分类',
  `sign_time` datetime NOT NULL COMMENT '签约时间',
  `start_date` date NOT NULL COMMENT '合同生效日',
  `end_date` date NOT NULL COMMENT '合同到期日',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`contract_id`),
  KEY `idx_ctr_app_id` (`application_id`),
  KEY `idx_ctr_user_id` (`user_id`),
  KEY `idx_ctr_status` (`contract_status`),
  KEY `idx_ctr_dates` (`start_date`,`end_date`),
  CONSTRAINT `fk_ctr_app` FOREIGN KEY (`application_id`) REFERENCES `loan_application` (`application_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款合同表';

-- 19. 还款记录表
CREATE TABLE IF NOT EXISTS `loan_repayment` (
  `repayment_id` bigint NOT NULL AUTO_INCREMENT,
  `contract_id` varchar(50) NOT NULL,
  `user_id` varchar(50) NOT NULL,
  `due_date` date NOT NULL,
  `due_amount` decimal(18,2) NOT NULL,
  `paid_amount` decimal(18,2) DEFAULT 0,
  `paid_date` date DEFAULT NULL,
  `payment_status` enum('未还','部分还','已还清','逾期') DEFAULT '未还',
  `overdue_days` int DEFAULT 0,
  PRIMARY KEY (`repayment_id`),
  KEY `idx_repay_contract_id` (`contract_id`),
  KEY `idx_repay_user_id` (`user_id`),
  KEY `idx_repay_due_date` (`due_date`),
  KEY `idx_repay_status` (`payment_status`),
  CONSTRAINT `fk_repay_ctr` FOREIGN KEY (`contract_id`) REFERENCES `loan_contract` (`contract_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='还款记录表';

-- 20. 多头借贷记录表
CREATE TABLE IF NOT EXISTS `loan_multi_platform` (
  `multi_id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` varchar(50) NOT NULL,
  `institution_name` varchar(200) NOT NULL,
  `loan_amount` decimal(18,2) NOT NULL,
  `loan_date` date NOT NULL,
  `loan_status` enum('正常','已结清','逾期') NOT NULL,
  `report_source` enum('征信报告','行内查询','第三方') NOT NULL,
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`multi_id`),
  KEY `idx_multi_user_id` (`user_id`),
  KEY `idx_multi_loan_date` (`loan_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='多头借贷记录表';

-- 21. 绑卡换卡记录表
CREATE TABLE IF NOT EXISTS `card_bind_record` (
  `bind_id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` varchar(50) NOT NULL,
  `card_id` varchar(50) NOT NULL,
  `bind_type` enum('绑定','解绑','换卡') NOT NULL,
  `bind_ip` varchar(50) DEFAULT NULL,
  `bind_device_id` varchar(50) DEFAULT NULL,
  `bind_city` varchar(30) DEFAULT NULL,
  `bind_time` datetime NOT NULL,
  `unbind_time` datetime DEFAULT NULL,
  PRIMARY KEY (`bind_id`),
  KEY `idx_bind_user_id` (`user_id`),
  KEY `idx_bind_card_id` (`card_id`),
  KEY `idx_bind_time` (`bind_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='绑卡换卡记录表';

-- 22. 信用卡账单表
CREATE TABLE IF NOT EXISTS `credit_card_bill` (
  `bill_id` bigint NOT NULL AUTO_INCREMENT,
  `card_id` varchar(50) NOT NULL,
  `user_id` varchar(50) NOT NULL,
  `bill_month` varchar(7) NOT NULL COMMENT 'YYYY-MM',
  `total_amount` decimal(18,2) NOT NULL,
  `min_payment` decimal(18,2) NOT NULL,
  `paid_amount` decimal(18,2) DEFAULT 0,
  `payment_status` enum('未还','部分还','已还清','逾期') DEFAULT '未还',
  `due_date` date NOT NULL,
  `paid_date` date DEFAULT NULL,
  PRIMARY KEY (`bill_id`),
  KEY `idx_bill_card_id` (`card_id`),
  KEY `idx_bill_user_id` (`user_id`),
  KEY `idx_bill_due_date` (`due_date`),
  KEY `idx_bill_status` (`payment_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='信用卡账单表';

-- 23. 额度变更记录表
CREATE TABLE IF NOT EXISTS `card_limit_change` (
  `change_id` bigint NOT NULL AUTO_INCREMENT,
  `card_id` varchar(50) NOT NULL,
  `old_limit` decimal(18,2) NOT NULL,
  `new_limit` decimal(18,2) NOT NULL,
  `change_type` enum('提额','降额','冻结','解冻') NOT NULL,
  `change_reason` text,
  `operator` varchar(50) DEFAULT NULL,
  `change_time` datetime NOT NULL,
  PRIMARY KEY (`change_id`),
  KEY `idx_limit_card_id` (`card_id`),
  KEY `idx_limit_change_time` (`change_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='额度变更记录表';

-- 24. 密码修改日志表
CREATE TABLE IF NOT EXISTS `password_change_log` (
  `pwd_change_id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` varchar(50) NOT NULL,
  `change_type` enum('修改密码','重置密码','修改手机号') NOT NULL,
  `change_ip` varchar(50) DEFAULT NULL,
  `change_device_id` varchar(50) DEFAULT NULL,
  `change_time` datetime NOT NULL,
  PRIMARY KEY (`pwd_change_id`),
  KEY `idx_pwd_user_id` (`user_id`),
  KEY `idx_pwd_change_time` (`change_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='密码修改日志表';

-- 25. 会话追踪表
CREATE TABLE IF NOT EXISTS `session_tracking` (
  `session_id` varchar(50) NOT NULL,
  `user_id` varchar(50) NOT NULL,
  `login_time` datetime NOT NULL,
  `logout_time` datetime DEFAULT NULL,
  `ip_list` text COMMENT 'IP变更JSON',
  `device_id` varchar(50) DEFAULT NULL,
  `is_active` tinyint DEFAULT 1,
  `ip_change_count` int DEFAULT 0,
  PRIMARY KEY (`session_id`),
  KEY `idx_session_user_id` (`user_id`),
  KEY `idx_session_active` (`is_active`),
  KEY `idx_session_login_time` (`login_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='会话追踪表';

-- 26. 大额可疑交易报告表
CREATE TABLE IF NOT EXISTS `txn_suspicious_report` (
  `report_id` bigint NOT NULL AUTO_INCREMENT,
  `txn_id` varchar(50) NOT NULL,
  `user_id` varchar(50) NOT NULL,
  `report_type` enum('大额','可疑') NOT NULL,
  `amount` decimal(18,2) NOT NULL,
  `trigger_rule` varchar(50) DEFAULT NULL COMMENT 'R001-R031',
  `report_status` enum('待上报','已上报','已反馈') DEFAULT '待上报',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `submit_time` datetime DEFAULT NULL,
  PRIMARY KEY (`report_id`),
  KEY `idx_report_txn_id` (`txn_id`),
  KEY `idx_report_user_id` (`user_id`),
  KEY `idx_report_type_status` (`report_type`,`report_status`),
  KEY `idx_report_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='大额可疑交易报告表';

-- 27. 资金拆分链路追踪表
CREATE TABLE IF NOT EXISTS `txn_split_chain` (
  `chain_id` bigint NOT NULL AUTO_INCREMENT,
  `root_txn_id` varchar(50) NOT NULL,
  `from_card` varchar(50) NOT NULL,
  `to_card` varchar(50) NOT NULL,
  `amount` decimal(18,2) NOT NULL,
  `split_level` int NOT NULL,
  `split_time` datetime NOT NULL,
  PRIMARY KEY (`chain_id`),
  KEY `idx_split_root_txn` (`root_txn_id`),
  KEY `idx_split_to_card` (`to_card`),
  KEY `idx_split_time` (`split_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='资金拆分链路追踪表';

-- 28. 用户日交易聚合表
CREATE TABLE IF NOT EXISTS `txn_agg_daily` (
  `agg_id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` varchar(50) NOT NULL,
  `agg_date` date NOT NULL,
  `txn_count` int DEFAULT 0,
  `total_amount` decimal(18,2) DEFAULT 0,
  `avg_amount` decimal(18,2) DEFAULT 0,
  `max_amount` decimal(18,2) DEFAULT 0,
  `min_amount` decimal(18,2) DEFAULT 0,
  `card_count` int DEFAULT 0,
  `city_count` int DEFAULT 0,
  `device_count` int DEFAULT 0,
  `counterparty_count` int DEFAULT 0,
  `night_txn_count` int DEFAULT 0,
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`agg_id`),
  UNIQUE KEY `idx_agg_user_date` (`user_id`,`agg_date`),
  KEY `idx_agg_date` (`agg_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户日交易聚合表';

-- 29. 欺诈案件记录表
CREATE TABLE IF NOT EXISTS `fraud_case_record` (
  `fraud_case_id` bigint NOT NULL AUTO_INCREMENT,
  `fraud_scenario` enum('F1','F2','F3','F4','F5','F6','F7','F8','F9','F10') NOT NULL,
  `user_id` varchar(50) NOT NULL,
  `involved_amount` decimal(18,2) NOT NULL,
  `report_source` enum('行内风控','客户投诉','公安通报','监管移送','同业通报') NOT NULL,
  `report_time` datetime NOT NULL,
  `case_status` enum('调查中','已结案','已移送') DEFAULT '调查中',
  `remark` text,
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`fraud_case_id`),
  KEY `idx_fraud_user_id` (`user_id`),
  KEY `idx_fraud_scenario` (`fraud_scenario`),
  KEY `idx_fraud_report_time` (`report_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='欺诈案件记录表';

-- 30. 监管报送记录表
CREATE TABLE IF NOT EXISTS `regulatory_report` (
  `regulatory_id` bigint NOT NULL AUTO_INCREMENT,
  `reg_type` enum('大额交易报告','可疑交易报告','客户风险等级') NOT NULL,
  `ref_id` varchar(50) NOT NULL,
  `report_content` text NOT NULL,
  `report_status` enum('待生成','已生成','已上报','已反馈','补正') DEFAULT '待生成',
  `submit_time` datetime DEFAULT NULL,
  `feedback_time` datetime DEFAULT NULL,
  `feedback_result` varchar(100) DEFAULT NULL,
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`regulatory_id`),
  KEY `idx_reg_ref_id` (`ref_id`),
  KEY `idx_reg_type_status` (`reg_type`,`report_status`),
  KEY `idx_reg_submit_time` (`submit_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='监管报送记录表';

SET FOREIGN_KEY_CHECKS = 1;

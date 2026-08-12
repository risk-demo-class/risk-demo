-- ============================================
-- 银行信贷风控系统 - 业务表 DDL 初始化脚本
-- 创建 17 张银行业务表 (按外键依赖顺序)
-- 与 app/models_business.py 一一对应
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 客户主档 (无业务外键)
-- ============================

-- 1. 借款人主档表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `gender` enum('男','女','未知') NOT NULL DEFAULT '未知' COMMENT '性别',
  `birth_date` date NOT NULL COMMENT '出生日期',
  `age` int NOT NULL COMMENT '年龄(冗余, 特征直接用)',
  `id_card_hash` varchar(64) NOT NULL COMMENT '身份证号SHA256哈希(脱敏)',
  `mobile` varchar(20) NOT NULL COMMENT '手机号',
  `marital_status` enum('未婚','已婚','离异','丧偶','未知') NOT NULL DEFAULT '未知' COMMENT '婚姻状况',
  `education` varchar(20) NOT NULL COMMENT '学历',
  `occupation` varchar(50) NOT NULL COMMENT '职业',
  `employer_name` varchar(100) DEFAULT NULL COMMENT '工作单位',
  `employer_category` varchar(50) DEFAULT NULL COMMENT '单位性质',
  `industry_code` varchar(20) DEFAULT NULL COMMENT '行业代码',
  `household_province` varchar(20) DEFAULT NULL COMMENT '户籍省',
  `household_city` varchar(20) DEFAULT NULL COMMENT '户籍市',
  `household_district` varchar(20) DEFAULT NULL COMMENT '户籍区县',
  `household_address` varchar(200) DEFAULT NULL COMMENT '户籍详细地址',
  `living_province` varchar(20) DEFAULT NULL COMMENT '居住省',
  `living_city` varchar(20) DEFAULT NULL COMMENT '居住市',
  `living_district` varchar(20) DEFAULT NULL COMMENT '居住区县',
  `living_address` varchar(200) DEFAULT NULL COMMENT '居住详细地址',
  `monthly_income` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '申报月收入',
  `verified_income` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '核验后月收入',
  `income_source` enum('受雇','自雇','经营','自由职业','其他') NOT NULL DEFAULT '其他' COMMENT '收入来源',
  `credit_score` int NOT NULL DEFAULT 600 COMMENT '行内信用分(0-1000)',
  `kyc_level` enum('未认证','L1','L2','L3') NOT NULL DEFAULT '未认证' COMMENT 'KYC等级(实名认证深度)',
  `register_at` datetime NOT NULL COMMENT '开户时间',
  `account_age_days` int NOT NULL DEFAULT 0 COMMENT '开户天数(冗余)',
  `is_employee` int NOT NULL DEFAULT 0 COMMENT '是否本行员工(内部欺诈场景)',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uk_user_id_card_hash` (`id_card_hash`),
  UNIQUE KEY `uk_user_mobile` (`mobile`),
  KEY `idx_user_kyc_level` (`kyc_level`),
  KEY `idx_user_register_at` (`register_at`),
  KEY `idx_user_living` (`living_province`,`living_city`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='借款人主档表';

-- 2. 企业经营档案表
CREATE TABLE IF NOT EXISTS `enterprise_info` (
  `ent_id` varchar(50) NOT NULL COMMENT '企业ID',
  `user_id` varchar(50) NOT NULL COMMENT '法定代表人用户ID',
  `ent_name` varchar(100) NOT NULL COMMENT '企业名称',
  `credit_code` varchar(18) NOT NULL COMMENT '统一社会信用代码',
  `legal_person` varchar(50) NOT NULL COMMENT '法定代表人',
  `reg_date` date NOT NULL COMMENT '成立日期',
  `business_years` int NOT NULL DEFAULT 0 COMMENT '经营年限(冗余)',
  `industry` varchar(50) NOT NULL COMMENT '所属行业',
  `reg_capital` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '注册资本',
  `paid_in_capital` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '实缴资本',
  `annual_revenue` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '年营业收入',
  `annual_tax_amount` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '年纳税额',
  `employee_count` int NOT NULL DEFAULT 0 COMMENT '员工人数',
  `operation_status` enum('存续','在业','吊销','注销','迁出') NOT NULL DEFAULT '存续' COMMENT '经营状态',
  `reg_address` varchar(200) DEFAULT NULL COMMENT '注册地址',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`ent_id`),
  UNIQUE KEY `uk_ent_credit_code` (`credit_code`),
  KEY `idx_ent_user_id` (`user_id`),
  CONSTRAINT `enterprise_info_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='企业经营档案表';

-- 3. 银行账户表
CREATE TABLE IF NOT EXISTS `bank_account` (
  `account_id` varchar(50) NOT NULL COMMENT '账户ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `account_no_hash` varchar(64) NOT NULL COMMENT '卡号SHA256哈希(脱敏)',
  `account_no_tail` varchar(4) NOT NULL COMMENT '卡号尾号4位(展示用)',
  `bank_code` varchar(20) NOT NULL COMMENT '开户行联行号',
  `bank_name` varchar(50) NOT NULL COMMENT '开户行名称',
  `account_type` enum('储蓄卡','信用卡','对公账户') NOT NULL COMMENT '账户类型',
  `card_status` enum('正常','冻结','挂失','销户') NOT NULL DEFAULT '正常' COMMENT '卡片状态',
  `credit_limit` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '信用卡额度(储蓄卡为0)',
  `open_time` datetime NOT NULL COMMENT '开户时间',
  `account_age_days` int NOT NULL DEFAULT 0 COMMENT '开户天数(冗余)',
  `is_default` int NOT NULL DEFAULT 0 COMMENT '是否默认还款账户',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`account_id`),
  UNIQUE KEY `uk_account_no_hash` (`account_no_hash`),
  KEY `idx_account_user_id` (`user_id`),
  KEY `idx_account_type` (`account_type`),
  CONSTRAINT `bank_account_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行账户表';

-- ============================
-- 第二层: 贷中核心 (申请/合同)
-- ============================

-- 4. 贷款申请表
CREATE TABLE IF NOT EXISTS `loan_application` (
  `application_id` varchar(50) NOT NULL COMMENT '申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID',
  `product_code` varchar(20) NOT NULL COMMENT '产品编码',
  `product_name` varchar(50) NOT NULL COMMENT '产品名称',
  `apply_amount` decimal(14,2) NOT NULL COMMENT '申请金额',
  `term_months` int NOT NULL COMMENT '期限(月)',
  `purpose` enum('消费','经营','购房','购车','装修','教育','医疗','其他') NOT NULL COMMENT '贷款用途',
  `guarantee_type` enum('信用','抵押','质押','保证','组合') NOT NULL DEFAULT '信用' COMMENT '担保方式',
  `repay_type` enum('等额本息','等额本金','先息后本','一次性还本付息') NOT NULL DEFAULT '等额本息' COMMENT '还款方式',
  `monthly_income` decimal(12,2) NOT NULL COMMENT '申报月收入',
  `monthly_debt` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '月负债',
  `debt_ratio` decimal(5,4) NOT NULL DEFAULT '0.0000' COMMENT '债务收入比DTI=月负债/月收入',
  `apply_time` datetime NOT NULL COMMENT '申请时间',
  `channel` enum('线上APP','网上银行','线下网点','第三方平台') NOT NULL DEFAULT '线上APP' COMMENT '申请渠道',
  `device_id` varchar(50) DEFAULT NULL COMMENT '申请设备ID',
  `ip` varchar(50) DEFAULT NULL COMMENT '申请IP',
  `geo` varchar(50) DEFAULT NULL COMMENT 'IP归属地',
  `status` varchar(20) NOT NULL DEFAULT '进件' COMMENT '申请状态(进件/反欺诈核查/准入授信/审批中/审批通过/审批拒绝/签约/放款/结清)',
  `reject_reason` varchar(200) DEFAULT NULL COMMENT '拒绝原因',
  `approval_amount` decimal(14,2) DEFAULT NULL COMMENT '审批通过金额',
  `approval_rate` decimal(8,4) DEFAULT NULL COMMENT '审批年化利率',
  `is_repay_plan_generated` int NOT NULL DEFAULT 0 COMMENT '是否已生成还款计划',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`application_id`),
  KEY `idx_loan_app_user_time` (`user_id`,`apply_time`),
  KEY `idx_loan_app_status` (`status`),
  KEY `idx_loan_app_product` (`product_code`),
  KEY `idx_loan_app_device` (`device_id`),
  KEY `idx_loan_app_ip` (`ip`),
  KEY `idx_loan_app_time` (`apply_time`),
  CONSTRAINT `loan_application_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请表';

-- 5. 贷款合同表
CREATE TABLE IF NOT EXISTS `loan_contract` (
  `contract_id` varchar(50) NOT NULL COMMENT '合同ID',
  `application_id` varchar(50) NOT NULL COMMENT '申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID',
  `contract_no` varchar(50) NOT NULL COMMENT '合同编号',
  `product_code` varchar(20) NOT NULL COMMENT '产品编码(冗余)',
  `product_name` varchar(50) NOT NULL COMMENT '产品名称(冗余)',
  `loan_amount` decimal(14,2) NOT NULL COMMENT '放款金额',
  `interest_rate` decimal(8,4) NOT NULL COMMENT '年化利率',
  `term_months` int NOT NULL COMMENT '期限(月)',
  `repay_type` enum('等额本息','等额本金','先息后本','一次性还本付息') NOT NULL COMMENT '还款方式',
  `disbursement_date` date NOT NULL COMMENT '放款日期',
  `maturity_date` date NOT NULL COMMENT '到期日期',
  `repay_account_id` varchar(50) DEFAULT NULL COMMENT '还款账户ID',
  `disbursement_account_id` varchar(50) DEFAULT NULL COMMENT '放款账户ID',
  `is_trustee_payment` int NOT NULL DEFAULT 0 COMMENT '是否受托支付',
  `trustee_payee` varchar(100) DEFAULT NULL COMMENT '受托支付收款人',
  `status` varchar(20) NOT NULL DEFAULT '正常' COMMENT '合同状态(正常/逾期/结清/核销/不良)',
  `overdue_days` int NOT NULL DEFAULT 0 COMMENT '当前最长逾期天数',
  `current_overdue_amount` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '当前逾期金额',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`contract_id`),
  UNIQUE KEY `uk_contract_application` (`application_id`),
  UNIQUE KEY `uk_contract_no` (`contract_no`),
  KEY `idx_contract_user_id` (`user_id`),
  KEY `idx_contract_repay_account` (`repay_account_id`),
  KEY `idx_contract_status` (`status`),
  KEY `idx_contract_disburse_date` (`disbursement_date`),
  CONSTRAINT `loan_contract_ibfk_1` FOREIGN KEY (`application_id`) REFERENCES `loan_application` (`application_id`),
  CONSTRAINT `loan_contract_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `loan_contract_ibfk_3` FOREIGN KEY (`repay_account_id`) REFERENCES `bank_account` (`account_id`),
  CONSTRAINT `loan_contract_ibfk_4` FOREIGN KEY (`disbursement_account_id`) REFERENCES `bank_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款合同表';

-- ============================
-- 第三层: 贷后 (还款计划/流水)
-- ============================

-- 6. 还款计划表
CREATE TABLE IF NOT EXISTS `repayment_plan` (
  `plan_id` varchar(50) NOT NULL COMMENT '还款计划ID',
  `contract_id` varchar(50) NOT NULL COMMENT '合同ID',
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID(冗余, 特征直接用)',
  `period_no` int NOT NULL COMMENT '期数(第N期)',
  `due_date` date NOT NULL COMMENT '应还日期',
  `principal` decimal(14,2) NOT NULL COMMENT '应还本金',
  `interest` decimal(14,2) NOT NULL COMMENT '应还利息',
  `total_due` decimal(14,2) NOT NULL COMMENT '应还总额',
  `status` varchar(20) NOT NULL DEFAULT '未到期' COMMENT '状态(未到期/待还/已还/逾期)',
  `overdue_days` int NOT NULL DEFAULT 0 COMMENT '逾期天数',
  `actual_repay_date` date DEFAULT NULL COMMENT '实际还款日期',
  `actual_repay_amount` decimal(14,2) DEFAULT NULL COMMENT '实际还款金额',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`plan_id`),
  UNIQUE KEY `uk_plan_contract_period` (`contract_id`,`period_no`),
  KEY `idx_plan_user_status` (`user_id`,`status`),
  KEY `idx_plan_due_date` (`due_date`),
  KEY `idx_plan_status` (`status`),
  CONSTRAINT `repayment_plan_ibfk_1` FOREIGN KEY (`contract_id`) REFERENCES `loan_contract` (`contract_id`),
  CONSTRAINT `repayment_plan_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='还款计划表';

-- 7. 还款流水表
CREATE TABLE IF NOT EXISTS `repayment_record` (
  `record_id` varchar(50) NOT NULL COMMENT '还款记录ID',
  `contract_id` varchar(50) NOT NULL COMMENT '合同ID',
  `plan_id` varchar(50) DEFAULT NULL COMMENT '还款计划ID',
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID(冗余)',
  `repay_amount` decimal(14,2) NOT NULL COMMENT '还款总额',
  `principal_part` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '还本部分',
  `interest_part` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '还息部分',
  `penalty_part` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '罚息部分',
  `channel` varchar(20) NOT NULL DEFAULT '自动扣款' COMMENT '还款渠道',
  `repay_time` datetime NOT NULL COMMENT '还款时间',
  `is_success` int NOT NULL DEFAULT 1 COMMENT '是否成功',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`record_id`),
  KEY `idx_repay_user_time` (`user_id`,`repay_time`),
  KEY `idx_repay_contract` (`contract_id`),
  KEY `idx_repay_plan` (`plan_id`),
  KEY `idx_repay_success` (`is_success`),
  CONSTRAINT `repayment_record_ibfk_1` FOREIGN KEY (`contract_id`) REFERENCES `loan_contract` (`contract_id`),
  CONSTRAINT `repayment_record_ibfk_2` FOREIGN KEY (`plan_id`) REFERENCES `repayment_plan` (`plan_id`),
  CONSTRAINT `repayment_record_ibfk_3` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='还款流水表';

-- ============================
-- 第四层: 贷前风控 (征信/收入核验/抵押/担保)
-- ============================

-- 8. 征信报告快照表
CREATE TABLE IF NOT EXISTS `credit_report` (
  `report_id` varchar(50) NOT NULL COMMENT '征信报告ID',
  `application_id` varchar(50) NOT NULL COMMENT '关联申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID',
  `report_date` date NOT NULL COMMENT '报告日期',
  `credit_score` int NOT NULL COMMENT '征信分(0-1000)',
  `overdue_24m_count` int NOT NULL DEFAULT 0 COMMENT '近24月累计逾期次数',
  `overdue_24m_max_days` int NOT NULL DEFAULT 0 COMMENT '近24月最长逾期月数',
  `current_overdue_count` int NOT NULL DEFAULT 0 COMMENT '当前逾期账户数',
  `current_overdue_amount` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '当前逾期金额',
  `five_level_class` varchar(10) NOT NULL DEFAULT '正常' COMMENT '五级分类(正常/关注/次级/可疑/损失)',
  `has_judgement` int NOT NULL DEFAULT 0 COMMENT '是否涉诉',
  `is_executed` int NOT NULL DEFAULT 0 COMMENT '是否被执行人',
  `is_discredited` int NOT NULL DEFAULT 0 COMMENT '是否失信被执行人',
  `is_daichang` int NOT NULL DEFAULT 0 COMMENT '是否代偿',
  `guarantee_amount` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '对外担保余额',
  `outstanding_loan_count` int NOT NULL DEFAULT 0 COMMENT '未结清贷款笔数',
  `credit_card_count` int NOT NULL DEFAULT 0 COMMENT '未销户信用卡数',
  `recent_6m_hard_query_count` int NOT NULL DEFAULT 0 COMMENT '近6月硬查询次数(贷款审批/信用卡审批)',
  `recent_1m_query_count` int NOT NULL DEFAULT 0 COMMENT '近1月查询次数',
  `open_account_count` int NOT NULL DEFAULT 0 COMMENT '已开立账户数',
  `settled_account_count` int NOT NULL DEFAULT 0 COMMENT '已结清账户数',
  `first_loan_date` date DEFAULT NULL COMMENT '首笔贷款日期',
  `loan_history_years` decimal(4,1) NOT NULL DEFAULT '0.0' COMMENT '征信历史年限',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`report_id`),
  KEY `idx_credit_user_report` (`user_id`,`report_date`),
  KEY `idx_credit_application` (`application_id`),
  KEY `idx_credit_report_date` (`report_date`),
  CONSTRAINT `credit_report_ibfk_1` FOREIGN KEY (`application_id`) REFERENCES `loan_application` (`application_id`),
  CONSTRAINT `credit_report_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='征信报告快照表';

-- 9. 收入三源交叉核验表
CREATE TABLE IF NOT EXISTS `income_verify` (
  `verify_id` varchar(50) NOT NULL COMMENT '核验ID',
  `application_id` varchar(50) NOT NULL COMMENT '关联申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID',
  `declared_monthly_income` decimal(12,2) NOT NULL COMMENT '申报月收入',
  `salary_proof_income` decimal(12,2) DEFAULT NULL COMMENT '收入证明月收入',
  `bank_flow_avg_income` decimal(12,2) DEFAULT NULL COMMENT '银行流水月均入账',
  `tax_proof_income` decimal(12,2) DEFAULT NULL COMMENT '完税证明推算月收入',
  `verified_monthly_income` decimal(12,2) NOT NULL COMMENT '核验后月收入',
  `has_payroll_record` int NOT NULL DEFAULT 0 COMMENT '是否有代发工资记录',
  `bank_flow_min_balance_3m` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '近3月账户最低余额',
  `bank_flow_total_in_6m` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '近6月入账总额',
  `cross_check_result` varchar(20) NOT NULL DEFAULT '一致' COMMENT '三源交叉结果(一致/轻微偏差/显著偏差/无法核验)',
  `verify_time` datetime NOT NULL COMMENT '核验时间',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`verify_id`),
  KEY `idx_income_verify_app` (`application_id`),
  KEY `idx_income_verify_user` (`user_id`),
  CONSTRAINT `income_verify_ibfk_1` FOREIGN KEY (`application_id`) REFERENCES `loan_application` (`application_id`),
  CONSTRAINT `income_verify_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='收入三源交叉核验表';

-- 10. 抵押物质押表
CREATE TABLE IF NOT EXISTS `collateral` (
  `collateral_id` varchar(50) NOT NULL COMMENT '抵押物ID',
  `application_id` varchar(50) NOT NULL COMMENT '关联申请ID',
  `contract_id` varchar(50) DEFAULT NULL COMMENT '关联合同ID',
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID',
  `collateral_type` enum('不动产','车辆','存单','应收账款','其他') NOT NULL COMMENT '抵押物类型',
  `cert_no` varchar(50) NOT NULL COMMENT '权证编号(不动产权证号/VIN/存单号)',
  `cert_no_hash` varchar(64) NOT NULL COMMENT '权证编号哈希(一房多贷查重)',
  `property_address` varchar(200) DEFAULT NULL COMMENT '不动产地址',
  `owner_name` varchar(50) DEFAULT NULL COMMENT '权利人姓名',
  `eval_value` decimal(14,2) NOT NULL COMMENT '评估价值',
  `mortgage_rate` decimal(5,4) NOT NULL DEFAULT '0.7000' COMMENT '抵押率=贷款金额/评估价值',
  `query_status` varchar(20) NOT NULL DEFAULT '无查封' COMMENT '不动产查询结果(无查封/已查封/已抵押/重复抵押)',
  `pledge_time` date DEFAULT NULL COMMENT '抵押设立日期',
  `release_time` date DEFAULT NULL COMMENT '解押日期',
  `status` varchar(20) NOT NULL DEFAULT '在押' COMMENT '状态(在押/已解押)',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`collateral_id`),
  KEY `idx_collateral_cert_hash` (`cert_no_hash`),
  KEY `idx_collateral_user` (`user_id`),
  KEY `idx_collateral_application` (`application_id`),
  CONSTRAINT `collateral_ibfk_1` FOREIGN KEY (`application_id`) REFERENCES `loan_application` (`application_id`),
  CONSTRAINT `collateral_ibfk_2` FOREIGN KEY (`contract_id`) REFERENCES `loan_contract` (`contract_id`),
  CONSTRAINT `collateral_ibfk_3` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='抵押物质押表';

-- 11. 担保关系表
CREATE TABLE IF NOT EXISTS `guarantee` (
  `guarantee_id` varchar(50) NOT NULL COMMENT '担保ID',
  `contract_id` varchar(50) NOT NULL COMMENT '合同ID',
  `user_id` varchar(50) NOT NULL COMMENT '借款人ID',
  `guarantor_id` varchar(50) NOT NULL COMMENT '担保人用户ID',
  `guarantor_name` varchar(50) NOT NULL COMMENT '担保人姓名(冗余)',
  `guarantee_type` enum('连带责任保证','一般保证','抵押担保','质押担保') NOT NULL COMMENT '担保方式',
  `guarantee_amount` decimal(14,2) NOT NULL COMMENT '担保金额',
  `relation_type` varchar(20) NOT NULL DEFAULT '亲属' COMMENT '与借款人关系(亲属/同事/朋友/互保/关联企业/其他)',
  `sign_time` date NOT NULL COMMENT '签署日期',
  `status` varchar(20) NOT NULL DEFAULT '有效' COMMENT '状态(有效/解除/履行完毕/代偿中)',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`guarantee_id`),
  KEY `idx_guarantee_user` (`user_id`),
  KEY `idx_guarantee_guarantor` (`guarantor_id`),
  KEY `idx_guarantee_contract` (`contract_id`),
  CONSTRAINT `guarantee_ibfk_1` FOREIGN KEY (`contract_id`) REFERENCES `loan_contract` (`contract_id`),
  CONSTRAINT `guarantee_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `guarantee_ibfk_3` FOREIGN KEY (`guarantor_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='担保关系表';

-- ============================
-- 第五层: 账户/设备/行为
-- ============================

-- 12. 账户交易流水表
CREATE TABLE IF NOT EXISTS `transaction` (
  `txn_id` varchar(50) NOT NULL COMMENT '交易ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `from_account_id` varchar(50) DEFAULT NULL COMMENT '转出账户ID',
  `to_account_id` varchar(50) DEFAULT NULL COMMENT '转入账户ID(取现/消费可为空)',
  `counterparty_name` varchar(100) DEFAULT NULL COMMENT '对手方名称',
  `amount` decimal(14,2) NOT NULL COMMENT '交易金额',
  `txn_type` enum('转账','消费','取现','代扣','理财','还款','工资入账','退款','其他') NOT NULL COMMENT '交易类型',
  `channel` varchar(30) NOT NULL DEFAULT '手机银行' COMMENT '交易渠道',
  `txn_time` datetime NOT NULL COMMENT '交易时间',
  `device_id` varchar(50) DEFAULT NULL COMMENT '设备ID',
  `ip` varchar(50) DEFAULT NULL COMMENT 'IP',
  `geo` varchar(50) DEFAULT NULL COMMENT 'IP归属地',
  `is_suspicious` int NOT NULL DEFAULT 0 COMMENT '异常标记(资金回流/涉赌涉诈)',
  `remark` varchar(200) DEFAULT NULL COMMENT '备注',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`txn_id`),
  KEY `idx_txn_from_time` (`from_account_id`,`txn_time`),
  KEY `idx_txn_to_time` (`to_account_id`,`txn_time`),
  KEY `idx_txn_user_time` (`user_id`,`txn_time`),
  KEY `idx_txn_device` (`device_id`),
  KEY `idx_txn_ip` (`ip`),
  KEY `idx_txn_time` (`txn_time`),
  CONSTRAINT `transaction_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `transaction_ibfk_2` FOREIGN KEY (`from_account_id`) REFERENCES `bank_account` (`account_id`),
  CONSTRAINT `transaction_ibfk_3` FOREIGN KEY (`to_account_id`) REFERENCES `bank_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='账户交易流水表';

-- 13. 登录日志表
CREATE TABLE IF NOT EXISTS `login_log` (
  `login_id` varchar(50) NOT NULL COMMENT '登录ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `device_id` varchar(50) DEFAULT NULL COMMENT '设备ID',
  `ip` varchar(50) DEFAULT NULL COMMENT '登录IP',
  `geo` varchar(50) DEFAULT NULL COMMENT 'IP归属地',
  `channel` varchar(20) NOT NULL DEFAULT 'APP' COMMENT '登录渠道',
  `success` int NOT NULL DEFAULT 1 COMMENT '是否成功',
  `login_time` datetime NOT NULL COMMENT '登录时间',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`login_id`),
  KEY `idx_login_user_time` (`user_id`,`login_time`),
  KEY `idx_login_device` (`device_id`),
  KEY `idx_login_ip` (`ip`),
  KEY `idx_login_time` (`login_time`),
  CONSTRAINT `login_log_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='登录日志表';

-- 14. 设备指纹表
CREATE TABLE IF NOT EXISTS `device_fingerprint` (
  `device_id` varchar(50) NOT NULL COMMENT '设备ID',
  `user_id` varchar(50) NOT NULL COMMENT '所属用户ID',
  `fingerprint_hash` varchar(64) NOT NULL COMMENT '设备指纹哈希',
  `os` varchar(50) NOT NULL COMMENT '操作系统',
  `browser` varchar(50) DEFAULT NULL COMMENT '浏览器',
  `device_type` varchar(20) NOT NULL DEFAULT '手机' COMMENT '设备类型(手机/平板/PC)',
  `is_root` int NOT NULL DEFAULT 0 COMMENT '是否Root/越狱',
  `mac_hash` varchar(64) DEFAULT NULL COMMENT 'MAC哈希',
  `imei_hash` varchar(64) DEFAULT NULL COMMENT 'IMEI哈希',
  `first_seen` datetime NOT NULL COMMENT '首次出现时间',
  `last_seen` datetime NOT NULL COMMENT '最近出现时间',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`device_id`),
  KEY `idx_device_user` (`user_id`),
  KEY `idx_device_fp_hash` (`fingerprint_hash`),
  CONSTRAINT `device_fingerprint_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

-- 15. IP 地理库表
CREATE TABLE IF NOT EXISTS `ip_geo_location` (
  `ip` varchar(50) NOT NULL COMMENT 'IP地址',
  `country` varchar(20) NOT NULL DEFAULT '中国' COMMENT '国家',
  `province` varchar(20) NOT NULL COMMENT '省份',
  `city` varchar(20) NOT NULL COMMENT '城市',
  `isp` varchar(30) NOT NULL COMMENT '运营商',
  `is_proxy` int NOT NULL DEFAULT 0 COMMENT '是否代理IP',
  `is_tor` int NOT NULL DEFAULT 0 COMMENT '是否Tor出口',
  `is_mobile` int NOT NULL DEFAULT 0 COMMENT '是否移动网络',
  `is_abroad` int NOT NULL DEFAULT 0 COMMENT '是否境外IP',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP地理库表';

-- ============================
-- 第六层: 反欺诈 (黑名单/关联图谱)
-- ============================

-- 16. 银行业务黑名单扩展表
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `type` enum('设备指纹','IP','银行卡号','身份证号','手机号','对公账户','统一社会信用代码') NOT NULL COMMENT '黑名单类型',
  `value` varchar(200) NOT NULL COMMENT '黑名单值(敏感值存哈希)',
  `reason` varchar(200) DEFAULT NULL COMMENT '加入原因',
  `source` varchar(50) NOT NULL DEFAULT '内部案件' COMMENT '来源',
  `expire_time` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`entry_id`),
  KEY `idx_blacklist_type_value` (`type`,`value`),
  KEY `idx_blacklist_expire` (`expire_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行业务黑名单扩展表';

-- 17. 用户关联关系表
CREATE TABLE IF NOT EXISTS `user_relation` (
  `relation_id` varchar(50) NOT NULL COMMENT '关系ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID(A)',
  `related_user_id` varchar(50) NOT NULL COMMENT '关联用户ID(B)',
  `relation_type` varchar(20) NOT NULL COMMENT '关系类型(共享设备/共享手机/共享地址/亲属/同事/互保/资金往来/共享收款账户)',
  `detail_value` varchar(100) DEFAULT NULL COMMENT '共享的具体值(device_id/手机号/地址/账户)',
  `source` varchar(20) NOT NULL DEFAULT '设备' COMMENT '关系来源(设备/担保/交易/申请/外部)',
  `first_seen` datetime NOT NULL COMMENT '首次发现时间',
  `last_seen` datetime NOT NULL COMMENT '最近发现时间',
  `is_active` int NOT NULL DEFAULT 1 COMMENT '是否有效',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`relation_id`),
  KEY `idx_relation_user` (`user_id`),
  KEY `idx_relation_related` (`related_user_id`),
  KEY `idx_relation_type` (`relation_type`),
  KEY `idx_relation_detail` (`detail_value`),
  CONSTRAINT `user_relation_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `user_relation_ibfk_2` FOREIGN KEY (`related_user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户关联关系表';

SET FOREIGN_KEY_CHECKS = 1;

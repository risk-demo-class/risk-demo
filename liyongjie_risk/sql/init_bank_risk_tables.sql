-- ============================================
-- 银行风控系统 - 全部表 DDL 初始化脚本
-- 在 bank_risk 数据库中创建 12 张风控表 (按外键依赖顺序)
-- 覆盖四大场景: 登录 / 转账 / 贷款 / 信用卡
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础维度表 (无外键依赖)
-- ============================

-- 1. 设备指纹表
CREATE TABLE IF NOT EXISTS `device_fingerprint` (
    `device_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '设备 ID',
    `fingerprint_hash` CHAR(64) NOT NULL COMMENT '设备指纹哈希 (SHA-256)',
    `os` VARCHAR(32) DEFAULT NULL COMMENT '操作系统 (iOS/Android/Windows/macOS)',
    `browser` VARCHAR(32) DEFAULT NULL COMMENT '浏览器',
    `is_emulator` TINYINT(1) DEFAULT 0 COMMENT '是否模拟器 (0=否, 1=是)',
    `is_root` TINYINT(1) DEFAULT 0 COMMENT '是否越狱/root (0=否, 1=是)',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '设备状态: 1=正常, 2=高风险, 3=黑名单',
    `first_seen` DATETIME NOT NULL COMMENT '首次出现时间',
    `last_seen` DATETIME NOT NULL COMMENT '最近出现时间',
    PRIMARY KEY (`device_id`),
    UNIQUE INDEX `uk_fingerprint_hash` (`fingerprint_hash`),
    INDEX `idx_device_status` (`status`),
    INDEX `idx_device_last_seen` (`last_seen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

-- 2. IP 地理位置表
CREATE TABLE IF NOT EXISTS `ip_geo_location` (
    `ip` VARCHAR(45) NOT NULL COMMENT 'IP 地址',
    `country` VARCHAR(64) DEFAULT NULL COMMENT '国家',
    `province` VARCHAR(64) DEFAULT NULL COMMENT '省份',
    `city` VARCHAR(64) DEFAULT NULL COMMENT '城市',
    `isp` VARCHAR(32) DEFAULT NULL COMMENT '运营商',
    `is_proxy` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否代理',
    `is_tor` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否 Tor 出口',
    `is_vpn` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否 VPN',
    `is_mobile` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否移动网络',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`ip`),
    INDEX `idx_ip_geo_city` (`city`),
    INDEX `idx_ip_proxy` (`is_proxy`),
    INDEX `idx_ip_tor` (`is_tor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='IP 地理位置表';

-- 3. 黑名单表
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
    `entry_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '名单 ID',
    `type` TINYINT NOT NULL COMMENT '名单类型: 1=设备, 2=IP, 3=银行卡号, 4=身份证, 5=手机号',
    `value` VARCHAR(128) NOT NULL COMMENT '命中值 (哈希或原文)',
    `reason` VARCHAR(256) DEFAULT NULL COMMENT '入单原因',
    `source` VARCHAR(32) NOT NULL DEFAULT '内部' COMMENT '来源: 内部/公安涉诈/法院/同业/外部',
    `risk_level` TINYINT NOT NULL DEFAULT 3 COMMENT '名单风险等级: 1=低, 2=中, 3=高, 4=极高',
    `expire_at` DATETIME DEFAULT NULL COMMENT '过期时间, NULL=永久有效',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1=有效, 0=失效',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`entry_id`),
    INDEX `idx_blacklist_type` (`type`),
    INDEX `idx_blacklist_value` (`value`),
    INDEX `idx_blacklist_status` (`status`),
    INDEX `idx_blacklist_expire` (`expire_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='黑名单扩展表';

-- 4. 规则配置表
CREATE TABLE IF NOT EXISTS `rule_config` (
    `rule_id` VARCHAR(16) NOT NULL COMMENT '规则编号 (R001-R099)',
    `rule_name` VARCHAR(64) NOT NULL COMMENT '规则名称',
    `scene` VARCHAR(16) NOT NULL COMMENT '所属场景: 登录/转账/贷款/信用卡',
    `conditions` JSON NOT NULL COMMENT '条件表达式 (含窗口/阈值)',
    `risk_level` TINYINT NOT NULL COMMENT '风险等级: 1=低, 2=中, 3=高, 4=极高',
    `decision` VARCHAR(16) NOT NULL COMMENT '决策: PASS/CHALLENGE/MANUAL/REJECT',
    `action` VARCHAR(64) DEFAULT NULL COMMENT '处置动作: TAG/LIMIT/FREEZE/STOP_PAYMENT/REPORT',
    `priority` INT NOT NULL DEFAULT 100 COMMENT '优先级, 小者先执行',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1=启用, 0=停用',
    `operator` VARCHAR(32) DEFAULT 'admin' COMMENT '最后操作人',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`rule_id`),
    INDEX `idx_rule_scene` (`scene`),
    INDEX `idx_rule_status` (`status`),
    INDEX `idx_rule_priority` (`priority`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控规则配置表';

-- ============================
-- 第二层: 用户相关表
-- ============================

-- 5. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
    `user_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '用户 ID',
    `name` VARCHAR(64) NOT NULL COMMENT '姓名',
    `id_card_hash` CHAR(64) NOT NULL COMMENT '身份证号哈希 (SHA-256)',
    `phone_hash` CHAR(64) NOT NULL COMMENT '手机号哈希 (SHA-256)',
    `credit_score` INT DEFAULT NULL COMMENT '信用分 (300-850)',
    `kyc_level` TINYINT NOT NULL DEFAULT 1 COMMENT 'KYC 等级: 1=L1要素核验, 2=L2人脸, 3=L3证件上传, 4=L4面签',
    `risk_tag` VARCHAR(128) DEFAULT NULL COMMENT '风险标签 (涉诈/失信/涉案, 逗号分隔)',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1=正常, 2=冻结, 3=止付, 4=销户',
    `register_at` DATETIME NOT NULL COMMENT '注册时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`user_id`),
    UNIQUE INDEX `uk_id_card_hash` (`id_card_hash`),
    UNIQUE INDEX `uk_phone_hash` (`phone_hash`),
    INDEX `idx_user_status` (`status`),
    INDEX `idx_user_risk_tag` (`risk_tag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 6. 用户画像表
CREATE TABLE IF NOT EXISTS `user_profile` (
    `user_id` BIGINT NOT NULL COMMENT '用户 ID',
    `common_city` VARCHAR(64) DEFAULT NULL COMMENT '常用城市',
    `common_device_id` BIGINT DEFAULT NULL COMMENT '常用设备 ID',
    `avg_txn_amount` DECIMAL(18,2) DEFAULT NULL COMMENT '平均单笔交易金额',
    `txn_freq_day` DECIMAL(8,2) DEFAULT NULL COMMENT '日均交易笔数',
    `active_hours` VARCHAR(32) DEFAULT NULL COMMENT '常用活跃时段 (如 9-18)',
    `profile_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '画像更新时间',
    PRIMARY KEY (`user_id`),
    CONSTRAINT `fk_profile_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户画像表';

-- 7. 银行卡表
CREATE TABLE IF NOT EXISTS `bank_card` (
    `card_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '卡 ID',
    `user_id` BIGINT NOT NULL COMMENT '持卡人 ID',
    `card_no_hash` CHAR(64) NOT NULL COMMENT '卡号哈希 (SHA-256)',
    `bank_code` VARCHAR(16) NOT NULL COMMENT '发卡行代码 (ICBC/CCB/ABC/BOC/CMB/...)',
    `card_type` TINYINT NOT NULL COMMENT '卡类型: 1=储蓄卡, 2=信用卡',
    `credit_limit` DECIMAL(18,2) DEFAULT NULL COMMENT '信用卡额度 (信用卡必填)',
    `single_limit` DECIMAL(18,2) NOT NULL DEFAULT 50000.00 COMMENT '单笔限额',
    `daily_limit` DECIMAL(18,2) NOT NULL DEFAULT 200000.00 COMMENT '单日限额',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1=正常, 2=冻结, 3=止付, 4=挂失, 5=销户',
    `open_at` DATETIME NOT NULL COMMENT '开户时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`card_id`),
    UNIQUE INDEX `uk_card_no_hash` (`card_no_hash`),
    INDEX `idx_card_user` (`user_id`),
    INDEX `idx_card_bank` (`bank_code`),
    INDEX `idx_card_status` (`status`),
    CONSTRAINT `fk_card_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡表';

-- ============================
-- 第三层: 业务事件表
-- ============================

-- 8. 登录日志表
CREATE TABLE IF NOT EXISTS `login_log` (
    `login_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '登录 ID',
    `user_id` BIGINT NOT NULL COMMENT '用户 ID',
    `device_id` BIGINT DEFAULT NULL COMMENT '设备 ID',
    `ip` VARCHAR(45) NOT NULL COMMENT '登录 IP',
    `geo` VARCHAR(64) DEFAULT NULL COMMENT '省市 (如 北京-北京市)',
    `success` TINYINT NOT NULL COMMENT '是否成功: 1=成功, 0=失败',
    `fail_reason` VARCHAR(128) DEFAULT NULL COMMENT '失败原因 (密码错/被拒/风控拦截)',
    `login_at` DATETIME NOT NULL COMMENT '登录时间',
    PRIMARY KEY (`login_id`),
    INDEX `idx_login_user_time` (`user_id`, `login_at`),
    INDEX `idx_login_device_time` (`device_id`, `login_at`),
    INDEX `idx_login_ip_time` (`ip`, `login_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='登录日志表';

-- 9. 交易表
CREATE TABLE IF NOT EXISTS `transaction` (
    `txn_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '交易 ID',
    `from_card_id` BIGINT NOT NULL COMMENT '出款卡 ID',
    `to_card_id` BIGINT DEFAULT NULL COMMENT '入款卡 ID (本行卡时填写)',
    `to_card_no_hash` CHAR(64) DEFAULT NULL COMMENT '对手方卡号哈希 (跨行)',
    `to_account_name_hash` CHAR(64) DEFAULT NULL COMMENT '对手方户名哈希 (跨行)',
    `to_bank_code` VARCHAR(16) DEFAULT NULL COMMENT '对手方银行代码 (跨行)',
    `amount` DECIMAL(18,2) NOT NULL COMMENT '交易金额',
    `txn_type` TINYINT NOT NULL COMMENT '交易类型: 1=转账, 2=支付, 3=取现, 4=还款, 5=收款',
    `channel` VARCHAR(16) NOT NULL DEFAULT 'APP' COMMENT '渠道: APP/网银/ATM/POS/第三方',
    `device_id` BIGINT DEFAULT NULL COMMENT '设备 ID',
    `ip` VARCHAR(45) DEFAULT NULL COMMENT '交易 IP',
    `geo` VARCHAR(64) DEFAULT NULL COMMENT '省市',
    `risk_score` DECIMAL(5,2) DEFAULT NULL COMMENT '风控评分 (0-100)',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1=成功, 2=失败, 3=挂起, 4=拒绝',
    `created_at` DATETIME NOT NULL COMMENT '交易时间',
    PRIMARY KEY (`txn_id`),
    INDEX `idx_txn_from_card_time` (`from_card_id`, `created_at`),
    INDEX `idx_txn_to_card_time` (`to_card_id`, `created_at`),
    INDEX `idx_txn_device_time` (`device_id`, `created_at`),
    INDEX `idx_txn_status` (`status`),
    INDEX `idx_txn_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='交易表';

-- 10. 贷款申请表
CREATE TABLE IF NOT EXISTS `loan_application` (
    `loan_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '申请 ID',
    `user_id` BIGINT NOT NULL COMMENT '申请人 ID',
    `amount` DECIMAL(18,2) NOT NULL COMMENT '申请金额',
    `term_months` INT NOT NULL COMMENT '期限（月）',
    `purpose` VARCHAR(32) NOT NULL COMMENT '用途: 消费/经营/购车/装修',
    `monthly_income` DECIMAL(18,2) NOT NULL COMMENT '月收入',
    `debt_ratio` DECIMAL(5,2) NOT NULL COMMENT '负债率 (0.00-1.00)',
    `credit_query_1m` INT DEFAULT 0 COMMENT '近 1 月征信查询次数',
    `credit_query_3m` INT DEFAULT 0 COMMENT '近 3 月征信查询次数',
    `credit_query_6m` INT DEFAULT 0 COMMENT '近 6 月征信查询次数',
    `channel` VARCHAR(16) NOT NULL DEFAULT 'APP' COMMENT '申请渠道',
    `device_id` BIGINT DEFAULT NULL COMMENT '申请设备 ID',
    `ip` VARCHAR(45) DEFAULT NULL COMMENT '申请 IP',
    `geo` VARCHAR(64) DEFAULT NULL COMMENT '省市',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1=待审批, 2=通过, 3=拒绝, 4=人工, 5=已放款, 6=已结清, 7=逾期',
    `applied_at` DATETIME NOT NULL COMMENT '申请时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`loan_id`),
    INDEX `idx_loan_user` (`user_id`),
    INDEX `idx_loan_status` (`status`),
    INDEX `idx_loan_applied_at` (`applied_at`),
    CONSTRAINT `fk_loan_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请表';

-- 11. 风险事件表
CREATE TABLE IF NOT EXISTS `risk_event` (
    `event_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '事件 ID',
    `event_type` VARCHAR(32) NOT NULL COMMENT '事件类型: REGISTER/BIND_CARD/CARD_APPLY/LOAN_APPLY/LIMIT_ADJUST/LOGIN/TRANSFER/PAYMENT/WITHDRAW/REPAY/CHANGE_PWD/CHANGE_PHONE/UPDATE_PROFILE/DISBURSE/OVERDUE/DISPUTE/FROZEN/SAR/REVIEW',
    `user_id` BIGINT DEFAULT NULL COMMENT '用户 ID',
    `card_id` BIGINT DEFAULT NULL COMMENT '卡 ID',
    `device_id` BIGINT DEFAULT NULL COMMENT '设备 ID',
    `ip` VARCHAR(45) DEFAULT NULL COMMENT 'IP 地址',
    `amount` DECIMAL(18,2) DEFAULT NULL COMMENT '金额',
    `rule_ids` VARCHAR(128) DEFAULT NULL COMMENT '命中的规则编号列表 (逗号分隔)',
    `risk_score` DECIMAL(5,2) DEFAULT NULL COMMENT '模型评分 (0-100)',
    `decision` VARCHAR(16) NOT NULL COMMENT '决策结果: PASS/CHALLENGE/MANUAL/REJECT',
    `action` VARCHAR(64) DEFAULT NULL COMMENT '处置动作: TAG/LIMIT/FREEZE/STOP_PAYMENT/REPORT',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '处理状态: 1=待处理, 2=已处理, 3=误报',
    `handler` VARCHAR(32) DEFAULT NULL COMMENT '处理人',
    `handled_at` DATETIME DEFAULT NULL COMMENT '处理时间',
    `remark` VARCHAR(256) DEFAULT NULL COMMENT '处理备注',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件时间',
    PRIMARY KEY (`event_id`),
    INDEX `idx_risk_event_user` (`user_id`),
    INDEX `idx_risk_event_type` (`event_type`),
    INDEX `idx_risk_event_decision` (`decision`),
    INDEX `idx_risk_event_status` (`status`),
    INDEX `idx_risk_event_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风险事件表';

-- ============================
-- 第四层: 关联表
-- ============================

-- 12. 设备用户关联表 (多对多)
CREATE TABLE IF NOT EXISTS `device_user_rel` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增 ID',
    `device_id` BIGINT NOT NULL COMMENT '设备 ID',
    `user_id` BIGINT NOT NULL COMMENT '用户 ID',
    `rel_type` TINYINT NOT NULL DEFAULT 1 COMMENT '关联类型: 1=登录, 2=交易, 3=申请',
    `first_seen` DATETIME NOT NULL COMMENT '首次关联时间',
    `last_seen` DATETIME NOT NULL COMMENT '最近关联时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_device_user` (`device_id`, `user_id`),
    INDEX `idx_rel_device` (`device_id`),
    INDEX `idx_rel_user` (`user_id`),
    CONSTRAINT `fk_rel_device` FOREIGN KEY (`device_id`) REFERENCES `device_fingerprint` (`device_id`),
    CONSTRAINT `fk_rel_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备用户关联表 (多对多)';

SET FOREIGN_KEY_CHECKS = 1;

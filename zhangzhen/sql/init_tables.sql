-- 由 scripts/export_mysql_ddl.py 从 SQLAlchemy ORM 自动生成

-- 8 张银行业务表 + 9 张风控核心表

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `bank_risk` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

USE `bank_risk`;

CREATE TABLE IF NOT EXISTS customer_info (
	user_id VARCHAR(50) NOT NULL COMMENT '客户ID', 
	name_hash VARCHAR(128) NOT NULL COMMENT '姓名哈希', 
	id_card_hash VARCHAR(128) NOT NULL COMMENT '身份证哈希', 
	mobile_hash VARCHAR(128) NOT NULL COMMENT '手机号哈希', 
	credit_score INTEGER NOT NULL COMMENT '模拟信用分', 
	kyc_level ENUM('L1','L2','L3') NOT NULL COMMENT '身份核验等级', 
	monthly_income NUMERIC(14, 2) NOT NULL COMMENT '月收入(演示数据)', 
	home_city VARCHAR(50) NOT NULL COMMENT '常驻城市', 
	register_at DATETIME NOT NULL COMMENT '注册时间', 
	status ENUM('NORMAL','FROZEN','CLOSED') NOT NULL COMMENT '客户状态', 
	CONSTRAINT pk_customer_info PRIMARY KEY (user_id), 
	CONSTRAINT ck_customer_info_credit_score_range CHECK (credit_score BETWEEN 300 AND 850), 
	CONSTRAINT ck_customer_info_monthly_income_non_negative CHECK (monthly_income >= 0), 
	CONSTRAINT uq_customer_info_id_card_hash UNIQUE (id_card_hash)
);

CREATE INDEX idx_customer_mobile_hash ON customer_info (mobile_hash);

CREATE INDEX idx_customer_register_at ON customer_info (register_at);

CREATE TABLE IF NOT EXISTS ip_geo_location (
	ip VARCHAR(64) NOT NULL COMMENT '演示IP', 
	country VARCHAR(50) NOT NULL COMMENT '国家', 
	province VARCHAR(50) NOT NULL COMMENT '省份', 
	city VARCHAR(50) NOT NULL COMMENT '城市', 
	isp VARCHAR(100) NOT NULL COMMENT '运营商', 
	is_proxy BOOL NOT NULL COMMENT '是否代理', 
	is_tor BOOL NOT NULL COMMENT '是否Tor出口', 
	risk_score INTEGER NOT NULL COMMENT 'IP风险分', 
	updated_at DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	CONSTRAINT pk_ip_geo_location PRIMARY KEY (ip), 
	CONSTRAINT ck_ip_geo_location_risk_score_range CHECK (risk_score BETWEEN 0 AND 100)
);

CREATE TABLE IF NOT EXISTS risk_action_log (
	log_id BIGINT NOT NULL COMMENT '日志ID' AUTO_INCREMENT, 
	operator VARCHAR(50) NOT NULL COMMENT '操作人', 
	action_type ENUM('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST','HANDLE_ALERT','RESOLVE_ALERT','IGNORE_ALERT') NOT NULL COMMENT '操作类型', 
	target_type ENUM('rule','case','blacklist','alert') NOT NULL COMMENT '对象类型', 
	target_id VARCHAR(50) NOT NULL COMMENT '对象ID', 
	before_value JSON COMMENT '变更前', 
	after_value JSON COMMENT '变更后', 
	ip VARCHAR(50) COMMENT '操作IP', 
	remark VARCHAR(500) COMMENT '备注', 
	create_time DATETIME NOT NULL COMMENT '操作时间' DEFAULT now(), 
	CONSTRAINT pk_risk_action_log PRIMARY KEY (log_id)
);

CREATE INDEX idx_action_log_create_time ON risk_action_log (create_time);

CREATE INDEX idx_action_log_operator ON risk_action_log (operator);

CREATE INDEX idx_action_log_target ON risk_action_log (target_type, target_id);

CREATE TABLE IF NOT EXISTS risk_alert (
	alert_id BIGINT NOT NULL COMMENT '告警ID' AUTO_INCREMENT, 
	alert_type ENUM('BUSINESS','MODEL','SYSTEM','SECURITY') NOT NULL COMMENT '告警分类', 
	alert_level ENUM('P0','P1','P2','P3') NOT NULL COMMENT '告警等级', 
	alert_title VARCHAR(200) NOT NULL COMMENT '告警标题', 
	alert_content TEXT COMMENT '告警详情', 
	metric_name VARCHAR(100) COMMENT '指标名', 
	metric_value NUMERIC(20, 6) COMMENT '触发值', 
	threshold NUMERIC(20, 6) COMMENT '阈值', 
	status ENUM('PENDING','HANDLING','RESOLVED','IGNORED') NOT NULL COMMENT '处理状态' DEFAULT 'PENDING', 
	handler VARCHAR(50) COMMENT '处理人', 
	resolve_time DATETIME COMMENT '解决时间', 
	create_time DATETIME NOT NULL COMMENT '告警时间' DEFAULT now(), 
	CONSTRAINT pk_risk_alert PRIMARY KEY (alert_id)
);

CREATE INDEX idx_alert_create_time ON risk_alert (create_time);

CREATE INDEX idx_alert_level ON risk_alert (alert_level);

CREATE INDEX idx_alert_status ON risk_alert (status);

CREATE TABLE IF NOT EXISTS risk_blacklist (
	blacklist_id BIGINT NOT NULL COMMENT '黑名单ID' AUTO_INCREMENT, 
	blacklist_type ENUM('用户','身份证','银行账户','银行卡','收款账户','设备指纹','IP','手机号') NOT NULL COMMENT '银行黑名单类型', 
	blacklist_value VARCHAR(200) NOT NULL COMMENT '对象ID、哈希值或脱敏值', 
	reason TEXT COMMENT '加入原因', 
	expire_time DATETIME COMMENT '过期时间', 
	create_time DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	deleted_at DATETIME COMMENT '软删除时间', 
	CONSTRAINT pk_risk_blacklist PRIMARY KEY (blacklist_id), 
	CONSTRAINT uq_blacklist_type_value UNIQUE (blacklist_type, blacklist_value)
);

CREATE INDEX idx_blacklist_active ON risk_blacklist (blacklist_type, deleted_at, expire_time);

CREATE TABLE IF NOT EXISTS risk_event (
	event_id VARCHAR(50) NOT NULL COMMENT '事件ID', 
	event_type ENUM('登录','转账','信用卡交易','贷款申请') NOT NULL COMMENT '银行事件类型', 
	event_source_id VARCHAR(50) NOT NULL COMMENT '关联业务ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '客户ID', 
	event_data JSON COMMENT '事件快照', 
	create_time DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	CONSTRAINT pk_risk_event PRIMARY KEY (event_id)
);

CREATE INDEX idx_risk_event_create_time ON risk_event (create_time);

CREATE INDEX idx_risk_event_source ON risk_event (event_type, event_source_id);

CREATE INDEX idx_risk_event_user_id ON risk_event (user_id);

CREATE TABLE IF NOT EXISTS risk_rule (
	rule_id VARCHAR(50) NOT NULL COMMENT '规则ID', 
	rule_name VARCHAR(100) NOT NULL COMMENT '规则名称', 
	rule_category ENUM('账户安全','转账欺诈','信用卡风险','信贷风险','设备风险','IP与地域风险') NOT NULL COMMENT '银行风险场景分类', 
	event_type ENUM('登录','转账','信用卡交易','贷款申请','通用') NOT NULL COMMENT '适用事件类型' DEFAULT '通用', 
	rule_condition JSON NOT NULL COMMENT 'JSON条件表达式', 
	risk_level ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级', 
	risk_score INTEGER NOT NULL COMMENT '命中分值(0-100)', 
	action ENUM('通过','标记','人工审核','拒绝') NOT NULL COMMENT '触发动作', 
	is_enabled BOOL NOT NULL COMMENT '是否启用', 
	priority INTEGER NOT NULL COMMENT '优先级', 
	description TEXT COMMENT '规则描述', 
	create_time DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	update_time DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	deleted_at DATETIME COMMENT '软删除时间', 
	CONSTRAINT pk_risk_rule PRIMARY KEY (rule_id), 
	CONSTRAINT ck_risk_rule_risk_score_range CHECK (risk_score BETWEEN 0 AND 100)
);

CREATE INDEX idx_risk_rule_event_enabled ON risk_rule (event_type, is_enabled);

CREATE TABLE IF NOT EXISTS risk_user_profile (
	user_id VARCHAR(50) NOT NULL COMMENT '客户ID', 
	risk_score INTEGER NOT NULL COMMENT '综合风险评分', 
	risk_level ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级' DEFAULT '低', 
	txn_count_30d INTEGER NOT NULL COMMENT '近30天交易笔数', 
	txn_amount_30d NUMERIC(16, 2) NOT NULL COMMENT '近30天交易金额', 
	failed_login_count_30d INTEGER NOT NULL COMMENT '近30天失败登录次数', 
	device_count INTEGER NOT NULL COMMENT '关联设备数', 
	high_risk_ip_count_30d INTEGER NOT NULL COMMENT '近30天高风险IP次数', 
	loan_application_count_30d INTEGER NOT NULL COMMENT '近30天贷款申请次数', 
	debt_ratio NUMERIC(6, 4) NOT NULL COMMENT '最近负债率', 
	assessment_count INTEGER NOT NULL COMMENT '评估次数', 
	last_assessment_time DATETIME COMMENT '最近评估时间', 
	profile_data JSON COMMENT '扩展银行风险画像', 
	update_time DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	CONSTRAINT pk_risk_user_profile PRIMARY KEY (user_id), 
	CONSTRAINT ck_risk_user_profile_risk_score_range CHECK (risk_score BETWEEN 0 AND 100), 
	CONSTRAINT ck_risk_user_profile_debt_ratio_range CHECK (debt_ratio BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS bank_account (
	account_id VARCHAR(50) NOT NULL COMMENT '账户ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '账户所有人', 
	account_no_hash VARCHAR(128) NOT NULL COMMENT '账号哈希', 
	account_type ENUM('SAVING','CURRENT','LOAN') NOT NULL COMMENT '账户类型', 
	balance NUMERIC(16, 2) NOT NULL COMMENT '账面余额', 
	available_balance NUMERIC(16, 2) NOT NULL COMMENT '可用余额', 
	home_branch VARCHAR(100) NOT NULL COMMENT '开户网点', 
	open_at DATETIME NOT NULL COMMENT '开户时间', 
	status ENUM('NORMAL','FROZEN','CLOSED') NOT NULL COMMENT '账户状态', 
	CONSTRAINT pk_bank_account PRIMARY KEY (account_id), 
	CONSTRAINT ck_bank_account_balance_non_negative CHECK (balance >= 0), 
	CONSTRAINT ck_bank_account_available_balance_non_negative CHECK (available_balance >= 0), 
	CONSTRAINT fk_bank_account_user_id_customer_info FOREIGN KEY(user_id) REFERENCES customer_info (user_id), 
	CONSTRAINT uq_bank_account_account_no_hash UNIQUE (account_no_hash)
);

CREATE INDEX idx_bank_account_open_at ON bank_account (open_at);

CREATE INDEX ix_bank_account_user_id ON bank_account (user_id);

CREATE TABLE IF NOT EXISTS device_fingerprint (
	binding_id BIGINT NOT NULL COMMENT '绑定记录ID' AUTO_INCREMENT, 
	device_id VARCHAR(100) NOT NULL COMMENT '设备ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '关联用户', 
	fingerprint_hash VARCHAR(128) NOT NULL COMMENT '设备指纹哈希', 
	first_seen DATETIME NOT NULL COMMENT '首次出现', 
	last_seen DATETIME NOT NULL COMMENT '最近出现', 
	os VARCHAR(50) NOT NULL COMMENT '操作系统', 
	browser VARCHAR(50) NOT NULL COMMENT '浏览器或客户端', 
	is_rooted BOOL NOT NULL COMMENT '是否Root或越狱', 
	is_emulator BOOL NOT NULL COMMENT '是否模拟器', 
	CONSTRAINT pk_device_fingerprint PRIMARY KEY (binding_id), 
	CONSTRAINT uq_device_user UNIQUE (device_id, user_id), 
	CONSTRAINT fk_device_fingerprint_user_id_customer_info FOREIGN KEY(user_id) REFERENCES customer_info (user_id)
);

CREATE INDEX idx_device_last_seen ON device_fingerprint (last_seen);

CREATE INDEX ix_device_fingerprint_device_id ON device_fingerprint (device_id);

CREATE INDEX ix_device_fingerprint_user_id ON device_fingerprint (user_id);

CREATE TABLE IF NOT EXISTS loan_application (
	loan_id VARCHAR(50) NOT NULL COMMENT '贷款申请ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '申请人', 
	institution_code VARCHAR(50) NOT NULL COMMENT '模拟申请机构', 
	amount NUMERIC(16, 2) NOT NULL COMMENT '申请金额', 
	term_months INTEGER NOT NULL COMMENT '期限(月)', 
	purpose VARCHAR(100) NOT NULL COMMENT '贷款用途', 
	monthly_income NUMERIC(14, 2) NOT NULL COMMENT '申报月收入', 
	debt_ratio NUMERIC(6, 4) NOT NULL COMMENT '负债收入比', 
	device_id VARCHAR(100) NOT NULL COMMENT '申请设备', 
	ip VARCHAR(64) NOT NULL COMMENT '申请IP', 
	apply_at DATETIME NOT NULL COMMENT '申请时间', 
	status ENUM('SUBMITTED','REVIEWING','APPROVED','REJECTED') NOT NULL COMMENT '申请状态', 
	CONSTRAINT pk_loan_application PRIMARY KEY (loan_id), 
	CONSTRAINT ck_loan_application_amount_positive CHECK (amount > 0), 
	CONSTRAINT ck_loan_application_term_months_range CHECK (term_months BETWEEN 1 AND 360), 
	CONSTRAINT ck_loan_application_monthly_income_non_negative CHECK (monthly_income >= 0), 
	CONSTRAINT ck_loan_application_debt_ratio_range CHECK (debt_ratio BETWEEN 0 AND 1), 
	CONSTRAINT fk_loan_application_user_id_customer_info FOREIGN KEY(user_id) REFERENCES customer_info (user_id)
);

CREATE INDEX idx_loan_institution_apply_at ON loan_application (institution_code, apply_at);

CREATE INDEX idx_loan_user_apply_at ON loan_application (user_id, apply_at);

CREATE INDEX ix_loan_application_apply_at ON loan_application (apply_at);

CREATE INDEX ix_loan_application_device_id ON loan_application (device_id);

CREATE INDEX ix_loan_application_ip ON loan_application (ip);

CREATE INDEX ix_loan_application_user_id ON loan_application (user_id);

CREATE TABLE IF NOT EXISTS login_log (
	login_id VARCHAR(50) NOT NULL COMMENT '登录事件ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '登录用户', 
	device_id VARCHAR(100) NOT NULL COMMENT '登录设备', 
	ip VARCHAR(64) NOT NULL COMMENT '登录IP', 
	geo VARCHAR(100) NOT NULL COMMENT '登录城市', 
	success BOOL NOT NULL COMMENT '是否成功', 
	fail_reason VARCHAR(200) COMMENT '失败原因', 
	login_at DATETIME NOT NULL COMMENT '登录时间', 
	CONSTRAINT pk_login_log PRIMARY KEY (login_id), 
	CONSTRAINT fk_login_log_user_id_customer_info FOREIGN KEY(user_id) REFERENCES customer_info (user_id)
);

CREATE INDEX idx_login_user_time ON login_log (user_id, login_at);

CREATE INDEX ix_login_log_device_id ON login_log (device_id);

CREATE INDEX ix_login_log_ip ON login_log (ip);

CREATE INDEX ix_login_log_login_at ON login_log (login_at);

CREATE INDEX ix_login_log_user_id ON login_log (user_id);

CREATE TABLE IF NOT EXISTS risk_assessment (
	assessment_id VARCHAR(50) NOT NULL COMMENT '评估ID', 
	event_id VARCHAR(50) NOT NULL COMMENT '关联事件ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '客户ID', 
	rule_results JSON COMMENT '规则结果', 
	rule_count INTEGER NOT NULL COMMENT '命中规则数', 
	final_score INTEGER NOT NULL COMMENT '最终评分(0-100)', 
	risk_level ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级', 
	decision ENUM('通过','标记','人工审核','拒绝') NOT NULL COMMENT '最终决策', 
	ml_score NUMERIC(5, 4) COMMENT 'XGBoost风险概率[0,1]', 
	ml_decision VARCHAR(10) COMMENT 'ML维度决策', 
	create_time DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	CONSTRAINT pk_risk_assessment PRIMARY KEY (assessment_id), 
	CONSTRAINT ck_risk_assessment_rule_count_non_negative CHECK (rule_count >= 0), 
	CONSTRAINT ck_risk_assessment_final_score_range CHECK (final_score BETWEEN 0 AND 100), 
	CONSTRAINT ck_risk_assessment_ml_score_range CHECK (ml_score IS NULL OR (ml_score BETWEEN 0 AND 1)), 
	CONSTRAINT uq_risk_assessment_event_id UNIQUE (event_id), 
	CONSTRAINT fk_risk_assessment_event_id_risk_event FOREIGN KEY(event_id) REFERENCES risk_event (event_id)
);

CREATE INDEX idx_risk_assessment_create_time ON risk_assessment (create_time);

CREATE INDEX idx_risk_assessment_decision ON risk_assessment (decision);

CREATE INDEX idx_risk_assessment_user_id ON risk_assessment (user_id);

CREATE TABLE IF NOT EXISTS risk_feature (
	feature_id BIGINT NOT NULL COMMENT '特征ID' AUTO_INCREMENT, 
	event_id VARCHAR(50) NOT NULL COMMENT '关联事件ID', 
	entity_type ENUM('用户','交易','设备','信贷') NOT NULL COMMENT '特征实体类型', 
	entity_id VARCHAR(50) NOT NULL COMMENT '实体ID', 
	feature_name VARCHAR(100) NOT NULL COMMENT '特征名称', 
	feature_value NUMERIC(15, 4) NOT NULL COMMENT '特征值', 
	compute_time DATETIME NOT NULL COMMENT '计算时间' DEFAULT now(), 
	CONSTRAINT pk_risk_feature PRIMARY KEY (feature_id), 
	CONSTRAINT uq_event_feature_name UNIQUE (event_id, feature_name), 
	CONSTRAINT fk_risk_feature_event_id_risk_event FOREIGN KEY(event_id) REFERENCES risk_event (event_id)
);

CREATE INDEX idx_risk_feature_entity ON risk_feature (entity_type, entity_id);

CREATE INDEX idx_risk_feature_event_id ON risk_feature (event_id);

CREATE TABLE IF NOT EXISTS bank_card (
	card_id VARCHAR(50) NOT NULL COMMENT '卡ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '持卡人', 
	account_id VARCHAR(50) NOT NULL COMMENT '关联账户', 
	card_no_hash VARCHAR(128) NOT NULL COMMENT '卡号哈希', 
	card_type ENUM('DEBIT','CREDIT') NOT NULL COMMENT '卡类型', 
	credit_limit NUMERIC(14, 2) NOT NULL COMMENT '信用额度', 
	available_limit NUMERIC(14, 2) NOT NULL COMMENT '可用额度', 
	issue_at DATETIME NOT NULL COMMENT '发卡时间', 
	status ENUM('NORMAL','FROZEN','LOST','CLOSED') NOT NULL COMMENT '卡状态', 
	CONSTRAINT pk_bank_card PRIMARY KEY (card_id), 
	CONSTRAINT ck_bank_card_credit_limit_non_negative CHECK (credit_limit >= 0), 
	CONSTRAINT ck_bank_card_available_limit_non_negative CHECK (available_limit >= 0), 
	CONSTRAINT fk_bank_card_user_id_customer_info FOREIGN KEY(user_id) REFERENCES customer_info (user_id), 
	CONSTRAINT fk_bank_card_account_id_bank_account FOREIGN KEY(account_id) REFERENCES bank_account (account_id), 
	CONSTRAINT uq_bank_card_card_no_hash UNIQUE (card_no_hash)
);

CREATE INDEX ix_bank_card_account_id ON bank_card (account_id);

CREATE INDEX ix_bank_card_user_id ON bank_card (user_id);

CREATE TABLE IF NOT EXISTS risk_case (
	case_id VARCHAR(50) NOT NULL COMMENT '案件ID', 
	assessment_id VARCHAR(50) NOT NULL COMMENT '关联评估ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '客户ID', 
	case_status ENUM('待审核','审核中','已通过','已拒绝','已关闭') NOT NULL COMMENT '案件状态' DEFAULT '待审核', 
	case_category VARCHAR(50) COMMENT '案件分类', 
	risk_detail JSON COMMENT '风险详情', 
	source_id VARCHAR(50) COMMENT '原始业务ID', 
	event_type ENUM('登录','转账','信用卡交易','贷款申请') COMMENT '触发案件的事件类型', 
	reviewer VARCHAR(50) COMMENT '审核人', 
	review_comment TEXT COMMENT '审核意见', 
	review_time DATETIME COMMENT '审核时间', 
	create_time DATETIME NOT NULL COMMENT '创建时间' DEFAULT now(), 
	update_time DATETIME NOT NULL COMMENT '更新时间' DEFAULT now(), 
	CONSTRAINT pk_risk_case PRIMARY KEY (case_id), 
	CONSTRAINT uq_risk_case_assessment_id UNIQUE (assessment_id), 
	CONSTRAINT fk_risk_case_assessment_id_risk_assessment FOREIGN KEY(assessment_id) REFERENCES risk_assessment (assessment_id)
);

CREATE INDEX idx_risk_case_source_id ON risk_case (source_id);

CREATE INDEX idx_risk_case_status ON risk_case (case_status);

CREATE INDEX idx_risk_case_user_id ON risk_case (user_id);

CREATE TABLE IF NOT EXISTS bank_transaction (
	txn_id VARCHAR(50) NOT NULL COMMENT '交易ID', 
	user_id VARCHAR(50) NOT NULL COMMENT '发起客户', 
	from_account_id VARCHAR(50) COMMENT '付款账户', 
	from_card_id VARCHAR(50) COMMENT '付款卡', 
	beneficiary_account_hash VARCHAR(128) COMMENT '收款账户哈希', 
	amount NUMERIC(16, 2) NOT NULL COMMENT '交易金额', 
	currency VARCHAR(3) NOT NULL COMMENT '币种', 
	txn_type ENUM('TRANSFER','CARD_PAYMENT') NOT NULL COMMENT '交易类型', 
	channel ENUM('APP','WEB','ATM','POS') NOT NULL COMMENT '交易渠道', 
	device_id VARCHAR(100) NOT NULL COMMENT '设备标识', 
	ip VARCHAR(64) NOT NULL COMMENT '演示IP', 
	geo VARCHAR(100) NOT NULL COMMENT '交易城市或地理编码', 
	txn_time DATETIME NOT NULL COMMENT '交易时间', 
	status ENUM('PENDING','SUCCESS','REJECTED','FAILED') NOT NULL COMMENT '交易状态', 
	CONSTRAINT pk_bank_transaction PRIMARY KEY (txn_id), 
	CONSTRAINT ck_bank_transaction_amount_positive CHECK (amount > 0), 
	CONSTRAINT fk_bank_transaction_user_id_customer_info FOREIGN KEY(user_id) REFERENCES customer_info (user_id), 
	CONSTRAINT fk_bank_transaction_from_account_id_bank_account FOREIGN KEY(from_account_id) REFERENCES bank_account (account_id), 
	CONSTRAINT fk_bank_transaction_from_card_id_bank_card FOREIGN KEY(from_card_id) REFERENCES bank_card (card_id)
);

CREATE INDEX idx_bank_txn_beneficiary_time ON bank_transaction (beneficiary_account_hash, txn_time);

CREATE INDEX idx_bank_txn_user_time ON bank_transaction (user_id, txn_time);

CREATE INDEX ix_bank_transaction_beneficiary_account_hash ON bank_transaction (beneficiary_account_hash);

CREATE INDEX ix_bank_transaction_device_id ON bank_transaction (device_id);

CREATE INDEX ix_bank_transaction_from_account_id ON bank_transaction (from_account_id);

CREATE INDEX ix_bank_transaction_from_card_id ON bank_transaction (from_card_id);

CREATE INDEX ix_bank_transaction_ip ON bank_transaction (ip);

CREATE INDEX ix_bank_transaction_txn_time ON bank_transaction (txn_time);

CREATE INDEX ix_bank_transaction_user_id ON bank_transaction (user_id);

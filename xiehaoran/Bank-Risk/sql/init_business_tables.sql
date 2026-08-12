-- ============================================================
-- 银行风控系统 - 核心业务表 DDL (MySQL 8.0)
-- 对应 app/models_business.py (6 张表, 带 _biz 前缀)
-- 分区策略: 交易流水 / 结算 / 行为日志 按时间 RANGE 分区 (按季度)
-- 字符集: utf8mb4 / 排序: utf8mb4_general_ci
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ------------------------------------------------------------
-- 1. 商户信息表 merchant_info
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `merchant_info` (
  `merchant_id`     VARCHAR(32)   NOT NULL                COMMENT '商户/对公账户编号 PK',
  `merchant_name`   VARCHAR(128)  NOT NULL                COMMENT '商户名称/企业名称',
  `merchant_type`   VARCHAR(16)   NOT NULL                COMMENT '商户类型: 个体/企业/对公通道/个人收款码',
  `mcc_code`        VARCHAR(8)    DEFAULT NULL            COMMENT '商户类别码 MCC',
  `legal_person`    VARCHAR(64)   DEFAULT NULL            COMMENT '法人/实际控制人',
  `id_card_no`      VARCHAR(32)   DEFAULT NULL            COMMENT '法人证件号(脱敏存储)',
  `contact_phone`   VARCHAR(20)   DEFAULT NULL            COMMENT '预留手机号(脱敏)',
  `province`        VARCHAR(32)   DEFAULT NULL            COMMENT '注册省份',
  `city`            VARCHAR(32)   DEFAULT NULL            COMMENT '注册城市',
  `risk_level`      SMALLINT      NOT NULL DEFAULT 0      COMMENT '商户风险等级 0低 1中 2高',
  `status`          SMALLINT      NOT NULL DEFAULT 1      COMMENT '状态 1正常 2冻结 3注销 4涉案冻结',
  `open_date`       DATETIME      DEFAULT NULL            COMMENT '入网/开户日期',
  `f_ext_json`      JSON          DEFAULT NULL            COMMENT '风控特征扩展位',
  `created_at`      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`merchant_id`),
  UNIQUE KEY `uq_merchant_idcard` (`id_card_no`),
  KEY `ix_merchant_name` (`merchant_name`),
  KEY `ix_merchant_type_status` (`merchant_type`, `status`),
  KEY `ix_merchant_risk` (`risk_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='商户信息表(收单/对公账户主体)';

-- ------------------------------------------------------------
-- 2. 交易流水表 txn_flow (按 txn_time 季度 RANGE 分区)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `txn_flow` (
  `txn_id`             VARCHAR(40)   NOT NULL                COMMENT '交易流水号 PK',
  `merchant_id`        VARCHAR(32)   DEFAULT NULL            COMMENT '商户/对公账户编号 FK',
  `cust_id`            VARCHAR(32)   NOT NULL                COMMENT '客户/付款人编号',
  `counterparty_id`    VARCHAR(32)   DEFAULT NULL            COMMENT '交易对手/收款人编号',
  `counterparty_account` VARCHAR(40) DEFAULT NULL            COMMENT '收款账号(脱敏)',
  `txn_type`           VARCHAR(16)   NOT NULL                COMMENT '交易类型: transfer/loan_apply/card_txn/repay/login',
  `channel`            VARCHAR(16)   DEFAULT NULL            COMMENT '渠道: 手机银行/网银/ATM/POS/柜面',
  `amount`             DECIMAL(19,4) NOT NULL                COMMENT '交易金额(元)',
  `currency`           VARCHAR(3)    NOT NULL DEFAULT 'CNY'  COMMENT '币种',
  `txn_time`           DATETIME      NOT NULL                COMMENT '交易时间(分区键)',
  `device_fingerprint` VARCHAR(64)   DEFAULT NULL            COMMENT '设备指纹',
  `ip_addr`            VARCHAR(45)   DEFAULT NULL            COMMENT '客户端 IP',
  `geo_province`       VARCHAR(32)   DEFAULT NULL            COMMENT '交易地理-省',
  `geo_city`           VARCHAR(32)   DEFAULT NULL            COMMENT '交易地理-市',
  `txn_status`         SMALLINT      NOT NULL DEFAULT 1      COMMENT '1成功 2失败 3可疑拦截 4保护性止付 5已报送',
  `is_fraud`           TINYINT       NOT NULL DEFAULT 0      COMMENT '是否确认为欺诈/涉案',
  `f_speed`            DECIMAL(10,2) DEFAULT NULL            COMMENT '特征: 快进快出耗时(分钟)',
  `f_counterparty_cnt` INT           DEFAULT NULL            COMMENT '特征: 近1h交易对手数',
  `f_ext_json`         JSON          DEFAULT NULL            COMMENT '风控特征扩展位',
  `created_at`         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`txn_id`, `txn_time`),
  KEY `ix_txn_merchant_time` (`merchant_id`, `txn_time`),
  KEY `ix_txn_cust_time` (`cust_id`, `txn_time`),
  KEY `ix_txn_counterparty` (`counterparty_id`),
  KEY `ix_txn_type_status` (`txn_type`, `txn_status`),
  KEY `ix_txn_device` (`device_fingerprint`),
  KEY `ix_txn_fraud` (`is_fraud`, `txn_time`),
  CONSTRAINT `ck_txn_amount_nonneg` CHECK (`amount` >= 0)
  -- 注: MySQL 分区表不支持外键 (err 1506), merchant_id 一致性由应用层/造数脚本保证
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
COMMENT='交易流水表(转账/卡片/还款, 风控特征主数据源)'
PARTITION BY RANGE (TO_DAYS(`txn_time`)) (
  PARTITION p2025q4 VALUES LESS THAN (TO_DAYS('2026-01-01')),
  PARTITION p2026q1 VALUES LESS THAN (TO_DAYS('2026-04-01')),
  PARTITION p2026q2 VALUES LESS THAN (TO_DAYS('2026-07-01')),
  PARTITION p2026q3 VALUES LESS THAN (TO_DAYS('2026-10-01')),
  PARTITION p_future  VALUES LESS THAN MAXVALUE
);

-- ------------------------------------------------------------
-- 3. 结算记录表 settlement_log (按 settle_date 季度分区)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `settlement_log` (
  `settle_id`     VARCHAR(40)   NOT NULL                COMMENT '结算流水号 PK',
  `txn_id`        VARCHAR(40)   NOT NULL                COMMENT '关联交易流水号 FK',
  `merchant_id`   VARCHAR(32)   DEFAULT NULL            COMMENT '关联商户编号 FK',
  `settle_amount` DECIMAL(19,4) NOT NULL                COMMENT '结算金额(元)',
  `fee_amount`    DECIMAL(19,4) NOT NULL DEFAULT 0      COMMENT '手续费',
  `net_amount`    DECIMAL(19,4) NOT NULL                COMMENT '净额=结算-手续费',
  `settle_date`   DATETIME      NOT NULL                COMMENT '清算日期(分区键)',
  `settle_status` SMALLINT      NOT NULL DEFAULT 1      COMMENT '1待清算 2已清算 3差错 4调单 5退回',
  `error_code`    VARCHAR(16)   DEFAULT NULL            COMMENT '差错码',
  `f_ext_json`    JSON          DEFAULT NULL            COMMENT '风控特征扩展位',
  `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`settle_id`, `settle_date`),
  KEY `ix_settle_txn` (`txn_id`),
  KEY `ix_settle_merchant_date` (`merchant_id`, `settle_date`),
  KEY `ix_settle_status` (`settle_status`),
  CONSTRAINT `ck_settle_amount_nonneg` CHECK (`settle_amount` >= 0),
  CONSTRAINT `ck_settle_net_nonneg` CHECK (`net_amount` >= 0)
  -- 注: 分区表不支持外键; txn_id/merchant_id 一致性由应用层/造数脚本保证
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
COMMENT='结算记录表(T+1清算/差错/调单)'
PARTITION BY RANGE (TO_DAYS(`settle_date`)) (
  PARTITION p2025q4 VALUES LESS THAN (TO_DAYS('2026-01-01')),
  PARTITION p2026q1 VALUES LESS THAN (TO_DAYS('2026-04-01')),
  PARTITION p2026q2 VALUES LESS THAN (TO_DAYS('2026-07-01')),
  PARTITION p2026q3 VALUES LESS THAN (TO_DAYS('2026-10-01')),
  PARTITION p_future  VALUES LESS THAN MAXVALUE
);

-- ------------------------------------------------------------
-- 4. 用户行为日志表 user_behavior_log (按 action_time 季度分区)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `user_behavior_log` (
  `log_id`            BIGINT        NOT NULL AUTO_INCREMENT COMMENT '行为日志自增ID PK',
  `cust_id`           VARCHAR(32)   NOT NULL                COMMENT '客户编号',
  `action`            VARCHAR(24)   NOT NULL                COMMENT '行为: login/login_fail/change_bind/transfer_prepay/query',
  `action_time`       DATETIME      NOT NULL                COMMENT '行为时间(分区键)',
  `device_fingerprint` VARCHAR(64)  DEFAULT NULL            COMMENT '设备指纹',
  `ip_addr`           VARCHAR(45)   DEFAULT NULL            COMMENT 'IP',
  `geo_province`      VARCHAR(32)   DEFAULT NULL            COMMENT '地理-省',
  `geo_city`          VARCHAR(32)   DEFAULT NULL            COMMENT '地理-市',
  `result`            SMALLINT      NOT NULL DEFAULT 1      COMMENT '1成功 0失败',
  `f_ext_json`        JSON          DEFAULT NULL            COMMENT '风控特征扩展位',
  `created_at`        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`log_id`, `action_time`),
  KEY `ix_behavior_cust_time` (`cust_id`, `action_time`),
  KEY `ix_behavior_action` (`action`),
  KEY `ix_behavior_device` (`device_fingerprint`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
COMMENT='用户行为日志表(登录/改绑/交易前置行为)'
PARTITION BY RANGE (TO_DAYS(`action_time`)) (
  PARTITION p2025q4 VALUES LESS THAN (TO_DAYS('2026-01-01')),
  PARTITION p2026q1 VALUES LESS THAN (TO_DAYS('2026-04-01')),
  PARTITION p2026q2 VALUES LESS THAN (TO_DAYS('2026-07-01')),
  PARTITION p2026q3 VALUES LESS THAN (TO_DAYS('2026-10-01')),
  PARTITION p_future  VALUES LESS THAN MAXVALUE
);

-- ------------------------------------------------------------
-- 5. 风险事件表 risk_event_biz
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `risk_event_biz` (
  `event_id`      VARCHAR(40) NOT NULL                COMMENT '风险事件编号 PK',
  `txn_id`        VARCHAR(40) DEFAULT NULL            COMMENT '关联交易流水号 FK',
  `cust_id`       VARCHAR(32) DEFAULT NULL            COMMENT '关联客户编号',
  `event_type`    VARCHAR(24) NOT NULL                COMMENT '事件类型: aml_suspect/veto/anti_fraud_freeze/blacklist_hit',
  `trigger_rule`  VARCHAR(64) DEFAULT NULL            COMMENT '触发规则/模型名',
  `severity`      SMALLINT    NOT NULL DEFAULT 1      COMMENT '严重度 1低 2中 3高 4一票否决',
  `decision`      VARCHAR(16) NOT NULL                COMMENT '决策: pass/review/reject/freeze/report',
  `reported`      TINYINT     NOT NULL DEFAULT 0      COMMENT '是否已报送监管',
  `report_no`     VARCHAR(40) DEFAULT NULL            COMMENT '报送流水号',
  `detail_json`   JSON        DEFAULT NULL            COMMENT '事件详情',
  `created_at`    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`event_id`),
  KEY `ix_revent_txn` (`txn_id`),
  KEY `ix_revent_cust` (`cust_id`),
  KEY `ix_revent_type_sev` (`event_type`, `severity`),
  KEY `ix_revent_reported` (`reported`)
  -- 注: 父表 txn_flow 为分区表, 按 MySQL 限制不可建 FK; txn_id 一致性由应用层保证
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
COMMENT='风险事件表(一票否决/可疑交易/反诈止付)';

-- ------------------------------------------------------------
-- 6. 关联关系表 relation_graph
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `relation_graph` (
  `relation_id`   BIGINT        NOT NULL AUTO_INCREMENT COMMENT '关系自增ID PK',
  `src_id`        VARCHAR(40)   NOT NULL                COMMENT '源节点(客户/商户/账户)',
  `dst_id`        VARCHAR(40)   NOT NULL                COMMENT '目标节点(客户/商户/账户)',
  `rel_type`      VARCHAR(24)   NOT NULL                COMMENT '关系: fund_collect/device_share/ip_share/beneficiary/same_phone',
  `weight`        DECIMAL(10,4) NOT NULL DEFAULT 1.0    COMMENT '关系强度(出现频次)',
  `first_seen`    DATETIME      DEFAULT NULL            COMMENT '首次发现时间',
  `last_seen`     DATETIME      DEFAULT NULL            COMMENT '末次发现时间',
  `is_suspicious` TINYINT       NOT NULL DEFAULT 0      COMMENT '是否可疑团伙边',
  `f_ext_json`    JSON          DEFAULT NULL            COMMENT '风控特征扩展位',
  `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`relation_id`),
  UNIQUE KEY `uq_relation_edge` (`src_id`, `dst_id`, `rel_type`),
  KEY `ix_rel_src` (`src_id`),
  KEY `ix_rel_dst` (`dst_id`),
  KEY `ix_rel_type` (`rel_type`),
  KEY `ix_rel_susp` (`is_suspicious`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
COMMENT='关联关系表(资金归集/同设备/IP/受益人, 团伙识别)';

SET FOREIGN_KEY_CHECKS = 1;

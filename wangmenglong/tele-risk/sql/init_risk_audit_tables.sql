-- =============================================================================
-- 电信风控系统 - 风控审计表 DDL (6 张)
-- 位置: tele-risk/sql/init_risk_audit_tables.sql
-- 数据库: telecom
--
-- 6 张审计表 (跟 models_risk.py 对齐):
--   telecom_risk_event       事件记录 (每次风控检查 1 行)
--   telecom_risk_feature     特征快照 (25 维落库, 审计 + 训练取数)
--   telecom_risk_assessment  评估结果 (评分 + 等级 + 决策 + 命中规则)
--   telecom_risk_case        案件管理 (人工审核/关停流程)
--   telecom_risk_blacklist   黑名单 (号卡/客户/设备/渠道, 反诈法第21条)
--   telecom_card_profile     号卡画像 (累积风险历史)
--
-- 注: telecom_risk_rule 在 init_risk_tables.sql 单独建.
-- =============================================================================

USE `telecom`;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS telecom_risk_event;
DROP TABLE IF EXISTS telecom_risk_feature;
DROP TABLE IF EXISTS telecom_risk_assessment;
DROP TABLE IF EXISTS telecom_risk_case;
DROP TABLE IF EXISTS telecom_risk_blacklist;
DROP TABLE IF EXISTS telecom_card_profile;
SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- 1. 风控事件表
-- ============================================================
CREATE TABLE telecom_risk_event (
    event_id        VARCHAR(50)  NOT NULL COMMENT '事件ID (evt+ULID)',
    event_type      VARCHAR(20)  NOT NULL COMMENT '事件类型 (开户/通话/国际来电/短信发送/物联网激活)',
    event_source_id VARCHAR(50)  NOT NULL COMMENT '关联业务ID',
    msisdn          VARCHAR(11)  NOT NULL COMMENT '号卡',
    event_data      TEXT         DEFAULT NULL COMMENT '事件快照 JSON',
    create_time     DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (event_id),
    KEY idx_telecom_event_msisdn (msisdn),
    KEY idx_telecom_event_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控事件表';

-- ============================================================
-- 2. 特征快照表 (25 维特征每次评估落库)
-- ============================================================
CREATE TABLE telecom_risk_feature (
    feature_id    BIGINT       NOT NULL AUTO_INCREMENT COMMENT '特征ID',
    event_id      VARCHAR(50)  NOT NULL COMMENT '关联事件ID',
    entity_type   VARCHAR(20)  NOT NULL COMMENT '实体类型 (号卡/客户/设备/渠道/物联网)',
    entity_id     VARCHAR(50)  NOT NULL COMMENT '实体ID',
    feature_name  VARCHAR(100) NOT NULL COMMENT '特征名称',
    feature_value DECIMAL(15,4) DEFAULT NULL COMMENT '特征值',
    compute_time  DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '计算时间',
    PRIMARY KEY (feature_id),
    KEY idx_telecom_feature_event_id (event_id),
    KEY idx_telecom_feature_entity (entity_type, entity_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='特征快照表';

-- ============================================================
-- 3. 评估结果表
-- ============================================================
CREATE TABLE telecom_risk_assessment (
    assessment_id VARCHAR(50)  NOT NULL COMMENT '评估ID (ast+ULID)',
    event_id      VARCHAR(50)  NOT NULL COMMENT '关联事件ID',
    msisdn        VARCHAR(11)  NOT NULL COMMENT '号卡',
    rule_results  TEXT         DEFAULT NULL COMMENT '命中规则详情 JSON',
    rule_count    INT          NOT NULL DEFAULT 0 COMMENT '命中规则数',
    final_score   INT          NOT NULL COMMENT '最终评分 (0-100)',
    risk_level    VARCHAR(10)  NOT NULL COMMENT '风险等级 (低/中/高/极高)',
    decision      VARCHAR(20)  NOT NULL COMMENT '决策 (通过/标记/人工审核/拒绝/关停号码)',
    create_time   DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    ml_score      DECIMAL(5,4) DEFAULT NULL COMMENT 'XGBoost P(高风险) [0,1]',
    ml_decision   VARCHAR(10)  DEFAULT NULL COMMENT 'ML 决策',
    PRIMARY KEY (assessment_id),
    KEY idx_telecom_assessment_msisdn (msisdn),
    KEY idx_telecom_assessment_decision (decision),
    KEY idx_telecom_assessment_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控评估结果表';

-- ============================================================
-- 4. 案件管理表
-- ============================================================
CREATE TABLE telecom_risk_case (
    case_id       VARCHAR(50)  NOT NULL COMMENT '案件ID (cas+ULID)',
    assessment_id VARCHAR(50)  NOT NULL COMMENT '关联评估ID',
    msisdn        VARCHAR(11)  NOT NULL COMMENT '号卡',
    case_status   VARCHAR(20)  NOT NULL DEFAULT '待审核' COMMENT '案件状态 (待审核/审核中/已通过/已拒绝/已关闭/已关停)',
    case_category VARCHAR(30)  DEFAULT NULL COMMENT '案件分类',
    risk_detail   TEXT         DEFAULT NULL COMMENT '风险详情 JSON',
    reviewer      VARCHAR(50)  DEFAULT NULL COMMENT '审核人',
    review_comment TEXT        DEFAULT NULL COMMENT '审核意见',
    review_time   DATETIME     DEFAULT NULL COMMENT '审核时间',
    source_id     VARCHAR(50)  DEFAULT NULL COMMENT '原始业务ID',
    event_type    VARCHAR(20)  DEFAULT NULL COMMENT '触发案件的事件类型',
    create_time   DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time   DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (case_id),
    KEY idx_telecom_case_status (case_status),
    KEY idx_telecom_case_msisdn (msisdn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控案件表';

-- ============================================================
-- 5. 黑名单表 (号卡/客户/设备/渠道, 反诈法第21条)
-- ============================================================
CREATE TABLE telecom_risk_blacklist (
    blacklist_id   BIGINT       NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
    blacklist_type VARCHAR(20)  NOT NULL COMMENT '黑名单类型 (号卡/客户/设备/渠道)',
    blacklist_value VARCHAR(50) NOT NULL COMMENT '黑名单值',
    reason         TEXT         DEFAULT NULL COMMENT '加入原因',
    expire_time    DATETIME     DEFAULT NULL COMMENT '过期时间 (NULL=永久)',
    create_time    DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deleted_at     DATETIME     DEFAULT NULL COMMENT '软删时间 (NULL=未删)',
    PRIMARY KEY (blacklist_id),
    UNIQUE KEY idx_telecom_blacklist_type_value (blacklist_type, blacklist_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控黑名单表';

-- ============================================================
-- 6. 号卡画像表
-- ============================================================
CREATE TABLE telecom_card_profile (
    msisdn              VARCHAR(11)  NOT NULL COMMENT '号卡',
    risk_score          INT          NOT NULL DEFAULT 0 COMMENT '综合风险评分 (0-100)',
    risk_level          VARCHAR(10)  NOT NULL DEFAULT '低' COMMENT '风险等级',
    assessment_count    INT          NOT NULL DEFAULT 0 COMMENT '评估次数',
    last_assessment_time DATETIME    DEFAULT NULL COMMENT '最近评估时间',
    profile_data        TEXT         DEFAULT NULL COMMENT '扩展画像数据 JSON',
    update_time         DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (msisdn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='号卡风险画像表';

-- 校验
SELECT TABLE_NAME, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='telecom' AND TABLE_NAME LIKE 'telecom_risk_%' OR TABLE_NAME='telecom_card_profile'
ORDER BY TABLE_NAME;

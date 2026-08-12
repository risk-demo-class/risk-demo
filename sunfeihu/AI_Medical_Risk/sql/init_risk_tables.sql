-- ============================================
-- 医疗风控系统 - 风控核心表 DDL (9 张, 复用并适配自 AI_Risk)
-- 适配: event_type / rule_category / feature entity_type / blacklist_type 改为医疗语义
-- 该脚本由 scripts/init_db.py 在已选中的数据库上下文中执行 (不写死 USE)
-- 全部 IF NOT EXISTS, 可重复执行 (幂等)
-- ============================================

-- 1. 风控规则配置表
CREATE TABLE IF NOT EXISTS `risk_rule` (
    `rule_id` VARCHAR(50) NOT NULL COMMENT '规则ID',
    `rule_name` VARCHAR(100) NOT NULL COMMENT '规则名称',
    `rule_category` ENUM('医保结算异常','处方合规','挂号行为','通用') NOT NULL COMMENT '风险场景分类',
    `event_type` ENUM('挂号申请','挂号退号','处方开立','医保结算','通用') NOT NULL DEFAULT '通用' COMMENT '适用事件类型',
    `rule_condition` JSON NOT NULL COMMENT '条件表达式',
    `risk_level` ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级',
    `risk_score` INT NOT NULL COMMENT '命中分值(0-100)',
    `action` ENUM('通过','标记','人工审核','拒绝') NOT NULL COMMENT '触发动作',
    `is_enabled` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `priority` INT DEFAULT 0 COMMENT '优先级(越高越先执行)',
    `description` TEXT COMMENT '规则描述',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`rule_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控规则配置表';

-- 2. 风控事件审计表
CREATE TABLE IF NOT EXISTS `risk_event` (
    `event_id` VARCHAR(50) NOT NULL COMMENT '事件ID',
    `event_type` ENUM('挂号申请','挂号退号','处方开立','医保结算') NOT NULL COMMENT '事件类型',
    `event_source_id` VARCHAR(50) NOT NULL COMMENT '关联业务ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `event_data` JSON COMMENT '事件快照',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`event_id`),
    INDEX `idx_risk_event_user_id` (`user_id`),
    INDEX `idx_risk_event_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控事件审计表';

-- 3. 风控特征快照表
CREATE TABLE IF NOT EXISTS `risk_feature` (
    `feature_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '特征ID',
    `event_id` VARCHAR(50) NOT NULL COMMENT '关联事件ID',
    `entity_type` ENUM('患者','单据','机构') NOT NULL COMMENT '实体类型',
    `entity_id` VARCHAR(50) NOT NULL COMMENT '实体ID',
    `feature_name` VARCHAR(100) NOT NULL COMMENT '特征名称',
    `feature_value` DECIMAL(15,4) COMMENT '特征值',
    `compute_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '计算时间',
    PRIMARY KEY (`feature_id`),
    INDEX `idx_risk_feature_event_id` (`event_id`),
    INDEX `idx_risk_feature_entity` (`entity_type`, `entity_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控特征快照表';

-- 4. 风控评估结果表
CREATE TABLE IF NOT EXISTS `risk_assessment` (
    `assessment_id` VARCHAR(50) NOT NULL COMMENT '评估ID',
    `event_id` VARCHAR(50) NOT NULL COMMENT '关联事件ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `rule_results` JSON COMMENT '规则结果',
    `rule_count` INT DEFAULT 0 COMMENT '命中规则数',
    `final_score` INT NOT NULL COMMENT '最终评分(0-100)',
    `risk_level` ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级',
    `decision` ENUM('通过','标记','人工审核','拒绝') NOT NULL COMMENT '决策',
    `ml_score` DECIMAL(5,4) DEFAULT NULL COMMENT 'XGBoost 拒绝概率 [0,1](NULL=未加载)',
    `ml_decision` VARCHAR(10) DEFAULT NULL COMMENT 'ML 维度决策(通过/标记/人工审核/拒绝)',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`assessment_id`),
    INDEX `idx_risk_assessment_user_id` (`user_id`),
    INDEX `idx_risk_assessment_decision` (`decision`),
    INDEX `idx_risk_assessment_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控评估结果表';

-- 5. 风控案件表
CREATE TABLE IF NOT EXISTS `risk_case` (
    `case_id` VARCHAR(50) NOT NULL COMMENT '案件ID',
    `assessment_id` VARCHAR(50) NOT NULL COMMENT '关联评估ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `case_status` ENUM('待审核','审核中','已通过','已拒绝','已关闭') NOT NULL DEFAULT '待审核' COMMENT '案件状态',
    `case_category` VARCHAR(50) DEFAULT NULL COMMENT '案件分类',
    `risk_detail` JSON COMMENT '风险详情',
    `reviewer` VARCHAR(50) DEFAULT NULL COMMENT '审核人',
    `review_comment` TEXT COMMENT '审核意见',
    `review_time` DATETIME DEFAULT NULL COMMENT '审核时间',
    `source_id` VARCHAR(50) DEFAULT NULL COMMENT '原始业务ID(挂号/处方/结算ID), 重做检查用',
    `event_type` ENUM('挂号申请','挂号退号','处方开立','医保结算') DEFAULT NULL COMMENT '触发案件的事件类型',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`case_id`),
    INDEX `idx_risk_case_status` (`case_status`),
    INDEX `idx_risk_case_user_id` (`user_id`),
    INDEX `idx_risk_case_source_id` (`source_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控案件表';

-- 6. 风控黑名单表 (7 类医疗主体, PRD §10)
CREATE TABLE IF NOT EXISTS `risk_blacklist` (
    `blacklist_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
    `blacklist_type` ENUM('PATIENT_ID','ID_CARD_HASH','INSURANCE_CARD_HASH','PHONE_HASH','DOCTOR_ID','DEVICE_ID_HASH','HOSPITAL_ID') NOT NULL COMMENT '黑名单类型',
    `blacklist_value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` TEXT COMMENT '加入原因',
    `expire_time` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`blacklist_id`),
    UNIQUE INDEX `idx_blacklist_type_value` (`blacklist_type`, `blacklist_value`),
    INDEX `idx_blacklist_type_value_status` (`blacklist_type`, `blacklist_value`, `deleted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控黑名单表';

-- 7. 患者风险画像表 (适配: 去除电商字段, 改为患者中性画像)
CREATE TABLE IF NOT EXISTS `risk_user_profile` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `risk_score` INT DEFAULT 0 COMMENT '综合风险评分(0-100)',
    `risk_level` ENUM('低','中','高','极高') DEFAULT '低' COMMENT '风险等级',
    `registration_count` INT DEFAULT 0 COMMENT '累计挂号次数',
    `cancel_count` INT DEFAULT 0 COMMENT '累计退号次数',
    `claim_count` INT DEFAULT 0 COMMENT '累计医保结算次数',
    `assessment_count` INT DEFAULT 0 COMMENT '评估次数',
    `last_assessment_time` DATETIME DEFAULT NULL COMMENT '最近评估时间',
    `profile_data` JSON COMMENT '扩展画像数据',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='患者风险画像表';

-- 8. 操作审计日志表 (通用, 无电商语义)
CREATE TABLE IF NOT EXISTS `risk_action_log` (
    `log_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `operator` VARCHAR(50) NOT NULL COMMENT '操作人(admin/system/ai_agent)',
    `action_type` ENUM('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST','ASSIGN_CASE','REOPEN_CASE','CREATE_USER','UPDATE_USER','RESET_PASSWORD','CHANGE_PASSWORD','LOGIN','LOGOUT') NOT NULL COMMENT '操作类型',
    `target_type` ENUM('rule','case','blacklist','user') NOT NULL COMMENT '对象类型',
    `target_id` VARCHAR(50) NOT NULL COMMENT '对象ID',
    `before_value` JSON COMMENT '变更前 (NULL=新增)',
    `after_value` JSON COMMENT '变更后 (NULL=删除)',
    `ip` VARCHAR(50) COMMENT '操作IP',
    `remark` VARCHAR(500) COMMENT '备注',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (`log_id`),
    INDEX `idx_action_log_operator` (`operator`),
    INDEX `idx_action_log_target` (`target_type`, `target_id`),
    INDEX `idx_action_log_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控操作审计日志表';

-- 9. 风控告警记录表 (通用, 无电商语义)
CREATE TABLE IF NOT EXISTS `risk_alert` (
    `alert_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '告警ID',
    `alert_type` ENUM('BUSINESS','MODEL','SYSTEM','SECURITY') NOT NULL COMMENT '告警分类',
    `alert_level` ENUM('P0','P1','P2','P3') NOT NULL COMMENT '告警等级 (P0=致命, P3=提示)',
    `alert_title` VARCHAR(200) NOT NULL COMMENT '告警标题',
    `alert_content` TEXT COMMENT '告警详情',
    `metric_name` VARCHAR(100) COMMENT '指标名',
    `metric_value` DECIMAL(20,6) COMMENT '触发值',
    `threshold` DECIMAL(20,6) COMMENT '阈值',
    `status` ENUM('PENDING','HANDLING','RESOLVED','IGNORED') DEFAULT 'PENDING' COMMENT '处理状态',
    `handler` VARCHAR(50) COMMENT '处理人',
    `resolve_time` DATETIME DEFAULT NULL COMMENT '解决时间',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '告警时间',
    PRIMARY KEY (`alert_id`),
    INDEX `idx_alert_status` (`status`),
    INDEX `idx_alert_level` (`alert_level`),
    INDEX `idx_alert_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控告警记录表';

-- 10. 后台用户表
CREATE TABLE IF NOT EXISTS `app_user` (
    `user_id` BIGINT NOT NULL AUTO_INCREMENT,
    `username` VARCHAR(32) NOT NULL COMMENT '登录名',
    `password_hash` VARCHAR(255) NOT NULL COMMENT 'Argon2 密码摘要',
    `display_name` VARCHAR(50) NOT NULL COMMENT '显示名称',
    `role` ENUM('admin','reviewer','analyst','viewer') NOT NULL DEFAULT 'viewer' COMMENT '角色',
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
    `is_superuser` BOOLEAN NOT NULL DEFAULT FALSE,
    `session_version` INT NOT NULL DEFAULT 1 COMMENT '会话撤销版本',
    `last_login_at` DATETIME DEFAULT NULL,
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`),
    UNIQUE INDEX `uq_app_user_username` (`username`),
    INDEX `idx_app_user_role_active` (`role`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='后台用户表';

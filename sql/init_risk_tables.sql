-- ============================================
-- 医疗风控系统 - 风控表 DDL 初始化脚本
-- 在 medical_risk 数据库中创建 9 张风控表
-- 表结构与电商版完全一致 (风控核心不许改), 仅枚举值适配医疗行业
-- ============================================

USE medical_risk;

-- 1. 风控规则配置表
CREATE TABLE IF NOT EXISTS `risk_rule` (
    `rule_id` VARCHAR(50) NOT NULL COMMENT '规则ID',
    `rule_name` VARCHAR(100) NOT NULL COMMENT '规则名称',
    `rule_category` ENUM('医保欺诈','处方违规','挂号黄牛','药品代购','账户风险','机构风险') NOT NULL COMMENT '风险场景分类',
    `event_type` ENUM('挂号','处方开具','医保结算','药品下单','通用') NOT NULL DEFAULT '通用' COMMENT '适用事件类型',
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
    `event_type` ENUM('挂号','处方开具','医保结算','药品下单') NOT NULL COMMENT '事件类型',
    `event_source_id` VARCHAR(50) NOT NULL COMMENT '关联业务ID(挂号/处方/结算/药品订单)',
    `user_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `event_data` JSON COMMENT '事件快照',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`event_id`),
    INDEX `idx_risk_event_user_id` (`user_id`),
    INDEX `idx_risk_event_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控事件审计表';

-- 3. 风控特征快照表
-- entity_type 语义映射: 用户=患者, 订单=诊疗单据, 地址=医疗机构
CREATE TABLE IF NOT EXISTS `risk_feature` (
    `feature_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '特征ID',
    `event_id` VARCHAR(50) NOT NULL COMMENT '关联事件ID',
    `entity_type` ENUM('用户','订单','地址') NOT NULL COMMENT '实体类型(患者/诊疗单据/医疗机构)',
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
    `source_id` VARCHAR(50) DEFAULT NULL COMMENT '原始业务ID(挂号/处方/结算/药品订单ID), 重做检查时用',
    `event_type` ENUM('挂号','处方开具','医保结算','药品下单') DEFAULT NULL COMMENT '触发案件的事件类型',
    `reviewer` VARCHAR(50) DEFAULT NULL COMMENT '审核人',
    `review_comment` TEXT COMMENT '审核意见',
    `review_time` DATETIME DEFAULT NULL COMMENT '审核时间',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`case_id`),
    INDEX `idx_risk_case_status` (`case_status`),
    INDEX `idx_risk_case_user_id` (`user_id`),
    INDEX `idx_risk_case_source_id` (`source_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控案件表';

-- 6. 风控黑名单表 (医疗行业 5 类: 用户/医保卡号/身份证号/医生执业证/医院编码)
CREATE TABLE IF NOT EXISTS `risk_blacklist` (
    `blacklist_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
    `blacklist_type` ENUM('用户','医保卡号','身份证号','医生执业证','医院编码') NOT NULL COMMENT '黑名单类型',
    `blacklist_value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` TEXT COMMENT '加入原因',
    `expire_time` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`blacklist_id`),
    UNIQUE INDEX `idx_blacklist_type_value` (`blacklist_type`, `blacklist_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控黑名单表';

-- 7. 患者风险画像表 (列名与电商版一致, 医疗语义映射见 COMMENT)
CREATE TABLE IF NOT EXISTS `risk_user_profile` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `risk_score` INT DEFAULT 0 COMMENT '综合风险评分(0-100)',
    `risk_level` ENUM('低','中','高','极高') DEFAULT '低' COMMENT '风险等级',
    `total_orders` INT DEFAULT 0 COMMENT '总就诊(挂号)数',
    `total_refunds` INT DEFAULT 0 COMMENT '取消挂号次数',
    `refund_rate` DECIMAL(5,4) DEFAULT 0 COMMENT '挂号取消率',
    `avg_order_amount` DECIMAL(10,2) DEFAULT 0 COMMENT '平均结算金额',
    `address_count` INT DEFAULT 0 COMMENT '就诊医院数量',
    `complaint_count` INT DEFAULT 0 COMMENT '医保结算次数',
    `assessment_count` INT DEFAULT 0 COMMENT '评估次数',
    `last_assessment_time` DATETIME DEFAULT NULL COMMENT '最近评估时间',
    `profile_data` JSON COMMENT '扩展画像数据',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='患者风险画像表';


-- ============================================
-- 系统管理表 (审计日志 + 告警, 与电商版完全一致)
-- ============================================

-- 8. 操作审计日志表
CREATE TABLE IF NOT EXISTS `risk_action_log` (
    `log_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `operator` VARCHAR(50) NOT NULL COMMENT '操作人(admin/system/ai_agent)',
    `action_type` ENUM('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST') NOT NULL COMMENT '操作类型',
    `target_type` ENUM('rule','case','blacklist') NOT NULL COMMENT '对象类型',
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

-- 9. 告警记录表
CREATE TABLE IF NOT EXISTS `risk_alert` (
    `alert_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '告警ID',
    `alert_type` ENUM('BUSINESS','MODEL','SYSTEM','SECURITY') NOT NULL COMMENT '告警分类',
    `alert_level` ENUM('P0','P1','P2','P3') NOT NULL COMMENT '告警等级 (P0=致命, P3=提示)',
    `alert_title` VARCHAR(200) NOT NULL COMMENT '告警标题',
    `alert_content` TEXT COMMENT '告警详情',
    `metric_name` VARCHAR(100) COMMENT '指标名(规则命中率/案件积压数等)',
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

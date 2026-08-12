-- ============================================================
-- 制造业风控系统 - 风控表 DDL 初始化脚本
-- 在 manufacturing_risk 数据库中创建 8 张风控自建表
-- (跟业务表分开管理; 仿 AI_Risk 电商风控的 9 张, 此处 8 张, 暂不做告警)
-- ============================================================

USE manufacturing_risk;

-- 1. 风控规则配置表
CREATE TABLE IF NOT EXISTS `risk_rule` (
    `rule_id` VARCHAR(50) NOT NULL COMMENT '规则ID',
    `rule_name` VARCHAR(100) NOT NULL COMMENT '规则名称',
    `rule_category` ENUM('串货风险','保修滥用','囤货风险','维修异常','资质风险','综合风险') NOT NULL COMMENT '风险场景分类',
    `event_type` ENUM('经销商订货','保修申请','售后维修','串货举报','通用') NOT NULL DEFAULT '通用' COMMENT '适用事件类型',
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
    `event_type` ENUM('经销商订货','保修申请','售后维修','串货举报') NOT NULL COMMENT '事件类型',
    `event_source_id` VARCHAR(50) NOT NULL COMMENT '关联业务ID(订单/保修单/举报单)',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID(经销商/举报人)',
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
    `entity_type` ENUM('经销商','订单','产品','保修') NOT NULL COMMENT '实体类型',
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
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
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
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `case_status` ENUM('待审核','审核中','已通过','已拒绝','已关闭') NOT NULL DEFAULT '待审核' COMMENT '案件状态',
    `case_category` VARCHAR(50) DEFAULT NULL COMMENT '案件分类',
    `risk_detail` JSON COMMENT '风险详情',
    `reviewer` VARCHAR(50) DEFAULT NULL COMMENT '审核人',
    `review_comment` TEXT DEFAULT NULL COMMENT '审核意见',
    `review_time` DATETIME DEFAULT NULL COMMENT '审核时间',
    `source_id` VARCHAR(50) DEFAULT NULL COMMENT '原始业务ID(订单/保修单/举报单)',
    `event_type` ENUM('经销商订货','保修申请','售后维修','串货举报') DEFAULT NULL COMMENT '触发案件的事件类型',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`case_id`),
    INDEX `idx_risk_case_status` (`case_status`),
    INDEX `idx_risk_case_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控案件表';

-- 6. 风控黑名单表 (风控系统自管: 经销商ID / 设备SN / 维修工 / 用户)
CREATE TABLE IF NOT EXISTS `risk_blacklist` (
    `blacklist_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
    `blacklist_type` ENUM('经销商ID','设备SN','维修工','用户') NOT NULL COMMENT '黑名单类型',
    `blacklist_value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` TEXT DEFAULT NULL COMMENT '加入原因',
    `expire_time` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`blacklist_id`),
    UNIQUE KEY `idx_blacklist_type_value` (`blacklist_type`, `blacklist_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控黑名单表';

-- 7. 经销商风险画像表
CREATE TABLE IF NOT EXISTS `risk_user_profile` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID(经销商)',
    `risk_score` INT DEFAULT 0 COMMENT '综合风险评分(0-100)',
    `risk_level` ENUM('低','中','高','极高') DEFAULT '低' COMMENT '风险等级',
    `total_orders` INT DEFAULT 0 COMMENT '总订货单数',
    `total_amount` DECIMAL(14,2) DEFAULT 0 COMMENT '历史订货总金额',
    `avg_order_amount` DECIMAL(12,2) DEFAULT 0 COMMENT '平均订货金额',
    `warranty_count` INT DEFAULT 0 COMMENT '保修申请次数',
    `repair_count` INT DEFAULT 0 COMMENT '维修次数',
    `contract_expired` INT DEFAULT 0 COMMENT '合同是否过期(0/1)',
    `assessment_count` INT DEFAULT 0 COMMENT '评估次数',
    `last_assessment_time` DATETIME DEFAULT NULL COMMENT '最近评估时间',
    `profile_data` JSON DEFAULT NULL COMMENT '扩展画像数据',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='经销商风险画像表';

-- 8. 操作审计日志表
CREATE TABLE IF NOT EXISTS `risk_action_log` (
    `log_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `operator` VARCHAR(50) NOT NULL COMMENT '操作人(admin/system)',
    `action_type` ENUM('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST') NOT NULL COMMENT '操作类型',
    `target_type` ENUM('rule','case','blacklist') NOT NULL COMMENT '对象类型',
    `target_id` VARCHAR(50) NOT NULL COMMENT '对象ID',
    `before_value` JSON DEFAULT NULL COMMENT '变更前 JSON (NULL=新增)',
    `after_value` JSON DEFAULT NULL COMMENT '变更后 JSON (NULL=删除)',
    `ip` VARCHAR(50) DEFAULT NULL COMMENT '操作 IP',
    `remark` VARCHAR(500) DEFAULT NULL COMMENT '备注',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (`log_id`),
    INDEX `idx_action_log_operator` (`operator`),
    INDEX `idx_action_log_target` (`target_type`, `target_id`),
    INDEX `idx_action_log_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='操作审计日志表';

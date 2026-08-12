-- ============================================================
-- 旅游出行风控系统 - 数据库建表脚本
-- 说明:
--   1. 脚本不写死数据库名, 连接目标库后执行即可
--   2. 全部使用 CREATE TABLE IF NOT EXISTS, 可重复执行
--   3. 业务表 11 张 + 风控核心表 9 张
--   4. 字符集统一 utf8mb4
-- 执行示例(库名从环境配置传入, 不硬编码):
--   mysql -h ${DB_HOST} -P ${DB_PORT} -u ${DB_USER} -p ${DB_NAME} < db/init.sql
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- 一、旅游业务表
-- ============================================================

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `name` VARCHAR(100) DEFAULT NULL COMMENT '用户姓名',
    `real_name_status` ENUM('未实名','已实名') DEFAULT '未实名' COMMENT '实名状态',
    `vip_level` VARCHAR(20) DEFAULT '普通' COMMENT '会员等级',
    `register_at` DATETIME DEFAULT NULL COMMENT '注册时间',
    `account_age_days` INT DEFAULT 0 COMMENT '账号年龄(天)',
    `phone` VARCHAR(20) DEFAULT NULL COMMENT '手机号',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`user_id`),
    INDEX `idx_user_phone` (`phone`),
    INDEX `idx_user_register_at` (`register_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游用户信息表';

-- 2. 设备指纹表
CREATE TABLE IF NOT EXISTS `device_fingerprint` (
    `fingerprint_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '设备指纹ID',
    `device_id` VARCHAR(100) NOT NULL COMMENT '设备ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `fingerprint_hash` VARCHAR(128) DEFAULT NULL COMMENT '设备指纹哈希',
    `first_seen` DATETIME DEFAULT NULL COMMENT '首次出现时间',
    `last_seen` DATETIME DEFAULT NULL COMMENT '最近出现时间',
    `os` VARCHAR(50) DEFAULT NULL COMMENT '操作系统',
    `browser` VARCHAR(100) DEFAULT NULL COMMENT '浏览器',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`fingerprint_id`),
    UNIQUE INDEX `idx_device_user` (`device_id`, `user_id`),
    INDEX `idx_device_user_id` (`user_id`),
    INDEX `idx_device_hash` (`fingerprint_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

-- 3. 旅游订单主表
CREATE TABLE IF NOT EXISTS `order_info` (
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `order_type` ENUM('机票','酒店','签证','跟团游','团票') NOT NULL COMMENT '订单类型',
    `total_amount` DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '订单总金额',
    `dest_country` VARCHAR(100) DEFAULT NULL COMMENT '目的地国家',
    `depart_date` DATE DEFAULT NULL COMMENT '出发日期',
    `return_date` DATE DEFAULT NULL COMMENT '返回日期',
    `passenger_count` INT NOT NULL DEFAULT 1 COMMENT '乘客人数',
    `pay_account` VARCHAR(100) DEFAULT NULL COMMENT '支付账号',
    `device_id` VARCHAR(100) DEFAULT NULL COMMENT '下单设备ID',
    `ip_address` VARCHAR(64) DEFAULT NULL COMMENT '下单IP',
    `order_remark` VARCHAR(1000) DEFAULT NULL COMMENT '订单备注',
    `order_status` VARCHAR(20) NOT NULL DEFAULT '待支付' COMMENT '订单状态',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
    `payment_time` DATETIME DEFAULT NULL COMMENT '支付时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`order_id`),
    INDEX `idx_order_user_id` (`user_id`),
    INDEX `idx_order_create_time` (`create_time`),
    INDEX `idx_order_pay_account` (`pay_account`),
    INDEX `idx_order_device_id` (`device_id`),
    INDEX `idx_order_dest_country` (`dest_country`),
    CONSTRAINT `fk_order_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单主表';

-- 4. 乘客信息表
CREATE TABLE IF NOT EXISTS `passenger_info` (
    `passenger_id` VARCHAR(50) NOT NULL COMMENT '乘客ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '下单用户ID',
    `name` VARCHAR(100) DEFAULT NULL COMMENT '乘客姓名',
    `id_type` ENUM('身份证','护照','其他') DEFAULT '身份证' COMMENT '证件类型',
    `id_number` VARCHAR(64) DEFAULT NULL COMMENT '证件号码',
    `passport_no` VARCHAR(64) DEFAULT NULL COMMENT '护照号码',
    `nationality` VARCHAR(50) DEFAULT NULL COMMENT '国籍',
    `age` INT DEFAULT NULL COMMENT '年龄',
    `phone` VARCHAR(20) DEFAULT NULL COMMENT '联系电话',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`passenger_id`),
    INDEX `idx_passenger_order_id` (`order_id`),
    INDEX `idx_passenger_user_id` (`user_id`),
    INDEX `idx_passenger_id_number` (`id_number`),
    INDEX `idx_passenger_passport_no` (`passport_no`),
    CONSTRAINT `fk_passenger_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
    CONSTRAINT `fk_passenger_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='乘客信息表';

-- 5. 机票预订表
CREATE TABLE IF NOT EXISTS `booking_flight` (
    `booking_id` VARCHAR(50) NOT NULL COMMENT '机票预订ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `flight_no` VARCHAR(20) NOT NULL COMMENT '航班号',
    `depart_airport` VARCHAR(100) DEFAULT NULL COMMENT '出发机场',
    `arrive_airport` VARCHAR(100) DEFAULT NULL COMMENT '到达机场',
    `depart_time` DATETIME DEFAULT NULL COMMENT '起飞时间',
    `cabin_class` VARCHAR(20) DEFAULT NULL COMMENT '舱位等级',
    `amount` DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '票面金额',
    `refundable` TINYINT(1) DEFAULT 1 COMMENT '是否可退',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`booking_id`),
    INDEX `idx_flight_order_id` (`order_id`),
    INDEX `idx_flight_no_time` (`flight_no`, `depart_time`),
    CONSTRAINT `fk_flight_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机票预订表';

-- 6. 酒店预订表
CREATE TABLE IF NOT EXISTS `booking_hotel` (
    `booking_id` VARCHAR(50) NOT NULL COMMENT '酒店预订ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `hotel_id` VARCHAR(50) NOT NULL COMMENT '酒店ID',
    `hotel_name` VARCHAR(200) DEFAULT NULL COMMENT '酒店名称',
    `check_in` DATE DEFAULT NULL COMMENT '入住日期',
    `check_out` DATE DEFAULT NULL COMMENT '离店日期',
    `room_count` INT NOT NULL DEFAULT 1 COMMENT '房间数',
    `is_refundable` TINYINT(1) DEFAULT 1 COMMENT '是否可取消',
    `amount` DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '预订金额',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`booking_id`),
    INDEX `idx_hotel_order_id` (`order_id`),
    INDEX `idx_hotel_id` (`hotel_id`),
    CONSTRAINT `fk_hotel_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='酒店预订表';

-- 7. 签证申请表
CREATE TABLE IF NOT EXISTS `visa_application` (
    `visa_id` VARCHAR(50) NOT NULL COMMENT '签证申请ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `dest_country` VARCHAR(100) NOT NULL COMMENT '目的地国家',
    `visa_type` VARCHAR(50) DEFAULT NULL COMMENT '签证类型',
    `passport_no` VARCHAR(64) DEFAULT NULL COMMENT '护照号',
    `reject_history` TINYINT(1) DEFAULT 0 COMMENT '是否有拒签历史',
    `submit_time` DATETIME DEFAULT NULL COMMENT '提交时间',
    `status` VARCHAR(20) DEFAULT '审核中' COMMENT '签证状态',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`visa_id`),
    INDEX `idx_visa_user_id` (`user_id`),
    INDEX `idx_visa_dest_country` (`dest_country`),
    INDEX `idx_visa_submit_time` (`submit_time`),
    INDEX `idx_visa_passport_no` (`passport_no`),
    CONSTRAINT `fk_visa_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='签证申请表';

-- 8. 机票退改申请表
CREATE TABLE IF NOT EXISTS `ticket_change_application` (
    `change_id` VARCHAR(50) NOT NULL COMMENT '退改申请ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `change_type` ENUM('改签','退票','其他') NOT NULL COMMENT '退改类型',
    `old_flight_no` VARCHAR(20) DEFAULT NULL COMMENT '原航班号',
    `new_flight_no` VARCHAR(20) DEFAULT NULL COMMENT '新航班号',
    `old_amount` DECIMAL(12,2) DEFAULT 0 COMMENT '原票面金额',
    `new_amount` DECIMAL(12,2) DEFAULT 0 COMMENT '新票面金额',
    `apply_time` DATETIME DEFAULT NULL COMMENT '申请时间',
    `status` VARCHAR(20) DEFAULT '待审核' COMMENT '处理状态',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`change_id`),
    INDEX `idx_change_order_id` (`order_id`),
    INDEX `idx_change_user_id` (`user_id`),
    INDEX `idx_change_apply_time` (`apply_time`),
    CONSTRAINT `fk_change_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
    CONSTRAINT `fk_change_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机票退改申请表';

-- 9. 酒店预授权表
CREATE TABLE IF NOT EXISTS `hotel_preauthorization` (
    `preauth_id` VARCHAR(50) NOT NULL COMMENT '预授权ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `hotel_id` VARCHAR(50) NOT NULL COMMENT '酒店ID',
    `preauth_amount` DECIMAL(12,2) DEFAULT 0 COMMENT '预授权金额',
    `actual_amount` DECIMAL(12,2) DEFAULT 0 COMMENT '实际扣款金额',
    `status` ENUM('待确认','已确认','已释放','异常') DEFAULT '待确认' COMMENT '预授权状态',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`preauth_id`),
    INDEX `idx_preauth_order_id` (`order_id`),
    INDEX `idx_preauth_user_id` (`user_id`),
    INDEX `idx_preauth_hotel_id` (`hotel_id`),
    CONSTRAINT `fk_preauth_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
    CONSTRAINT `fk_preauth_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='酒店预授权表';

-- 10. 团票 / 拼团表
CREATE TABLE IF NOT EXISTS `group_booking` (
    `group_id` VARCHAR(50) NOT NULL COMMENT '团票ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '关联订单ID',
    `leader_user_id` VARCHAR(50) NOT NULL COMMENT '团长用户ID',
    `member_count` INT NOT NULL DEFAULT 1 COMMENT '参团人数',
    `total_amount` DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '团票总金额',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`group_id`),
    INDEX `idx_group_order_id` (`order_id`),
    INDEX `idx_group_leader_user_id` (`leader_user_id`),
    CONSTRAINT `fk_group_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
    CONSTRAINT `fk_group_leader_user` FOREIGN KEY (`leader_user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='团票拼团表';

-- 11. 业务扩展黑名单表
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
    `entry_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
    `type` ENUM('护照号','签证号','设备指纹','支付账号','IP') NOT NULL COMMENT '黑名单类型',
    `value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` TEXT COMMENT '加入原因',
    `expire_at` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`entry_id`),
    UNIQUE INDEX `idx_blacklist_extra_type_value` (`type`, `value`),
    INDEX `idx_blacklist_extra_expire_at` (`expire_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游业务扩展黑名单表';

-- ============================================================
-- 二、风控核心表
-- ============================================================

-- 12. 风控规则配置表
CREATE TABLE IF NOT EXISTS `risk_rule` (
    `rule_id` VARCHAR(50) NOT NULL COMMENT '规则ID',
    `rule_name` VARCHAR(100) NOT NULL COMMENT '规则名称',
    `rule_category` ENUM('订单欺诈','支付风险','账户风险','退改滥用','签证风险','设备风险','跨境风险') NOT NULL COMMENT '风险场景分类',
    `event_type` ENUM('下单','支付','退改申请','签证申请','拼团报名','通用') NOT NULL DEFAULT '通用' COMMENT '适用事件类型',
    `rule_condition` JSON NOT NULL COMMENT '条件表达式',
    `risk_level` ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级',
    `risk_score` INT NOT NULL COMMENT '命中分值(0-100)',
    `action` ENUM('通过','标记','人工审核','拒绝') NOT NULL COMMENT '触发动作',
    `is_enabled` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `priority` INT DEFAULT 0 COMMENT '优先级(越高越先执行)',
    `description` TEXT COMMENT '规则描述',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`rule_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控规则配置表';

-- 13. 风控事件审计表
CREATE TABLE IF NOT EXISTS `risk_event` (
    `event_id` VARCHAR(50) NOT NULL COMMENT '事件ID',
    `event_type` ENUM('下单','支付','退改申请','签证申请','拼团报名') NOT NULL COMMENT '事件类型',
    `event_source_id` VARCHAR(50) NOT NULL COMMENT '关联业务ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `event_data` JSON COMMENT '事件快照',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`event_id`),
    INDEX `idx_risk_event_user_id` (`user_id`),
    INDEX `idx_risk_event_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控事件审计表';

-- 14. 风控特征快照表
CREATE TABLE IF NOT EXISTS `risk_feature` (
    `feature_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '特征ID',
    `event_id` VARCHAR(50) NOT NULL COMMENT '关联事件ID',
    `entity_type` ENUM('用户','订单','地址','设备','乘客','语义') NOT NULL COMMENT '实体类型',
    `entity_id` VARCHAR(50) NOT NULL COMMENT '实体ID',
    `feature_name` VARCHAR(100) NOT NULL COMMENT '特征名称',
    `feature_value` DECIMAL(15,4) COMMENT '特征值',
    `compute_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '计算时间',
    PRIMARY KEY (`feature_id`),
    INDEX `idx_risk_feature_event_id` (`event_id`),
    INDEX `idx_risk_feature_entity` (`entity_type`, `entity_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控特征快照表';

-- 15. 风控评估结果表
CREATE TABLE IF NOT EXISTS `risk_assessment` (
    `assessment_id` VARCHAR(50) NOT NULL COMMENT '评估ID',
    `event_id` VARCHAR(50) NOT NULL COMMENT '关联事件ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `rule_results` JSON COMMENT '规则结果',
    `rule_count` INT DEFAULT 0 COMMENT '命中规则数',
    `final_score` INT NOT NULL COMMENT '最终评分(0-100)',
    `risk_level` ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级',
    `decision` ENUM('通过','标记','人工审核','拒绝') NOT NULL COMMENT '决策',
    `ml_score` DECIMAL(5,2) DEFAULT NULL COMMENT 'XGBoost 风险分(0-100)',
    `ml_probability` DECIMAL(6,4) DEFAULT NULL COMMENT 'XGBoost 拒绝概率(0-1)',
    `ml_decision` VARCHAR(10) DEFAULT NULL COMMENT 'ML 维度决策',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`assessment_id`),
    INDEX `idx_risk_assessment_user_id` (`user_id`),
    INDEX `idx_risk_assessment_decision` (`decision`),
    INDEX `idx_risk_assessment_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控评估结果表';

-- 16. 风控案件表
CREATE TABLE IF NOT EXISTS `risk_case` (
    `case_id` VARCHAR(50) NOT NULL COMMENT '案件ID',
    `assessment_id` VARCHAR(50) NOT NULL COMMENT '关联评估ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `case_status` ENUM('待审核','审核中','已通过','已拒绝','已关闭') NOT NULL DEFAULT '待审核' COMMENT '案件状态',
    `case_category` VARCHAR(50) DEFAULT NULL COMMENT '案件分类',
    `risk_detail` JSON COMMENT '风险详情',
    `source_id` VARCHAR(50) DEFAULT NULL COMMENT '原始业务ID',
    `event_type` ENUM('下单','支付','退改申请','签证申请','拼团报名') DEFAULT NULL COMMENT '触发案件的事件类型',
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

-- 17. 风控黑名单表
CREATE TABLE IF NOT EXISTS `risk_blacklist` (
    `blacklist_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
    `blacklist_type` ENUM('用户','手机号','护照号','签证号','设备指纹','支付账号','IP') NOT NULL COMMENT '黑名单类型',
    `blacklist_value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` TEXT COMMENT '加入原因',
    `expire_time` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`blacklist_id`),
    UNIQUE INDEX `idx_blacklist_type_value` (`blacklist_type`, `blacklist_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控黑名单表';

-- 18. 用户风险画像表
CREATE TABLE IF NOT EXISTS `risk_user_profile` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `risk_score` INT DEFAULT 0 COMMENT '综合风险评分(0-100)',
    `risk_level` ENUM('低','中','高','极高') DEFAULT '低' COMMENT '风险等级',
    `total_orders` INT DEFAULT 0 COMMENT '总订单数',
    `total_refunds` INT DEFAULT 0 COMMENT '退改次数',
    `refund_rate` DECIMAL(5,4) DEFAULT 0 COMMENT '退改率',
    `avg_order_amount` DECIMAL(10,2) DEFAULT 0 COMMENT '平均订单金额',
    `address_count` INT DEFAULT 0 COMMENT '常用乘客/联系人数量',
    `complaint_count` INT DEFAULT 0 COMMENT '投诉次数',
    `assessment_count` INT DEFAULT 0 COMMENT '评估次数',
    `last_assessment_time` DATETIME DEFAULT NULL COMMENT '最近评估时间',
    `profile_data` JSON COMMENT '扩展画像数据',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户风险画像表';

-- 19. 操作审计日志表
CREATE TABLE IF NOT EXISTS `risk_action_log` (
    `log_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `operator` VARCHAR(50) NOT NULL COMMENT '操作人(admin/system/ai_agent)',
    `action_type` ENUM(
        'CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE',
        'REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE',
        'ADD_BLACKLIST','REMOVE_BLACKLIST','LLM_REMARK'
    ) NOT NULL COMMENT '操作类型',
    `target_type` ENUM('rule','case','blacklist','model') NOT NULL COMMENT '对象类型',
    `target_id` VARCHAR(50) NOT NULL COMMENT '对象ID',
    `before_value` JSON COMMENT '变更前',
    `after_value` JSON COMMENT '变更后',
    `ip` VARCHAR(50) DEFAULT NULL COMMENT '操作IP',
    `remark` VARCHAR(500) DEFAULT NULL COMMENT '备注',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (`log_id`),
    INDEX `idx_action_log_operator` (`operator`),
    INDEX `idx_action_log_target` (`target_type`, `target_id`),
    INDEX `idx_action_log_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控操作审计日志表';

-- 20. 告警记录表
CREATE TABLE IF NOT EXISTS `risk_alert` (
    `alert_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '告警ID',
    `alert_type` ENUM('BUSINESS','MODEL','SYSTEM','SECURITY') NOT NULL COMMENT '告警分类',
    `alert_level` ENUM('P0','P1','P2','P3') NOT NULL COMMENT '告警等级',
    `alert_title` VARCHAR(200) NOT NULL COMMENT '告警标题',
    `alert_content` TEXT COMMENT '告警详情',
    `metric_name` VARCHAR(100) DEFAULT NULL COMMENT '指标名',
    `metric_value` DECIMAL(20,6) DEFAULT NULL COMMENT '触发值',
    `threshold` DECIMAL(20,6) DEFAULT NULL COMMENT '阈值',
    `status` ENUM('PENDING','HANDLING','RESOLVED','IGNORED') DEFAULT 'PENDING' COMMENT '处理状态',
    `handler` VARCHAR(50) DEFAULT NULL COMMENT '处理人',
    `resolve_time` DATETIME DEFAULT NULL COMMENT '解决时间',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '告警时间',
    PRIMARY KEY (`alert_id`),
    INDEX `idx_alert_status` (`status`),
    INDEX `idx_alert_level` (`alert_level`),
    INDEX `idx_alert_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控告警记录表';

SET FOREIGN_KEY_CHECKS = 1;

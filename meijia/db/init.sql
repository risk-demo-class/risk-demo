SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS `risk_proj` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE `risk_proj`;

CREATE TABLE `user_info` (
  `user_id` VARCHAR(50) NOT NULL, `name` VARCHAR(100) NOT NULL,
  `role` VARCHAR(20) NOT NULL, `student_id` VARCHAR(50) NULL,
  `real_name_status` VARCHAR(20) NOT NULL DEFAULT '未认证',
  `register_at` DATETIME(3) NOT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`user_id`), UNIQUE KEY `uk_user_student_id` (`student_id`),
  KEY `idx_user_role` (`role`), KEY `idx_user_register_at` (`register_at`),
  CONSTRAINT `chk_user_role` CHECK (`role` IN ('学生','家长','老师')),
  CONSTRAINT `chk_real_name_status` CHECK (`real_name_status` IN ('未认证','认证中','已认证','认证失败'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';

CREATE TABLE `user_device` (
  `relation_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id` VARCHAR(50) NOT NULL, `device_fingerprint` CHAR(64) NOT NULL,
  `first_seen_at` DATETIME(3) NOT NULL, `last_seen_at` DATETIME(3) NOT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`relation_id`), UNIQUE KEY `uk_user_device` (`user_id`,`device_fingerprint`),
  KEY `idx_device_active` (`device_fingerprint`,`last_seen_at`,`user_id`),
  KEY `idx_user_device_active` (`user_id`,`last_seen_at`),
  CONSTRAINT `fk_user_device_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_device_seen_time` CHECK (`last_seen_at` >= `first_seen_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户设备关联表';

CREATE TABLE `course` (
  `course_id` VARCHAR(50) NOT NULL, `name` VARCHAR(150) NOT NULL,
  `category` VARCHAR(50) NOT NULL, `price` DECIMAL(12,2) NOT NULL,
  `teacher_id` VARCHAR(50) NOT NULL, `total_hours` DECIMAL(7,2) NOT NULL,
  `course_status` VARCHAR(20) NOT NULL DEFAULT '草稿',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`course_id`), KEY `idx_course_teacher` (`teacher_id`),
  KEY `idx_course_category_status` (`category`,`course_status`),
  CONSTRAINT `fk_course_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_course_price` CHECK (`price` >= 0),
  CONSTRAINT `chk_course_total_hours` CHECK (`total_hours` > 0),
  CONSTRAINT `chk_course_status` CHECK (`course_status` IN ('草稿','已上架','已下架','已归档'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='课程信息表';

CREATE TABLE `order_info` (
  `order_id` VARCHAR(50) NOT NULL, `user_id` VARCHAR(50) NOT NULL,
  `learner_user_id` VARCHAR(50) NOT NULL, `course_id` VARCHAR(50) NOT NULL,
  `total_amount` DECIMAL(12,2) NOT NULL, `currency` CHAR(3) NOT NULL DEFAULT 'CNY',
  `study_goal` VARCHAR(500) NULL, `expected_finish_days` SMALLINT UNSIGNED NULL,
  `payment_account_hash` CHAR(64) NULL, `order_status` VARCHAR(20) NOT NULL DEFAULT '待支付',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3), `paid_at` DATETIME(3) NULL,
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`order_id`),
  KEY `idx_order_user_paid` (`user_id`,`order_status`,`paid_at`),
  KEY `idx_order_course_created` (`course_id`,`order_status`,`created_at`,`learner_user_id`),
  KEY `idx_order_payment_course` (`payment_account_hash`,`course_id`,`created_at`),
  KEY `idx_order_learner` (`learner_user_id`,`course_id`),
  CONSTRAINT `fk_order_buyer` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_order_learner` FOREIGN KEY (`learner_user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_order_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_order_amount` CHECK (`total_amount` >= 0),
  CONSTRAINT `chk_order_days` CHECK (`expected_finish_days` IS NULL OR `expected_finish_days` > 0),
  CONSTRAINT `chk_order_status` CHECK (`order_status` IN ('待支付','已支付','已取消','已关闭','部分退款','已退款'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='课程报名订单表';

CREATE TABLE `learning_progress` (
  `progress_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id` VARCHAR(50) NOT NULL, `course_id` VARCHAR(50) NOT NULL,
  `total_minutes` INT UNSIGNED NOT NULL DEFAULT 0,
  `completion_rate` DECIMAL(5,2) NOT NULL DEFAULT 0,
  `last_active_at` DATETIME(3) NULL, `completed_at` DATETIME(3) NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`progress_id`), UNIQUE KEY `uk_progress_user_course` (`user_id`,`course_id`),
  KEY `idx_progress_course_active` (`course_id`,`last_active_at`,`user_id`),
  CONSTRAINT `fk_progress_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_progress_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_progress_rate` CHECK (`completion_rate` BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习进度表';

CREATE TABLE `refund_request` (
  `refund_id` VARCHAR(50) NOT NULL, `order_id` VARCHAR(50) NOT NULL,
  `requested_by_user_id` VARCHAR(50) NOT NULL, `reason` VARCHAR(500) NOT NULL,
  `study_minutes_before_refund` INT UNSIGNED NOT NULL,
  `requested_amount` DECIMAL(12,2) NOT NULL, `refund_amount` DECIMAL(12,2) NULL,
  `refund_status` VARCHAR(20) NOT NULL DEFAULT '待审核',
  `requested_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3), `completed_at` DATETIME(3) NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`refund_id`), KEY `idx_refund_order_requested` (`order_id`,`requested_at`),
  KEY `idx_refund_status_completed` (`refund_status`,`completed_at`,`order_id`),
  KEY `idx_refund_requester` (`requested_by_user_id`,`requested_at`),
  CONSTRAINT `fk_refund_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_refund_requester` FOREIGN KEY (`requested_by_user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_refund_requested_amount` CHECK (`requested_amount` > 0),
  CONSTRAINT `chk_refund_amount` CHECK (`refund_amount` IS NULL OR (`refund_amount` >= 0 AND `refund_amount` <= `requested_amount`)),
  CONSTRAINT `chk_refund_status` CHECK (`refund_status` IN ('待审核','审核中','已批准','已拒绝','已取消','退款成功','退款失败'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='退费申请表';

CREATE TABLE `blacklist_extra` (
  `entry_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, `type` VARCHAR(20) NOT NULL,
  `value` VARCHAR(200) NOT NULL, `value_masked` VARCHAR(200) NULL,
  `reason` VARCHAR(500) NOT NULL, `status` VARCHAR(20) NOT NULL DEFAULT '启用',
  `expire_at` DATETIME(3) NULL, `created_by` VARCHAR(50) NOT NULL DEFAULT 'system',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  `deleted_at` DATETIME(3) NULL,
  PRIMARY KEY (`entry_id`), UNIQUE KEY `uk_blacklist_type_value` (`type`,`value`),
  KEY `idx_blacklist_active` (`status`,`expire_at`,`deleted_at`),
  CONSTRAINT `chk_blacklist_type` CHECK (`type` IN ('用户ID','学号','身份证','设备指纹','直播账号')),
  CONSTRAINT `chk_blacklist_status` CHECK (`status` IN ('启用','停用'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控黑名单表';

CREATE TABLE `education_credential` (
  `credential_id` VARCHAR(50) NOT NULL, `user_id` VARCHAR(50) NOT NULL,
  `id_card_ciphertext` VARBINARY(512) NOT NULL, `id_card_hash` CHAR(64) NOT NULL,
  `id_card_masked` VARCHAR(20) NOT NULL, `submitted_education_level` VARCHAR(30) NOT NULL,
  `authoritative_education_level` VARCHAR(30) NULL,
  `verify_status` VARCHAR(20) NOT NULL DEFAULT '待核验', `mismatch_reason` VARCHAR(100) NULL,
  `verify_source` VARCHAR(50) NULL, `verify_reference_id` VARCHAR(100) NULL,
  `submitted_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3), `verified_at` DATETIME(3) NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`credential_id`), KEY `idx_credential_user_submitted` (`user_id`,`submitted_at`),
  KEY `idx_credential_status` (`verify_status`,`verified_at`), KEY `idx_credential_id_hash` (`id_card_hash`),
  CONSTRAINT `fk_credential_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_credential_status` CHECK (`verify_status` IN ('待核验','匹配','不匹配','无记录','系统异常'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学历认证表';

CREATE TABLE `live_reward` (
  `reward_id` VARCHAR(50) NOT NULL, `live_session_id` VARCHAR(50) NOT NULL,
  `user_id` VARCHAR(50) NOT NULL, `reward_account_id` VARCHAR(50) NOT NULL,
  `original_reward_id` VARCHAR(50) NULL, `transaction_type` VARCHAR(20) NOT NULL DEFAULT '打赏',
  `amount` DECIMAL(12,2) NOT NULL, `reward_status` VARCHAR(20) NOT NULL DEFAULT '处理中',
  `rewarded_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`reward_id`),
  KEY `idx_reward_account_session` (`reward_account_id`,`live_session_id`,`reward_status`,`transaction_type`,`rewarded_at`),
  KEY `idx_reward_user_time` (`user_id`,`rewarded_at`), KEY `idx_reward_original` (`original_reward_id`),
  CONSTRAINT `fk_reward_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_reward_original` FOREIGN KEY (`original_reward_id`) REFERENCES `live_reward` (`reward_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_reward_type` CHECK (`transaction_type` IN ('打赏','退款','撤销','冲正')),
  CONSTRAINT `chk_reward_status` CHECK (`reward_status` IN ('处理中','成功','失败')),
  CONSTRAINT `chk_reward_amount` CHECK (`amount` > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='直播打赏流水表';

CREATE TABLE `risk_rule` (
  `rule_id` VARCHAR(20) NOT NULL, `rule_name` VARCHAR(100) NOT NULL,
  `rule_category` VARCHAR(30) NOT NULL, `event_type` VARCHAR(30) NOT NULL,
  `rule_condition` JSON NOT NULL, `risk_level` VARCHAR(20) NOT NULL,
  `risk_score` TINYINT UNSIGNED NOT NULL, `action` VARCHAR(20) NOT NULL,
  `is_enabled` TINYINT(1) NOT NULL DEFAULT 1, `priority` SMALLINT NOT NULL DEFAULT 0,
  `version` INT UNSIGNED NOT NULL DEFAULT 1, `description` VARCHAR(500) NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  `deleted_at` DATETIME(3) NULL,
  PRIMARY KEY (`rule_id`), KEY `idx_rule_event_enabled` (`event_type`,`is_enabled`,`deleted_at`,`priority`),
  CONSTRAINT `chk_rule_level` CHECK (`risk_level` IN ('低','中','高','极高')),
  CONSTRAINT `chk_rule_score` CHECK (`risk_score` BETWEEN 0 AND 100),
  CONSTRAINT `chk_rule_action` CHECK (`action` IN ('通过','标记','人工审核','拒绝'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控规则配置表';

CREATE TABLE `risk_event` (
  `event_id` VARCHAR(50) NOT NULL, `event_type` VARCHAR(30) NOT NULL,
  `event_source_id` VARCHAR(50) NOT NULL, `user_id` VARCHAR(50) NOT NULL,
  `event_data` JSON NULL, `occurred_at` DATETIME(3) NOT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`event_id`), KEY `idx_event_user_time` (`user_id`,`occurred_at`),
  KEY `idx_event_source` (`event_type`,`event_source_id`),
  CONSTRAINT `fk_event_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控事件审计表';

CREATE TABLE `risk_feature` (
  `feature_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, `event_id` VARCHAR(50) NOT NULL,
  `entity_type` VARCHAR(30) NOT NULL, `entity_id` VARCHAR(100) NOT NULL,
  `feature_name` VARCHAR(100) NOT NULL, `feature_value` JSON NOT NULL,
  `data_as_of` DATETIME(3) NOT NULL, `computed_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`feature_id`), UNIQUE KEY `uk_feature_event_name` (`event_id`,`entity_type`,`entity_id`,`feature_name`),
  KEY `idx_feature_entity` (`entity_type`,`entity_id`,`feature_name`,`computed_at`),
  CONSTRAINT `fk_feature_event` FOREIGN KEY (`event_id`) REFERENCES `risk_event` (`event_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控特征快照表';

CREATE TABLE `risk_assessment` (
  `assessment_id` VARCHAR(50) NOT NULL, `event_id` VARCHAR(50) NOT NULL, `user_id` VARCHAR(50) NOT NULL,
  `feature_snapshot` JSON NOT NULL, `rule_results` JSON NOT NULL,
  `rule_count` SMALLINT UNSIGNED NOT NULL DEFAULT 0, `final_score` TINYINT UNSIGNED NOT NULL,
  `risk_level` VARCHAR(20) NOT NULL, `decision` VARCHAR(20) NOT NULL, `blocked_by` VARCHAR(30) NULL,
  `ml_score` FLOAT NULL, `ml_decision` VARCHAR(20) NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`assessment_id`), UNIQUE KEY `uk_assessment_event` (`event_id`),
  KEY `idx_assessment_user_time` (`user_id`,`created_at`), KEY `idx_assessment_decision_time` (`decision`,`created_at`),
  CONSTRAINT `fk_assessment_event` FOREIGN KEY (`event_id`) REFERENCES `risk_event` (`event_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_assessment_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_assessment_score` CHECK (`final_score` BETWEEN 0 AND 100),
  CONSTRAINT `chk_assessment_level` CHECK (`risk_level` IN ('低','中','高','极高')),
  CONSTRAINT `chk_assessment_decision` CHECK (`decision` IN ('通过','标记','人工审核','拒绝'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控评估结果表';

CREATE TABLE `risk_case` (
  `case_id` VARCHAR(50) NOT NULL, `assessment_id` VARCHAR(50) NOT NULL, `user_id` VARCHAR(50) NOT NULL,
  `case_status` VARCHAR(20) NOT NULL DEFAULT '待审核', `case_category` VARCHAR(50) NOT NULL,
  `risk_detail` JSON NULL, `reviewer` VARCHAR(50) NULL, `review_comment` VARCHAR(1000) NULL,
  `reviewed_at` DATETIME(3) NULL, `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`case_id`), UNIQUE KEY `uk_case_assessment` (`assessment_id`),
  KEY `idx_case_status_time` (`case_status`,`created_at`), KEY `idx_case_user_time` (`user_id`,`created_at`),
  CONSTRAINT `fk_case_assessment` FOREIGN KEY (`assessment_id`) REFERENCES `risk_assessment` (`assessment_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_case_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_case_status` CHECK (`case_status` IN ('待审核','审核中','已通过','已拒绝','已关闭'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人工审核案件表';

CREATE TABLE `risk_alert` (
  `alert_id` BIGINT NOT NULL AUTO_INCREMENT,
  `alert_type` VARCHAR(20) NOT NULL, `alert_level` VARCHAR(10) NOT NULL,
  `alert_title` VARCHAR(200) NOT NULL, `alert_content` VARCHAR(1000) NOT NULL,
  `metric_name` VARCHAR(100) NULL, `metric_value` FLOAT NULL, `threshold` FLOAT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING', `handler` VARCHAR(50) NULL,
  `create_time` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3), `resolve_time` DATETIME(3) NULL,
  PRIMARY KEY (`alert_id`), KEY `idx_alert_status_time` (`status`,`create_time`),
  CONSTRAINT `chk_alert_type` CHECK (`alert_type` IN ('BUSINESS','MODEL')),
  CONSTRAINT `chk_alert_level` CHECK (`alert_level` IN ('P1','P2')),
  CONSTRAINT `chk_alert_status` CHECK (`status` IN ('PENDING','HANDLING','RESOLVED','IGNORED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控告警表';

CREATE TABLE `risk_action_log` (
  `log_id` BIGINT NOT NULL AUTO_INCREMENT,
  `operator` VARCHAR(50) NOT NULL, `action_type` VARCHAR(50) NOT NULL,
  `target_type` VARCHAR(30) NOT NULL, `target_id` VARCHAR(100) NOT NULL,
  `before_value` JSON NULL, `after_value` JSON NULL,
  `ip` VARCHAR(50) NULL, `remark` VARCHAR(500) NULL,
  `create_time` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`log_id`), KEY `idx_actionlog_target` (`target_type`,`target_id`),
  KEY `idx_actionlog_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作审计日志表';

INSERT INTO `risk_rule` (`rule_id`,`rule_name`,`rule_category`,`event_type`,`rule_condition`,`risk_level`,`risk_score`,`action`,`priority`,`description`) VALUES
('R001','刷单式报名','报名风险','报名支付成功',JSON_OBJECT('field','course_linked_new_student_count_7d','op','>=','value',3),'极高',100,'拒绝',100,'同课程7天内至少3个有关联的新学员报名'),
('R002','0学时退费','退费风险','退费申请提交',JSON_OBJECT('field','study_minutes_before_refund','op','<','value',5),'高',80,'人工审核',80,'退费前学习不足5分钟'),
('R005','大额连报','报名风险','报名支付成功',JSON_OBJECT('field','buyer_paid_amount_1h','op','>','value',30000),'高',80,'人工审核',80,'购买者1小时支付毛额超过30000元'),
('R008','假学员代理','设备风险','设备关联更新',JSON_OBJECT('field','device_student_count','op','>=','value',5),'极高',100,'拒绝',100,'同设备近180天关联至少5个学员'),
('R012','退费连环','退费风险','退款成功',JSON_OBJECT('and',JSON_ARRAY(JSON_OBJECT('field','user_refund_count_90d','op','>=','value',3),JSON_OBJECT('field','user_refund_amount_90d','op','>','value',10000))),'中',50,'标记',50,'90天退款次数和金额同时超阈值'),
('R018','直播打赏异常','直播风险','直播打赏变更',JSON_OBJECT('and',JSON_ARRAY(JSON_OBJECT('field','session_reward_net_amount','op','>','value',5000),JSON_OBJECT('field','account_age_days','op','<','value',30))),'中',50,'标记',50,'新账号单场打赏净额超过5000元'),
('R025','学历认证冲突','认证风险','学历核验完成',JSON_OBJECT('field','credential_mismatch','op','==','value',1),'高',80,'人工审核',80,'学历或身份与权威源明确不匹配'),
('R030','黑学员拦截','黑名单风险','通用',JSON_OBJECT('field','student_blacklist_hit','op','==','value',1),'极高',100,'拒绝',1000,'学号命中有效黑名单');

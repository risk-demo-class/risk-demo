-- ============================================================
-- 教育行业 AI 风控系统 - 业务表 DDL
-- 7 张业务表，按外键依赖顺序创建
-- 对应 ORM: app/models_business.py
-- MySQL 8.0 / utf8mb4
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(100) NOT NULL COMMENT '用户姓名',
  `role` enum('学生','家长','老师') NOT NULL COMMENT '用户角色',
  `student_id` varchar(50) DEFAULT NULL COMMENT '学号/学员编号（非学生可为空）',
  `id_card_hash` varchar(64) DEFAULT NULL COMMENT '身份证号SHA-256哈希，不保存明文',
  `real_name_status` enum('未认证','已认证','认证失败') NOT NULL DEFAULT '未认证' COMMENT '实名认证状态',
  `guardian_consent_status` enum('不适用','待确认','已同意','已撤回') NOT NULL DEFAULT '不适用' COMMENT '未成年人监护人同意状态',
  `register_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
  `device_id` varchar(64) DEFAULT NULL COMMENT '注册/常用设备指纹',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '账号是否有效',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `student_id` (`student_id`),
  KEY `idx_user_role_active` (`role`,`is_active`),
  KEY `idx_user_device` (`device_id`),
  KEY `idx_user_id_card_hash` (`id_card_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育平台用户信息';

-- 2. 课程信息表
CREATE TABLE IF NOT EXISTS `course` (
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `name` varchar(150) NOT NULL COMMENT '课程名称',
  `category` varchar(50) NOT NULL COMMENT '课程分类',
  `price` decimal(12,2) NOT NULL COMMENT '课程标准价格',
  `teacher_id` varchar(50) NOT NULL COMMENT '授课老师ID',
  `total_hours` decimal(8,2) NOT NULL COMMENT '课程总学时',
  `target_role` enum('学生','家长','老师','不限') NOT NULL DEFAULT '学生' COMMENT '课程适用角色',
  `status` enum('草稿','上架','下架') NOT NULL DEFAULT '草稿' COMMENT '课程状态',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`course_id`),
  KEY `idx_course_category_status` (`category`,`status`),
  KEY `idx_course_teacher` (`teacher_id`),
  CONSTRAINT `ck_course_price_non_negative` CHECK ((`price` >= 0)),
  CONSTRAINT `ck_course_total_hours_positive` CHECK ((`total_hours` > 0)),
  CONSTRAINT `fk_course_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育课程信息';

-- 3. 课程报名订单
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '报名订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '报名用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `total_amount` decimal(12,2) NOT NULL COMMENT '订单原始金额',
  `discount_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '优惠金额',
  `study_goal` varchar(255) DEFAULT NULL COMMENT '学习目标',
  `expected_finish_days` int NOT NULL DEFAULT '90' COMMENT '预计完成天数',
  `status` enum('待支付','已支付','已取消','部分退费','已退费') NOT NULL DEFAULT '待支付' COMMENT '订单状态',
  `order_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  `payment_time` datetime DEFAULT NULL COMMENT '支付时间',
  `pay_channel` varchar(30) DEFAULT NULL COMMENT '支付渠道',
  `payment_account_hash` varchar(64) DEFAULT NULL COMMENT '支付账号哈希',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`order_id`),
  KEY `idx_order_user_time` (`user_id`,`order_time`),
  KEY `idx_order_course_time` (`course_id`,`order_time`),
  KEY `idx_order_status_time` (`status`,`order_time`),
  CONSTRAINT `ck_order_total_amount_non_negative` CHECK ((`total_amount` >= 0)),
  CONSTRAINT `ck_order_discount_non_negative` CHECK ((`discount_amount` >= 0)),
  CONSTRAINT `ck_order_discount_not_exceed_total` CHECK ((`discount_amount` <= `total_amount`)),
  CONSTRAINT `ck_order_finish_days_positive` CHECK ((`expected_finish_days` > 0)),
  CONSTRAINT `fk_order_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_order_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程报名订单';

-- 4. 学习进度
CREATE TABLE IF NOT EXISTS `learning_progress` (
  `progress_id` varchar(50) NOT NULL COMMENT '学习进度ID',
  `order_id` varchar(50) NOT NULL COMMENT '报名订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `total_minutes` int NOT NULL DEFAULT '0' COMMENT '累计学习分钟数',
  `completion_rate` decimal(5,2) NOT NULL DEFAULT '0.00' COMMENT '完成率(0-100)',
  `last_active_at` datetime DEFAULT NULL COMMENT '最后学习时间',
  `device_id` varchar(64) DEFAULT NULL COMMENT '最近学习设备指纹',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`progress_id`),
  UNIQUE KEY `uk_progress_order` (`order_id`),
  KEY `idx_progress_user_active` (`user_id`,`last_active_at`),
  KEY `idx_progress_course` (`course_id`),
  KEY `idx_progress_device` (`device_id`),
  CONSTRAINT `ck_progress_minutes_non_negative` CHECK ((`total_minutes` >= 0)),
  CONSTRAINT `ck_progress_completion_rate_range` CHECK (((`completion_rate` >= 0) AND (`completion_rate` <= 100))),
  CONSTRAINT `fk_progress_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_progress_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_progress_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程学习进度';

-- 5. 退费申请
CREATE TABLE IF NOT EXISTS `refund_request` (
  `refund_id` varchar(50) NOT NULL COMMENT '退费申请ID',
  `order_id` varchar(50) NOT NULL COMMENT '报名订单ID',
  `reason` text NOT NULL COMMENT '退费原因',
  `study_minutes_before_refund` int NOT NULL DEFAULT '0' COMMENT '退费申请时已学分钟数',
  `refund_amount` decimal(12,2) NOT NULL COMMENT '申请退费金额',
  `status` enum('待审核','已通过','已拒绝','已退款') NOT NULL DEFAULT '待审核' COMMENT '退费状态',
  `refund_account_hash` varchar(64) DEFAULT NULL COMMENT '退款目标账号哈希',
  `is_original_route` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否原路退回',
  `apply_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '申请时间',
  `complete_time` datetime DEFAULT NULL COMMENT '完成时间',
  PRIMARY KEY (`refund_id`),
  KEY `idx_refund_order_time` (`order_id`,`apply_time`),
  KEY `idx_refund_status_time` (`status`,`apply_time`),
  KEY `idx_refund_account` (`refund_account_hash`),
  CONSTRAINT `ck_refund_amount_non_negative` CHECK ((`refund_amount` >= 0)),
  CONSTRAINT `ck_refund_study_minutes_non_negative` CHECK ((`study_minutes_before_refund` >= 0)),
  CONSTRAINT `fk_refund_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程退费申请';

-- 6. 直播课堂打赏
CREATE TABLE IF NOT EXISTS `live_reward` (
  `reward_id` varchar(50) NOT NULL COMMENT '打赏记录ID',
  `user_id` varchar(50) NOT NULL COMMENT '打赏用户ID',
  `teacher_id` varchar(50) NOT NULL COMMENT '收款老师ID',
  `live_session_id` varchar(50) NOT NULL COMMENT '直播场次ID',
  `reward_amount` decimal(12,2) NOT NULL COMMENT '打赏金额',
  `device_id` varchar(64) DEFAULT NULL COMMENT '打赏设备指纹',
  `guardian_consent_snapshot` enum('不适用','待确认','已同意','已撤回') NOT NULL DEFAULT '不适用' COMMENT '打赏时监护人同意状态快照',
  `payment_account_hash` varchar(64) DEFAULT NULL COMMENT '支付账号哈希',
  `status` enum('待支付','已支付','已拦截','已退款') NOT NULL DEFAULT '待支付' COMMENT '打赏状态',
  `reward_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '打赏时间',
  PRIMARY KEY (`reward_id`),
  KEY `idx_reward_user_time` (`user_id`,`reward_time`),
  KEY `idx_reward_session_time` (`live_session_id`,`reward_time`),
  KEY `idx_reward_device` (`device_id`),
  KEY `idx_reward_teacher` (`teacher_id`),
  CONSTRAINT `ck_reward_amount_positive` CHECK ((`reward_amount` > 0)),
  CONSTRAINT `fk_reward_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_reward_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `user_info` (`user_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='直播课堂打赏记录';

-- 7. 教育业务补充黑名单
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` int NOT NULL AUTO_INCREMENT COMMENT '条目ID',
  `entry_type` enum('学号','身份证哈希','设备指纹','直播账号') NOT NULL COMMENT '黑名单标识类型',
  `entry_value` varchar(128) NOT NULL COMMENT '标识值；敏感标识只保存哈希',
  `reason` varchar(500) NOT NULL COMMENT '加入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间，空值表示永久',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否有效',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `uk_blacklist_extra_type_value` (`entry_type`,`entry_value`),
  KEY `idx_blacklist_extra_expire` (`expire_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育业务补充黑名单';

SET FOREIGN_KEY_CHECKS = 1;

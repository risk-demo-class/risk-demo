-- ============================================
-- 教育风控系统 - 业务表 DDL 初始化脚本
-- 创建 6 张教育业务表 (按外键依赖顺序)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础维度表 (无外键依赖)
-- ============================

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) NOT NULL DEFAULT '' COMMENT '姓名',
  `role` enum('学生','家长','老师') NOT NULL DEFAULT '学生' COMMENT '角色',
  `student_id` varchar(50) DEFAULT NULL COMMENT '学号',
  `real_name_status` enum('未认证','已认证','认证失败') NOT NULL DEFAULT '未认证' COMMENT '实名认证状态',
  `register_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
  PRIMARY KEY (`user_id`),
  KEY `idx_student_id` (`student_id`),
  KEY `idx_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 课程表
CREATE TABLE IF NOT EXISTS `course` (
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `name` varchar(200) NOT NULL COMMENT '课程名称',
  `category` enum('学科辅导','兴趣培养','职业技能','语言学习','考级考证','其他') NOT NULL COMMENT '课程类别',
  `price` decimal(10,2) NOT NULL COMMENT '课程价格(元)',
  `teacher_id` varchar(50) NOT NULL COMMENT '老师ID',
  `total_hours` int NOT NULL DEFAULT 0 COMMENT '总课时(分钟)',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否上架',
  `create_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`course_id`),
  KEY `idx_teacher` (`teacher_id`),
  KEY `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程表';

-- ============================
-- 第二层: 核心业务表 (依赖基础表)
-- ============================

-- 3. 报名订单表
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `total_amount` decimal(10,2) NOT NULL COMMENT '实付金额',
  `study_goal` varchar(500) DEFAULT NULL COMMENT '学习目标',
  `expected_finish_days` int DEFAULT NULL COMMENT '预期完成天数',
  `status` enum('待支付','已支付','学习中','已完成','已取消','已退费') NOT NULL DEFAULT '待支付' COMMENT '订单状态',
  `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `payment_time` timestamp NULL DEFAULT NULL COMMENT '支付时间',
  `complete_time` timestamp NULL DEFAULT NULL COMMENT '完成时间',
  PRIMARY KEY (`order_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_course_id` (`course_id`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_status` (`status`),
  CONSTRAINT `order_info_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `order_info_ibfk_2` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='报名订单表';

-- 4. 学习进度表
CREATE TABLE IF NOT EXISTS `learning_progress` (
  `progress_id` varchar(50) NOT NULL COMMENT '进度ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `total_minutes` int NOT NULL DEFAULT 0 COMMENT '累计学习时长(分钟)',
  `last_active_at` timestamp NULL DEFAULT NULL COMMENT '最近学习时间',
  `completion_rate` decimal(5,4) NOT NULL DEFAULT 0.0000 COMMENT '完课率(0-1)',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`progress_id`),
  UNIQUE KEY `uk_user_course_order` (`user_id`,`course_id`,`order_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_course_id` (`course_id`),
  CONSTRAINT `learning_progress_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `learning_progress_ibfk_2` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`),
  CONSTRAINT `learning_progress_ibfk_3` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学习进度表';

-- 5. 退费申请表
CREATE TABLE IF NOT EXISTS `refund_request` (
  `refund_id` varchar(50) NOT NULL COMMENT '退费ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `reason` varchar(500) NOT NULL COMMENT '退费原因',
  `study_minutes_before_refund` int NOT NULL DEFAULT 0 COMMENT '退费前学习时长(分钟)',
  `refund_amount` decimal(10,2) NOT NULL COMMENT '退费金额',
  `status` enum('待审核','已通过','已拒绝') NOT NULL DEFAULT '待审核' COMMENT '退费状态',
  `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '申请时间',
  `resolve_time` timestamp NULL DEFAULT NULL COMMENT '处理时间',
  PRIMARY KEY (`refund_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_create_time` (`create_time`),
  CONSTRAINT `refund_request_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
  CONSTRAINT `refund_request_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='退费申请表';

-- 6. 设备指纹表
CREATE TABLE IF NOT EXISTS `device_fingerprint` (
  `device_id` varchar(50) NOT NULL COMMENT '设备ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `fingerprint` varchar(200) NOT NULL COMMENT '设备指纹',
  `ip` varchar(50) DEFAULT NULL COMMENT 'IP地址',
  `create_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次出现时间',
  `last_seen_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近出现时间',
  PRIMARY KEY (`device_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_fingerprint` (`fingerprint`),
  CONSTRAINT `device_fingerprint_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

SET FOREIGN_KEY_CHECKS = 1;

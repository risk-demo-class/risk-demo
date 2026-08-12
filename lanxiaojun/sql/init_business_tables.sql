-- ============================================
-- 教育风控系统 - 业务表 DDL 初始化脚本
-- 创建 10 张教育业务表 (按外键依赖顺序)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础用户表 (无外键依赖)
-- ============================

-- 1. 用户信息表 (教育版: 扩充 role/phone/real_name_status)
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(100) NOT NULL COMMENT '姓名',
  `role` enum('学生','老师','家长') NOT NULL COMMENT '角色',
  `phone` varchar(20) NOT NULL COMMENT '手机号',
  `real_name_status` int NOT NULL DEFAULT 0 COMMENT '实名认证 0=未认证 1=已认证',
  `account_age_days` int NOT NULL DEFAULT 0 COMMENT '账号年龄(天)',
  `register_at` datetime NOT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表(教育版)';

-- 2. 学籍档案表
CREATE TABLE IF NOT EXISTS `student_profile` (
  `profile_id` varchar(50) NOT NULL COMMENT '学籍档案ID',
  `user_id` varchar(50) NOT NULL COMMENT '关联用户ID',
  `student_id` varchar(50) NOT NULL COMMENT '学号',
  `school_name` varchar(200) DEFAULT NULL COMMENT '学校名称',
  `grade` varchar(50) DEFAULT NULL COMMENT '年级/班级',
  `id_card_hash` varchar(128) DEFAULT NULL COMMENT '身份证号(SHA-256)',
  `parent_phone` varchar(20) DEFAULT NULL COMMENT '家长手机号',
  PRIMARY KEY (`profile_id`),
  KEY `idx_sp_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学籍档案表';

-- 3. 教师信息表
CREATE TABLE IF NOT EXISTS `teacher_info` (
  `teacher_id` varchar(50) NOT NULL COMMENT '教师ID',
  `user_id` varchar(50) NOT NULL COMMENT '关联用户ID',
  `name` varchar(100) NOT NULL COMMENT '教师姓名',
  `cert_no` varchar(100) DEFAULT NULL COMMENT '资质证书编号',
  `teach_years` int DEFAULT 0 COMMENT '教龄(年)',
  `avg_rating` decimal(3,2) DEFAULT 0.00 COMMENT '平均评分',
  `course_count` int DEFAULT 0 COMMENT '开课数量',
  PRIMARY KEY (`teacher_id`),
  KEY `idx_ti_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教师信息表';

-- ============================
-- 第二层: 课程域
-- ============================

-- 4. 课程信息表
CREATE TABLE IF NOT EXISTS `course` (
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `name` varchar(200) NOT NULL COMMENT '课程名称',
  `category` varchar(50) NOT NULL COMMENT '课程类别(考研/公考/职业/语言/素质)',
  `price` decimal(10,2) NOT NULL COMMENT '课程价格',
  `total_hours` int DEFAULT NULL COMMENT '总课时',
  `teacher_id` varchar(50) DEFAULT NULL COMMENT '授课教师ID',
  `publish_date` datetime DEFAULT NULL COMMENT '上架时间',
  `status` enum('上架','下架') DEFAULT '上架' COMMENT '课程状态',
  PRIMARY KEY (`course_id`),
  KEY `idx_course_teacher` (`teacher_id`),
  KEY `idx_course_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程信息表';

-- ============================
-- 第三层: 订单/报名表
-- ============================

-- 5. 订单/报名表 (教育版: 关联 course_id, 去电商字段)
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `amount` decimal(10,2) NOT NULL COMMENT '订单金额',
  `pay_time` datetime DEFAULT NULL COMMENT '支付时间',
  `study_goal` varchar(200) DEFAULT NULL COMMENT '学习目标',
  `expected_finish_days` int DEFAULT NULL COMMENT '预计完成天数',
  `order_status` enum('待支付','已支付','已退款','已关闭') NOT NULL COMMENT '订单状态',
  PRIMARY KEY (`order_id`),
  KEY `idx_oi_user_id` (`user_id`),
  KEY `idx_oi_course_id` (`course_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单/报名表(教育版)';

-- ============================
-- 第四层: 学习行为表
-- ============================

-- 6. 学习进度表
CREATE TABLE IF NOT EXISTS `learning_progress` (
  `progress_id` varchar(50) NOT NULL COMMENT '进度ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `total_minutes` int DEFAULT 0 COMMENT '累计学习时长(分钟)',
  `completion_rate` decimal(5,2) DEFAULT 0.00 COMMENT '完成率(%)',
  `last_active_at` datetime DEFAULT NULL COMMENT '最后活跃时间',
  `chapter_progress` text COMMENT '章节进度(JSON)',
  PRIMARY KEY (`progress_id`),
  KEY `idx_lp_user_id` (`user_id`),
  KEY `idx_lp_course_id` (`course_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学习进度表';

-- ============================
-- 第五层: 退费 + 投诉
-- ============================

-- 7. 退费申请表 (替代电商售后)
CREATE TABLE IF NOT EXISTS `refund_request` (
  `refund_id` varchar(50) NOT NULL COMMENT '退费申请ID',
  `order_id` varchar(50) NOT NULL COMMENT '关联订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `reason` varchar(500) DEFAULT NULL COMMENT '退费原因',
  `study_minutes_before_refund` int DEFAULT 0 COMMENT '退费前已学时长(分钟)',
  `refund_amount` decimal(10,2) DEFAULT NULL COMMENT '退费金额',
  `status` enum('待审核','已通过','已拒绝') NOT NULL COMMENT '退费状态',
  `apply_time` datetime DEFAULT NULL COMMENT '申请时间',
  PRIMARY KEY (`refund_id`),
  KEY `idx_rr_order_id` (`order_id`),
  KEY `idx_rr_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='退费申请表';

-- 8. 投诉举报表
CREATE TABLE IF NOT EXISTS `complaint` (
  `complaint_id` varchar(50) NOT NULL COMMENT '投诉ID',
  `user_id` varchar(50) NOT NULL COMMENT '投诉人',
  `course_id` varchar(50) DEFAULT NULL COMMENT '被投诉课程',
  `complaint_type` varchar(50) NOT NULL COMMENT '投诉类型',
  `content` text COMMENT '投诉内容',
  `status` enum('待处理','已处理','已驳回') NOT NULL COMMENT '处理状态',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`complaint_id`),
  KEY `idx_c_user_id` (`user_id`),
  KEY `idx_c_course_id` (`course_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投诉举报表';

-- ============================
-- 第六层: 支付 & 设备
-- ============================

-- 9. 支付账户表
CREATE TABLE IF NOT EXISTS `payment_account` (
  `account_id` varchar(50) NOT NULL COMMENT '账户ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `payment_type` enum('微信','支付宝','银行卡') NOT NULL COMMENT '支付方式',
  `account_hash` varchar(128) DEFAULT NULL COMMENT '账户标识(SHA-256)',
  `bind_time` datetime DEFAULT NULL COMMENT '绑定时间',
  `is_verified` int DEFAULT 0 COMMENT '是否验证',
  PRIMARY KEY (`account_id`),
  KEY `idx_pa_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='支付账户表';

-- 10. 设备指纹表
CREATE TABLE IF NOT EXISTS `device_fingerprint` (
  `device_id` varchar(128) NOT NULL COMMENT '设备ID',
  `user_id` varchar(50) NOT NULL COMMENT '最近关联用户',
  `fingerprint_hash` varchar(256) DEFAULT NULL COMMENT '指纹SHA-256',
  `first_seen` datetime DEFAULT NULL COMMENT '首次出现',
  `last_seen` datetime DEFAULT NULL COMMENT '最后出现',
  `os` varchar(50) DEFAULT NULL COMMENT '操作系统',
  `browser` varchar(50) DEFAULT NULL COMMENT '浏览器',
  `ip` varchar(50) DEFAULT NULL COMMENT '最近IP',
  PRIMARY KEY (`device_id`),
  KEY `idx_df_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指纹表';

SET FOREIGN_KEY_CHECKS = 1;
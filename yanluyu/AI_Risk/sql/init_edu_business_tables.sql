-- ============================================
-- 教育风控系统 - 业务表 DDL 初始化脚本
-- 7 张业务表 (6 张核心 + 1 张辅助 DonationRecord)
-- ============================================

SET FOREIGN_KEY_CHECKS = 0;

-- 1. 用户信息表
DROP TABLE IF EXISTS `user_info`;
CREATE TABLE `user_info` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `name` VARCHAR(100) NOT NULL COMMENT '姓名',
    `role` ENUM('学生','老师','管理员') NOT NULL COMMENT '角色',
    `student_id` VARCHAR(50) DEFAULT NULL COMMENT '学号(学生必填)',
    `id_number` VARCHAR(20) DEFAULT NULL COMMENT '身份证号',
    `real_name_status` ENUM('未认证','已认证','认证失败') NOT NULL DEFAULT '未认证' COMMENT '实名认证状态',
    `register_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    PRIMARY KEY (`user_id`),
    INDEX `idx_user_student_id` (`student_id`),
    INDEX `idx_user_id_number` (`id_number`),
    INDEX `idx_user_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 课程信息表
DROP TABLE IF EXISTS `course`;
CREATE TABLE `course` (
    `course_id` VARCHAR(50) NOT NULL COMMENT '课程ID',
    `name` VARCHAR(200) NOT NULL COMMENT '课程名称',
    `category` ENUM('学科辅导','兴趣特长','职业技能','语言学习','考试考证','其他') NOT NULL COMMENT '课程分类',
    `price` DECIMAL(10,2) NOT NULL COMMENT '课程价格(元)',
    `teacher_id` VARCHAR(50) NOT NULL COMMENT '授课老师ID',
    `total_hours` DECIMAL(6,1) NOT NULL COMMENT '总课时(小时)',
    `target_audience` ENUM('学生','通用') NOT NULL DEFAULT '通用' COMMENT '面向对象',
    `is_live` TINYINT(1) DEFAULT 0 COMMENT '是否直播课(0=录播,1=直播)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`course_id`),
    INDEX `idx_course_teacher` (`teacher_id`),
    INDEX `idx_course_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程信息表';

-- 3. 订单/报名信息表
DROP TABLE IF EXISTS `order_info`;
CREATE TABLE `order_info` (
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `course_id` VARCHAR(50) NOT NULL COMMENT '课程ID',
    `total_amount` DECIMAL(10,2) NOT NULL COMMENT '订单金额',
    `device_fingerprint` VARCHAR(100) DEFAULT NULL COMMENT '设备指纹(设备唯一标识)',
    `study_goal` VARCHAR(200) DEFAULT NULL COMMENT '学习目标',
    `expected_finish_days` INT DEFAULT NULL COMMENT '预计完成天数',
    `order_status` ENUM('待支付','已支付','学习中','已完成','已取消') NOT NULL DEFAULT '待支付' COMMENT '订单状态',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '报名时间',
    `payment_time` DATETIME DEFAULT NULL COMMENT '支付时间',
    PRIMARY KEY (`order_id`),
    INDEX `idx_order_user` (`user_id`),
    INDEX `idx_order_course` (`course_id`),
    INDEX `idx_order_device` (`device_fingerprint`),
    INDEX `idx_order_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单/报名信息表';

-- 4. 学习进度表
DROP TABLE IF EXISTS `learning_progress`;
CREATE TABLE `learning_progress` (
    `progress_id` VARCHAR(50) NOT NULL COMMENT '进度ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `course_id` VARCHAR(50) NOT NULL COMMENT '课程ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '关联订单ID',
    `total_minutes` INT DEFAULT 0 COMMENT '累计学习时长(分钟)',
    `last_active_at` DATETIME DEFAULT NULL COMMENT '最近活跃时间',
    `completion_rate` DECIMAL(5,2) DEFAULT 0.00 COMMENT '完成率(0-100)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`progress_id`),
    INDEX `idx_progress_user` (`user_id`),
    INDEX `idx_progress_course` (`course_id`),
    INDEX `idx_progress_order` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学习进度表';

-- 5. 退费申请表
DROP TABLE IF EXISTS `refund_request`;
CREATE TABLE `refund_request` (
    `refund_id` VARCHAR(50) NOT NULL COMMENT '退费ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '关联订单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `reason` VARCHAR(500) NOT NULL COMMENT '退费原因',
    `study_minutes_before_refund` INT DEFAULT 0 COMMENT '退费前已学习时长(分钟)',
    `refund_amount` DECIMAL(10,2) NOT NULL COMMENT '退费金额',
    `refund_status` ENUM('待审核','已同意','已拒绝') NOT NULL DEFAULT '待审核' COMMENT '退费状态',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '申请时间',
    PRIMARY KEY (`refund_id`),
    INDEX `idx_refund_order` (`order_id`),
    INDEX `idx_refund_user` (`user_id`),
    INDEX `idx_refund_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='退费申请表';

-- 6. 黑名单扩展表 (教育专属黑名单信息)
DROP TABLE IF EXISTS `blacklist_extra`;
CREATE TABLE `blacklist_extra` (
    `entry_id` VARCHAR(50) NOT NULL COMMENT '记录ID',
    `type` ENUM('学号','身份证号','手机号','设备指纹') NOT NULL COMMENT '黑名单类型',
    `value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` VARCHAR(500) NOT NULL COMMENT '加入原因',
    `expire_at` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`entry_id`),
    UNIQUE INDEX `idx_blacklist_extra_type_value` (`type`, `value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育黑名单扩展表';

-- 7. 打赏记录表 (辅助表, 支持 R018 直播打赏异常)
DROP TABLE IF EXISTS `donation_record`;
CREATE TABLE `donation_record` (
    `donation_id` VARCHAR(50) NOT NULL COMMENT '打赏ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '打赏用户ID',
    `course_id` VARCHAR(50) NOT NULL COMMENT '关联直播课程ID',
    `amount` DECIMAL(10,2) NOT NULL COMMENT '打赏金额(元)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '打赏时间',
    PRIMARY KEY (`donation_id`),
    INDEX `idx_donation_user` (`user_id`),
    INDEX `idx_donation_course` (`course_id`),
    INDEX `idx_donation_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='打赏记录表';

SET FOREIGN_KEY_CHECKS = 1;

-- 教育行业风控：七张业务表
-- 由 scripts/init_db.py 在已选中的目标数据库中执行，因此此处不写死 USE 数据库名。

CREATE TABLE IF NOT EXISTS `user_info` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `name` VARCHAR(50) NOT NULL COMMENT '展示名称',
    `role` ENUM('学员','家长','教师') NOT NULL COMMENT '用户角色',
    `student_id_hash` CHAR(64) DEFAULT NULL COMMENT '学号SHA-256哈希',
    `id_number_hash` CHAR(64) DEFAULT NULL COMMENT '身份证号SHA-256哈希',
    `real_name_status` ENUM('未认证','认证中','已认证','认证失败') NOT NULL DEFAULT '未认证' COMMENT '实名认证状态',
    `register_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    `account_status` ENUM('正常','冻结','注销') NOT NULL DEFAULT '正常' COMMENT '账户状态',
    PRIMARY KEY (`user_id`),
    KEY `idx_user_student_hash` (`student_id_hash`),
    KEY `idx_user_id_number_hash` (`id_number_hash`),
    KEY `idx_user_register_at` (`register_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育用户表';

CREATE TABLE IF NOT EXISTS `course` (
    `course_id` VARCHAR(50) NOT NULL COMMENT '课程ID',
    `course_name` VARCHAR(100) NOT NULL COMMENT '课程名称',
    `category` VARCHAR(50) NOT NULL COMMENT '课程分类',
    `price` DECIMAL(10,2) NOT NULL COMMENT '课程原价',
    `teacher_id` VARCHAR(50) NOT NULL COMMENT '授课教师ID',
    `total_hours` DECIMAL(8,2) NOT NULL COMMENT '课程总课时',
    `course_status` ENUM('草稿','上架','下架') NOT NULL DEFAULT '上架' COMMENT '课程状态',
    PRIMARY KEY (`course_id`),
    KEY `idx_course_category_status` (`category`, `course_status`),
    KEY `idx_course_teacher_id` (`teacher_id`),
    CONSTRAINT `fk_course_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程主数据';

CREATE TABLE IF NOT EXISTS `order_info` (
    `order_id` VARCHAR(50) NOT NULL COMMENT '报名订单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '报名用户ID',
    `course_id` VARCHAR(50) NOT NULL COMMENT '课程ID',
    `total_amount` DECIMAL(10,2) NOT NULL COMMENT '订单原金额',
    `discount_amount` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '优惠金额',
    `final_amount` DECIMAL(10,2) NOT NULL COMMENT '实付金额',
    `order_status` ENUM('待支付','已支付','已取消','已退费') NOT NULL DEFAULT '待支付' COMMENT '报名订单状态',
    `channel` ENUM('网页','移动端','线下录入') NOT NULL DEFAULT '网页' COMMENT '报名渠道',
    `device_id_hash` CHAR(64) DEFAULT NULL COMMENT '下单设备指纹哈希',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `payment_time` DATETIME DEFAULT NULL COMMENT '支付时间',
    PRIMARY KEY (`order_id`),
    KEY `idx_order_user_time` (`user_id`, `create_time`),
    KEY `idx_order_course_id` (`course_id`),
    KEY `idx_order_device_hash` (`device_id_hash`),
    KEY `idx_order_status_time` (`order_status`, `create_time`),
    CONSTRAINT `fk_order_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
    CONSTRAINT `fk_order_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程报名订单';

CREATE TABLE IF NOT EXISTS `learning_progress` (
    `progress_id` VARCHAR(50) NOT NULL COMMENT '学习进度ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '学员ID',
    `course_id` VARCHAR(50) NOT NULL COMMENT '课程ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '报名订单ID',
    `total_minutes` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '累计学习分钟',
    `completion_rate` DECIMAL(5,4) NOT NULL DEFAULT 0.0000 COMMENT '完成率[0,1]',
    `last_active_at` DATETIME DEFAULT NULL COMMENT '最后学习时间',
    PRIMARY KEY (`progress_id`),
    UNIQUE KEY `uk_progress_user_course_order` (`user_id`, `course_id`, `order_id`),
    KEY `idx_progress_order_id` (`order_id`),
    KEY `idx_progress_user_active` (`user_id`, `last_active_at`),
    CONSTRAINT `fk_progress_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
    CONSTRAINT `fk_progress_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`),
    CONSTRAINT `fk_progress_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程学习进度';

CREATE TABLE IF NOT EXISTS `refund_request` (
    `refund_id` VARCHAR(50) NOT NULL COMMENT '退费申请ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '报名订单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '申请用户ID',
    `refund_amount` DECIMAL(10,2) NOT NULL COMMENT '申请退费金额',
    `reason` VARCHAR(500) NOT NULL COMMENT '退费原因',
    `refund_status` ENUM('待审核','已通过','已拒绝','已撤销') NOT NULL DEFAULT '待审核' COMMENT '退费状态',
    `apply_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '申请时间',
    `processed_time` DATETIME DEFAULT NULL COMMENT '处理时间',
    PRIMARY KEY (`refund_id`),
    KEY `idx_refund_user_time` (`user_id`, `apply_time`),
    KEY `idx_refund_order_id` (`order_id`),
    KEY `idx_refund_status_time` (`refund_status`, `apply_time`),
    CONSTRAINT `fk_refund_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
    CONSTRAINT `fk_refund_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程退费申请';

CREATE TABLE IF NOT EXISTS `identity_verification` (
    `verify_id` VARCHAR(50) NOT NULL COMMENT '认证记录ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `verify_type` ENUM('实名认证','学籍验证','学历认证') NOT NULL COMMENT '认证类型',
    `document_hash` CHAR(64) NOT NULL COMMENT '证件或材料哈希',
    `verify_result` ENUM('待审核','通过','失败') NOT NULL DEFAULT '待审核' COMMENT '认证结果',
    `fail_reason` VARCHAR(500) DEFAULT NULL COMMENT '失败原因',
    `submit_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '提交时间',
    `review_time` DATETIME DEFAULT NULL COMMENT '审核时间',
    PRIMARY KEY (`verify_id`),
    KEY `idx_verify_user_time` (`user_id`, `submit_time`),
    KEY `idx_verify_document_hash` (`document_hash`),
    KEY `idx_verify_result_time` (`verify_result`, `submit_time`),
    CONSTRAINT `fk_verify_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='身份与学历认证记录';

CREATE TABLE IF NOT EXISTS `device_binding` (
    `binding_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '绑定记录ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `device_id_hash` CHAR(64) NOT NULL COMMENT '设备指纹哈希',
    `ip_hash` CHAR(64) DEFAULT NULL COMMENT 'IP地址哈希',
    `first_seen` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次出现时间',
    `last_seen` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最近出现时间',
    `is_current` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否为当前有效设备',
    PRIMARY KEY (`binding_id`),
    UNIQUE KEY `uk_device_user_hash` (`user_id`, `device_id_hash`),
    KEY `idx_device_hash_current` (`device_id_hash`, `is_current`),
    KEY `idx_device_user_last_seen` (`user_id`, `last_seen`),
    KEY `idx_device_ip_hash` (`ip_hash`),
    CONSTRAINT `fk_device_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户设备绑定';

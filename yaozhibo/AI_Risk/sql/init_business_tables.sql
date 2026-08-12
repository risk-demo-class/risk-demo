-- 在线教育风控系统：6 张业务表
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `user_info` (
    `user_id` VARCHAR(50) NOT NULL,
    `name` VARCHAR(50) NOT NULL,
    `role` ENUM('student','parent','teacher') NOT NULL DEFAULT 'student',
    `student_id` VARCHAR(50) DEFAULT NULL,
    `id_card_hash` VARCHAR(64) DEFAULT NULL,
    `real_name_status` ENUM('UNVERIFIED','VERIFIED','REJECTED') NOT NULL DEFAULT 'UNVERIFIED',
    `register_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `device_id` VARCHAR(100) DEFAULT NULL,
    PRIMARY KEY (`user_id`),
    UNIQUE KEY `uq_user_student_id` (`student_id`),
    UNIQUE KEY `uq_user_id_card_hash` (`id_card_hash`),
    KEY `idx_user_role` (`role`),
    KEY `idx_user_device_id` (`device_id`),
    KEY `idx_user_register_at` (`register_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育平台用户';

CREATE TABLE IF NOT EXISTS `course` (
    `course_id` VARCHAR(50) NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `category` VARCHAR(50) NOT NULL,
    `price` DECIMAL(12,2) NOT NULL,
    `teacher_id` VARCHAR(50) NOT NULL,
    `total_hours` INT NOT NULL,
    `audience_role` ENUM('student','all') NOT NULL DEFAULT 'student',
    `status` ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT 'ACTIVE',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`course_id`),
    KEY `idx_course_category` (`category`),
    KEY `idx_course_teacher` (`teacher_id`),
    CONSTRAINT `fk_course_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `user_info` (`user_id`),
    CONSTRAINT `ck_course_price` CHECK (`price` >= 0),
    CONSTRAINT `ck_course_total_hours` CHECK (`total_hours` > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程主档';

CREATE TABLE IF NOT EXISTS `order_info` (
    `order_id` VARCHAR(50) NOT NULL,
    `user_id` VARCHAR(50) NOT NULL,
    `course_id` VARCHAR(50) NOT NULL,
    `order_type` ENUM('ENROLLMENT','PURCHASE') NOT NULL DEFAULT 'PURCHASE',
    `total_amount` DECIMAL(12,2) NOT NULL,
    `payment_status` ENUM('PENDING','PAID','CANCELLED','REFUNDED') NOT NULL DEFAULT 'PAID',
    `study_goal` VARCHAR(200) DEFAULT NULL,
    `expected_finish_days` INT DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`order_id`),
    KEY `idx_order_user_time` (`user_id`,`created_at`),
    KEY `idx_order_course_time` (`course_id`,`created_at`),
    CONSTRAINT `fk_order_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
    CONSTRAINT `fk_order_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`),
    CONSTRAINT `ck_order_total_amount` CHECK (`total_amount` >= 0),
    CONSTRAINT `ck_order_expected_finish_days` CHECK (`expected_finish_days` IS NULL OR `expected_finish_days` > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程报名与购买订单';

CREATE TABLE IF NOT EXISTS `learning_progress` (
    `progress_id` VARCHAR(50) NOT NULL,
    `user_id` VARCHAR(50) NOT NULL,
    `course_id` VARCHAR(50) NOT NULL,
    `order_id` VARCHAR(50) NOT NULL,
    `total_minutes` INT NOT NULL DEFAULT 0,
    `completion_rate` DECIMAL(5,4) NOT NULL DEFAULT 0,
    `last_active_at` DATETIME DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`progress_id`),
    UNIQUE KEY `uq_progress_user_course` (`user_id`,`course_id`),
    KEY `idx_progress_user_active` (`user_id`,`last_active_at`),
    KEY `idx_progress_order` (`order_id`),
    CONSTRAINT `fk_progress_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
    CONSTRAINT `fk_progress_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`),
    CONSTRAINT `fk_progress_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
    CONSTRAINT `ck_progress_minutes` CHECK (`total_minutes` >= 0),
    CONSTRAINT `ck_progress_rate` CHECK (`completion_rate` >= 0 AND `completion_rate` <= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程学习进度';

CREATE TABLE IF NOT EXISTS `refund_request` (
    `refund_id` VARCHAR(50) NOT NULL,
    `order_id` VARCHAR(50) NOT NULL,
    `user_id` VARCHAR(50) NOT NULL,
    `reason` VARCHAR(200) NOT NULL,
    `study_minutes_before_refund` INT NOT NULL DEFAULT 0,
    `refund_amount` DECIMAL(12,2) NOT NULL,
    `status` ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`refund_id`),
    KEY `idx_refund_user_time` (`user_id`,`created_at`),
    KEY `idx_refund_order` (`order_id`),
    CONSTRAINT `fk_refund_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
    CONSTRAINT `fk_refund_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
    CONSTRAINT `ck_refund_study_minutes` CHECK (`study_minutes_before_refund` >= 0),
    CONSTRAINT `ck_refund_amount` CHECK (`refund_amount` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程退费申请';

CREATE TABLE IF NOT EXISTS `blacklist_extra` (
    `entry_id` BIGINT NOT NULL AUTO_INCREMENT,
    `type` ENUM('student_id','id_card','device_id','live_account') NOT NULL,
    `value` VARCHAR(128) NOT NULL,
    `reason` TEXT NOT NULL,
    `status` ENUM('ACTIVE','REMOVED') NOT NULL DEFAULT 'ACTIVE',
    `expire_at` DATETIME DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`entry_id`),
    UNIQUE KEY `uq_blacklist_extra_type_value` (`type`,`value`),
    KEY `idx_blacklist_extra_active` (`status`,`expire_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育业务扩展黑名单';

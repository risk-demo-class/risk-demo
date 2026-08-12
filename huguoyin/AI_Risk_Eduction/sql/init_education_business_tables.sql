-- ============================================
-- 教育行业风控系统 - 业务表 DDL 初始化脚本
-- 创建 15 张教育业务表
-- 设计目标: 方便按用户/课程/机构/设备/支付账户/时间窗计算风控特征
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础主体
-- ============================

CREATE TABLE IF NOT EXISTS `edu_institution` (
  `institution_id` varchar(50) NOT NULL COMMENT '机构ID',
  `institution_name` varchar(100) NOT NULL COMMENT '机构名称',
  `license_no` varchar(80) DEFAULT NULL COMMENT '办学许可证号',
  `license_status` varchar(20) NOT NULL COMMENT '许可状态: VALID/EXPIRED/MISSING',
  `whitelist_status` varchar(20) NOT NULL COMMENT '监管名单状态: WHITE/GRAY/BLACK',
  `supervision_account_no` varchar(80) DEFAULT NULL COMMENT '培训收费监管账户',
  `province` varchar(30) NOT NULL COMMENT '省',
  `city` varchar(30) NOT NULL COMMENT '市',
  `created_at` timestamp NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`institution_id`),
  KEY `idx_edu_inst_license` (`license_status`, `whitelist_status`),
  KEY `idx_edu_inst_account` (`supervision_account_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育机构表';

CREATE TABLE IF NOT EXISTS `edu_user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `role` varchar(20) NOT NULL COMMENT '角色: STUDENT/GUARDIAN/TEACHER',
  `student_id` varchar(50) DEFAULT NULL COMMENT '平台学员号',
  `name_hash` varchar(64) NOT NULL COMMENT '姓名哈希',
  `cert_no_hash` varchar(64) DEFAULT NULL COMMENT '证件号哈希',
  `age` int DEFAULT NULL COMMENT '年龄',
  `grade` varchar(20) DEFAULT NULL COMMENT '年级',
  `guardian_id` varchar(50) DEFAULT NULL COMMENT '监护人用户ID',
  `real_name_status` varchar(20) NOT NULL COMMENT '实名状态: VERIFIED/PENDING/FAILED',
  `guardian_consent_status` varchar(20) NOT NULL COMMENT '监护同意状态',
  `device_fingerprint` varchar(100) DEFAULT NULL COMMENT '注册设备指纹',
  `ip_region` varchar(60) DEFAULT NULL COMMENT '注册IP归属地',
  `register_at` timestamp NOT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`),
  KEY `idx_edu_user_role_age` (`role`, `age`),
  KEY `idx_edu_user_guardian` (`guardian_id`),
  KEY `idx_edu_user_device` (`device_fingerprint`),
  KEY `idx_edu_user_register` (`register_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教育用户表';

-- ============================
-- 第二层: 教师与课程
-- ============================

CREATE TABLE IF NOT EXISTS `edu_teacher` (
  `teacher_id` varchar(50) NOT NULL COMMENT '教师ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `institution_id` varchar(50) NOT NULL COMMENT '机构ID',
  `qualification_no_hash` varchar(64) DEFAULT NULL COMMENT '教师资格证哈希',
  `qualification_status` varchar(20) NOT NULL COMMENT '资质状态: VERIFIED/PENDING/FAILED',
  `subject_scope` varchar(80) NOT NULL COMMENT '可授课范围',
  `hired_at` timestamp NOT NULL COMMENT '入职时间',
  PRIMARY KEY (`teacher_id`),
  KEY `idx_edu_teacher_inst` (`institution_id`),
  KEY `idx_edu_teacher_qual` (`qualification_status`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `edu_teacher_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`),
  CONSTRAINT `edu_teacher_ibfk_2` FOREIGN KEY (`institution_id`) REFERENCES `edu_institution` (`institution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教师表';

CREATE TABLE IF NOT EXISTS `edu_course` (
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `institution_id` varchar(50) NOT NULL COMMENT '机构ID',
  `teacher_id` varchar(50) NOT NULL COMMENT '主讲教师ID',
  `course_name` varchar(120) NOT NULL COMMENT '课程名称',
  `subject_type` varchar(20) NOT NULL COMMENT '学科类型: SUBJECT/NON_SUBJECT',
  `training_type` varchar(30) NOT NULL COMMENT '培训类型: ONLINE/OFFLINE/HYBRID',
  `delivery_mode` varchar(30) NOT NULL COMMENT '交付方式: LIVE/RECORDED/CLASSROOM',
  `total_hours` int NOT NULL COMMENT '总课时',
  `price` decimal(10,2) NOT NULL COMMENT '课程价格',
  `published_status` varchar(20) NOT NULL COMMENT '发布状态',
  `content_risk_label` varchar(30) DEFAULT NULL COMMENT '内容风险标签',
  `created_at` timestamp NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`course_id`),
  KEY `idx_edu_course_inst` (`institution_id`, `published_status`),
  KEY `idx_edu_course_teacher` (`teacher_id`),
  KEY `idx_edu_course_type` (`subject_type`, `training_type`),
  KEY `idx_edu_course_price` (`price`),
  CONSTRAINT `edu_course_ibfk_1` FOREIGN KEY (`institution_id`) REFERENCES `edu_institution` (`institution_id`),
  CONSTRAINT `edu_course_ibfk_2` FOREIGN KEY (`teacher_id`) REFERENCES `edu_teacher` (`teacher_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程表';

-- ============================
-- 第三层: 报名、合同、支付
-- ============================

CREATE TABLE IF NOT EXISTS `edu_enrollment` (
  `enrollment_id` varchar(50) NOT NULL COMMENT '报名ID',
  `user_id` varchar(50) NOT NULL COMMENT '学员用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `institution_id` varchar(50) NOT NULL COMMENT '机构ID',
  `study_goal` varchar(100) DEFAULT NULL COMMENT '学习目标',
  `expected_finish_days` int DEFAULT NULL COMMENT '预计完成天数',
  `enrollment_status` varchar(20) NOT NULL COMMENT '报名状态',
  `prepaid_months` int NOT NULL COMMENT '预收费覆盖月份',
  `prepaid_hours` int NOT NULL COMMENT '预收费课时',
  `device_fingerprint` varchar(100) DEFAULT NULL COMMENT '报名设备指纹',
  `ip_region` varchar(60) DEFAULT NULL COMMENT '报名IP归属地',
  `enrolled_at` timestamp NOT NULL COMMENT '报名时间',
  PRIMARY KEY (`enrollment_id`),
  KEY `idx_edu_enroll_user_time` (`user_id`, `enrolled_at`),
  KEY `idx_edu_enroll_course_time` (`course_id`, `enrolled_at`),
  KEY `idx_edu_enroll_device_time` (`device_fingerprint`, `enrolled_at`),
  KEY `idx_edu_enroll_status` (`enrollment_status`),
  KEY `institution_id` (`institution_id`),
  CONSTRAINT `edu_enrollment_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`),
  CONSTRAINT `edu_enrollment_ibfk_2` FOREIGN KEY (`course_id`) REFERENCES `edu_course` (`course_id`),
  CONSTRAINT `edu_enrollment_ibfk_3` FOREIGN KEY (`institution_id`) REFERENCES `edu_institution` (`institution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='报名表';

CREATE TABLE IF NOT EXISTS `edu_contract` (
  `contract_id` varchar(50) NOT NULL COMMENT '合同ID',
  `enrollment_id` varchar(50) NOT NULL COMMENT '报名ID',
  `contract_version` varchar(30) NOT NULL COMMENT '合同版本',
  `standard_template_flag` tinyint(1) NOT NULL COMMENT '是否使用示范文本',
  `sign_channel` varchar(30) NOT NULL COMMENT '签署渠道',
  `contract_status` varchar(20) NOT NULL COMMENT '合同状态',
  `signed_at` timestamp NULL DEFAULT NULL COMMENT '签署时间',
  PRIMARY KEY (`contract_id`),
  KEY `idx_edu_contract_enroll` (`enrollment_id`),
  KEY `idx_edu_contract_signed` (`signed_at`),
  CONSTRAINT `edu_contract_ibfk_1` FOREIGN KEY (`enrollment_id`) REFERENCES `edu_enrollment` (`enrollment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='合同表';

CREATE TABLE IF NOT EXISTS `edu_payment` (
  `payment_id` varchar(50) NOT NULL COMMENT '支付ID',
  `enrollment_id` varchar(50) NOT NULL COMMENT '报名ID',
  `user_id` varchar(50) NOT NULL COMMENT '学员用户ID',
  `payer_id` varchar(50) DEFAULT NULL COMMENT '付款人用户ID',
  `pay_amount` decimal(10,2) NOT NULL COMMENT '支付金额',
  `pay_channel` varchar(30) NOT NULL COMMENT '支付渠道',
  `payment_account_type` varchar(30) NOT NULL COMMENT '账户类型: SUPERVISION/PRIVATE/THIRD_PARTY',
  `payment_account_hash` varchar(64) NOT NULL COMMENT '支付账号哈希',
  `supervision_account_flag` tinyint(1) NOT NULL COMMENT '是否进入监管账户',
  `loan_flag` tinyint(1) NOT NULL COMMENT '是否培训贷',
  `payment_status` varchar(20) NOT NULL COMMENT '支付状态',
  `paid_at` timestamp NULL DEFAULT NULL COMMENT '支付时间',
  PRIMARY KEY (`payment_id`),
  KEY `idx_edu_pay_user_time` (`user_id`, `paid_at`),
  KEY `idx_edu_pay_enroll` (`enrollment_id`),
  KEY `idx_edu_pay_account` (`payment_account_hash`),
  KEY `idx_edu_pay_compliance` (`supervision_account_flag`, `loan_flag`),
  KEY `idx_edu_pay_amount` (`pay_amount`),
  KEY `payer_id` (`payer_id`),
  CONSTRAINT `edu_payment_ibfk_1` FOREIGN KEY (`enrollment_id`) REFERENCES `edu_enrollment` (`enrollment_id`),
  CONSTRAINT `edu_payment_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`),
  CONSTRAINT `edu_payment_ibfk_3` FOREIGN KEY (`payer_id`) REFERENCES `edu_user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='支付表';

-- ============================
-- 第四层: 履约、退费、投诉、认证、互动
-- ============================

CREATE TABLE IF NOT EXISTS `edu_lesson` (
  `lesson_id` varchar(50) NOT NULL COMMENT '课节ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `teacher_id` varchar(50) NOT NULL COMMENT '教师ID',
  `lesson_title` varchar(120) NOT NULL COMMENT '课节标题',
  `scheduled_start_at` timestamp NOT NULL COMMENT '计划开始时间',
  `scheduled_end_at` timestamp NOT NULL COMMENT '计划结束时间',
  `delivery_mode` varchar(30) NOT NULL COMMENT '交付方式',
  PRIMARY KEY (`lesson_id`),
  KEY `idx_edu_lesson_course_time` (`course_id`, `scheduled_start_at`),
  KEY `idx_edu_lesson_teacher_time` (`teacher_id`, `scheduled_start_at`),
  CONSTRAINT `edu_lesson_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `edu_course` (`course_id`),
  CONSTRAINT `edu_lesson_ibfk_2` FOREIGN KEY (`teacher_id`) REFERENCES `edu_teacher` (`teacher_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课节表';

CREATE TABLE IF NOT EXISTS `edu_learning_progress` (
  `progress_id` varchar(50) NOT NULL COMMENT '学习进度ID',
  `enrollment_id` varchar(50) NOT NULL COMMENT '报名ID',
  `user_id` varchar(50) NOT NULL COMMENT '学员用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `lesson_id` varchar(50) DEFAULT NULL COMMENT '课节ID',
  `watch_minutes` int NOT NULL COMMENT '学习分钟数',
  `interaction_count` int NOT NULL COMMENT '互动次数',
  `completion_rate` decimal(5,4) NOT NULL COMMENT '完成率',
  `device_fingerprint` varchar(100) DEFAULT NULL COMMENT '学习设备指纹',
  `ip_region` varchar(60) DEFAULT NULL COMMENT '学习IP归属地',
  `last_active_at` timestamp NOT NULL COMMENT '最近学习时间',
  PRIMARY KEY (`progress_id`),
  KEY `idx_edu_progress_user_time` (`user_id`, `last_active_at`),
  KEY `idx_edu_progress_enroll` (`enrollment_id`),
  KEY `idx_edu_progress_device_time` (`device_fingerprint`, `last_active_at`),
  KEY `idx_edu_progress_course` (`course_id`),
  KEY `lesson_id` (`lesson_id`),
  CONSTRAINT `edu_learning_progress_ibfk_1` FOREIGN KEY (`enrollment_id`) REFERENCES `edu_enrollment` (`enrollment_id`),
  CONSTRAINT `edu_learning_progress_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`),
  CONSTRAINT `edu_learning_progress_ibfk_3` FOREIGN KEY (`course_id`) REFERENCES `edu_course` (`course_id`),
  CONSTRAINT `edu_learning_progress_ibfk_4` FOREIGN KEY (`lesson_id`) REFERENCES `edu_lesson` (`lesson_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学习进度表';

CREATE TABLE IF NOT EXISTS `edu_refund_request` (
  `refund_id` varchar(50) NOT NULL COMMENT '退款ID',
  `enrollment_id` varchar(50) NOT NULL COMMENT '报名ID',
  `payment_id` varchar(50) DEFAULT NULL COMMENT '支付ID',
  `user_id` varchar(50) NOT NULL COMMENT '学员用户ID',
  `refund_reason` varchar(200) NOT NULL COMMENT '退款原因',
  `study_minutes_before_refund` int NOT NULL COMMENT '退款前学习分钟数',
  `consumed_hours` decimal(8,2) NOT NULL COMMENT '已消课时',
  `refund_amount` decimal(10,2) NOT NULL COMMENT '退款金额',
  `refund_status` varchar(20) NOT NULL COMMENT '退款状态',
  `applied_at` timestamp NOT NULL COMMENT '申请时间',
  `reviewed_at` timestamp NULL DEFAULT NULL COMMENT '审核时间',
  PRIMARY KEY (`refund_id`),
  KEY `idx_edu_refund_user_time` (`user_id`, `applied_at`),
  KEY `idx_edu_refund_enroll` (`enrollment_id`),
  KEY `idx_edu_refund_status` (`refund_status`),
  KEY `idx_edu_refund_amount` (`refund_amount`),
  KEY `payment_id` (`payment_id`),
  CONSTRAINT `edu_refund_request_ibfk_1` FOREIGN KEY (`enrollment_id`) REFERENCES `edu_enrollment` (`enrollment_id`),
  CONSTRAINT `edu_refund_request_ibfk_2` FOREIGN KEY (`payment_id`) REFERENCES `edu_payment` (`payment_id`),
  CONSTRAINT `edu_refund_request_ibfk_3` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='退费申请表';

CREATE TABLE IF NOT EXISTS `edu_complaint` (
  `complaint_id` varchar(50) NOT NULL COMMENT '投诉ID',
  `user_id` varchar(50) NOT NULL COMMENT '投诉用户ID',
  `institution_id` varchar(50) NOT NULL COMMENT '机构ID',
  `enrollment_id` varchar(50) DEFAULT NULL COMMENT '报名ID',
  `complaint_type` varchar(30) NOT NULL COMMENT '投诉类型',
  `complaint_status` varchar(20) NOT NULL COMMENT '投诉状态',
  `content_summary` text COMMENT '投诉摘要',
  `created_at` timestamp NOT NULL COMMENT '投诉时间',
  `closed_at` timestamp NULL DEFAULT NULL COMMENT '关闭时间',
  PRIMARY KEY (`complaint_id`),
  KEY `idx_edu_complaint_user_time` (`user_id`, `created_at`),
  KEY `idx_edu_complaint_inst_time` (`institution_id`, `created_at`),
  KEY `idx_edu_complaint_type` (`complaint_type`, `complaint_status`),
  KEY `enrollment_id` (`enrollment_id`),
  CONSTRAINT `edu_complaint_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`),
  CONSTRAINT `edu_complaint_ibfk_2` FOREIGN KEY (`institution_id`) REFERENCES `edu_institution` (`institution_id`),
  CONSTRAINT `edu_complaint_ibfk_3` FOREIGN KEY (`enrollment_id`) REFERENCES `edu_enrollment` (`enrollment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投诉表';

CREATE TABLE IF NOT EXISTS `edu_certificate_verification` (
  `cert_id` varchar(50) NOT NULL COMMENT '认证ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `cert_type` varchar(30) NOT NULL COMMENT '证书类型',
  `cert_verify_source` varchar(50) NOT NULL COMMENT '核验来源',
  `material_hash` varchar(64) NOT NULL COMMENT '材料哈希',
  `verify_result` varchar(20) NOT NULL COMMENT '核验结果',
  `submitted_at` timestamp NOT NULL COMMENT '提交时间',
  `verified_at` timestamp NULL DEFAULT NULL COMMENT '核验时间',
  PRIMARY KEY (`cert_id`),
  KEY `idx_edu_cert_user_time` (`user_id`, `submitted_at`),
  KEY `idx_edu_cert_material` (`material_hash`),
  KEY `idx_edu_cert_result` (`verify_result`),
  CONSTRAINT `edu_certificate_verification_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='证书学历核验表';

CREATE TABLE IF NOT EXISTS `edu_live_reward` (
  `reward_id` varchar(50) NOT NULL COMMENT '打赏ID',
  `live_session_id` varchar(50) NOT NULL COMMENT '直播场次ID',
  `user_id` varchar(50) NOT NULL COMMENT '打赏用户ID',
  `course_id` varchar(50) NOT NULL COMMENT '课程ID',
  `teacher_id` varchar(50) NOT NULL COMMENT '教师ID',
  `reward_amount` decimal(10,2) NOT NULL COMMENT '打赏金额',
  `reward_status` varchar(20) NOT NULL COMMENT '打赏状态',
  `paid_at` timestamp NOT NULL COMMENT '支付时间',
  PRIMARY KEY (`reward_id`),
  KEY `idx_edu_reward_user_time` (`user_id`, `paid_at`),
  KEY `idx_edu_reward_session` (`live_session_id`),
  KEY `idx_edu_reward_amount` (`reward_amount`),
  KEY `course_id` (`course_id`),
  KEY `teacher_id` (`teacher_id`),
  CONSTRAINT `edu_live_reward_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`),
  CONSTRAINT `edu_live_reward_ibfk_2` FOREIGN KEY (`course_id`) REFERENCES `edu_course` (`course_id`),
  CONSTRAINT `edu_live_reward_ibfk_3` FOREIGN KEY (`teacher_id`) REFERENCES `edu_teacher` (`teacher_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='直播打赏表';

-- ============================
-- 第五层: 设备与资金账户画像
-- ============================

CREATE TABLE IF NOT EXISTS `edu_device_binding` (
  `binding_id` varchar(50) NOT NULL COMMENT '绑定ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `device_fingerprint` varchar(100) NOT NULL COMMENT '设备指纹',
  `device_type` varchar(30) NOT NULL COMMENT '设备类型',
  `ip_region` varchar(60) DEFAULT NULL COMMENT 'IP归属地',
  `bind_channel` varchar(30) NOT NULL COMMENT '绑定渠道',
  `first_seen_at` timestamp NOT NULL COMMENT '首次出现时间',
  `last_seen_at` timestamp NOT NULL COMMENT '最近出现时间',
  PRIMARY KEY (`binding_id`),
  KEY `idx_edu_device_fp` (`device_fingerprint`),
  KEY `idx_edu_device_user` (`user_id`),
  KEY `idx_edu_device_seen` (`last_seen_at`),
  CONSTRAINT `edu_device_binding_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `edu_user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备绑定表';

CREATE TABLE IF NOT EXISTS `edu_institution_account_change` (
  `change_id` varchar(50) NOT NULL COMMENT '变更ID',
  `institution_id` varchar(50) NOT NULL COMMENT '机构ID',
  `old_account_hash` varchar(64) DEFAULT NULL COMMENT '原收款账户哈希',
  `new_account_hash` varchar(64) NOT NULL COMMENT '新收款账户哈希',
  `account_type` varchar(30) NOT NULL COMMENT '账户类型',
  `change_reason` varchar(120) DEFAULT NULL COMMENT '变更原因',
  `changed_at` timestamp NOT NULL COMMENT '变更时间',
  PRIMARY KEY (`change_id`),
  KEY `idx_edu_account_inst_time` (`institution_id`, `changed_at`),
  KEY `idx_edu_account_hash` (`new_account_hash`),
  CONSTRAINT `edu_institution_account_change_ibfk_1` FOREIGN KEY (`institution_id`) REFERENCES `edu_institution` (`institution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机构账户变更表';

SET FOREIGN_KEY_CHECKS = 1;

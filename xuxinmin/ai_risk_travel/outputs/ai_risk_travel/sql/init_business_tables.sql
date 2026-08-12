-- ============================================
-- 旅游风控系统 - 行业业务表 DDL 初始化脚本
-- 7 张旅游业务表 (按外键依赖顺序)
-- 跟电商版 17 张业务表完全不同的行业设计
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 1. 用户信息表 (实名状态 / VIP 等级 / 账号年龄)
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) NOT NULL COMMENT '用户姓名',
  `phone` varchar(20) NOT NULL COMMENT '手机号',
  `id_card_hash` varchar(64) DEFAULT NULL COMMENT '身份证号哈希(脱敏)',
  `real_name_status` int DEFAULT 0 COMMENT '实名状态(0=未实名,1=已实名)',
  `vip_level` int DEFAULT 0 COMMENT 'VIP等级(0-5)',
  `account_age_days` int DEFAULT 0 COMMENT '账号注册天数',
  `register_at` datetime NOT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表(旅游)';

-- 2. 订单表 (机票/酒店/签证/跟团游)
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `order_type` enum('机票','酒店','签证','跟团游') NOT NULL COMMENT '订单类型',
  `total_amount` decimal(10,2) NOT NULL COMMENT '订单总金额',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `depart_date` datetime DEFAULT NULL COMMENT '出发日期',
  `return_date` datetime DEFAULT NULL COMMENT '返程日期',
  `passenger_count` int DEFAULT 1 COMMENT '乘客数',
  `order_status` varchar(20) NOT NULL COMMENT '订单状态(待支付/已支付/已出票/已退订/已取消)',
  `create_time` datetime NOT NULL COMMENT '下单时间',
  `payment_time` datetime DEFAULT NULL COMMENT '支付时间',
  PRIMARY KEY (`order_id`),
  INDEX `idx_order_user_create` (`user_id`,`create_time`),
  INDEX `idx_order_dest_country` (`dest_country`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单表(旅游)';

-- 3. 乘客信息表 (1 订单 N 乘客)
CREATE TABLE IF NOT EXISTS `passenger_info` (
  `passenger_id` varchar(50) NOT NULL COMMENT '乘客ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `name` varchar(50) NOT NULL COMMENT '乘客姓名',
  `id_type` enum('身份证','护照') NOT NULL COMMENT '证件类型',
  `id_number` varchar(64) NOT NULL COMMENT '证件号',
  `nationality` varchar(50) DEFAULT '中国' COMMENT '国籍',
  `age` int DEFAULT 30 COMMENT '年龄',
  PRIMARY KEY (`passenger_id`),
  INDEX `idx_passenger_order` (`order_id`),
  INDEX `idx_passenger_id_number` (`id_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='乘客信息表';

-- 4. 签证申请表 (全新表, 电商没有"签证"概念)
CREATE TABLE IF NOT EXISTS `visa_application` (
  `visa_id` varchar(50) NOT NULL COMMENT '签证申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `dest_country` varchar(50) NOT NULL COMMENT '申请国家',
  `visa_type` varchar(50) NOT NULL COMMENT '签证类型(旅游/商务/探亲)',
  `reject_history` int DEFAULT 0 COMMENT '该用户历史拒签次数',
  `visa_status` varchar(20) NOT NULL COMMENT '状态(审核中/通过/被拒)',
  `submit_time` datetime NOT NULL COMMENT '提交时间',
  PRIMARY KEY (`visa_id`),
  INDEX `idx_visa_user_submit` (`user_id`,`submit_time`),
  INDEX `idx_visa_dest_country` (`dest_country`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='签证申请表';

-- 5. 机票预订表
CREATE TABLE IF NOT EXISTS `booking_flight` (
  `booking_id` varchar(50) NOT NULL COMMENT '机票预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `flight_no` varchar(20) NOT NULL COMMENT '航班号',
  `depart_airport` varchar(50) NOT NULL COMMENT '出发机场',
  `arrive_airport` varchar(50) NOT NULL COMMENT '到达机场',
  `depart_time` datetime DEFAULT NULL COMMENT '起飞时间',
  `cabin_class` enum('经济舱','公务舱','头等舱') DEFAULT '经济舱' COMMENT '舱位等级',
  PRIMARY KEY (`booking_id`),
  INDEX `idx_flight_order` (`order_id`),
  INDEX `idx_flight_no_time` (`flight_no`,`depart_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机票预订表';

-- 6. 酒店预订表
CREATE TABLE IF NOT EXISTS `booking_hotel` (
  `booking_id` varchar(50) NOT NULL COMMENT '酒店预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `hotel_id` varchar(50) NOT NULL COMMENT '酒店ID',
  `check_in` datetime DEFAULT NULL COMMENT '入住时间',
  `check_out` datetime DEFAULT NULL COMMENT '离店时间',
  `room_count` int DEFAULT 1 COMMENT '房间数',
  `is_refundable` int DEFAULT 1 COMMENT '是否可退(0/1)',
  PRIMARY KEY (`booking_id`),
  INDEX `idx_hotel_order` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='酒店预订表';

-- 7. 行业黑名单扩展表
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '条目ID',
  `entry_type` varchar(30) NOT NULL COMMENT '类型(护照号/签证号/设备指纹/身份证号/IP)',
  `entry_value` varchar(200) NOT NULL COMMENT '值',
  `reason` varchar(500) DEFAULT NULL COMMENT '加入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  PRIMARY KEY (`entry_id`),
  INDEX `idx_blacklist_extra_type_value` (`entry_type`,`entry_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='行业黑名单扩展表';

SET FOREIGN_KEY_CHECKS = 1;

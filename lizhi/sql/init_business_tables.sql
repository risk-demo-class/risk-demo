-- ============================================
-- 旅游风控系统 - 业务表 DDL 初始化脚本
-- 创建 7 张旅游业务表 (场景 A: 机票/酒店/签证/跟团游)
-- 按外键依赖顺序创建: user_info -> order_info -> passenger_info / visa_application / booking_hotel / booking_flight
-- 索引设计面向风控特征计算 (user / order / 证件号 / 时间 高频查询)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 1. 用户信息表
-- ============================
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `real_name_status` tinyint(1) NOT NULL DEFAULT 0 COMMENT '实名状态(0=未实名,1=已实名, 旅游强制实名)',
  `vip_level` varchar(20) NOT NULL DEFAULT '普通' COMMENT '会员等级(普通/银卡/金卡/铂金/钻石)',
  `account_age_days` int NOT NULL DEFAULT 0 COMMENT '注册时长(天), 新用户大单特征直接取数',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
  PRIMARY KEY (`user_id`),
  KEY `idx_user_account_age` (`account_age_days`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游用户信息表';

-- ============================
-- 2. 订单主表 (机票/酒店/签证/跟团游)
-- ============================
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '下单用户ID',
  `order_type` varchar(20) NOT NULL COMMENT '订单类型(机票/酒店/签证/跟团游)',
  `total_amount` decimal(10,2) NOT NULL COMMENT '订单金额(元)',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `depart_date` date NOT NULL COMMENT '出发日期',
  `return_date` date DEFAULT NULL COMMENT '返回日期',
  `passenger_count` int NOT NULL DEFAULT 1 COMMENT '乘客数',
  `order_status` varchar(20) NOT NULL DEFAULT '待支付' COMMENT '订单状态(待支付/已支付/已出票/已出行/已完成/已取消/已退改)',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间(0点突击下单特征取数)',
  `payment_time` datetime DEFAULT NULL COMMENT '支付时间',
  PRIMARY KEY (`order_id`),
  KEY `idx_order_user_id` (`user_id`),
  KEY `idx_order_create_time` (`create_time`),
  KEY `idx_order_type` (`order_type`),
  KEY `idx_order_depart_date` (`depart_date`),
  KEY `idx_order_dest_country` (`dest_country`),
  CONSTRAINT `order_info_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单主表';

-- ============================
-- 3. 乘客信息表 (1 订单 N 乘客)
-- ============================
CREATE TABLE IF NOT EXISTS `passenger_info` (
  `passenger_id` varchar(50) NOT NULL COMMENT '乘客ID',
  `order_id` varchar(50) NOT NULL COMMENT '所属订单ID',
  `name` varchar(50) NOT NULL COMMENT '乘客姓名',
  `id_type` varchar(20) NOT NULL DEFAULT '身份证' COMMENT '证件类型(身份证/护照/港澳通行证/台湾通行证/其他)',
  `id_number` varchar(50) NOT NULL COMMENT '证件号(身份证号/护照号, 黑名单比对目标)',
  `nationality` varchar(50) NOT NULL DEFAULT '中国' COMMENT '国籍',
  `age` int NOT NULL COMMENT '年龄',
  PRIMARY KEY (`passenger_id`),
  KEY `idx_passenger_order_id` (`order_id`),
  KEY `idx_passenger_id_number` (`id_number`),
  CONSTRAINT `passenger_info_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游乘客信息表';

-- ============================
-- 4. 签证申请表 (全新表, 电商没有)
-- ============================
CREATE TABLE IF NOT EXISTS `visa_application` (
  `visa_id` varchar(50) NOT NULL COMMENT '签证申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '申请用户ID',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `visa_type` varchar(50) NOT NULL COMMENT '签证类型(旅游/商务/探亲/留学等)',
  `reject_history` int NOT NULL DEFAULT 0 COMMENT '历史拒签次数(拒签历史特征取数)',
  `submit_time` datetime NOT NULL COMMENT '提交时间(短期多国签证特征取数)',
  `status` varchar(20) NOT NULL DEFAULT '待审核' COMMENT '状态(待审核/通过/拒签)',
  PRIMARY KEY (`visa_id`),
  KEY `idx_visa_user_id` (`user_id`),
  KEY `idx_visa_dest_country` (`dest_country`),
  KEY `idx_visa_submit_time` (`submit_time`),
  CONSTRAINT `visa_application_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游签证申请表';

-- ============================
-- 5. 酒店预订明细表
-- ============================
CREATE TABLE IF NOT EXISTS `booking_hotel` (
  `booking_id` varchar(50) NOT NULL COMMENT '酒店预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '所属订单ID',
  `hotel_id` varchar(50) NOT NULL COMMENT '酒店ID',
  `check_in` date NOT NULL COMMENT '入住日期',
  `check_out` date NOT NULL COMMENT '离店日期',
  `room_count` int NOT NULL DEFAULT 1 COMMENT '房间数',
  `is_refundable` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否可免费取消(0=否,1=是)',
  PRIMARY KEY (`booking_id`),
  KEY `idx_hotel_order_id` (`order_id`),
  KEY `idx_hotel_check_in` (`check_in`),
  CONSTRAINT `booking_hotel_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游酒店预订明细表';

-- ============================
-- 6. 机票预订明细表
-- ============================
CREATE TABLE IF NOT EXISTS `booking_flight` (
  `booking_id` varchar(50) NOT NULL COMMENT '机票预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '所属订单ID',
  `flight_no` varchar(20) NOT NULL COMMENT '航班号',
  `depart_airport` varchar(50) NOT NULL COMMENT '出发机场',
  `arrive_airport` varchar(50) NOT NULL COMMENT '到达机场',
  `cabin_class` varchar(20) NOT NULL DEFAULT '经济舱' COMMENT '舱位等级(经济舱/公务舱/头等舱)',
  PRIMARY KEY (`booking_id`),
  KEY `idx_flight_order_id` (`order_id`),
  KEY `idx_flight_no` (`flight_no`),
  CONSTRAINT `booking_flight_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游机票预订明细表';

-- ============================
-- 7. 业务黑名单扩展表
-- ============================
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `type` varchar(20) NOT NULL COMMENT '黑名单类型(设备指纹/IP/护照号/签证号/身份证号)',
  `value` varchar(200) NOT NULL COMMENT '黑名单值',
  `reason` varchar(500) DEFAULT NULL COMMENT '加入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `uk_blacklist_extra_type_value` (`type`,`value`),
  KEY `idx_blacklist_extra_type` (`type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游业务黑名单扩展表';

SET FOREIGN_KEY_CHECKS = 1;

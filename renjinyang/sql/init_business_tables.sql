-- ============================================
-- 旅游风控系统 - 业务表 DDL 初始化脚本
-- 创建 7 张 OTA 旅游业务表
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) NOT NULL COMMENT '用户名称',
  `real_name_status` enum('未实名','已实名','已认证') NOT NULL COMMENT '实名状态',
  `vip_level` int NOT NULL COMMENT '会员等级',
  `account_age_days` int NOT NULL COMMENT '账户注册天数',
  `phone` varchar(20) NOT NULL COMMENT '手机号',
  `register_time` datetime NOT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='OTA用户信息表';

-- 2. 旅游订单表
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `order_type` enum('机票','酒店','签证','跟团游') NOT NULL COMMENT '订单类型',
  `total_amount` decimal(12,2) NOT NULL COMMENT '订单总金额',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家或地区',
  `depart_date` date NOT NULL COMMENT '出发或入住日期',
  `return_date` date NOT NULL COMMENT '返回或离店日期',
  `passenger_count` int NOT NULL COMMENT '乘客或入住人数',
  `book_time` datetime NOT NULL COMMENT '下单时间',
  PRIMARY KEY (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单表';

-- 3. 乘客信息表
CREATE TABLE IF NOT EXISTS `passenger_info` (
  `passenger_id` varchar(50) NOT NULL COMMENT '乘客ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `name` varchar(50) NOT NULL COMMENT '乘客姓名',
  `id_type` enum('身份证','护照','港澳通行证') NOT NULL COMMENT '证件类型',
  `id_number` varchar(100) NOT NULL COMMENT '脱敏证件号',
  `nationality` varchar(50) NOT NULL COMMENT '国籍',
  `age` int NOT NULL COMMENT '年龄',
  PRIMARY KEY (`passenger_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单乘客信息表';

-- 4. 签证申请表
CREATE TABLE IF NOT EXISTS `visa_application` (
  `visa_id` varchar(50) NOT NULL COMMENT '签证申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `dest_country` varchar(50) NOT NULL COMMENT '签证目的国',
  `visa_type` varchar(50) NOT NULL COMMENT '签证类型',
  `reject_history` int NOT NULL COMMENT '历史拒签次数',
  `submit_time` datetime NOT NULL COMMENT '提交时间',
  PRIMARY KEY (`visa_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='签证申请表';

-- 5. 酒店预订明细表
CREATE TABLE IF NOT EXISTS `booking_hotel` (
  `booking_id` varchar(50) NOT NULL COMMENT '酒店预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `hotel_id` varchar(50) NOT NULL COMMENT '酒店ID',
  `check_in` date NOT NULL COMMENT '入住日期',
  `check_out` date NOT NULL COMMENT '离店日期',
  `room_count` int NOT NULL COMMENT '房间数',
  `is_refundable` tinyint(1) NOT NULL COMMENT '是否可退',
  PRIMARY KEY (`booking_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='酒店预订明细表';

-- 6. 航班预订明细表
CREATE TABLE IF NOT EXISTS `booking_flight` (
  `booking_id` varchar(50) NOT NULL COMMENT '航班预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `flight_no` varchar(20) NOT NULL COMMENT '航班号',
  `depart_airport` varchar(50) NOT NULL COMMENT '出发机场',
  `arrive_airport` varchar(50) NOT NULL COMMENT '到达机场',
  `cabin_class` varchar(20) NOT NULL COMMENT '舱位等级',
  PRIMARY KEY (`booking_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='航班预订明细表';

-- 7. 业务黑名单扩展表
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` varchar(50) NOT NULL COMMENT '扩展黑名单条目ID',
  `type` enum('护照号','签证号','设备指纹','手机号') NOT NULL COMMENT '黑名单类型',
  `value` varchar(128) NOT NULL COMMENT '黑名单值',
  `reason` varchar(255) NOT NULL COMMENT '列入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间',
  PRIMARY KEY (`entry_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游业务黑名单扩展表';

SET FOREIGN_KEY_CHECKS = 1;

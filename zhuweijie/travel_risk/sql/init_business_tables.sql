-- ============================================
-- 旅游风控系统 - 业务表 DDL 初始化脚本
-- 创建 7 张 OTA 业务表 (按外键依赖顺序, 无物理外键, 用索引加速特征查询)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) DEFAULT NULL COMMENT '姓名/昵称',
  `real_name_status` ENUM('未实名','已实名') DEFAULT '未实名' COMMENT '实名状态(旅游必须)',
  `id_card_hash` varchar(64) DEFAULT NULL COMMENT '身份证号哈希(脱敏)',
  `vip_level` int DEFAULT 0 COMMENT '会员等级 0-5',
  `account_age_days` int DEFAULT 0 COMMENT '注册天数',
  `register_at` datetime DEFAULT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`),
  INDEX `idx_user_idcard_hash` (`id_card_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 旅游订单主表 (机票/酒店/跟团游)
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `order_type` ENUM('机票','酒店','跟团游') NOT NULL COMMENT '订单类型',
  `total_amount` decimal(10,2) NOT NULL COMMENT '订单总金额',
  `dest_country` varchar(50) DEFAULT NULL COMMENT '目的地国家',
  `depart_date` date DEFAULT NULL COMMENT '出发日期',
  `return_date` date DEFAULT NULL COMMENT '返程日期',
  `passenger_count` int DEFAULT 1 COMMENT '乘客数',
  `pay_status` ENUM('待支付','已支付','已取消') DEFAULT '待支付' COMMENT '支付状态',
  `create_time` datetime DEFAULT NULL COMMENT '下单时间',
  `payment_time` datetime DEFAULT NULL COMMENT '支付时间',
  PRIMARY KEY (`order_id`),
  INDEX `idx_order_user_id` (`user_id`),
  INDEX `idx_order_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单主表';

-- 3. 乘客表 (1 个订单 N 个乘客)
CREATE TABLE IF NOT EXISTS `passenger_info` (
  `passenger_id` varchar(50) NOT NULL COMMENT '乘客ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `name` varchar(50) NOT NULL COMMENT '乘客姓名',
  `id_type` ENUM('身份证','护照','其他') DEFAULT '身份证' COMMENT '证件类型',
  `id_number` varchar(50) NOT NULL COMMENT '证件号',
  `nationality` varchar(50) DEFAULT NULL COMMENT '国籍',
  `age` int DEFAULT NULL COMMENT '年龄',
  PRIMARY KEY (`passenger_id`),
  INDEX `idx_passenger_order_id` (`order_id`),
  INDEX `idx_passenger_id_number` (`id_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='乘客表';

-- 4. 签证申请表
CREATE TABLE IF NOT EXISTS `visa_application` (
  `visa_id` varchar(50) NOT NULL COMMENT '签证申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `visa_type` varchar(30) DEFAULT '旅游签证' COMMENT '签证类型',
  `reject_history` int DEFAULT 0 COMMENT '历史拒签次数',
  `submit_time` datetime DEFAULT NULL COMMENT '提交时间',
  PRIMARY KEY (`visa_id`),
  INDEX `idx_visa_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='签证申请表';

-- 5. 机票预订明细表
CREATE TABLE IF NOT EXISTS `booking_flight` (
  `booking_id` varchar(50) NOT NULL COMMENT '机票预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `flight_no` varchar(20) NOT NULL COMMENT '航班号',
  `depart_airport` varchar(20) DEFAULT NULL COMMENT '出发机场',
  `arrive_airport` varchar(20) DEFAULT NULL COMMENT '到达机场',
  `cabin_class` ENUM('经济舱','公务舱','头等舱') DEFAULT '经济舱' COMMENT '舱位',
  `depart_time` datetime DEFAULT NULL COMMENT '起飞时间',
  PRIMARY KEY (`booking_id`),
  INDEX `idx_flight_order_id` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机票预订明细表';

-- 6. 酒店预订明细表
CREATE TABLE IF NOT EXISTS `booking_hotel` (
  `booking_id` varchar(50) NOT NULL COMMENT '酒店预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `hotel_id` varchar(50) DEFAULT NULL COMMENT '酒店ID',
  `check_in` date DEFAULT NULL COMMENT '入住日期',
  `check_out` date DEFAULT NULL COMMENT '离店日期',
  `room_count` int DEFAULT 1 COMMENT '房间数',
  `is_refundable` int DEFAULT 1 COMMENT '是否可免费取消 1/0',
  PRIMARY KEY (`booking_id`),
  INDEX `idx_hotel_order_id` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='酒店预订明细表';

-- 7. 扩展黑名单表 (旅游行业)
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '条目ID',
  `type` ENUM('护照号','证件号','设备指纹','支付账号') NOT NULL COMMENT '黑名单类型',
  `value` varchar(200) NOT NULL COMMENT '黑名单值',
  `reason` text COMMENT '原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`entry_id`),
  INDEX `idx_blacklist_extra_type_value` (`type`,`value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='扩展黑名单表';
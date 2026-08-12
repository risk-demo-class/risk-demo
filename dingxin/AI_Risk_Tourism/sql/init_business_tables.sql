-- ============================================
-- 旅游风控系统 - 业务表 DDL 初始化脚本
-- 创建 8 张旅游业务表 (任务书场景 A 必须 7 张 + 退改单 1 张)
-- 独立数据库 tourism, 与电商基线 ecs 完全隔离
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 1. 用户信息表 (实名状态 / VIP / 账号年龄)
-- ============================
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `real_name_status` int NOT NULL DEFAULT 0 COMMENT '实名状态 0=未实名 1=已实名',
  `vip_level` int NOT NULL DEFAULT 0 COMMENT 'VIP等级 0-4',
  `account_age_days` int NOT NULL DEFAULT 0 COMMENT '账号年龄(天)',
  `register_time` datetime NOT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`),
  KEY `idx_real_name_status` (`real_name_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游用户信息表';

-- ============================
-- 2. 订单表 (目的地/出行日期/乘客数)
-- ============================
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `order_type` enum('机票','酒店','签证','跟团游') NOT NULL COMMENT '订单类型',
  `total_amount` decimal(10,2) NOT NULL COMMENT '订单金额',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `depart_date` datetime NOT NULL COMMENT '出发日期',
  `return_date` datetime NOT NULL COMMENT '返程日期',
  `passenger_count` int NOT NULL DEFAULT 1 COMMENT '乘客数',
  `create_time` datetime NOT NULL COMMENT '下单时间',
  `order_status` enum('已支付','已完成','已取消','已退改') NOT NULL DEFAULT '已支付' COMMENT '订单状态',
  PRIMARY KEY (`order_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_dest_country` (`dest_country`),
  KEY `idx_create_time` (`create_time`),
  CONSTRAINT `order_info_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单表';

-- ============================
-- 3. 乘客信息表 (1 订单 N 乘客)
-- ============================
CREATE TABLE IF NOT EXISTS `passenger_info` (
  `passenger_id` varchar(50) NOT NULL COMMENT '乘客ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `id_type` enum('身份证','护照','港澳通行证','台胞证') NOT NULL DEFAULT '身份证' COMMENT '证件类型',
  `id_number` varchar(50) NOT NULL COMMENT '证件号',
  `nationality` varchar(50) NOT NULL COMMENT '国籍',
  `age` int NOT NULL DEFAULT 0 COMMENT '年龄',
  PRIMARY KEY (`passenger_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_id_number` (`id_number`),
  CONSTRAINT `passenger_info_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='乘客信息表';

-- ============================
-- 4. 签证申请表 (拒签历史)
-- ============================
CREATE TABLE IF NOT EXISTS `visa_application` (
  `visa_id` varchar(50) NOT NULL COMMENT '签证申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `visa_type` enum('旅游签证','商务签证','留学签证','探亲签证') NOT NULL DEFAULT '旅游签证' COMMENT '签证类型',
  `reject_history` int NOT NULL DEFAULT 0 COMMENT '历史拒签次数',
  `submit_time` datetime NOT NULL COMMENT '提交时间',
  PRIMARY KEY (`visa_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_dest_country` (`dest_country`),
  CONSTRAINT `visa_application_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='签证申请表';

-- ============================
-- 5. 酒店预订表
-- ============================
CREATE TABLE IF NOT EXISTS `booking_hotel` (
  `booking_id` varchar(50) NOT NULL COMMENT '酒店预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `hotel_id` varchar(50) NOT NULL COMMENT '酒店ID',
  `check_in` datetime NOT NULL COMMENT '入住时间',
  `check_out` datetime NOT NULL COMMENT '离店时间',
  `room_count` int NOT NULL DEFAULT 1 COMMENT '房间数',
  `is_refundable` int NOT NULL DEFAULT 1 COMMENT '是否可退 1=可退 0=不可退',
  PRIMARY KEY (`booking_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_hotel_id` (`hotel_id`),
  CONSTRAINT `booking_hotel_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='酒店预订表';

-- ============================
-- 6. 机票预订表 (同航班高频 = 黄牛囤票)
-- ============================
CREATE TABLE IF NOT EXISTS `booking_flight` (
  `booking_id` varchar(50) NOT NULL COMMENT '机票预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `flight_no` varchar(20) NOT NULL COMMENT '航班号',
  `depart_airport` varchar(50) NOT NULL COMMENT '出发机场',
  `arrive_airport` varchar(50) NOT NULL COMMENT '到达机场',
  `cabin_class` enum('经济舱','商务舱','头等舱') NOT NULL DEFAULT '经济舱' COMMENT '舱位',
  PRIMARY KEY (`booking_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_flight_no` (`flight_no`),
  CONSTRAINT `booking_flight_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机票预订表';

-- ============================
-- 7. 退改申请表 (第 8 张表, "退改申请"事件校验实体)
-- ============================
CREATE TABLE IF NOT EXISTS `order_refund` (
  `refund_id` varchar(50) NOT NULL COMMENT '退改单ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `refund_amount` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT '退改金额',
  `refund_type` enum('退款','改期','换乘客') NOT NULL DEFAULT '退款' COMMENT '退改类型',
  `refund_status` enum('处理中','已完成','已驳回') NOT NULL DEFAULT '处理中' COMMENT '退改状态',
  `apply_time` datetime NOT NULL COMMENT '申请时间',
  PRIMARY KEY (`refund_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_user_id` (`user_id`),
  CONSTRAINT `order_refund_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
  CONSTRAINT `order_refund_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游退改申请表';

-- ============================
-- 8. 业务侧黑名单台账 (决策权威是 risk_blacklist, 本表是业务镜像)
-- ============================
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '条目ID',
  `type` enum('护照号','签证号','设备指纹') NOT NULL COMMENT '黑名单类型',
  `value` varchar(200) NOT NULL COMMENT '黑名单值',
  `reason` varchar(500) DEFAULT NULL COMMENT '加入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `idx_blacklist_extra_type_value` (`type`,`value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务侧黑名单台账表';

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================
-- 旅游行业风控系统 - 业务表 DDL 初始化脚本
-- 创建 10 张旅游业务表 (按外键依赖顺序)
-- 风控核心表继续复用参考项目 init_risk_tables.sql
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `blacklist_extra`;
DROP TABLE IF EXISTS `travel_complaint`;
DROP TABLE IF EXISTS `travel_refund`;
DROP TABLE IF EXISTS `booking_flight`;
DROP TABLE IF EXISTS `booking_hotel`;
DROP TABLE IF EXISTS `visa_application`;
DROP TABLE IF EXISTS `passenger_info`;
DROP TABLE IF EXISTS `order_info`;
DROP TABLE IF EXISTS `destination_risk`;
DROP TABLE IF EXISTS `user_info`;

-- ============================
-- 第一层: 基础实体表
-- ============================

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) NOT NULL COMMENT '用户姓名',
  `phone` varchar(30) NOT NULL COMMENT '手机号',
  `real_name_status` enum('未实名','已实名','实名失败') NOT NULL DEFAULT '未实名' COMMENT '实名状态',
  `vip_level` enum('普通','银卡','金卡','白金') NOT NULL DEFAULT '普通' COMMENT '会员等级',
  `account_age_days` int NOT NULL DEFAULT 0 COMMENT '账号年龄(天)',
  `register_time` timestamp NOT NULL COMMENT '注册时间',
  `pay_account` varchar(80) NOT NULL COMMENT '常用支付账号',
  `device_id` varchar(80) NOT NULL COMMENT '常用设备指纹',
  `login_ip` varchar(45) DEFAULT NULL COMMENT '最近登录IP',
  `source_channel` enum('App','小程序','H5','旅行社后台') NOT NULL DEFAULT 'App' COMMENT '注册渠道',
  `risk_label` tinyint NOT NULL DEFAULT 0 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uk_user_phone` (`phone`),
  KEY `idx_user_pay_account` (`pay_account`),
  KEY `idx_user_device` (`device_id`),
  KEY `idx_user_register_time` (`register_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游用户信息表';

-- 2. 目的地风险字典表
CREATE TABLE IF NOT EXISTS `destination_risk` (
  `destination_id` varchar(50) NOT NULL COMMENT '目的地ID',
  `country` varchar(50) NOT NULL COMMENT '目的地国家',
  `city` varchar(50) NOT NULL COMMENT '目的地城市',
  `risk_level` enum('低','中','高','极高') NOT NULL DEFAULT '低' COMMENT '目的地风险等级',
  `risk_score` int NOT NULL DEFAULT 0 COMMENT '目的地风险分 0-100',
  `risk_reason` varchar(300) DEFAULT NULL COMMENT '风险原因',
  `is_cross_border` tinyint NOT NULL DEFAULT 0 COMMENT '是否跨境目的地',
  `update_time` timestamp NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`destination_id`),
  UNIQUE KEY `uk_destination_country_city` (`country`,`city`),
  KEY `idx_destination_risk_score` (`risk_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='目的地风险字典表';

-- ============================
-- 第二层: 订单主表
-- ============================

-- 3. 旅游订单主表
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `order_type` enum('跟团游','自由行','机票','酒店','签证') NOT NULL COMMENT '订单类型',
  `total_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '订单总金额',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `dest_city` varchar(50) NOT NULL COMMENT '目的地城市',
  `depart_date` date NOT NULL COMMENT '出发日期',
  `return_date` date DEFAULT NULL COMMENT '返回日期',
  `passenger_count` int NOT NULL DEFAULT 1 COMMENT '旅客数',
  `order_status` enum('待支付','已支付','已出票','已确认','已取消','已完成','退款中','已退款') NOT NULL DEFAULT '待支付' COMMENT '订单状态',
  `create_time` timestamp NOT NULL COMMENT '下单时间',
  `payment_time` timestamp NULL DEFAULT NULL COMMENT '支付时间',
  `pay_account` varchar(80) NOT NULL COMMENT '支付账号',
  `device_id` varchar(80) NOT NULL COMMENT '下单设备指纹',
  `ip_address` varchar(45) DEFAULT NULL COMMENT '下单IP',
  `source_channel` enum('App','小程序','H5','旅行社后台') NOT NULL DEFAULT 'App' COMMENT '订单来源',
  `risk_label` tinyint NOT NULL DEFAULT 0 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`order_id`),
  KEY `idx_order_user` (`user_id`),
  KEY `idx_order_dest` (`dest_country`,`dest_city`),
  KEY `idx_order_create_time` (`create_time`),
  KEY `idx_order_pay_account_time` (`pay_account`,`create_time`),
  KEY `idx_order_device` (`device_id`),
  CONSTRAINT `fk_order_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单主表';

-- ============================
-- 第三层: 订单业务明细
-- ============================

-- 4. 旅客与证件信息表
CREATE TABLE IF NOT EXISTS `passenger_info` (
  `passenger_id` varchar(50) NOT NULL COMMENT '旅客ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '所属用户ID',
  `name` varchar(50) NOT NULL COMMENT '旅客姓名',
  `id_type` enum('身份证','护照','港澳通行证','台胞证') NOT NULL COMMENT '证件类型',
  `id_number` varchar(80) NOT NULL COMMENT '证件号',
  `passport_no` varchar(80) DEFAULT NULL COMMENT '护照号',
  `nationality` varchar(50) NOT NULL DEFAULT '中国' COMMENT '国籍',
  `age` int NOT NULL DEFAULT 18 COMMENT '年龄',
  `document_expire_date` date DEFAULT NULL COMMENT '证件有效期',
  `document_status` enum('有效','即将过期','已过期','疑似冒用') NOT NULL DEFAULT '有效' COMMENT '证件状态',
  `risk_label` tinyint NOT NULL DEFAULT 0 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`passenger_id`),
  KEY `idx_passenger_order` (`order_id`),
  KEY `idx_passenger_user` (`user_id`),
  KEY `idx_passenger_id_number` (`id_number`),
  KEY `idx_passenger_passport` (`passport_no`),
  CONSTRAINT `fk_passenger_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
  CONSTRAINT `fk_passenger_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅客与证件信息表';

-- 5. 签证申请表
CREATE TABLE IF NOT EXISTS `visa_application` (
  `visa_id` varchar(50) NOT NULL COMMENT '签证申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `dest_country` varchar(50) NOT NULL COMMENT '签证国家',
  `visa_type` enum('旅游签','商务签','探亲签','过境签') NOT NULL DEFAULT '旅游签' COMMENT '签证类型',
  `reject_history` int NOT NULL DEFAULT 0 COMMENT '历史拒签次数',
  `submit_time` timestamp NOT NULL COMMENT '提交时间',
  `visa_status` enum('申请中','通过','拒签','补材料','撤销') NOT NULL DEFAULT '申请中' COMMENT '签证状态',
  `material_change_count` int NOT NULL DEFAULT 0 COMMENT '材料变更次数',
  `reject_reason` varchar(300) DEFAULT NULL COMMENT '拒签原因',
  `risk_label` tinyint NOT NULL DEFAULT 0 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`visa_id`),
  KEY `idx_visa_user` (`user_id`),
  KEY `idx_visa_order` (`order_id`),
  KEY `idx_visa_country_time` (`dest_country`,`submit_time`),
  CONSTRAINT `fk_visa_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `fk_visa_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='签证申请表';

-- 6. 酒店预订表
CREATE TABLE IF NOT EXISTS `booking_hotel` (
  `booking_id` varchar(50) NOT NULL COMMENT '酒店预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `hotel_id` varchar(50) NOT NULL COMMENT '酒店ID',
  `hotel_name` varchar(100) NOT NULL COMMENT '酒店名称',
  `city` varchar(50) NOT NULL COMMENT '酒店城市',
  `check_in` date NOT NULL COMMENT '入住日期',
  `check_out` date NOT NULL COMMENT '离店日期',
  `room_count` int NOT NULL DEFAULT 1 COMMENT '房间数',
  `night_count` int NOT NULL DEFAULT 1 COMMENT '入住晚数',
  `is_refundable` tinyint NOT NULL DEFAULT 1 COMMENT '是否可退款',
  `guest_document_status` enum('有效','缺失','不一致','疑似冒用') NOT NULL DEFAULT '有效' COMMENT '入住人证件状态',
  `risk_label` tinyint NOT NULL DEFAULT 0 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`booking_id`),
  KEY `idx_hotel_order` (`order_id`),
  KEY `idx_hotel_city_checkin` (`city`,`check_in`),
  KEY `idx_hotel_id` (`hotel_id`),
  CONSTRAINT `fk_hotel_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='酒店预订表';

-- 7. 机票预订表
CREATE TABLE IF NOT EXISTS `booking_flight` (
  `booking_id` varchar(50) NOT NULL COMMENT '机票预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `flight_no` varchar(30) NOT NULL COMMENT '航班号',
  `airline` varchar(50) NOT NULL COMMENT '航司',
  `depart_airport` varchar(20) NOT NULL COMMENT '出发机场',
  `arrive_airport` varchar(20) NOT NULL COMMENT '到达机场',
  `depart_time` timestamp NOT NULL COMMENT '起飞时间',
  `cabin_class` enum('经济舱','超级经济舱','商务舱','头等舱') NOT NULL DEFAULT '经济舱' COMMENT '舱位',
  `ticket_count` int NOT NULL DEFAULT 1 COMMENT '票数',
  `refund_rule` enum('不可退','有条件退','免费退') NOT NULL DEFAULT '有条件退' COMMENT '退改规则',
  `risk_label` tinyint NOT NULL DEFAULT 0 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`booking_id`),
  KEY `idx_flight_order` (`order_id`),
  KEY `idx_flight_no_time` (`flight_no`,`depart_time`),
  KEY `idx_flight_route` (`depart_airport`,`arrive_airport`),
  CONSTRAINT `fk_flight_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机票预订表';

-- 8. 旅游售后/退款表
CREATE TABLE IF NOT EXISTS `travel_refund` (
  `refund_id` varchar(50) NOT NULL COMMENT '售后退款ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `refund_type` enum('退款','改签','取消','补偿') NOT NULL DEFAULT '退款' COMMENT '售后类型',
  `refund_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '退款/补偿金额',
  `refund_reason` varchar(300) NOT NULL COMMENT '售后原因',
  `apply_time` timestamp NOT NULL COMMENT '申请时间',
  `refund_status` enum('待审核','已通过','已拒绝','已完成') NOT NULL DEFAULT '待审核' COMMENT '售后状态',
  `risk_label` tinyint NOT NULL DEFAULT 0 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`refund_id`),
  KEY `idx_refund_order` (`order_id`),
  KEY `idx_refund_user_time` (`user_id`,`apply_time`),
  CONSTRAINT `fk_refund_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
  CONSTRAINT `fk_refund_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游售后退款表';

-- 9. 投诉与赔付表
CREATE TABLE IF NOT EXISTS `travel_complaint` (
  `complaint_id` varchar(50) NOT NULL COMMENT '投诉ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `complaint_type` enum('行程变更','酒店问题','航班延误','签证问题','服务态度','重复索赔') NOT NULL COMMENT '投诉类型',
  `complaint_time` timestamp NOT NULL COMMENT '投诉时间',
  `compensation_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '赔付金额',
  `complaint_status` enum('待处理','处理中','已赔付','已驳回','已关闭') NOT NULL DEFAULT '待处理' COMMENT '投诉状态',
  `risk_label` tinyint NOT NULL DEFAULT 0 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`complaint_id`),
  KEY `idx_complaint_order` (`order_id`),
  KEY `idx_complaint_user_time` (`user_id`,`complaint_time`),
  CONSTRAINT `fk_complaint_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
  CONSTRAINT `fk_complaint_user` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投诉与赔付表';

-- 10. 旅游业务黑名单扩展表
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` varchar(50) NOT NULL COMMENT '扩展黑名单ID',
  `type` enum('用户','手机号','护照号','身份证号','支付账号','设备指纹','IP','订单') NOT NULL COMMENT '黑名单类型',
  `value` varchar(120) NOT NULL COMMENT '黑名单值',
  `reason` varchar(300) DEFAULT NULL COMMENT '加入原因',
  `expire_at` timestamp NULL DEFAULT NULL COMMENT '过期时间',
  `create_time` timestamp NOT NULL COMMENT '创建时间',
  `risk_label` tinyint NOT NULL DEFAULT 1 COMMENT '训练标签: 0正常 1风险',
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `uk_blacklist_extra_type_value` (`type`,`value`),
  KEY `idx_blacklist_extra_expire` (`expire_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游业务黑名单扩展表';

SET FOREIGN_KEY_CHECKS = 1;

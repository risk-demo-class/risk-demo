-- ============================================
-- 旅游风控系统 - 业务表 DDL 初始化脚本
-- 创建 18 张旅游业务表 (按外键依赖顺序)
-- 业务域: 用户 / 产品 / 供应商 / 旅游订单 / 出行人 / 支付 / 退改 / 理赔 / 投诉 / 点评 / 设备
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础维度表 (无外键依赖)
-- ============================

-- 1. 用户信息表
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `phone` varchar(20) DEFAULT NULL COMMENT '注册手机号',
  `register_time` datetime NOT NULL COMMENT '注册时间',
  `register_channel` varchar(20) DEFAULT 'APP' COMMENT '注册渠道(APP/WEB/小程序/H5)',
  `is_verified` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否实名认证',
  PRIMARY KEY (`user_id`),
  KEY `idx_user_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 目的地区域表
CREATE TABLE IF NOT EXISTS `region` (
  `country` varchar(20) NOT NULL COMMENT '国家',
  `province` varchar(20) NOT NULL COMMENT '省/州',
  `city` varchar(20) NOT NULL COMMENT '城市',
  PRIMARY KEY (`country`,`province`,`city`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='目的地区域表';

-- 3. 产品分类表
CREATE TABLE IF NOT EXISTS `product_category` (
  `product_category` varchar(20) NOT NULL COMMENT '产品分类',
  PRIMARY KEY (`product_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='产品分类表';

-- 4. 供应商表
CREATE TABLE IF NOT EXISTS `supplier_info` (
  `supplier_id` varchar(50) NOT NULL COMMENT '供应商ID',
  `supplier_name` varchar(100) NOT NULL COMMENT '供应商名称',
  `supplier_type` varchar(20) NOT NULL COMMENT '供应商类型(旅行社/酒店/航司/门票/签证)',
  `credit_score` int NOT NULL DEFAULT 100 COMMENT '供应商信用分',
  `complaint_count` int NOT NULL DEFAULT 0 COMMENT '累计被投诉次数',
  `order_count` int NOT NULL DEFAULT 0 COMMENT '累计成交订单数',
  PRIMARY KEY (`supplier_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商表';

-- 5. 订单状态表
CREATE TABLE IF NOT EXISTS `booking_status` (
  `booking_status` varchar(20) NOT NULL COMMENT '订单状态',
  `status_code` int DEFAULT NULL COMMENT '状态码',
  PRIMARY KEY (`booking_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单状态表';

-- 6. 设备表
CREATE TABLE IF NOT EXISTS `device_info` (
  `device_id` varchar(50) NOT NULL COMMENT '设备ID',
  `device_model` varchar(100) DEFAULT NULL COMMENT '设备型号',
  `os` varchar(50) DEFAULT NULL COMMENT '操作系统',
  `browser` varchar(50) DEFAULT NULL COMMENT '浏览器',
  PRIMARY KEY (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备表';

-- ============================
-- 第二层: 依赖基础维度表
-- ============================

-- 7. 旅游产品表
CREATE TABLE IF NOT EXISTS `product_info` (
  `product_id` varchar(50) NOT NULL COMMENT '产品ID',
  `product_name` varchar(100) NOT NULL COMMENT '产品名称',
  `product_category` varchar(20) NOT NULL COMMENT '产品分类',
  `supplier_id` varchar(50) NOT NULL COMMENT '供应商ID',
  `price` decimal(10,2) NOT NULL COMMENT '产品单价',
  `destination_country` varchar(20) NOT NULL COMMENT '目的地国家',
  `destination_province` varchar(20) DEFAULT NULL COMMENT '目的地省/州',
  `destination_city` varchar(20) DEFAULT NULL COMMENT '目的地城市',
  `stock` int NOT NULL DEFAULT 0 COMMENT '库存',
  `is_overseas` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否出境游',
  `trip_days` int NOT NULL DEFAULT 1 COMMENT '行程天数',
  PRIMARY KEY (`product_id`),
  KEY `idx_product_category` (`product_category`),
  KEY `idx_product_supplier` (`supplier_id`),
  CONSTRAINT `product_info_ibfk_1` FOREIGN KEY (`product_category`) REFERENCES `product_category` (`product_category`),
  CONSTRAINT `product_info_ibfk_2` FOREIGN KEY (`supplier_id`) REFERENCES `supplier_info` (`supplier_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游产品表';

-- 8. 出行人表
CREATE TABLE IF NOT EXISTS `traveler_info` (
  `traveler_id` varchar(50) NOT NULL COMMENT '出行人ID',
  `user_id` varchar(50) NOT NULL COMMENT '所属用户ID',
  `traveler_name` varchar(50) NOT NULL COMMENT '出行人姓名',
  `id_card_no` varchar(30) DEFAULT NULL COMMENT '身份证号',
  `phone` varchar(20) DEFAULT NULL COMMENT '出行人手机号',
  PRIMARY KEY (`traveler_id`),
  KEY `idx_traveler_user` (`user_id`),
  CONSTRAINT `traveler_info_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='出行人表';

-- ============================
-- 第三层: 核心业务表
-- ============================

-- 9. 旅游订单表
CREATE TABLE IF NOT EXISTS `booking_info` (
  `booking_id` varchar(50) NOT NULL COMMENT '旅游订单ID',
  `create_time` datetime NOT NULL COMMENT '下单时间',
  `payment_time` datetime DEFAULT NULL COMMENT '支付时间',
  `departure_time` datetime NOT NULL COMMENT '出发时间',
  `end_time` datetime DEFAULT NULL COMMENT '行程结束时间',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `contact_phone` varchar(20) NOT NULL COMMENT '联系人手机号',
  `booking_status` varchar(20) NOT NULL COMMENT '订单状态',
  `traveler_count` int NOT NULL DEFAULT 1 COMMENT '出行人数',
  PRIMARY KEY (`booking_id`),
  KEY `idx_booking_user` (`user_id`),
  KEY `idx_booking_status` (`booking_status`),
  KEY `idx_booking_create_time` (`create_time`),
  CONSTRAINT `booking_info_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `booking_info_ibfk_2` FOREIGN KEY (`booking_status`) REFERENCES `booking_status` (`booking_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单表';

-- 10. 优惠券表
CREATE TABLE IF NOT EXISTS `coupon_info` (
  `coupon_id` varchar(50) NOT NULL COMMENT '优惠券ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `coupon_amount` decimal(10,2) NOT NULL COMMENT '优惠金额',
  `coupon_status` varchar(20) NOT NULL DEFAULT '未使用' COMMENT '状态(未使用/已使用/已过期)',
  `expire_time` datetime DEFAULT NULL COMMENT '过期时间',
  PRIMARY KEY (`coupon_id`),
  KEY `idx_coupon_user` (`user_id`),
  CONSTRAINT `coupon_info_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='优惠券表';

-- 11. 支付记录表
CREATE TABLE IF NOT EXISTS `payment_info` (
  `payment_id` varchar(50) NOT NULL COMMENT '支付ID',
  `booking_id` varchar(50) NOT NULL COMMENT '旅游订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `pay_time` datetime NOT NULL COMMENT '支付时间',
  `pay_amount` decimal(10,2) NOT NULL COMMENT '支付金额',
  `pay_channel` varchar(20) NOT NULL COMMENT '支付渠道(微信/支付宝/银联/银行卡)',
  `pay_status` varchar(20) NOT NULL DEFAULT '成功' COMMENT '支付状态',
  PRIMARY KEY (`payment_id`),
  KEY `idx_payment_booking` (`booking_id`),
  KEY `idx_payment_user` (`user_id`),
  CONSTRAINT `payment_info_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `booking_info` (`booking_id`),
  CONSTRAINT `payment_info_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='支付记录表';

-- ============================
-- 第四层: 关联表和明细表
-- ============================

-- 12. 订单明细表
CREATE TABLE IF NOT EXISTS `booking_detail` (
  `booking_detail_id` varchar(50) NOT NULL COMMENT '订单明细ID',
  `booking_id` varchar(50) NOT NULL COMMENT '旅游订单ID',
  `product_id` varchar(50) NOT NULL COMMENT '产品ID',
  `product_name` varchar(100) NOT NULL COMMENT '产品名称',
  `quantity` int NOT NULL DEFAULT 1 COMMENT '数量',
  `unit_price` decimal(10,2) NOT NULL COMMENT '产品单价',
  `total_amount` decimal(10,2) NOT NULL COMMENT '总计金额',
  `discount_amount` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT '优惠金额',
  `final_amount` decimal(10,2) NOT NULL COMMENT '实付金额',
  PRIMARY KEY (`booking_detail_id`),
  KEY `idx_detail_booking` (`booking_id`),
  KEY `idx_detail_product` (`product_id`),
  CONSTRAINT `booking_detail_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `booking_info` (`booking_id`),
  CONSTRAINT `booking_detail_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `product_info` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单明细表';

-- 13. 订单出行人关联表
CREATE TABLE IF NOT EXISTS `booking_traveler` (
  `booking_id` varchar(50) NOT NULL COMMENT '旅游订单ID',
  `traveler_id` varchar(50) NOT NULL COMMENT '出行人ID',
  `relation` varchar(20) DEFAULT '同行人' COMMENT '关系(本人/同行人)',
  PRIMARY KEY (`booking_id`,`traveler_id`),
  KEY `idx_bt_traveler` (`traveler_id`),
  CONSTRAINT `booking_traveler_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `booking_info` (`booking_id`),
  CONSTRAINT `booking_traveler_ibfk_2` FOREIGN KEY (`traveler_id`) REFERENCES `traveler_info` (`traveler_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单出行人关联表';

-- 14. 用户设备绑定表
CREATE TABLE IF NOT EXISTS `user_device` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `device_id` varchar(50) NOT NULL COMMENT '设备ID',
  `bind_time` datetime NOT NULL COMMENT '绑定时间',
  PRIMARY KEY (`user_id`,`device_id`),
  KEY `idx_ud_device` (`device_id`),
  CONSTRAINT `user_device_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `user_device_ibfk_2` FOREIGN KEY (`device_id`) REFERENCES `device_info` (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户设备绑定表';

-- ============================
-- 第五层: 售后与体验域
-- ============================

-- 15. 退改申请表
CREATE TABLE IF NOT EXISTS `refund_change` (
  `refund_id` varchar(50) NOT NULL COMMENT '退改申请ID',
  `create_time` datetime NOT NULL COMMENT '申请时间',
  `complete_time` datetime DEFAULT NULL COMMENT '完成时间',
  `booking_id` varchar(50) NOT NULL COMMENT '旅游订单ID',
  `refund_amount` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT '退改金额',
  `refund_type` varchar(20) NOT NULL COMMENT '退改类型(退订/改期/部分退款)',
  `refund_reason` varchar(500) DEFAULT NULL COMMENT '退改原因',
  `refund_status` varchar(20) NOT NULL DEFAULT '处理中' COMMENT '状态(处理中/已完成/已驳回)',
  PRIMARY KEY (`refund_id`),
  KEY `idx_refund_booking` (`booking_id`),
  KEY `idx_refund_create_time` (`create_time`),
  CONSTRAINT `refund_change_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `booking_info` (`booking_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='退改申请表';

-- 16. 投诉记录表
CREATE TABLE IF NOT EXISTS `complaint_info` (
  `complaint_id` varchar(50) NOT NULL COMMENT '投诉ID',
  `booking_id` varchar(50) NOT NULL COMMENT '旅游订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `complaint_time` datetime NOT NULL COMMENT '投诉时间',
  `complaint_content` varchar(500) NOT NULL COMMENT '投诉内容',
  `complaint_type` varchar(50) DEFAULT NULL COMMENT '投诉类型',
  `complaint_status` varchar(20) NOT NULL DEFAULT '处理中' COMMENT '处理状态',
  PRIMARY KEY (`complaint_id`),
  KEY `idx_complaint_user` (`user_id`),
  KEY `idx_complaint_booking` (`booking_id`),
  CONSTRAINT `complaint_info_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `booking_info` (`booking_id`),
  CONSTRAINT `complaint_info_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投诉记录表';

-- 17. 理赔申请表
CREATE TABLE IF NOT EXISTS `claim_info` (
  `claim_id` varchar(50) NOT NULL COMMENT '理赔申请ID',
  `booking_id` varchar(50) NOT NULL COMMENT '旅游订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `claim_type` varchar(20) NOT NULL COMMENT '理赔类型(航班延误/取消险/意外险/行程变更)',
  `claim_amount` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT '理赔金额',
  `apply_time` datetime NOT NULL COMMENT '申请时间',
  `claim_status` varchar(20) NOT NULL DEFAULT '审核中' COMMENT '状态(审核中/已通过/已驳回)',
  PRIMARY KEY (`claim_id`),
  KEY `idx_claim_user` (`user_id`),
  KEY `idx_claim_booking` (`booking_id`),
  CONSTRAINT `claim_info_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `booking_info` (`booking_id`),
  CONSTRAINT `claim_info_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='理赔申请表';

-- 18. 点评表
CREATE TABLE IF NOT EXISTS `review_info` (
  `review_id` varchar(50) NOT NULL COMMENT '点评ID',
  `booking_id` varchar(50) NOT NULL COMMENT '旅游订单ID',
  `product_id` varchar(50) NOT NULL COMMENT '产品ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `rating` tinyint NOT NULL DEFAULT 5 COMMENT '评分(1-5)',
  `content` varchar(1000) DEFAULT NULL COMMENT '点评内容',
  `review_time` datetime NOT NULL COMMENT '点评时间',
  `is_verified` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否已购验证',
  PRIMARY KEY (`review_id`),
  KEY `idx_review_user` (`user_id`),
  KEY `idx_review_product` (`product_id`),
  CONSTRAINT `review_info_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `booking_info` (`booking_id`),
  CONSTRAINT `review_info_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `product_info` (`product_id`),
  CONSTRAINT `review_info_ibfk_3` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='点评表';

SET FOREIGN_KEY_CHECKS = 1;

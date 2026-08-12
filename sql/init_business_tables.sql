-- ============================================
-- 物流风控系统 - 业务表 DDL 初始化脚本
-- 创建 7 张物流业务表 (按外键依赖顺序)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础维度表 (无外键依赖)
-- ============================

-- 1. 用户信息表 (寄件人/收件人统一)
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `user_name` varchar(50) NOT NULL COMMENT '用户姓名',
  `user_role` enum('寄件人','收件人','两者都是') NOT NULL DEFAULT '两者都是' COMMENT '用户角色',
  `phone` varchar(20) NOT NULL COMMENT '手机号',
  `id_card_hash` varchar(100) DEFAULT NULL COMMENT '身份证号哈希',
  `real_name_status` enum('未实名','已实名','实名中','实名失败') NOT NULL DEFAULT '未实名' COMMENT '实名认证状态',
  `register_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
  `vip_level` int NOT NULL DEFAULT 0 COMMENT 'VIP等级 0-5',
  `total_shipments` int NOT NULL DEFAULT 0 COMMENT '累计寄件次数',
  PRIMARY KEY (`user_id`),
  KEY `idx_phone` (`phone`),
  KEY `idx_real_name` (`real_name_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 物品分类表 (禁运/危险品分类)
CREATE TABLE IF NOT EXISTS `item_category` (
  `category_code` varchar(20) NOT NULL COMMENT '物品分类编码',
  `category_name` varchar(50) NOT NULL COMMENT '分类名称',
  `is_dangerous` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否危险品 0否1是',
  `is_prohibited` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否禁运品 0否1是',
  `need_real_name` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否需要实名 0否1是',
  `description` varchar(200) DEFAULT NULL COMMENT '分类说明',
  PRIMARY KEY (`category_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物品分类表';

-- 3. 运单状态表
CREATE TABLE IF NOT EXISTS `shipment_status` (
  `status_code` varchar(20) NOT NULL COMMENT '状态编码',
  `status_name` varchar(50) NOT NULL COMMENT '状态名称',
  `description` varchar(200) DEFAULT NULL COMMENT '状态说明',
  PRIMARY KEY (`status_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单状态表';

-- ============================
-- 第二层: 依赖基础维度表
-- ============================

-- 4. 地址表 (收/寄件地址)
CREATE TABLE IF NOT EXISTS `address` (
  `address_id` bigint NOT NULL AUTO_INCREMENT COMMENT '地址ID',
  `user_id` varchar(50) NOT NULL COMMENT '关联用户ID',
  `address_tag` enum('家','公司','学校','朋友','代收点','其他') NOT NULL DEFAULT '家' COMMENT '地址标签',
  `contact_name` varchar(50) NOT NULL COMMENT '联系人姓名',
  `contact_phone` varchar(20) NOT NULL COMMENT '联系人电话',
  `province` varchar(20) NOT NULL COMMENT '省',
  `city` varchar(20) NOT NULL COMMENT '市',
  `district` varchar(20) NOT NULL COMMENT '区',
  `street_address` varchar(200) NOT NULL COMMENT '详细街道地址',
  `is_remote` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否偏远地区 0否1是',
  `is_temporary` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否临时地址 0否1是',
  `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`address_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_region` (`province`,`city`,`district`),
  KEY `idx_remote` (`is_remote`),
  CONSTRAINT `address_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='地址表';

-- ============================
-- 第三层: 核心业务表
-- ============================

-- 5. 运单主表
CREATE TABLE IF NOT EXISTS `shipment` (
  `shipment_id` varchar(50) NOT NULL COMMENT '运单ID',
  `waybill_no` varchar(50) NOT NULL COMMENT '运单号',
  `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `pick_up_time` timestamp NULL DEFAULT NULL COMMENT '揽收时间',
  `delivered_time` timestamp NULL DEFAULT NULL COMMENT '签收时间',
  `sender_user_id` varchar(50) NOT NULL COMMENT '寄件人用户ID',
  `receiver_user_id` varchar(50) NOT NULL COMMENT '收件人用户ID',
  `sender_address_id` bigint NOT NULL COMMENT '寄件地址ID',
  `receiver_address_id` bigint NOT NULL COMMENT '收件地址ID',
  `shipment_type` enum('普通标快','生鲜冷链','次日达','隔日达','国际快递') NOT NULL DEFAULT '普通标快' COMMENT '运输类型',
  `payment_method` enum('寄付现结','到付','月结','寄付月结') NOT NULL DEFAULT '寄付现结' COMMENT '付款方式',
  `total_weight_kg` decimal(10,3) NOT NULL DEFAULT 0.000 COMMENT '总重量(kg)',
  `declared_value` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '申报价值(元)',
  `freight_amount` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT '运费金额',
  `cod_amount` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '代收货款金额',
  `insurance_amount` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT '保价金额',
  `shipment_status` varchar(20) NOT NULL DEFAULT '待揽收' COMMENT '运单状态',
  `is_cross_border` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否跨境 0否1是',
  `reject_count` int NOT NULL DEFAULT 0 COMMENT '拒收次数',
  `item_count` int NOT NULL DEFAULT 0 COMMENT '物品件数',
  PRIMARY KEY (`shipment_id`),
  UNIQUE KEY `uk_waybill_no` (`waybill_no`),
  KEY `idx_sender` (`sender_user_id`),
  KEY `idx_receiver` (`receiver_user_id`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_status` (`shipment_status`),
  KEY `idx_payment` (`payment_method`),
  KEY `idx_cross_border` (`is_cross_border`),
  CONSTRAINT `shipment_ibfk_1` FOREIGN KEY (`sender_user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `shipment_ibfk_2` FOREIGN KEY (`receiver_user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `shipment_ibfk_3` FOREIGN KEY (`sender_address_id`) REFERENCES `address` (`address_id`),
  CONSTRAINT `shipment_ibfk_4` FOREIGN KEY (`receiver_address_id`) REFERENCES `address` (`address_id`),
  CONSTRAINT `shipment_ibfk_5` FOREIGN KEY (`shipment_status`) REFERENCES `shipment_status` (`status_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单主表';

-- ============================
-- 第四层: 明细与扩展表
-- ============================

-- 6. 运单物品明细表
CREATE TABLE IF NOT EXISTS `shipment_item` (
  `item_id` varchar(50) NOT NULL COMMENT '物品明细ID',
  `shipment_id` varchar(50) NOT NULL COMMENT '运单ID',
  `item_name` varchar(100) NOT NULL COMMENT '物品名称',
  `category_code` varchar(20) NOT NULL COMMENT '物品分类编码',
  `quantity` int NOT NULL DEFAULT 1 COMMENT '数量',
  `unit_weight_kg` decimal(10,3) NOT NULL DEFAULT 0.000 COMMENT '单件重量(kg)',
  `declared_value` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '申报价值',
  `is_dangerous_declared` tinyint(1) NOT NULL DEFAULT 0 COMMENT '申报是否危险品 0否1是',
  `hs_code` varchar(20) DEFAULT NULL COMMENT 'HS编码(跨境用)',
  PRIMARY KEY (`item_id`),
  KEY `idx_shipment_id` (`shipment_id`),
  KEY `idx_category` (`category_code`),
  CONSTRAINT `shipment_item_ibfk_1` FOREIGN KEY (`shipment_id`) REFERENCES `shipment` (`shipment_id`),
  CONSTRAINT `shipment_item_ibfk_2` FOREIGN KEY (`category_code`) REFERENCES `item_category` (`category_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单物品明细表';

-- 7. 跨境申报记录表
CREATE TABLE IF NOT EXISTS `customs_declaration` (
  `declaration_id` varchar(50) NOT NULL COMMENT '申报ID',
  `shipment_id` varchar(50) NOT NULL COMMENT '关联运单ID',
  `declare_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '申报时间',
  `dest_country` varchar(50) NOT NULL COMMENT '目的国家',
  `dest_customs_code` varchar(50) DEFAULT NULL COMMENT '目的国海关编码',
  `sender_id_card` varchar(128) DEFAULT NULL COMMENT '寄件人证件号',
  `receiver_id_card` varchar(128) DEFAULT NULL COMMENT '收件人证件号',
  `total_declared_value` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '申报总价值',
  `currency` varchar(10) NOT NULL DEFAULT 'CNY' COMMENT '币种',
  `declare_status` enum('待申报','已申报','审核中','已放行','被扣留') NOT NULL DEFAULT '待申报' COMMENT '申报状态',
  `is_value_mismatch` tinyint(1) NOT NULL DEFAULT 0 COMMENT '申报价值是否异常 0否1是',
  PRIMARY KEY (`declaration_id`),
  KEY `idx_shipment_id` (`shipment_id`),
  KEY `idx_dest_country` (`dest_country`),
  KEY `idx_status` (`declare_status`),
  CONSTRAINT `customs_declaration_ibfk_1` FOREIGN KEY (`shipment_id`) REFERENCES `shipment` (`shipment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='跨境申报记录表';

-- 8. 物流投诉记录表
CREATE TABLE IF NOT EXISTS `complaint_record` (
  `record_id` bigint NOT NULL AUTO_INCREMENT COMMENT '投诉记录ID',
  `shipment_id` varchar(50) NOT NULL COMMENT '关联运单ID',
  `user_id` varchar(50) NOT NULL COMMENT '投诉用户ID',
  `complaint_type` enum('延误','破损','丢失','服务态度差','费用争议','派送失败','虚假签收') NOT NULL DEFAULT '延误' COMMENT '投诉类型',
  `complaint_content` text NOT NULL COMMENT '投诉内容',
  `complaint_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '投诉时间',
  `claim_amount` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '索赔金额',
  `handle_status` enum('待处理','处理中','已结案','已驳回') NOT NULL DEFAULT '待处理' COMMENT '处理状态',
  `is_malicious` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否恶意投诉 0否1是',
  PRIMARY KEY (`record_id`),
  KEY `idx_shipment_id` (`shipment_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_complaint_time` (`complaint_time`),
  KEY `idx_handle_status` (`handle_status`),
  CONSTRAINT `complaint_record_ibfk_1` FOREIGN KEY (`shipment_id`) REFERENCES `shipment` (`shipment_id`),
  CONSTRAINT `complaint_record_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物流投诉记录表';

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================
-- 物流风控系统 - 业务表 DDL 初始化脚本
-- 创建 9 张物流业务表 (7 核心 + 2 支撑) (按外键依赖顺序)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础维度表 (无外键依赖)
-- ============================

-- 1. 省份编码表 (特征计算用: 省份名称 → 编码, 支持"跨省/省份编码"特征)
CREATE TABLE IF NOT EXISTS `region` (
  `province` varchar(20) NOT NULL COMMENT '省份名称',
  `province_code` int NOT NULL COMMENT '省份编码',
  PRIMARY KEY (`province`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='省份编码表';

-- 2. 物品类目表 (包裹 item_category 的可选值)
CREATE TABLE IF NOT EXISTS `item_category` (
  `item_category` varchar(50) NOT NULL COMMENT '物品类目',
  PRIMARY KEY (`item_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物品类目表';

-- ============================
-- 第二层: 用户与实名域
-- ============================

-- 3. 寄件用户信息表 (区分个人/企业寄件人)
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID(寄件人账号)',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `real_name_status` varchar(20) NOT NULL COMMENT '实名状态(已认证/未认证/认证失败)',
  `account_type` varchar(20) NOT NULL COMMENT '账号类型(personal个人/enterprise企业)',
  `register_at` datetime NOT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='寄件用户信息表';

-- 4. 寄件人实名表 (物流风控双向对象之一)
CREATE TABLE IF NOT EXISTS `sender_info` (
  `sender_id` varchar(32) NOT NULL COMMENT '寄件人ID(与 user_id 一致)',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `id_type` varchar(20) NOT NULL COMMENT '证件类型(身份证/护照/军官证)',
  `id_number` varchar(50) NOT NULL COMMENT '证件号码',
  `phone` varchar(20) NOT NULL COMMENT '手机号',
  `address` varchar(200) NOT NULL COMMENT '寄件地址',
  `sender_province` varchar(20) NOT NULL COMMENT '寄件省份',
  `is_blacklisted` int NOT NULL DEFAULT 0 COMMENT '是否黑名单(0/1)',
  PRIMARY KEY (`sender_id`),
  KEY `sender_province` (`sender_province`),
  CONSTRAINT `sender_info_ibfk_1` FOREIGN KEY (`sender_province`) REFERENCES `region` (`province`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='寄件人实名表';

-- 5. 收件人表 (1 包裹 1 收件人; 标记是否代签收)
CREATE TABLE IF NOT EXISTS `receiver_info` (
  `receiver_id` varchar(32) NOT NULL COMMENT '收件人ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `phone` varchar(20) NOT NULL COMMENT '手机号',
  `address` varchar(200) NOT NULL COMMENT '收件地址',
  `receiver_province` varchar(20) NOT NULL COMMENT '收件省份',
  `is_proxy_received` int NOT NULL DEFAULT 0 COMMENT '是否代签收(0/1)',
  PRIMARY KEY (`receiver_id`),
  KEY `receiver_province` (`receiver_province`),
  CONSTRAINT `receiver_info_ibfk_1` FOREIGN KEY (`receiver_province`) REFERENCES `region` (`province`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='收件人表';

-- ============================
-- 第三层: 包裹核心表 (依赖用户/寄件人/收件人/类目)
-- ============================

-- 6. 包裹表 (物流风控的核心实体, 业务核心是"物")
CREATE TABLE IF NOT EXISTS `parcel` (
  `parcel_id` varchar(32) NOT NULL COMMENT '包裹ID(面单号)',
  `user_id` varchar(50) NOT NULL COMMENT '寄件用户ID(风控主体)',
  `sender_id` varchar(32) NOT NULL COMMENT '寄件人ID',
  `receiver_id` varchar(32) NOT NULL COMMENT '收件人ID',
  `weight_kg` decimal(8,2) NOT NULL COMMENT '实际称重(kg)',
  `declared_value` decimal(10,2) NOT NULL COMMENT '申报价值(元)',
  `item_category` varchar(50) NOT NULL COMMENT '物品类目(电子产品/服装/食品/化工品/普通)',
  `is_international` int NOT NULL DEFAULT 0 COMMENT '是否国际件(0/1)',
  `piece_count` int DEFAULT NULL COMMENT '货物件数(用于大额低报规则)',
  `status` varchar(20) NOT NULL DEFAULT 'created' COMMENT '状态(created/in_transit/delivered/returned)',
  `created_at` datetime NOT NULL COMMENT '揽收时间',
  PRIMARY KEY (`parcel_id`),
  KEY `user_id` (`user_id`),
  KEY `sender_id` (`sender_id`),
  KEY `receiver_id` (`receiver_id`),
  KEY `item_category` (`item_category`),
  CONSTRAINT `parcel_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `parcel_ibfk_2` FOREIGN KEY (`sender_id`) REFERENCES `sender_info` (`sender_id`),
  CONSTRAINT `parcel_ibfk_3` FOREIGN KEY (`receiver_id`) REFERENCES `receiver_info` (`receiver_id`),
  CONSTRAINT `parcel_ibfk_4` FOREIGN KEY (`item_category`) REFERENCES `item_category` (`item_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='包裹表';

-- ============================
-- 第四层: 物流专属表 (依赖包裹)
-- ============================

-- 7. 危险品申报表 (寄递物品的危险品申报与检测)
CREATE TABLE IF NOT EXISTS `dangerous_declaration` (
  `decl_id` varchar(32) NOT NULL COMMENT '申报ID',
  `parcel_id` varchar(32) NOT NULL COMMENT '包裹ID',
  `item_type` varchar(50) NOT NULL COMMENT '物品类型(锂电池/液体/粉末等)',
  `is_liquid` int NOT NULL DEFAULT 0 COMMENT '是否液体(0/1)',
  `is_battery` int NOT NULL DEFAULT 0 COMMENT '是否含电池(0/1)',
  `msds_url` varchar(200) DEFAULT NULL COMMENT 'MSDS 安全数据表链接',
  `declared_at` datetime NOT NULL COMMENT '申报时间',
  PRIMARY KEY (`decl_id`),
  KEY `parcel_id` (`parcel_id`),
  CONSTRAINT `dangerous_declaration_ibfk_1` FOREIGN KEY (`parcel_id`) REFERENCES `parcel` (`parcel_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='危险品申报表';

-- 8. 代收货款流水表 (货到付款 COD 场景的资金流转)
CREATE TABLE IF NOT EXISTS `cod_transaction` (
  `cod_id` varchar(32) NOT NULL COMMENT 'COD ID',
  `parcel_id` varchar(32) NOT NULL COMMENT '包裹ID',
  `amount` decimal(10,2) NOT NULL COMMENT '代收金额(元)',
  `cod_status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT '状态(pending待收/paid已付/returned已退/overdue逾期)',
  `paid_at` datetime DEFAULT NULL COMMENT '实际付款时间',
  `returned_at` datetime DEFAULT NULL COMMENT '退回时间',
  `days_overdue` int DEFAULT NULL COMMENT '逾期天数(签收后未付款)',
  PRIMARY KEY (`cod_id`),
  KEY `parcel_id` (`parcel_id`),
  CONSTRAINT `cod_transaction_ibfk_1` FOREIGN KEY (`parcel_id`) REFERENCES `parcel` (`parcel_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='代收货款流水表';

-- ============================
-- 第五层: 物流业务黑名单扩展表
-- ============================

-- 9. 物流业务黑名单扩展表 (type 含 身份证号/手机号/地址/面单条码/IP)
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '黑名单条目ID',
  `type` varchar(30) NOT NULL COMMENT '黑名单类型(id_number/phone/address/waybill_barcode/ip_address)',
  `value` varchar(200) NOT NULL COMMENT '黑名单值',
  `reason` text COMMENT '加入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  PRIMARY KEY (`entry_id`),
  KEY `idx_blacklist_extra_type_value` (`type`, `value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物流业务黑名单扩展表';

SET FOREIGN_KEY_CHECKS = 1;

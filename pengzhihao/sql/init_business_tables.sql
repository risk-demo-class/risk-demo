-- 物流风控业务表（5 张）。9 张风险核心表由 init_risk_tables.sql 原样创建。
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `blacklist_extra`;
DROP TABLE IF EXISTS `shipment_item`;
DROP TABLE IF EXISTS `shipment`;
DROP TABLE IF EXISTS `address`;
DROP TABLE IF EXISTS `user_info`;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE `user_info` (
  `user_id` varchar(50) NOT NULL,
  `user_role` enum('寄件人','收件人','双方') NOT NULL DEFAULT '寄件人',
  `full_name` varchar(50) NOT NULL,
  `phone` varchar(32) NOT NULL,
  `id_type` varchar(30) NOT NULL DEFAULT '居民身份证',
  `id_no_hash` varchar(64) NOT NULL,
  `id_no_masked` varchar(32) NOT NULL,
  `real_name_status` enum('已核验','未核验','信息不符','证件过期') NOT NULL DEFAULT '已核验',
  `device_fingerprint` varchar(100) DEFAULT NULL,
  `last_ip` varchar(64) DEFAULT NULL,
  `account_status` enum('正常','限制寄件','停用') NOT NULL DEFAULT '正常',
  `register_time` datetime NOT NULL,
  PRIMARY KEY (`user_id`),
  KEY `idx_user_phone` (`phone`),
  KEY `idx_user_id_hash` (`id_no_hash`),
  KEY `idx_user_device` (`device_fingerprint`),
  KEY `idx_user_last_ip` (`last_ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物流寄递用户';

CREATE TABLE `address` (
  `address_id` varchar(50) NOT NULL,
  `user_id` varchar(50) NOT NULL,
  `contact_name` varchar(50) NOT NULL,
  `contact_phone` varchar(32) NOT NULL,
  `province` varchar(30) NOT NULL,
  `city` varchar(30) NOT NULL,
  `district` varchar(30) NOT NULL,
  `detail_address` varchar(200) NOT NULL,
  `normalized_hash` varchar(64) NOT NULL,
  `address_type` enum('住宅','单位','驿站','临时') NOT NULL DEFAULT '住宅',
  `is_remote` tinyint NOT NULL DEFAULT 0,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`address_id`),
  KEY `idx_address_user` (`user_id`),
  KEY `idx_address_hash` (`normalized_hash`),
  KEY `idx_address_region` (`province`,`city`,`district`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物流收寄地址';

CREATE TABLE `shipment` (
  `shipment_id` varchar(50) NOT NULL,
  `waybill_no` varchar(50) NOT NULL,
  `sender_id` varchar(50) NOT NULL,
  `receiver_id` varchar(50) DEFAULT NULL,
  `sender_address_id` varchar(50) DEFAULT NULL,
  `receiver_address_id` varchar(50) NOT NULL,
  `create_time` datetime NOT NULL,
  `pickup_time` datetime DEFAULT NULL,
  `delivered_time` datetime DEFAULT NULL,
  `shipment_status` enum('待揽收','运输中','已签收','拒收退回','已取消','海关查验','安全拦截') NOT NULL DEFAULT '待揽收',
  `channel` enum('柜台','上门取件','直营网点','合作平台') NOT NULL DEFAULT '上门取件',
  `payment_type` enum('寄付','到付','代收货款') NOT NULL DEFAULT '寄付',
  `cod_amount` decimal(12,2) NOT NULL DEFAULT 0,
  `cod_status` enum('无','待收','已收','拒收','退回') NOT NULL DEFAULT '无',
  `is_cross_border` tinyint NOT NULL DEFAULT 0,
  `origin_country` varchar(50) NOT NULL DEFAULT '中国',
  `destination_country` varchar(50) NOT NULL DEFAULT '中国',
  `customs_subject` varchar(100) DEFAULT NULL,
  `customs_status` enum('不适用','待申报','已放行','查验中','退运') NOT NULL DEFAULT '不适用',
  `declared_weight_kg` decimal(10,3) NOT NULL,
  `actual_weight_kg` decimal(10,3) NOT NULL,
  `declared_value` decimal(12,2) NOT NULL,
  `customs_assessed_value` decimal(12,2) NOT NULL DEFAULT 0,
  `real_name_verified` tinyint NOT NULL DEFAULT 1,
  `inspection_status` enum('待验视','已通过','疑似危险品','拒绝收寄') NOT NULL DEFAULT '待验视',
  `risk_label` tinyint NOT NULL DEFAULT 0,
  `risk_pattern` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`shipment_id`),
  UNIQUE KEY `uq_shipment_waybill` (`waybill_no`),
  KEY `idx_shipment_sender_time` (`sender_id`,`create_time`),
  KEY `idx_shipment_receiver_address` (`receiver_address_id`),
  KEY `idx_shipment_cross_border` (`is_cross_border`,`customs_status`),
  KEY `idx_shipment_cod` (`payment_type`,`cod_status`),
  KEY `idx_shipment_risk_label` (`risk_label`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物流运单';

CREATE TABLE `shipment_item` (
  `item_id` varchar(50) NOT NULL,
  `shipment_id` varchar(50) NOT NULL,
  `item_name` varchar(100) NOT NULL,
  `declared_category` varchar(50) NOT NULL,
  `actual_category` varchar(50) NOT NULL,
  `quantity` int NOT NULL DEFAULT 1,
  `unit_value` decimal(12,2) NOT NULL DEFAULT 0,
  `dangerous_declared` tinyint NOT NULL DEFAULT 0,
  `detected_dangerous_type` varchar(50) DEFAULT NULL,
  `inspection_result` enum('正常','限寄','禁寄','信息不符') NOT NULL DEFAULT '正常',
  PRIMARY KEY (`item_id`),
  KEY `idx_shipment_item_shipment` (`shipment_id`),
  KEY `idx_shipment_item_danger` (`inspection_result`,`dangerous_declared`),
  CONSTRAINT `fk_item_shipment` FOREIGN KEY (`shipment_id`) REFERENCES `shipment` (`shipment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单物品明细';

CREATE TABLE `blacklist_extra` (
  `extra_id` bigint NOT NULL AUTO_INCREMENT,
  `entity_type` enum('实名证件','设备指纹','IP地址','海关主体') NOT NULL,
  `entity_value` varchar(200) NOT NULL,
  `reason` text,
  `source` varchar(50) NOT NULL DEFAULT '人工录入',
  `status` enum('启用','停用') NOT NULL DEFAULT '启用',
  `expire_time` datetime DEFAULT NULL,
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`extra_id`),
  UNIQUE KEY `uq_blacklist_extra_type_value` (`entity_type`,`entity_value`),
  KEY `idx_blacklist_extra_status` (`status`,`expire_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物流扩展黑名单';

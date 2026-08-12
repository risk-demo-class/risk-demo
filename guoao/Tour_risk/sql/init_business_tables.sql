-- ============================================
-- 物流风控系统 - 业务表 DDL 初始化脚本
-- 5 张业务表: user_info / address / shipment / shipment_item / blacklist_extra
-- 与 app/models_business.py 一一对应
-- ============================================

CREATE TABLE IF NOT EXISTS `user_info` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `user_name` VARCHAR(50) NOT NULL COMMENT '姓名',
    `phone` VARCHAR(20) NOT NULL COMMENT '手机号',
    `id_number_hash` VARCHAR(64) DEFAULT NULL COMMENT '身份证号(哈希)',
    `real_name_status` INT DEFAULT 0 COMMENT '实名状态(0=未实名 1=已实名)',
    `company_name` VARCHAR(100) DEFAULT NULL COMMENT '企业名称(企业寄件)',
    `account_age_days` INT DEFAULT 0 COMMENT '账号年龄(天)',
    `create_time` DATETIME DEFAULT NULL COMMENT '注册时间',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='寄件人/收件人用户表';

CREATE TABLE IF NOT EXISTS `address` (
    `address_id` VARCHAR(50) NOT NULL COMMENT '地址ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '归属用户ID',
    `receiver_name` VARCHAR(50) NOT NULL COMMENT '收件人姓名',
    `receiver_phone` VARCHAR(20) NOT NULL COMMENT '收件人手机',
    `province` VARCHAR(50) NOT NULL COMMENT '省',
    `city` VARCHAR(50) NOT NULL COMMENT '市',
    `district` VARCHAR(50) NOT NULL COMMENT '区',
    `street` VARCHAR(200) NOT NULL COMMENT '详细地址',
    `is_temp` INT DEFAULT 0 COMMENT '是否临时地址(0/1)',
    `use_count` INT DEFAULT 0 COMMENT '已使用次数',
    `create_time` DATETIME DEFAULT NULL COMMENT '创建时间',
    PRIMARY KEY (`address_id`),
    INDEX `idx_address_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='收件地址表';

CREATE TABLE IF NOT EXISTS `shipment` (
    `shipment_id` VARCHAR(50) NOT NULL COMMENT '运单ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '寄件人用户ID',
    `shipment_type` ENUM('普通','跨境','代收货款') NOT NULL DEFAULT '普通' COMMENT '运单类型',
    `receiver_name` VARCHAR(50) NOT NULL COMMENT '收件人姓名',
    `receiver_phone` VARCHAR(20) NOT NULL COMMENT '收件人手机',
    `address_id` VARCHAR(50) NOT NULL COMMENT '收件地址ID',
    `origin_province` VARCHAR(50) NOT NULL COMMENT '寄出省',
    `dest_province` VARCHAR(50) NOT NULL COMMENT '目的省',
    `dest_city` VARCHAR(50) NOT NULL COMMENT '目的市',
    `dest_country` VARCHAR(50) DEFAULT NULL COMMENT '目的国家(跨境用)',
    `weight_kg` DECIMAL(10,2) DEFAULT 0 COMMENT '总重量(kg)',
    `declared_value` DECIMAL(12,2) DEFAULT 0 COMMENT '申报价值(元)',
    `cod_amount` DECIMAL(12,2) DEFAULT 0 COMMENT '代收货款金额(元)',
    `is_dangerous_declared` INT DEFAULT 0 COMMENT '是否如实申报危险品(0/1)',
    `is_delivered` INT DEFAULT 0 COMMENT '是否已送达(0/1)',
    `is_rejected` INT DEFAULT 0 COMMENT '是否拒收(0/1, COD 用)',
    `status` ENUM('待揽收','运输中','已签收','拒收','已取消') NOT NULL DEFAULT '待揽收' COMMENT '运单状态',
    `create_time` DATETIME DEFAULT NULL COMMENT '下单/寄件时间',
    PRIMARY KEY (`shipment_id`),
    INDEX `idx_shipment_user_id` (`user_id`),
    INDEX `idx_shipment_type` (`shipment_type`),
    INDEX `idx_shipment_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单主表';

CREATE TABLE IF NOT EXISTS `shipment_item` (
    `item_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '明细ID',
    `shipment_id` VARCHAR(50) NOT NULL COMMENT '运单ID',
    `item_name` VARCHAR(100) NOT NULL COMMENT '物品名称',
    `item_category` ENUM('普通','电池','液体','化学品') NOT NULL DEFAULT '普通' COMMENT '物品类别',
    `quantity` INT DEFAULT 1 COMMENT '数量',
    `unit_weight` DECIMAL(10,2) DEFAULT 0 COMMENT '单件重量(kg)',
    `unit_price` DECIMAL(12,2) DEFAULT 0 COMMENT '单件价格(元)',
    PRIMARY KEY (`item_id`),
    INDEX `idx_shipment_item_shipment_id` (`shipment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单物品明细表';

CREATE TABLE IF NOT EXISTS `blacklist_extra` (
    `entry_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '条目ID',
    `blacklist_type` ENUM('身份证号','寄件网点') NOT NULL COMMENT '黑名单类型',
    `blacklist_value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` VARCHAR(500) DEFAULT NULL COMMENT '加入原因',
    `expire_time` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `create_time` DATETIME DEFAULT NULL COMMENT '创建时间',
    PRIMARY KEY (`entry_id`),
    INDEX `idx_blacklist_extra_type_value` (`blacklist_type`, `blacklist_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物流行业扩展黑名单表';

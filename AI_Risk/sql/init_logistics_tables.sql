-- 物流行业业务表 DDL

SET FOREIGN_KEY_CHECKS = 0;

-- 1. 用户信息表
DROP TABLE IF EXISTS `user_info`;
CREATE TABLE `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) NOT NULL COMMENT '真实姓名',
  `phone` varchar(20) NOT NULL COMMENT '手机号',
  `id_card_hash` varchar(64) DEFAULT NULL COMMENT '身份证脱敏哈希',
  `real_name_verified` tinyint(1) DEFAULT '0' COMMENT '实名核验状态',
  `account_age_days` int DEFAULT '0' COMMENT '账号年龄(天)',
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物流用户信息表';

-- 2. 地址库
DROP TABLE IF EXISTS `address`;
CREATE TABLE `address` (
  `address_id` varchar(50) NOT NULL COMMENT '地址ID',
  `province` varchar(50) NOT NULL COMMENT '省',
  `city` varchar(50) NOT NULL COMMENT '市',
  `district` varchar(50) NOT NULL COMMENT '区',
  `detail` varchar(200) NOT NULL COMMENT '详细地址',
  `is_temporary` tinyint(1) DEFAULT '0' COMMENT '是否临时地址',
  PRIMARY KEY (`address_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='地址库';

-- 3. 运单主表
DROP TABLE IF EXISTS `shipment`;
CREATE TABLE `shipment` (
  `shipment_id` varchar(50) NOT NULL COMMENT '运单号',
  `sender_id` varchar(50) NOT NULL COMMENT '寄件人ID',
  `receiver_name` varchar(50) NOT NULL COMMENT '收件人姓名',
  `receiver_phone` varchar(20) NOT NULL COMMENT '收件人手机',
  `shipment_type` enum('普快','特快','跨境','代收货款') NOT NULL COMMENT '运单类型',
  `declared_value` decimal(10,2) NOT NULL COMMENT '申报价值',
  `actual_weight` decimal(10,2) NOT NULL COMMENT '实际重量(kg)',
  `cod_amount` decimal(10,2) DEFAULT '0.00' COMMENT '代收货款金额',
  `origin_address_id` varchar(50) NOT NULL COMMENT '起始地ID',
  `dest_address_id` varchar(50) NOT NULL COMMENT '目的地ID',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `status` varchar(20) DEFAULT '待揽收' COMMENT '运单状态',
  PRIMARY KEY (`shipment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运单主表';

-- 4. 运单物品明细
DROP TABLE IF EXISTS `shipment_item`;
CREATE TABLE `shipment_item` (
  `item_id` varchar(50) NOT NULL COMMENT '物品ID',
  `shipment_id` varchar(50) NOT NULL COMMENT '运单号',
  `item_name` varchar(100) NOT NULL COMMENT '物品名称',
  `item_category` varchar(50) NOT NULL COMMENT '物品分类',
  `quantity` int DEFAULT '1' COMMENT '数量',
  `is_dangerous` tinyint(1) DEFAULT '0' COMMENT '是否标识为危险品',
  PRIMARY KEY (`item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运单物品明细';

-- 5. 物流状态更新日志
DROP TABLE IF EXISTS `logistics_status_update`;
CREATE TABLE `logistics_status_update` (
  `update_id` bigint NOT NULL AUTO_INCREMENT COMMENT '更新ID',
  `shipment_id` varchar(50) NOT NULL COMMENT '运单号',
  `status` varchar(50) NOT NULL COMMENT '状态',
  `location` varchar(200) DEFAULT NULL COMMENT '当前位置',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`update_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物流状态更新日志';

-- 6. 运单投诉记录
DROP TABLE IF EXISTS `shipment_complaint`;
CREATE TABLE `shipment_complaint` (
  `complaint_id` bigint NOT NULL AUTO_INCREMENT COMMENT '投诉ID',
  `shipment_id` varchar(50) NOT NULL COMMENT '运单号',
  `user_id` varchar(50) NOT NULL COMMENT '投诉人ID',
  `complaint_type` varchar(50) NOT NULL COMMENT '投诉类型',
  `content` varchar(500) DEFAULT NULL COMMENT '投诉内容',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '投诉时间',
  PRIMARY KEY (`complaint_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运单投诉记录';

SET FOREIGN_KEY_CHECKS = 1;

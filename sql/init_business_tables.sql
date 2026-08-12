-- ============================================
-- 制造业风控系统 - 业务表 DDL 初始化脚本
-- 创建 7 张行业业务表 (按外键依赖顺序)
-- 业务边界: 经销商订货 / 采购订单 / 设备保修 / 售后维修
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础表 (无外键依赖)
-- ============================

-- 1. 用户信息表 (经销商 / 终端用户 / 内部员工)
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID(经销商时=dealer_id)',
  `name` varchar(50) NOT NULL COMMENT '姓名/企业联系人',
  `role` ENUM('经销商','终端用户','内部员工') NOT NULL COMMENT '角色',
  `dealer_level` ENUM('一级','二级','三级') DEFAULT NULL COMMENT '经销商等级',
  `region` varchar(50) DEFAULT NULL COMMENT '授权区域',
  `phone` varchar(20) DEFAULT NULL COMMENT '联系电话',
  `register_at` datetime NOT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 产品表 (制造业"商品", 带 MSRP + 保修期)
CREATE TABLE IF NOT EXISTS `product` (
  `product_id` varchar(50) NOT NULL COMMENT '产品ID',
  `name` varchar(100) NOT NULL COMMENT '产品名称',
  `model` varchar(50) NOT NULL COMMENT '型号',
  `category` varchar(50) NOT NULL COMMENT '品类',
  `msrp` decimal(12,2) NOT NULL COMMENT '官方建议零售价',
  `warranty_months` int NOT NULL COMMENT '保修月数',
  PRIMARY KEY (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='产品表';

-- ============================
-- 第二层: 依赖基础表
-- ============================

-- 3. 经销商档案表 (全新表, 电商没有"经销商"概念)
CREATE TABLE IF NOT EXISTS `dealer_info` (
  `dealer_id` varchar(50) NOT NULL COMMENT '经销商ID',
  `dealer_name` varchar(100) NOT NULL COMMENT '经销商名称',
  `region` varchar(50) NOT NULL COMMENT '授权区域',
  `authorized_brands` varchar(200) NOT NULL COMMENT '授权品牌',
  `contract_start` datetime NOT NULL COMMENT '合同开始',
  `contract_end` datetime NOT NULL COMMENT '合同到期',
  `status` ENUM('合作中','已终止') NOT NULL DEFAULT '合作中' COMMENT '合作状态',
  PRIMARY KEY (`dealer_id`),
  CONSTRAINT `dealer_info_ibfk_1` FOREIGN KEY (`dealer_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='经销商档案表';

-- 4. 订货/采购订单表 (经销商向制造企业下单)
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `order_type` ENUM('经销商订货','采购订单') NOT NULL COMMENT '订单类型',
  `dealer_id` varchar(50) NOT NULL COMMENT '经销商ID',
  `product_id` varchar(50) NOT NULL COMMENT '产品ID',
  `quantity` int NOT NULL COMMENT '订购数量',
  `unit_price` decimal(12,2) NOT NULL COMMENT '成交单价',
  `total_amount` decimal(14,2) NOT NULL COMMENT '订单总额',
  `ship_to_region` varchar(50) NOT NULL COMMENT '发货区域',
  `order_status` ENUM('待发货','已发货','已完成','已取消') NOT NULL COMMENT '订单状态',
  `create_time` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`order_id`),
  KEY `idx_order_dealer_id` (`dealer_id`),
  KEY `idx_order_product_id` (`product_id`),
  CONSTRAINT `order_info_ibfk_1` FOREIGN KEY (`dealer_id`) REFERENCES `user_info` (`user_id`),
  CONSTRAINT `order_info_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `product` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订货/采购订单表';

-- 5. 保修/维修工单表 (全新表, 按设备 SN 管理)
CREATE TABLE IF NOT EXISTS `warranty_record` (
  `warranty_id` varchar(50) NOT NULL COMMENT '工单ID',
  `product_sn` varchar(100) NOT NULL COMMENT '设备序列号',
  `order_id` varchar(50) NOT NULL COMMENT '关联订货单ID',
  `issue_date` datetime NOT NULL COMMENT '报修时间',
  `issue_type` ENUM('保修','维修') NOT NULL COMMENT '工单类型',
  `repair_cost` decimal(12,2) NOT NULL DEFAULT 0 COMMENT '维修费用',
  `technician_id` varchar(50) NOT NULL COMMENT '维修工ID',
  `description` text DEFAULT NULL COMMENT '故障描述',
  PRIMARY KEY (`warranty_id`),
  KEY `idx_warranty_sn` (`product_sn`),
  KEY `idx_warranty_order_id` (`order_id`),
  CONSTRAINT `warranty_record_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='保修/维修工单表';

-- 6. 跨区串货举报表 (全新表, 电商没有"串货"概念)
CREATE TABLE IF NOT EXISTS `cross_region_report` (
  `report_id` bigint NOT NULL AUTO_INCREMENT COMMENT '举报ID',
  `order_id` varchar(50) NOT NULL COMMENT '被举报订单ID',
  `dealer_id` varchar(50) NOT NULL COMMENT '被举报经销商ID',
  `ship_to_region` varchar(50) NOT NULL COMMENT '订单发货区域',
  `dealer_region` varchar(50) NOT NULL COMMENT '经销商授权区域',
  `reporter_id` varchar(50) NOT NULL COMMENT '举报人ID',
  `report_status` ENUM('待核实','已核实','无效') NOT NULL DEFAULT '待核实' COMMENT '核实状态',
  `create_time` datetime NOT NULL COMMENT '举报时间',
  PRIMARY KEY (`report_id`),
  KEY `idx_report_order_id` (`order_id`),
  KEY `idx_report_dealer_id` (`dealer_id`),
  CONSTRAINT `cross_region_report_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
  CONSTRAINT `cross_region_report_ibfk_2` FOREIGN KEY (`dealer_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='跨区串货举报表';

-- 7. 行业黑名单扩展表 (type: 经销商ID / 设备SN / 维修工)
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `type` ENUM('经销商','设备SN','维修工') NOT NULL COMMENT '黑名单类型',
  `value` varchar(200) NOT NULL COMMENT '黑名单值',
  `reason` text DEFAULT NULL COMMENT '加入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  `create_time` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `idx_extra_type_value` (`type`,`value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='行业黑名单扩展表';

SET FOREIGN_KEY_CHECKS = 1;

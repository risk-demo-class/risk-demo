-- ============================================
-- 制造业风控系统 - 业务表 DDL 初始化脚本 (7 张)
-- 场景 D: 经销商订货 / 设备保修 / 采购订单 / 售后维修
-- 数据库: mfg_risk
-- ============================================

USE mfg_risk;

-- 重置时先关外键约束 (本脚本无物理外键, 保留习惯)
SET FOREIGN_KEY_CHECKS = 0;

-- 1. 用户信息表 (经销商 / 终端用户 / 内部员工)
DROP TABLE IF EXISTS `user_info`;
CREATE TABLE `user_info` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID(经销商账号)',
    `name` VARCHAR(50) NOT NULL COMMENT '姓名/联系人',
    `role` ENUM('经销商','终端用户','内部员工') NOT NULL COMMENT '角色',
    `dealer_level` ENUM('核心经销商','授权经销商','普通经销商') DEFAULT NULL COMMENT '经销商等级',
    `region` VARCHAR(50) NOT NULL COMMENT '所属区域(省)',
    `register_at` DATETIME NOT NULL COMMENT '注册时间',
    PRIMARY KEY (`user_id`),
    INDEX `idx_user_role` (`role`),
    INDEX `idx_user_region` (`region`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 产品信息表 (制造业"商品" + 保修期)
DROP TABLE IF EXISTS `product`;
CREATE TABLE `product` (
    `product_id` VARCHAR(50) NOT NULL COMMENT '产品ID',
    `name` VARCHAR(100) NOT NULL COMMENT '产品名称',
    `model` VARCHAR(50) NOT NULL COMMENT '型号',
    `category` VARCHAR(50) NOT NULL COMMENT '品类(机床/注塑机/空压机等)',
    `msrp` DECIMAL(12,2) NOT NULL COMMENT '官方建议零售价 MSRP',
    `warranty_months` INT NOT NULL COMMENT '保修期(月)',
    PRIMARY KEY (`product_id`),
    INDEX `idx_product_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='产品信息表';

-- 3. 经销商档案表 (全新表, 电商没有"经销商"概念)
DROP TABLE IF EXISTS `dealer_info`;
CREATE TABLE `dealer_info` (
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '经销商ID',
    `dealer_name` VARCHAR(100) NOT NULL COMMENT '经销商名称',
    `region` VARCHAR(50) NOT NULL COMMENT '授权区域(省)',
    `authorized_brands` VARCHAR(200) NOT NULL COMMENT '授权品牌(逗号分隔)',
    `contract_start` DATETIME NOT NULL COMMENT '合同开始时间',
    `contract_end` DATETIME NOT NULL COMMENT '合同到期时间',
    PRIMARY KEY (`dealer_id`),
    INDEX `idx_dealer_region` (`region`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='经销商档案表';

-- 4. 经销商订货订单表 (B 端经销订单)
DROP TABLE IF EXISTS `order_info`;
CREATE TABLE `order_info` (
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '经销商ID',
    `product_id` VARCHAR(50) NOT NULL COMMENT '产品ID',
    `quantity` INT NOT NULL COMMENT '订货数量(台)',
    `unit_price` DECIMAL(12,2) NOT NULL COMMENT '成交单价',
    `total_amount` DECIMAL(14,2) NOT NULL COMMENT '订单总金额',
    `ship_to_region` VARCHAR(50) NOT NULL COMMENT '收货区域(省)',
    `create_time` DATETIME NOT NULL COMMENT '下单时间',
    PRIMARY KEY (`order_id`),
    INDEX `idx_order_dealer` (`dealer_id`),
    INDEX `idx_order_product` (`product_id`),
    INDEX `idx_order_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='经销商订货订单表';

-- 5. 设备保修记录表 (全新表, 电商没有"保修")
DROP TABLE IF EXISTS `warranty_record`;
CREATE TABLE `warranty_record` (
    `warranty_id` VARCHAR(50) NOT NULL COMMENT '保修单ID',
    `product_sn` VARCHAR(50) NOT NULL COMMENT '设备序列号 SN',
    `order_id` VARCHAR(50) NOT NULL COMMENT '关联订货订单ID',
    `issue_date` DATETIME NOT NULL COMMENT '报修时间',
    `issue_type` ENUM('质量问题','人为损坏','正常保养','以旧换新') NOT NULL COMMENT '报修类型',
    `repair_cost` DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '维修费用(元)',
    `technician_id` VARCHAR(50) NOT NULL COMMENT '维修工ID',
    `create_time` DATETIME NOT NULL COMMENT '创建时间',
    PRIMARY KEY (`warranty_id`),
    INDEX `idx_warranty_sn` (`product_sn`),
    INDEX `idx_warranty_order` (`order_id`),
    INDEX `idx_warranty_issue_date` (`issue_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备保修记录表';

-- 6. 跨区串货举报记录表 (全新表: 串货举报)
DROP TABLE IF EXISTS `cross_region_report`;
CREATE TABLE `cross_region_report` (
    `report_id` VARCHAR(50) NOT NULL COMMENT '举报ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '被举报订单ID',
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '被举报经销商ID',
    `ship_to_region` VARCHAR(50) NOT NULL COMMENT '实际发货区域',
    `dealer_region` VARCHAR(50) NOT NULL COMMENT '经销商授权区域',
    `reporter_id` VARCHAR(50) NOT NULL COMMENT '举报人(内部员工ID)',
    `create_time` DATETIME NOT NULL COMMENT '举报时间',
    PRIMARY KEY (`report_id`),
    INDEX `idx_report_order` (`order_id`),
    INDEX `idx_report_dealer` (`dealer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='跨区串货举报记录表';

-- 7. 业务黑名单扩展表 (设备SN / 经销商ID / 维修工)
DROP TABLE IF EXISTS `blacklist_extra`;
CREATE TABLE `blacklist_extra` (
    `entry_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '条目ID',
    `type` ENUM('设备SN','经销商ID','维修工') NOT NULL COMMENT '业务黑名单类型',
    `value` VARCHAR(100) NOT NULL COMMENT '黑名单值',
    `reason` VARCHAR(500) DEFAULT NULL COMMENT '加入原因',
    `expire_at` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    PRIMARY KEY (`entry_id`),
    UNIQUE INDEX `idx_bl_extra_type_value` (`type`, `value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务黑名单扩展表';

SET FOREIGN_KEY_CHECKS = 1;

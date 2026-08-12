-- ============================================================
-- 制造业风控系统 - 业务表 DDL 初始化脚本
-- 在 manufacturing_risk 数据库中创建 7 张业务表
-- 业务边界: 经销商订货 / 设备保修 / 采购订单 / 售后维修
-- ============================================================

USE manufacturing_risk;

-- 1. 用户信息表 (经销商 / 终端用户 / 内部员工)
CREATE TABLE IF NOT EXISTS `user_info` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID(经销商/终端用户/员工ID)',
    `name` VARCHAR(100) NOT NULL COMMENT '姓名/企业名',
    `role` ENUM('经销商','终端用户','内部员工') NOT NULL COMMENT '用户角色',
    `dealer_level` ENUM('一级','二级','三级') DEFAULT NULL COMMENT '经销商等级(仅经销商)',
    `region` VARCHAR(50) DEFAULT NULL COMMENT '所属区域',
    `register_at` DATETIME DEFAULT NULL COMMENT '注册时间',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户信息表';

-- 2. 产品表 (制造业"商品", 带官方价 MSRP + 保修期)
CREATE TABLE IF NOT EXISTS `product` (
    `product_id` VARCHAR(50) NOT NULL COMMENT '产品ID',
    `name` VARCHAR(100) NOT NULL COMMENT '产品名称',
    `model` VARCHAR(100) DEFAULT NULL COMMENT '型号',
    `category` VARCHAR(50) DEFAULT NULL COMMENT '产品类别',
    `msrp` DECIMAL(12,2) NOT NULL COMMENT '官方建议零售价(MSRP)',
    `warranty_months` INT NOT NULL DEFAULT 12 COMMENT '保修期(月)',
    PRIMARY KEY (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='产品表';

-- 3. 经销商档案表 (全新表, 电商版没有)
CREATE TABLE IF NOT EXISTS `dealer_info` (
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '经销商ID',
    `dealer_name` VARCHAR(100) NOT NULL COMMENT '经销商名称',
    `region` VARCHAR(50) NOT NULL COMMENT '授权区域',
    `authorized_brands` VARCHAR(200) DEFAULT NULL COMMENT '授权品牌',
    `contract_start` DATETIME DEFAULT NULL COMMENT '合同开始时间',
    `contract_end` DATETIME DEFAULT NULL COMMENT '合同结束时间',
    PRIMARY KEY (`dealer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='经销商档案表';

-- 4. 订货单表 (单产品订单: 直接挂 product_id, 无明细表)
CREATE TABLE IF NOT EXISTS `order_info` (
    `order_id` VARCHAR(50) NOT NULL COMMENT '订单ID',
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '经销商ID',
    `product_id` VARCHAR(50) NOT NULL COMMENT '产品ID',
    `quantity` INT NOT NULL DEFAULT 1 COMMENT '数量',
    `unit_price` DECIMAL(12,2) NOT NULL COMMENT '成交单价',
    `total_amount` DECIMAL(14,2) NOT NULL COMMENT '订单总金额',
    `ship_to_region` VARCHAR(50) DEFAULT NULL COMMENT '收货区域',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
    PRIMARY KEY (`order_id`),
    INDEX `idx_order_dealer_id` (`dealer_id`),
    INDEX `idx_order_create_time` (`create_time`),
    CONSTRAINT `fk_order_dealer` FOREIGN KEY (`dealer_id`) REFERENCES `dealer_info` (`dealer_id`),
    CONSTRAINT `fk_order_product` FOREIGN KEY (`product_id`) REFERENCES `product` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='经销商订货单表';

-- 5. 保修记录表 (全新表, 电商版没有 "保修" 概念)
CREATE TABLE IF NOT EXISTS `warranty_record` (
    `warranty_id` VARCHAR(50) NOT NULL COMMENT '保修单ID',
    `product_sn` VARCHAR(100) NOT NULL COMMENT '设备序列号(SN)',
    `order_id` VARCHAR(50) NOT NULL COMMENT '关联订单ID',
    `issue_date` DATETIME NOT NULL COMMENT '申请/维修时间',
    `issue_type` ENUM('保修申请','维修') NOT NULL COMMENT '单据类型: 保修申请 / 维修',
    `repair_cost` DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '维修费用(申请时为0)',
    `technician_id` VARCHAR(50) DEFAULT NULL COMMENT '维修工ID',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`warranty_id`),
    INDEX `idx_warranty_sn` (`product_sn`),
    INDEX `idx_warranty_order_id` (`order_id`),
    CONSTRAINT `fk_warranty_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备保修记录表';

-- 6. 跨区串货举报表 (全新表: 串货 = 经销商把货卖到授权区域外)
CREATE TABLE IF NOT EXISTS `cross_region_report` (
    `report_id` VARCHAR(50) NOT NULL COMMENT '举报ID',
    `order_id` VARCHAR(50) NOT NULL COMMENT '被举报订单ID',
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '被举报经销商ID',
    `ship_to_region` VARCHAR(50) DEFAULT NULL COMMENT '实际收货区域',
    `dealer_region` VARCHAR(50) DEFAULT NULL COMMENT '经销商授权区域',
    `reporter_id` VARCHAR(50) DEFAULT NULL COMMENT '举报人ID(内部员工)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '举报时间',
    PRIMARY KEY (`report_id`),
    INDEX `idx_report_order_id` (`order_id`),
    CONSTRAINT `fk_report_order` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
    CONSTRAINT `fk_report_dealer` FOREIGN KEY (`dealer_id`) REFERENCES `dealer_info` (`dealer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='跨区串货举报表';

-- 7. 业务黑名单扩展表 (业务系统自管黑名单: 设备SN / 经销商ID / 维修工)
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
    `entry_id` VARCHAR(50) NOT NULL COMMENT '黑名单条目ID',
    `type` ENUM('设备SN','经销商ID','维修工') NOT NULL COMMENT '黑名单类型',
    `value` VARCHAR(100) NOT NULL COMMENT '黑名单值(SN/经销商ID/维修工ID)',
    `reason` VARCHAR(500) DEFAULT NULL COMMENT '加入原因',
    `expire_at` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`entry_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务黑名单扩展表';

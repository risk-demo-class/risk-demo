-- 制造业设备经销商风控系统 - 业务表 DDL（第一版严格 6 张）
-- 当前连接由 scripts/init_db.py 选择；本文件不得硬编码 USE 数据库。

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `dealer` (
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '经销商ID',
    `name` VARCHAR(100) NOT NULL COMMENT '经销商名称',
    `level` ENUM('普通','核心','战略') NOT NULL DEFAULT '普通' COMMENT '经销商等级',
    `region` VARCHAR(100) NOT NULL COMMENT '授权经营区域',
    `authorized_at` DATE NOT NULL COMMENT '授权日期',
    `contract_end` DATE NOT NULL COMMENT '合同到期日',
    PRIMARY KEY (`dealer_id`),
    UNIQUE INDEX `uq_dealer_name` (`name`),
    INDEX `idx_dealer_region` (`region`),
    INDEX `idx_dealer_contract_end` (`contract_end`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备经销商';

CREATE TABLE IF NOT EXISTS `device` (
    `device_id` VARCHAR(50) NOT NULL COMMENT '设备ID',
    `sn` VARCHAR(100) NOT NULL COMMENT '设备序列号',
    `model` VARCHAR(100) NOT NULL COMMENT '设备型号',
    `batch_no` VARCHAR(50) NOT NULL COMMENT '生产批次',
    `factory_at` DATE NOT NULL COMMENT '出厂日期',
    `warranty_end` DATE NOT NULL COMMENT '保修到期日',
    `dealer_id` VARCHAR(50) DEFAULT NULL COMMENT '当前归属经销商ID',
    PRIMARY KEY (`device_id`),
    UNIQUE INDEX `uq_device_sn` (`sn`),
    INDEX `idx_device_model` (`model`),
    INDEX `idx_device_batch_no` (`batch_no`),
    INDEX `idx_device_dealer_id` (`dealer_id`),
    CONSTRAINT `fk_device_dealer` FOREIGN KEY (`dealer_id`) REFERENCES `dealer` (`dealer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='制造设备';

CREATE TABLE IF NOT EXISTS `purchase_order` (
    `po_id` VARCHAR(50) NOT NULL COMMENT '采购订单ID',
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '经销商ID',
    `total_amount` DECIMAL(15,2) NOT NULL COMMENT '采购总金额',
    `items` JSON NOT NULL COMMENT '采购设备明细(JSON)',
    `ship_to` VARCHAR(200) NOT NULL COMMENT '交付区域或地址',
    `payment_term` ENUM('预付','账期30天','账期60天') NOT NULL COMMENT '付款条件',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '采购单创建时间',
    PRIMARY KEY (`po_id`),
    INDEX `idx_purchase_order_dealer_id` (`dealer_id`),
    INDEX `idx_purchase_order_create_time` (`create_time`),
    INDEX `idx_purchase_order_total_amount` (`total_amount`),
    CONSTRAINT `fk_purchase_order_dealer` FOREIGN KEY (`dealer_id`) REFERENCES `dealer` (`dealer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='经销商采购订单';

CREATE TABLE IF NOT EXISTS `warranty_claim` (
    `claim_id` VARCHAR(50) NOT NULL COMMENT '保修申请ID',
    `device_id` VARCHAR(50) NOT NULL COMMENT '设备ID',
    `dealer_id` VARCHAR(50) NOT NULL COMMENT '申请经销商ID',
    `fault_desc` TEXT NOT NULL COMMENT '故障描述',
    `claim_amount` DECIMAL(15,2) NOT NULL COMMENT '索赔金额',
    `photos` JSON DEFAULT NULL COMMENT '凭证照片(JSON)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '申请时间',
    PRIMARY KEY (`claim_id`),
    INDEX `idx_warranty_claim_device_id` (`device_id`),
    INDEX `idx_warranty_claim_dealer_id` (`dealer_id`),
    INDEX `idx_warranty_claim_create_time` (`create_time`),
    CONSTRAINT `fk_warranty_claim_device` FOREIGN KEY (`device_id`) REFERENCES `device` (`device_id`),
    CONSTRAINT `fk_warranty_claim_dealer` FOREIGN KEY (`dealer_id`) REFERENCES `dealer` (`dealer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备保修申请';

CREATE TABLE IF NOT EXISTS `cross_region_report` (
    `report_id` VARCHAR(50) NOT NULL COMMENT '串货举报ID',
    `device_id` VARCHAR(50) NOT NULL COMMENT '设备ID',
    `expected_region` VARCHAR(100) NOT NULL COMMENT '授权区域',
    `actual_region` VARCHAR(100) NOT NULL COMMENT '实际发现区域',
    `reporter_id` VARCHAR(50) NOT NULL COMMENT '举报人或来源ID',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '举报时间',
    PRIMARY KEY (`report_id`),
    INDEX `idx_cross_region_report_device_id` (`device_id`),
    INDEX `idx_cross_region_report_regions` (`expected_region`, `actual_region`),
    INDEX `idx_cross_region_report_create_time` (`create_time`),
    CONSTRAINT `fk_cross_region_report_device` FOREIGN KEY (`device_id`) REFERENCES `device` (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='跨区域串货举报';

CREATE TABLE IF NOT EXISTS `blacklist_extra` (
    `entry_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '扩展黑名单ID',
    `type` ENUM('统一社会信用代码','营业执照','银行账户','联系人手机号') NOT NULL COMMENT '扩展标识类型',
    `value` VARCHAR(200) NOT NULL COMMENT '扩展标识值',
    `reason` TEXT NOT NULL COMMENT '加入原因',
    `expire_at` DATETIME DEFAULT NULL COMMENT '到期时间(NULL=永久)',
    PRIMARY KEY (`entry_id`),
    UNIQUE INDEX `uq_blacklist_extra_type_value` (`type`, `value`),
    INDEX `idx_blacklist_extra_expire_at` (`expire_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='经销商扩展黑名单标识';

SET FOREIGN_KEY_CHECKS = 1;

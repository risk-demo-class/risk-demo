-- ============================================
-- 医疗风控系统 - 业务表 DDL 初始化脚本
-- 创建 8 张医疗业务表 (按依赖顺序)
-- 4 大业务场景: 医保结算 / 处方审核 / 挂号黄牛 / 药品代购
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 清空重建 (可重复执行)
DROP TABLE IF EXISTS `blacklist_extra`;
DROP TABLE IF EXISTS `drug_order`;
DROP TABLE IF EXISTS `insurance_claim`;
DROP TABLE IF EXISTS `prescription`;
DROP TABLE IF EXISTS `appointment`;
DROP TABLE IF EXISTS `doctor`;
DROP TABLE IF EXISTS `hospital`;
DROP TABLE IF EXISTS `user_info`;

-- ============================
-- 第一层: 基础档案表 (无外键依赖)
-- ============================

-- 1. 患者档案表
CREATE TABLE `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '患者ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `id_card_hash` varchar(64) NOT NULL COMMENT '身份证号哈希(SHA256, 脱敏存储)',
  `medical_card_no` varchar(50) NOT NULL COMMENT '医保卡号',
  `phone` varchar(20) DEFAULT NULL COMMENT '手机号',
  `insurance_type` enum('职工医保','居民医保','新农合','自费') NOT NULL DEFAULT '居民医保' COMMENT '参保类型',
  `insured_province` varchar(50) DEFAULT NULL COMMENT '参保地省份',
  `register_at` datetime DEFAULT NULL COMMENT '建档时间',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`user_id`),
  KEY `idx_user_medical_card` (`medical_card_no`),
  KEY `idx_user_id_card_hash` (`id_card_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='患者档案表';

-- 2. 医院档案表
CREATE TABLE `hospital` (
  `hospital_id` varchar(50) NOT NULL COMMENT '医院编码',
  `name` varchar(100) NOT NULL COMMENT '医院名称',
  `level` enum('三甲','三乙','二甲','二乙','社区') NOT NULL DEFAULT '二甲' COMMENT '医院等级',
  `province` varchar(50) NOT NULL COMMENT '省份',
  `city` varchar(50) NOT NULL COMMENT '城市',
  `is_insured` int DEFAULT 1 COMMENT '是否医保定点(1=是,0=否)',
  PRIMARY KEY (`hospital_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='医院档案表';

-- ============================
-- 第二层: 依赖医院档案
-- ============================

-- 3. 医生档案表
CREATE TABLE `doctor` (
  `doctor_id` varchar(50) NOT NULL COMMENT '医生ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `hospital_id` varchar(50) NOT NULL COMMENT '所属医院编码',
  `department` varchar(50) NOT NULL COMMENT '科室',
  `title` enum('主任医师','副主任医师','主治医师','住院医师') NOT NULL DEFAULT '主治医师' COMMENT '职称',
  `license_no` varchar(50) NOT NULL COMMENT '执业证号',
  PRIMARY KEY (`doctor_id`),
  KEY `idx_doctor_hospital` (`hospital_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='医生档案表';

-- ============================
-- 第三层: 诊疗流水表 (依赖患者/医院/医生)
-- ============================

-- 4. 挂号记录表 (电商"订单" → 医疗"挂号")
CREATE TABLE `appointment` (
  `appt_id` varchar(50) NOT NULL COMMENT '挂号ID',
  `user_id` varchar(50) NOT NULL COMMENT '患者ID',
  `hospital_id` varchar(50) NOT NULL COMMENT '医院编码',
  `department` varchar(50) NOT NULL COMMENT '挂号科室',
  `doctor_id` varchar(50) DEFAULT NULL COMMENT '医生ID',
  `phone` varchar(20) DEFAULT NULL COMMENT '预约手机号(黄牛识别用)',
  `appt_time` datetime DEFAULT NULL COMMENT '预约就诊时间',
  `pay_amount` decimal(10,2) DEFAULT 0 COMMENT '挂号费',
  `appt_status` enum('已预约','已就诊','已取消') NOT NULL DEFAULT '已预约' COMMENT '挂号状态',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`appt_id`),
  KEY `idx_appt_user_id` (`user_id`),
  KEY `idx_appt_hospital_id` (`hospital_id`),
  KEY `idx_appt_phone` (`phone`),
  KEY `idx_appt_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='挂号记录表';

-- 5. 处方单表 (处方审核场景核心)
CREATE TABLE `prescription` (
  `rx_id` varchar(50) NOT NULL COMMENT '处方ID',
  `doctor_id` varchar(50) NOT NULL COMMENT '开方医生ID',
  `user_id` varchar(50) NOT NULL COMMENT '患者ID',
  `hospital_id` varchar(50) NOT NULL COMMENT '医院编码',
  `diagnosis_code` varchar(20) DEFAULT NULL COMMENT '诊断编码(ICD-10)',
  `items` text COMMENT '药品明细 JSON, 如 [{"drug": "阿普唑仑片", "quantity": 20}]',
  `item_count` int DEFAULT 1 COMMENT '处方药品行数',
  `total_quantity` int DEFAULT 0 COMMENT '药品总数量(片/盒)',
  `total_amount` decimal(10,2) DEFAULT 0 COMMENT '处方总金额',
  `is_insured` int DEFAULT 1 COMMENT '是否医保处方(1=是,0=否)',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '开方时间',
  PRIMARY KEY (`rx_id`),
  KEY `idx_rx_user_id` (`user_id`),
  KEY `idx_rx_doctor_id` (`doctor_id`),
  KEY `idx_rx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='处方单表';

-- 6. 医保结算表 (强监管, 医保结算场景核心)
CREATE TABLE `insurance_claim` (
  `claim_id` varchar(50) NOT NULL COMMENT '结算单ID',
  `user_id` varchar(50) NOT NULL COMMENT '患者ID',
  `hospital_id` varchar(50) NOT NULL COMMENT '结算医院编码',
  `total_amount` decimal(12,2) DEFAULT 0 COMMENT '医疗总费用',
  `insured_amount` decimal(12,2) DEFAULT 0 COMMENT '医保报销金额',
  `claim_status` enum('待审核','已结算','已拒绝') NOT NULL DEFAULT '待审核' COMMENT '结算状态',
  `submit_at` datetime DEFAULT NULL COMMENT '提交结算时间',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`claim_id`),
  KEY `idx_claim_user_id` (`user_id`),
  KEY `idx_claim_hospital_id` (`hospital_id`),
  KEY `idx_claim_submit_at` (`submit_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='医保结算表';

-- 7. 药品订单表 (处方流转后的"商品"环节, 药品代购场景核心)
CREATE TABLE `drug_order` (
  `drug_order_id` varchar(50) NOT NULL COMMENT '药品订单ID',
  `rx_id` varchar(50) DEFAULT NULL COMMENT '关联处方ID(OTC 可为空)',
  `user_id` varchar(50) NOT NULL COMMENT '下单患者ID',
  `drug_name` varchar(100) NOT NULL COMMENT '药品名称',
  `quantity` int DEFAULT 1 COMMENT '购买数量',
  `drug_category` enum('处方药','OTC','麻醉药品','精神药品') NOT NULL DEFAULT '处方药' COMMENT '药品类别',
  `is_otc` int DEFAULT 0 COMMENT '是否 OTC(1=是,0=否)',
  `receiver_name` varchar(50) DEFAULT NULL COMMENT '收件人姓名(代购识别: !=患者本人)',
  `total_amount` decimal(10,2) DEFAULT 0 COMMENT '订单金额',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  PRIMARY KEY (`drug_order_id`),
  KEY `idx_drug_order_user_id` (`user_id`),
  KEY `idx_drug_order_rx_id` (`rx_id`),
  KEY `idx_drug_order_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='药品订单表';

-- ============================
-- 第四层: 行业黑名单登记簿
-- ============================

-- 8. 行业黑名单登记表 (业务侧登记, 风控撞黑走 risk_blacklist)
CREATE TABLE `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '登记ID',
  `type` enum('医保卡号','身份证号','医生执业证','医院编码') NOT NULL COMMENT '黑名单类型',
  `value` varchar(200) NOT NULL COMMENT '黑名单值',
  `reason` text COMMENT '登记原因',
  `expire_at` datetime DEFAULT NULL COMMENT '失效时间(NULL=永久)',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '登记时间',
  PRIMARY KEY (`entry_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='行业黑名单登记表';

SET FOREIGN_KEY_CHECKS = 1;

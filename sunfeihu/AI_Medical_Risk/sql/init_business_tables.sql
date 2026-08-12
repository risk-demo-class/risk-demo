-- ============================================
-- 医疗风控系统 - 医疗业务表 DDL (8 张, P0 新建)
-- 严格对齐 app/models_business.py (PRD §7.1 / §7.3 / §7.4)
-- 约束: 主键 / 外键 / 唯一约束 / DECIMAL 金额 / 索引
-- 全部 IF NOT EXISTS, 可重复执行 (幂等)
-- 建表顺序保证外键引用表先创建
-- ============================================

-- 1. 患者主档
CREATE TABLE IF NOT EXISTS `medical_patient` (
    `patient_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `name_masked` VARCHAR(50) NOT NULL COMMENT '脱敏姓名(合成)',
    `id_card_hash` VARCHAR(64) NOT NULL COMMENT '身份证摘要(SHA-256,合成)',
    `insurance_card_hash` VARCHAR(64) NOT NULL COMMENT '医保卡摘要(SHA-256,合成)',
    `phone_hash` VARCHAR(64) NOT NULL COMMENT '手机号摘要(SHA-256,合成)',
    `gender` ENUM('男','女','未知') NOT NULL DEFAULT '未知' COMMENT '性别',
    `birth_year` INT NOT NULL COMMENT '出生年份',
    `insured_province` VARCHAR(50) NOT NULL COMMENT '参保省份',
    `account_created_at` DATETIME NOT NULL COMMENT '账户创建时间',
    `real_name_status` ENUM('已实名','未实名') NOT NULL DEFAULT '已实名' COMMENT '实名状态',
    PRIMARY KEY (`patient_id`),
    UNIQUE KEY `uniq_patient_id_card_hash` (`id_card_hash`),
    UNIQUE KEY `uniq_patient_ins_card_hash` (`insurance_card_hash`),
    UNIQUE KEY `uniq_patient_phone_hash` (`phone_hash`),
    KEY `idx_patient_province` (`insured_province`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='患者主档';

-- 2. 医疗机构档案
CREATE TABLE IF NOT EXISTS `medical_hospital` (
    `hospital_id` VARCHAR(50) NOT NULL COMMENT '医疗机构ID',
    `hospital_name` VARCHAR(100) NOT NULL COMMENT '机构名称(合成)',
    `province` VARCHAR(50) NOT NULL COMMENT '省份',
    `city` VARCHAR(50) NOT NULL COMMENT '城市',
    `hospital_level` ENUM('三级','二级','一级','未定级') NOT NULL DEFAULT '三级' COMMENT '医院等级',
    `hospital_type` VARCHAR(50) NOT NULL COMMENT '机构类型(综合医院/专科/中医...)',
    `insurance_designated` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否医保定点',
    `status` ENUM('正常','异常','停用') NOT NULL DEFAULT '正常' COMMENT '机构状态',
    PRIMARY KEY (`hospital_id`),
    KEY `idx_hospital_province` (`province`),
    KEY `idx_hospital_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='医疗机构档案';

-- 3. 医生档案
CREATE TABLE IF NOT EXISTS `medical_doctor` (
    `doctor_id` VARCHAR(50) NOT NULL COMMENT '医生ID',
    `doctor_name_masked` VARCHAR(50) NOT NULL COMMENT '脱敏姓名(合成)',
    `hospital_id` VARCHAR(50) NOT NULL COMMENT '所属医院ID',
    `department` VARCHAR(50) NOT NULL COMMENT '科室',
    `professional_title` VARCHAR(50) NOT NULL COMMENT '职称',
    `license_status` ENUM('有效','异常','注销','暂停') NOT NULL DEFAULT '有效' COMMENT '执业状态(异常触发 MR014)',
    `practice_start_date` DATE NOT NULL COMMENT '执业起始日期',
    `status` ENUM('在职','离职','异常') NOT NULL DEFAULT '在职' COMMENT '医生状态',
    PRIMARY KEY (`doctor_id`),
    KEY `idx_doctor_hospital` (`hospital_id`),
    KEY `idx_doctor_department` (`department`),
    KEY `idx_doctor_license` (`license_status`),
    CONSTRAINT `fk_doctor_hospital` FOREIGN KEY (`hospital_id`) REFERENCES `medical_hospital` (`hospital_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='医生档案';

-- 4. 挂号记录
CREATE TABLE IF NOT EXISTS `medical_registration` (
    `registration_id` VARCHAR(50) NOT NULL COMMENT '挂号ID',
    `patient_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `hospital_id` VARCHAR(50) NOT NULL COMMENT '医院ID',
    `doctor_id` VARCHAR(50) NOT NULL COMMENT '医生ID',
    `department` VARCHAR(50) NOT NULL COMMENT '科室',
    `visit_date` DATE NOT NULL COMMENT '就诊日期',
    `register_channel` ENUM('窗口','微信','APP','自助机','电话') NOT NULL DEFAULT '微信' COMMENT '挂号渠道',
    `device_id_hash` VARCHAR(64) NOT NULL COMMENT '设备指纹摘要',
    `status` ENUM('已挂号','已退号','已完成') NOT NULL DEFAULT '已挂号' COMMENT '挂号状态',
    `register_at` DATETIME NOT NULL COMMENT '挂号时间',
    `cancel_at` DATETIME DEFAULT NULL COMMENT '退号时间(NULL=未退号)',
    PRIMARY KEY (`registration_id`),
    KEY `idx_reg_patient` (`patient_id`),
    KEY `idx_reg_hospital` (`hospital_id`),
    KEY `idx_reg_doctor` (`doctor_id`),
    KEY `idx_reg_status` (`status`),
    KEY `idx_reg_device` (`device_id_hash`),
    KEY `idx_reg_register_at` (`register_at`),
    CONSTRAINT `fk_reg_patient` FOREIGN KEY (`patient_id`) REFERENCES `medical_patient` (`patient_id`),
    CONSTRAINT `fk_reg_hospital` FOREIGN KEY (`hospital_id`) REFERENCES `medical_hospital` (`hospital_id`),
    CONSTRAINT `fk_reg_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `medical_doctor` (`doctor_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='挂号记录';

-- 5. 处方主表
CREATE TABLE IF NOT EXISTS `medical_prescription` (
    `prescription_id` VARCHAR(50) NOT NULL COMMENT '处方ID',
    `patient_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `doctor_id` VARCHAR(50) NOT NULL COMMENT '医生ID',
    `hospital_id` VARCHAR(50) NOT NULL COMMENT '医院ID',
    `registration_id` VARCHAR(50) DEFAULT NULL COMMENT '关联挂号ID(可空)',
    `prescription_type` ENUM('门诊','急诊','住院') NOT NULL DEFAULT '门诊' COMMENT '处方类型',
    `total_amount` DECIMAL(12,2) NOT NULL COMMENT '处方总金额',
    `drug_count` INT NOT NULL COMMENT '药品种数',
    `issued_at` DATETIME NOT NULL COMMENT '开方时间',
    `status` ENUM('有效','作废') NOT NULL DEFAULT '有效' COMMENT '处方状态',
    PRIMARY KEY (`prescription_id`),
    KEY `idx_rx_patient` (`patient_id`),
    KEY `idx_rx_doctor` (`doctor_id`),
    KEY `idx_rx_hospital` (`hospital_id`),
    KEY `idx_rx_registration` (`registration_id`),
    KEY `idx_rx_patient_issued` (`patient_id`, `issued_at`),
    KEY `idx_rx_doctor_issued` (`doctor_id`, `issued_at`),
    KEY `idx_rx_status` (`status`),
    CONSTRAINT `fk_rx_patient` FOREIGN KEY (`patient_id`) REFERENCES `medical_patient` (`patient_id`),
    CONSTRAINT `fk_rx_doctor` FOREIGN KEY (`doctor_id`) REFERENCES `medical_doctor` (`doctor_id`),
    CONSTRAINT `fk_rx_hospital` FOREIGN KEY (`hospital_id`) REFERENCES `medical_hospital` (`hospital_id`),
    CONSTRAINT `fk_rx_registration` FOREIGN KEY (`registration_id`) REFERENCES `medical_registration` (`registration_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='处方主表';

-- 6. 处方药品明细
CREATE TABLE IF NOT EXISTS `medical_prescription_item` (
    `item_id` VARCHAR(50) NOT NULL COMMENT '明细ID',
    `prescription_id` VARCHAR(50) NOT NULL COMMENT '处方ID',
    `drug_code` VARCHAR(50) NOT NULL COMMENT '药品编码(合成)',
    `drug_name` VARCHAR(100) NOT NULL COMMENT '药品名称(合成)',
    `drug_category` VARCHAR(50) NOT NULL COMMENT '药品分类(同类药归并)',
    `unit_price` DECIMAL(10,2) NOT NULL COMMENT '单价',
    `quantity` INT NOT NULL COMMENT '数量',
    `days_supply` INT NOT NULL COMMENT '供药天数',
    `is_controlled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否特殊管理药品',
    `is_high_value` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否高价药',
    PRIMARY KEY (`item_id`),
    KEY `idx_rx_item_prescription` (`prescription_id`),
    KEY `idx_rx_item_category` (`drug_category`),
    KEY `idx_rx_item_controlled` (`is_controlled`),
    CONSTRAINT `fk_rx_item_prescription` FOREIGN KEY (`prescription_id`) REFERENCES `medical_prescription` (`prescription_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='处方药品明细';

-- 7. 医保结算记录
CREATE TABLE IF NOT EXISTS `medical_insurance_claim` (
    `claim_id` VARCHAR(50) NOT NULL COMMENT '结算ID',
    `patient_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `hospital_id` VARCHAR(50) NOT NULL COMMENT '医院ID',
    `prescription_id` VARCHAR(50) DEFAULT NULL COMMENT '关联处方ID(可空)',
    `total_amount` DECIMAL(12,2) NOT NULL COMMENT '结算总额',
    `insurance_amount` DECIMAL(12,2) NOT NULL COMMENT '医保支付金额',
    `self_pay_amount` DECIMAL(12,2) NOT NULL COMMENT '自费金额',
    `claim_type` ENUM('门诊','住院','异地就医','大病') NOT NULL DEFAULT '门诊' COMMENT '结算类型',
    `visit_province` VARCHAR(50) NOT NULL COMMENT '就医省份',
    `claim_at` DATETIME NOT NULL COMMENT '结算时间',
    `status` ENUM('已申报','已结算','已拒付') NOT NULL DEFAULT '已结算' COMMENT '结算状态',
    PRIMARY KEY (`claim_id`),
    KEY `idx_claim_patient` (`patient_id`),
    KEY `idx_claim_hospital` (`hospital_id`),
    KEY `idx_claim_prescription` (`prescription_id`),
    KEY `idx_claim_patient_at` (`patient_id`, `claim_at`),
    KEY `idx_claim_hospital_at` (`hospital_id`, `claim_at`),
    KEY `idx_claim_status` (`status`),
    CONSTRAINT `fk_claim_patient` FOREIGN KEY (`patient_id`) REFERENCES `medical_patient` (`patient_id`),
    CONSTRAINT `fk_claim_hospital` FOREIGN KEY (`hospital_id`) REFERENCES `medical_hospital` (`hospital_id`),
    CONSTRAINT `fk_claim_prescription` FOREIGN KEY (`prescription_id`) REFERENCES `medical_prescription` (`prescription_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='医保结算记录';

-- 8. 患者设备关联
CREATE TABLE IF NOT EXISTS `medical_patient_device` (
    `relation_id` VARCHAR(50) NOT NULL COMMENT '关联ID',
    `patient_id` VARCHAR(50) NOT NULL COMMENT '患者ID',
    `device_id_hash` VARCHAR(64) NOT NULL COMMENT '设备指纹摘要',
    `first_seen_at` DATETIME NOT NULL COMMENT '首次出现时间',
    `last_seen_at` DATETIME NOT NULL COMMENT '最近出现时间',
    `use_count` INT NOT NULL DEFAULT 0 COMMENT '使用次数',
    PRIMARY KEY (`relation_id`),
    KEY `idx_device_patient` (`patient_id`),
    KEY `idx_device_hash` (`device_id_hash`),
    UNIQUE KEY `uniq_patient_device` (`patient_id`, `device_id_hash`),
    CONSTRAINT `fk_device_patient` FOREIGN KEY (`patient_id`) REFERENCES `medical_patient` (`patient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='患者设备关联';

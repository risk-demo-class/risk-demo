-- ============================================
-- 银行信贷风控系统 - 业务表 DDL 初始化脚本
-- 创建 17 张银行业务表 (按外键依赖顺序)
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础维度表 (无外键依赖)
-- ============================

-- 1. 客户信息表
CREATE TABLE IF NOT EXISTS `customer_info` (
  `customer_id` varchar(50) NOT NULL COMMENT '客户ID',
  `customer_name` varchar(50) NOT NULL COMMENT '客户姓名',
  `customer_phone` varchar(50) NOT NULL COMMENT '手机号',
  `id_card_no` varchar(50) NOT NULL COMMENT '身份证号',
  `status` varchar(20) NOT NULL COMMENT '状态(正常/冻结)',
  PRIMARY KEY (`customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='客户信息表';

-- 2. 地区表
CREATE TABLE IF NOT EXISTS `region` (
  `province` varchar(20) NOT NULL COMMENT '省',
  `city` varchar(20) NOT NULL COMMENT '市',
  `district` varchar(20) NOT NULL COMMENT '区',
  PRIMARY KEY (`province`,`city`,`district`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='地区表';

-- 3. 贷款产品类别表
CREATE TABLE IF NOT EXISTS `loan_product_category` (
  `product_category` varchar(20) NOT NULL COMMENT '贷款产品类别',
  PRIMARY KEY (`product_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款产品类别表';

-- 4. 贷款状态表
CREATE TABLE IF NOT EXISTS `loan_status` (
  `loan_status` varchar(20) NOT NULL COMMENT '贷款状态',
  `status_code` int DEFAULT NULL COMMENT '状态码',
  PRIMARY KEY (`loan_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款状态表';

-- 5. 银行网点表
CREATE TABLE IF NOT EXISTS `bank_branch` (
  `branch_name` varchar(50) NOT NULL COMMENT '银行网点名称',
  PRIMARY KEY (`branch_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行网点表';

-- 6. 还款状态表
CREATE TABLE IF NOT EXISTS `repayment_status` (
  `repayment_status` varchar(20) NOT NULL COMMENT '还款状态',
  `is_normal` tinyint(1) NOT NULL COMMENT '是否正常',
  `is_overdue` tinyint(1) NOT NULL COMMENT '是否逾期',
  `is_closed` tinyint(1) NOT NULL COMMENT '是否结清',
  `status_code` int DEFAULT NULL COMMENT '状态码',
  PRIMARY KEY (`repayment_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='还款状态表';

-- ============================
-- 第二层: 依赖基础维度表
-- ============================

-- 7. 联系信息表
CREATE TABLE IF NOT EXISTS `contact_info` (
  `contact_id` varchar(50) NOT NULL COMMENT '联系信息ID',
  `customer_id` varchar(50) NOT NULL COMMENT '客户ID',
  `contact_person` varchar(50) NOT NULL COMMENT '联系人姓名',
  `contact_phone` varchar(50) NOT NULL COMMENT '联系电话',
  `contact_province` varchar(50) NOT NULL COMMENT '省',
  `contact_city` varchar(50) NOT NULL COMMENT '市',
  `contact_district` varchar(50) NOT NULL COMMENT '区',
  `contact_address` varchar(50) NOT NULL COMMENT '详细地址',
  `emergency_name` varchar(50) DEFAULT NULL COMMENT '紧急联系人姓名',
  `emergency_phone` varchar(50) DEFAULT NULL COMMENT '紧急联系人电话',
  PRIMARY KEY (`contact_id`),
  UNIQUE KEY `customer_id` (`customer_id`,`contact_person`,`contact_phone`,`contact_province`,`contact_city`,`contact_district`,`contact_address`),
  KEY `contact_province` (`contact_province`,`contact_city`,`contact_district`),
  CONSTRAINT `contact_info_ibfk_1` FOREIGN KEY (`customer_id`) REFERENCES `customer_info` (`customer_id`),
  CONSTRAINT `contact_info_ibfk_2` FOREIGN KEY (`contact_province`, `contact_city`, `contact_district`) REFERENCES `region` (`province`, `city`, `district`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='联系信息表';

-- 8. 贷款产品表
CREATE TABLE IF NOT EXISTS `loan_product` (
  `product_id` varchar(50) NOT NULL COMMENT '产品ID',
  `product_name` varchar(100) NOT NULL COMMENT '产品名称',
  `annual_rate` decimal(5,4) NOT NULL COMMENT '年利率',
  `max_term_month` int NOT NULL COMMENT '最长期限(月)',
  `max_amount` decimal(12,2) NOT NULL COMMENT '额度上限',
  `product_category` varchar(20) NOT NULL COMMENT '贷款产品类别',
  PRIMARY KEY (`product_id`),
  KEY `product_category` (`product_category`),
  CONSTRAINT `loan_product_ibfk_1` FOREIGN KEY (`product_category`) REFERENCES `loan_product_category` (`product_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款产品表';

-- 9. 逾期原因表
CREATE TABLE IF NOT EXISTS `overdue_reason` (
  `overdue_reason` varchar(100) NOT NULL COMMENT '逾期原因',
  `product_category` varchar(20) DEFAULT NULL COMMENT '贷款产品类别',
  PRIMARY KEY (`overdue_reason`),
  KEY `product_category` (`product_category`),
  CONSTRAINT `overdue_reason_ibfk_1` FOREIGN KEY (`product_category`) REFERENCES `loan_product_category` (`product_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='逾期原因表';

-- ============================
-- 第三层: 核心业务表
-- ============================

-- 10. 贷款申请表
CREATE TABLE IF NOT EXISTS `loan_application` (
  `loan_id` varchar(50) NOT NULL COMMENT '贷款申请ID',
  `apply_time` timestamp NOT NULL COMMENT '申请时间',
  `approve_time` timestamp NULL DEFAULT NULL COMMENT '审批时间',
  `loan_time` timestamp NULL DEFAULT NULL COMMENT '放款时间',
  `mature_time` timestamp NULL DEFAULT NULL COMMENT '到期时间',
  `customer_id` varchar(50) NOT NULL COMMENT '客户ID',
  `contact_id` varchar(50) NOT NULL COMMENT '联系信息ID',
  `product_id` varchar(50) NOT NULL COMMENT '贷款产品ID',
  `loan_status` varchar(20) NOT NULL COMMENT '贷款状态',
  `loan_amount` decimal(12,2) NOT NULL COMMENT '申请金额',
  `loan_term_month` int NOT NULL COMMENT '期限(月)',
  `installment_count` int NOT NULL COMMENT '分期期数',
  `annual_income` decimal(12,2) NOT NULL COMMENT '年收入',
  `debt_amount` decimal(12,2) NOT NULL COMMENT '现有负债',
  `device_id` varchar(50) NOT NULL COMMENT '设备ID',
  `apply_ip_province` varchar(50) NOT NULL COMMENT '申请IP省份',
  PRIMARY KEY (`loan_id`),
  KEY `customer_id` (`customer_id`),
  KEY `contact_id` (`contact_id`),
  KEY `product_id` (`product_id`),
  KEY `loan_status` (`loan_status`),
  CONSTRAINT `loan_application_ibfk_1` FOREIGN KEY (`customer_id`) REFERENCES `customer_info` (`customer_id`),
  CONSTRAINT `loan_application_ibfk_2` FOREIGN KEY (`contact_id`) REFERENCES `contact_info` (`contact_id`),
  CONSTRAINT `loan_application_ibfk_3` FOREIGN KEY (`product_id`) REFERENCES `loan_product` (`product_id`),
  CONSTRAINT `loan_application_ibfk_4` FOREIGN KEY (`loan_status`) REFERENCES `loan_status` (`loan_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款申请表';

-- 11. 还款记录表
CREATE TABLE IF NOT EXISTS `repayment_record` (
  `repayment_id` varchar(50) NOT NULL COMMENT '还款记录ID',
  `create_time` timestamp NOT NULL COMMENT '还款时间',
  `repaid_time` timestamp NULL DEFAULT NULL COMMENT '实还时间',
  `repayment_amount` decimal(12,2) NOT NULL COMMENT '还款金额',
  `repayment_category` enum('正常还款','提前还款','逾期还款') DEFAULT NULL COMMENT '还款类别',
  PRIMARY KEY (`repayment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='还款记录表';

-- 12. 分期明细表
CREATE TABLE IF NOT EXISTS `loan_installment` (
  `installment_id` varchar(50) NOT NULL COMMENT '分期明细ID',
  `loan_id` varchar(50) NOT NULL COMMENT '贷款申请ID',
  `product_id` varchar(50) NOT NULL COMMENT '贷款产品ID',
  `installment_no` int NOT NULL COMMENT '期数序号',
  `due_amount` decimal(12,2) NOT NULL COMMENT '应还金额',
  `paid_amount` decimal(12,2) DEFAULT '0.00' COMMENT '实还金额',
  `due_date` timestamp NOT NULL COMMENT '应还日期',
  `paid_date` timestamp NULL DEFAULT NULL COMMENT '实还日期',
  PRIMARY KEY (`installment_id`),
  KEY `loan_id` (`loan_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `loan_installment_ibfk_1` FOREIGN KEY (`loan_id`) REFERENCES `loan_application` (`loan_id`),
  CONSTRAINT `loan_installment_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `loan_product` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='分期明细表';

-- ============================
-- 第四层: 关联表和明细关联
-- ============================

-- 13. 贷款与还款关联表
CREATE TABLE IF NOT EXISTS `loan_repayment_rel` (
  `loan_id` varchar(50) NOT NULL COMMENT '贷款申请ID',
  `repayment_id` varchar(50) NOT NULL COMMENT '还款记录ID',
  PRIMARY KEY (`loan_id`,`repayment_id`),
  KEY `repayment_id` (`repayment_id`),
  CONSTRAINT `loan_repayment_rel_ibfk_1` FOREIGN KEY (`loan_id`) REFERENCES `loan_application` (`loan_id`),
  CONSTRAINT `loan_repayment_rel_ibfk_2` FOREIGN KEY (`repayment_id`) REFERENCES `repayment_record` (`repayment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='贷款与还款关联表';

-- 14. 投诉内容对照表
CREATE TABLE IF NOT EXISTS `complaint_content` (
  `complaint_status` varchar(20) NOT NULL COMMENT '投诉类型',
  `complaint_content` varchar(100) NOT NULL COMMENT '投诉内容',
  PRIMARY KEY (`complaint_status`,`complaint_content`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投诉内容对照表';

-- 15. 投诉记录表
CREATE TABLE IF NOT EXISTS `complaint_record` (
  `record_id` bigint NOT NULL AUTO_INCREMENT COMMENT '投诉记录ID',
  `customer_id` varchar(50) NOT NULL COMMENT '客户ID',
  `loan_id` varchar(50) NOT NULL COMMENT '贷款申请ID',
  `complaint_content` varchar(500) NOT NULL COMMENT '投诉内容',
  `complaint_time` timestamp NOT NULL COMMENT '投诉时间',
  PRIMARY KEY (`record_id`),
  KEY `customer_id` (`customer_id`),
  KEY `loan_id` (`loan_id`),
  CONSTRAINT `complaint_record_ibfk_1` FOREIGN KEY (`customer_id`) REFERENCES `customer_info` (`customer_id`),
  CONSTRAINT `complaint_record_ibfk_2` FOREIGN KEY (`loan_id`) REFERENCES `loan_application` (`loan_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投诉记录表';

-- ============================
-- 第五层: 逾期相关
-- ============================

-- 16. 逾期记录表
CREATE TABLE IF NOT EXISTS `overdue_record` (
  `overdue_id` varchar(50) NOT NULL COMMENT '逾期记录ID',
  `create_time` timestamp NOT NULL COMMENT '创建时间',
  `complete_time` timestamp NULL DEFAULT NULL COMMENT '结清时间',
  `installment_id` varchar(50) NOT NULL COMMENT '分期明细ID',
  `overdue_amount` decimal(12,2) DEFAULT '0.00' COMMENT '逾期金额',
  `overdue_days` int NOT NULL COMMENT '逾期天数',
  `overdue_reason` varchar(500) NOT NULL COMMENT '逾期原因',
  `overdue_status` varchar(20) NOT NULL COMMENT '逾期状态',
  `contact_id` varchar(50) NOT NULL COMMENT '联系信息ID',
  PRIMARY KEY (`overdue_id`),
  KEY `installment_id` (`installment_id`),
  KEY `overdue_status` (`overdue_status`),
  KEY `contact_id` (`contact_id`),
  CONSTRAINT `overdue_record_ibfk_1` FOREIGN KEY (`installment_id`) REFERENCES `loan_installment` (`installment_id`),
  CONSTRAINT `overdue_record_ibfk_2` FOREIGN KEY (`overdue_status`) REFERENCES `repayment_status` (`repayment_status`),
  CONSTRAINT `overdue_record_ibfk_3` FOREIGN KEY (`contact_id`) REFERENCES `contact_info` (`contact_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='逾期记录表';

-- 17. 逾期与还款关联表
CREATE TABLE IF NOT EXISTS `overdue_repayment_rel` (
  `overdue_id` varchar(50) NOT NULL COMMENT '逾期记录ID',
  `repayment_id` varchar(50) NOT NULL COMMENT '还款记录ID',
  PRIMARY KEY (`overdue_id`,`repayment_id`),
  KEY `repayment_id` (`repayment_id`),
  CONSTRAINT `overdue_repayment_rel_ibfk_1` FOREIGN KEY (`overdue_id`) REFERENCES `overdue_record` (`overdue_id`),
  CONSTRAINT `overdue_repayment_rel_ibfk_2` FOREIGN KEY (`repayment_id`) REFERENCES `repayment_record` (`repayment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='逾期与还款关联表';

SET FOREIGN_KEY_CHECKS = 1;
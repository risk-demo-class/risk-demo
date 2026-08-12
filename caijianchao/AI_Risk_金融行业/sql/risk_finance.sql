/*
 Navicat Premium Data Transfer

 Source Server         : local_docker_insight
 Source Server Type    : MySQL
 Source Server Version : 80046 (8.0.46)
 Source Host           : localhost:3306
 Source Schema         : risk_finance

 Target Server Type    : MySQL
 Target Server Version : 80046 (8.0.46)
 File Encoding         : 65001

 Date: 12/08/2026 09:40:04
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for account_balance_log
-- ----------------------------
DROP TABLE IF EXISTS `account_balance_log`;
CREATE TABLE `account_balance_log`  (
  `log_id` bigint NOT NULL AUTO_INCREMENT,
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `txn_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '关联交易流水号',
  `before_balance` decimal(18, 2) NOT NULL COMMENT '变动前余额',
  `change_amount` decimal(18, 2) NOT NULL COMMENT '变动金额（正=入账，负=出账）',
  `after_balance` decimal(18, 2) NOT NULL COMMENT '变动后余额',
  `change_time` timestamp NOT NULL COMMENT '变动时间',
  `operator` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'SYSTEM' COMMENT '操作方',
  PRIMARY KEY (`log_id`) USING BTREE,
  UNIQUE INDEX `txn_id`(`txn_id` ASC) USING BTREE,
  INDEX `idx_account_time`(`account_id` ASC, `change_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 12 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '账户余额变动日志表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of account_balance_log
-- ----------------------------
INSERT INTO `account_balance_log` VALUES (1, 'ACC001', 'TXN001', 250000.00, -356.00, 249644.00, '2026-08-10 18:30:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (2, 'ACC001', 'TXN002', 249644.00, -42.00, 249602.00, '2026-08-11 08:15:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (3, 'ACC002', 'TXN005', 5000000.00, -600000.00, 4400000.00, '2026-08-11 09:00:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (4, 'ACC003', 'TXN006', 120000.00, -15000.00, 105000.00, '2026-08-11 03:30:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (5, 'ACC004', 'TXN008', 800000.00, -9999.00, 790001.00, '2026-08-11 08:00:05', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (6, 'ACC006', 'TXN012', 500000.00, -50000.00, 450000.00, '2026-08-11 10:00:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (7, 'ACC010', 'TXN016', 350000.00, 20000.00, 370000.00, '2026-08-11 14:00:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (8, 'ACC010', 'TXN017', 370000.00, 15000.00, 385000.00, '2026-08-11 14:30:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (9, 'ACC010', 'TXN018', 385000.00, 18000.00, 403000.00, '2026-08-11 15:00:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (10, 'ACC015', 'TXN023', 2000000.00, 1000000.00, 3000000.00, '2026-08-11 16:00:00', 'SYSTEM');
INSERT INTO `account_balance_log` VALUES (11, 'ACC013', 'TXN021', 600000.00, -1200.00, 598800.00, '2026-08-10 20:00:00', 'SYSTEM');

-- ----------------------------
-- Table structure for account_info
-- ----------------------------
DROP TABLE IF EXISTS `account_info`;
CREATE TABLE `account_info`  (
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '账户ID',
  `user_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户姓名',
  `id_card_no` varchar(18) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '身份证号（加密存储）',
  `phone_no` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '手机号（加密存储）',
  `account_type` enum('个人','企业') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '个人' COMMENT '账户类型',
  `register_time` timestamp NOT NULL COMMENT '注册时间',
  `kyc_level` enum('未认证','基础认证','高级认证') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '未认证' COMMENT 'KYC认证等级',
  `account_status` enum('正常','冻结','销户') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '正常' COMMENT '账户状态',
  `risk_level` enum('低','中','高','黑名单') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '低' COMMENT '当前风险等级',
  `monthly_income` decimal(18, 2) NULL DEFAULT NULL COMMENT '月收入（元）',
  `employment_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '职业状态（在职/退休/自由职业/学生）',
  `total_in_amount` decimal(18, 2) NULL DEFAULT 0.00 COMMENT '历史累计入账金额（生命周期）',
  `last_txn_time` timestamp NULL DEFAULT NULL COMMENT '最后一次交易时间（用于沉睡检测）',
  PRIMARY KEY (`account_id`) USING BTREE,
  UNIQUE INDEX `id_card_no`(`id_card_no` ASC) USING BTREE,
  UNIQUE INDEX `phone_no`(`phone_no` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '账户信息表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of account_info
-- ----------------------------
INSERT INTO `account_info` VALUES ('ACC001', '张伟', '110101199001011234', '13800000001', '个人', '2024-01-01 10:00:00', '高级认证', '正常', '低', 15000.00, '在职', 250000.00, '2026-08-10 09:00:00');
INSERT INTO `account_info` VALUES ('ACC002', '李强', '110101198512152345', '13800000002', '企业', '2023-06-01 14:00:00', '高级认证', '正常', '低', 80000.00, '在职', 5000000.00, '2026-08-09 16:00:00');
INSERT INTO `account_info` VALUES ('ACC003', '王芳', '110101199205203456', '13800000003', '个人', '2024-09-01 08:00:00', '基础认证', '正常', '中', 8000.00, '自由职业', 120000.00, '2026-08-11 02:30:00');
INSERT INTO `account_info` VALUES ('ACC004', '赵磊', '110101198808184567', '13800000004', '个人', '2023-11-11 11:00:00', '高级认证', '正常', '低', 20000.00, '在职', 800000.00, '2026-08-11 08:00:00');
INSERT INTO `account_info` VALUES ('ACC005', '孙丽', '110101199607225678', '13800000005', '个人', '2025-02-14 09:00:00', '基础认证', '正常', '低', 6000.00, '在职', 30000.00, '2026-08-11 07:00:00');
INSERT INTO `account_info` VALUES ('ACC006', '周明', '110101197309016789', '13800000006', '个人', '2010-05-01 09:00:00', '高级认证', '正常', '低', 10000.00, '退休', 500000.00, '2026-05-01 10:00:00');
INSERT INTO `account_info` VALUES ('ACC007', '吴敏', '110101198910103456', '13800000007', '个人', '2023-01-01 10:00:00', '高级认证', '正常', '中', 12000.00, '在职', 400000.00, '2026-08-10 12:00:00');
INSERT INTO `account_info` VALUES ('ACC008', '郑浩', '110101199503124567', '13800000008', '个人', '2022-08-15 15:00:00', '基础认证', '正常', '中', 9000.00, '在职', 150000.00, '2026-08-11 09:00:00');
INSERT INTO `account_info` VALUES ('ACC009', '钱华', '110101198601135678', '13800000009', '个人', '2025-12-01 20:00:00', '未认证', '正常', '高', 5000.00, '学生', 10000.00, '2026-08-11 13:00:00');
INSERT INTO `account_info` VALUES ('ACC010', '冯丽', '110101199108145678', '13800000010', '个人', '2024-07-01 16:00:00', '基础认证', '正常', '高', 7000.00, '自由职业', 350000.00, '2026-08-11 14:00:00');
INSERT INTO `account_info` VALUES ('ACC011', '陈勇', '110101198712156789', '13800000011', '个人', '2026-01-01 00:00:00', '未认证', '正常', '高', 3000.00, '学生', 5000.00, '2026-08-11 10:00:00');
INSERT INTO `account_info` VALUES ('ACC012', '褚霞', '110101199309166789', '13800000012', '个人', '2026-01-15 00:00:00', '未认证', '冻结', '黑名单', 0.00, '无业', 2000.00, '2026-08-11 10:05:00');
INSERT INTO `account_info` VALUES ('ACC013', '卫东', '110101197405175678', '13800000013', '个人', '2020-03-01 08:00:00', '基础认证', '正常', '中', 15000.00, '在职', 600000.00, '2026-08-10 18:00:00');
INSERT INTO `account_info` VALUES ('ACC014', '蒋欣', '110101198806187890', '13800000014', '个人', '2024-04-01 09:00:00', '高级认证', '正常', '中', 25000.00, '在职', 300000.00, '2026-08-10 11:00:00');
INSERT INTO `account_info` VALUES ('ACC015', '韩冰', '110101199511198901', '13800000015', '企业', '2023-10-01 10:00:00', '高级认证', '正常', '低', 100000.00, '在职', 2000000.00, '2026-08-11 16:00:00');

-- ----------------------------
-- Table structure for address_history
-- ----------------------------
DROP TABLE IF EXISTS `address_history`;
CREATE TABLE `address_history`  (
  `address_id` bigint NOT NULL AUTO_INCREMENT,
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `address_type` enum('注册地址','常用地址','交易IP属地','GPS位置') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `province` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `city` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `district` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `detail_address` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '详细地址（加密）',
  `ip_segment` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'IP段',
  `first_seen_time` timestamp NOT NULL,
  `last_seen_time` timestamp NOT NULL,
  `use_count` int NULL DEFAULT 1 COMMENT '使用次数',
  PRIMARY KEY (`address_id`) USING BTREE,
  INDEX `idx_account`(`account_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 6 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '地址/归属地历史记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of address_history
-- ----------------------------
INSERT INTO `address_history` VALUES (1, 'ACC001', '注册地址', '广东省', '深圳市', '南山区', '科技园南区XX号', '192.168.1.0', '2024-01-01 00:00:00', '2026-08-10 00:00:00', 100);
INSERT INTO `address_history` VALUES (2, 'ACC001', '交易IP属地', '广东省', '深圳市', '龙岗区', NULL, '192.168.5.0', '2026-08-01 00:00:00', '2026-08-10 00:00:00', 5);
INSERT INTO `address_history` VALUES (3, 'ACC003', '注册地址', '北京市', '北京市', '朝阳区', '三里屯XX号', '10.0.0.0', '2024-09-01 00:00:00', '2026-08-10 00:00:00', 50);
INSERT INTO `address_history` VALUES (4, 'ACC006', '注册地址', '上海市', '上海市', '浦东新区', '陆家嘴XX号', '172.16.0.0', '2010-05-01 00:00:00', '2026-05-01 00:00:00', 200);
INSERT INTO `address_history` VALUES (5, 'ACC009', '交易IP属地', '北京市', '北京市', '海淀区', NULL, '192.168.100.0', '2026-08-11 00:00:00', '2026-08-11 00:00:00', 1);

-- ----------------------------
-- Table structure for aml_suspicious_report
-- ----------------------------
DROP TABLE IF EXISTS `aml_suspicious_report`;
CREATE TABLE `aml_suspicious_report`  (
  `report_id` bigint NOT NULL AUTO_INCREMENT,
  `txn_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `report_type` enum('大额交易','可疑交易','制裁名单匹配') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `trigger_rule` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '触发规则名称',
  `report_content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '详细描述',
  `report_status` enum('待上报','已上报','已排除') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '待上报',
  `create_time` timestamp NOT NULL,
  `report_time` timestamp NULL DEFAULT NULL,
  `operator` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  PRIMARY KEY (`report_id`) USING BTREE,
  INDEX `idx_txn`(`txn_id` ASC) USING BTREE,
  INDEX `idx_account`(`account_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '反洗钱可疑交易报告表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of aml_suspicious_report
-- ----------------------------

-- ----------------------------
-- Table structure for blacklist
-- ----------------------------
DROP TABLE IF EXISTS `blacklist`;
CREATE TABLE `blacklist`  (
  `blacklist_id` bigint NOT NULL AUTO_INCREMENT,
  `target_type` enum('身份证','手机号','账户','IP','设备ID','国家地区') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '名单类型',
  `target_value` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '名单值（加密存储）',
  `reason` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '列入原因',
  `source` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '来源（人行/内部/风控）',
  `create_time` timestamp NOT NULL,
  `expire_time` timestamp NULL DEFAULT NULL COMMENT '过期时间（空为永久）',
  PRIMARY KEY (`blacklist_id`) USING BTREE,
  INDEX `idx_target`(`target_type` ASC, `target_value` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 5 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '黑名单/制裁名单表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of blacklist
-- ----------------------------
INSERT INTO `blacklist` VALUES (1, '国家地区', 'IRN', '伊朗制裁国家', '人行', '2025-01-01 00:00:00', NULL);
INSERT INTO `blacklist` VALUES (2, '国家地区', 'PRK', '朝鲜制裁国家', '人行', '2025-01-01 00:00:00', NULL);
INSERT INTO `blacklist` VALUES (3, '身份证', '110101199011111111', '涉案账户', '公安部', '2026-01-01 00:00:00', '2027-01-01 00:00:00');
INSERT INTO `blacklist` VALUES (4, '手机号', '13900001111', '涉诈号码', '反诈中心', '2026-02-01 00:00:00', NULL);

-- ----------------------------
-- Table structure for credit_card_info
-- ----------------------------
DROP TABLE IF EXISTS `credit_card_info`;
CREATE TABLE `credit_card_info`  (
  `card_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '信用卡卡号（加密）',
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `total_limit` decimal(18, 2) NOT NULL COMMENT '总额度',
  `used_limit` decimal(18, 2) NULL DEFAULT 0.00 COMMENT '已用额度（账单余额）',
  `update_time` timestamp NOT NULL COMMENT '额度更新时间（按账单周期更新）',
  PRIMARY KEY (`card_id`) USING BTREE,
  INDEX `idx_account`(`account_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '信用卡额度信息表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of credit_card_info
-- ----------------------------
INSERT INTO `credit_card_info` VALUES ('CARD001', 'ACC008', 50000.00, 47500.00, '2026-08-11 09:00:00');
INSERT INTO `credit_card_info` VALUES ('CARD002', 'ACC001', 30000.00, 12000.00, '2026-08-10 09:00:00');
INSERT INTO `credit_card_info` VALUES ('CARD003', 'ACC007', 80000.00, 60000.00, '2026-08-10 12:00:00');

-- ----------------------------
-- Table structure for credit_inquiry_log
-- ----------------------------
DROP TABLE IF EXISTS `credit_inquiry_log`;
CREATE TABLE `credit_inquiry_log`  (
  `inquiry_id` bigint NOT NULL AUTO_INCREMENT,
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `inquiry_time` timestamp NOT NULL COMMENT '查询时间',
  `inquiry_reason` enum('贷款审批','信用卡审批','贷后管理','本人查询') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '查询原因',
  `inquiry_org` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '查询机构',
  `is_approved` tinyint(1) NULL DEFAULT 0 COMMENT '是否最终批贷/批卡',
  PRIMARY KEY (`inquiry_id`) USING BTREE,
  INDEX `idx_account_time`(`account_id` ASC, `inquiry_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 8 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '征信查询记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of credit_inquiry_log
-- ----------------------------
INSERT INTO `credit_inquiry_log` VALUES (1, 'ACC014', '2026-06-01 10:00:00', '贷款审批', '建设银行', 0);
INSERT INTO `credit_inquiry_log` VALUES (2, 'ACC014', '2026-06-15 10:00:00', '信用卡审批', '招商银行', 0);
INSERT INTO `credit_inquiry_log` VALUES (3, 'ACC014', '2026-07-01 10:00:00', '贷款审批', '工商银行', 0);
INSERT INTO `credit_inquiry_log` VALUES (4, 'ACC014', '2026-07-15 10:00:00', '贷款审批', '中国银行', 0);
INSERT INTO `credit_inquiry_log` VALUES (5, 'ACC014', '2026-08-01 10:00:00', '信用卡审批', '中信银行', 1);
INSERT INTO `credit_inquiry_log` VALUES (6, 'ACC014', '2026-08-10 10:00:00', '贷款审批', '平安银行', 0);
INSERT INTO `credit_inquiry_log` VALUES (7, 'ACC014', '2026-08-11 09:00:00', '贷款审批', '浦发银行', 0);

-- ----------------------------
-- Table structure for loan_info
-- ----------------------------
DROP TABLE IF EXISTS `loan_info`;
CREATE TABLE `loan_info`  (
  `loan_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '贷款合同号',
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '借款人ID',
  `loan_amount` decimal(18, 2) NOT NULL COMMENT '贷款金额',
  `loan_term` int NOT NULL COMMENT '期限（月）',
  `annual_rate` decimal(5, 4) NOT NULL COMMENT '年化利率',
  `loan_purpose` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '贷款用途',
  `approve_time` timestamp NOT NULL COMMENT '放款时间',
  `due_time` timestamp NOT NULL COMMENT '到期时间',
  `repay_status` enum('正常','逾期','结清','核销') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '正常' COMMENT '还款状态',
  `overdue_days` int NULL DEFAULT 0 COMMENT '当前逾期天数',
  `remaining_principal` decimal(18, 2) NULL DEFAULT NULL COMMENT '剩余本金',
  `lender_org` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '贷款机构（用于多头借贷统计）',
  PRIMARY KEY (`loan_id`) USING BTREE,
  INDEX `idx_account`(`account_id` ASC) USING BTREE,
  CONSTRAINT `loan_info_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `account_info` (`account_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '贷款信息表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of loan_info
-- ----------------------------
INSERT INTO `loan_info` VALUES ('LOAN001', 'ACC007', 100000.00, 12, 0.0450, '消费', '2026-01-01 10:00:00', '2027-01-01 10:00:00', '正常', 0, 80000.00, '建设银行');
INSERT INTO `loan_info` VALUES ('LOAN002', 'ACC007', 50000.00, 6, 0.0550, '装修', '2026-03-01 10:00:00', '2026-09-01 10:00:00', '正常', 5, 30000.00, '招商银行');
INSERT INTO `loan_info` VALUES ('LOAN003', 'ACC007', 30000.00, 3, 0.0650, '购物', '2026-06-01 10:00:00', '2026-09-01 10:00:00', '正常', 0, 20000.00, '微粒贷');
INSERT INTO `loan_info` VALUES ('LOAN004', 'ACC014', 200000.00, 24, 0.0350, '购车', '2026-01-15 10:00:00', '2028-01-15 10:00:00', '正常', 0, 150000.00, '工商银行');

-- ----------------------------
-- Table structure for product_channel
-- ----------------------------
DROP TABLE IF EXISTS `product_channel`;
CREATE TABLE `product_channel`  (
  `channel_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '渠道编码',
  `channel_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '渠道名称',
  `channel_type` enum('线上','线下','移动') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '线上' COMMENT '渠道类型',
  `is_counter` tinyint(1) NULL DEFAULT 0 COMMENT '是否柜面渠道（0-否，1-是）',
  PRIMARY KEY (`channel_code`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '渠道表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of product_channel
-- ----------------------------
INSERT INTO `product_channel` VALUES ('CH001', '手机银行APP', '移动', 0);
INSERT INTO `product_channel` VALUES ('CH002', '网上银行PC', '线上', 0);
INSERT INTO `product_channel` VALUES ('CH003', '银行柜台', '线下', 1);
INSERT INTO `product_channel` VALUES ('CH004', 'POS刷卡', '线下', 1);
INSERT INTO `product_channel` VALUES ('CH005', '快捷支付(微信/支付宝)', '线上', 0);
INSERT INTO `product_channel` VALUES ('CH006', 'ATM取现', '线下', 1);

-- ----------------------------
-- Table structure for repayment_record
-- ----------------------------
DROP TABLE IF EXISTS `repayment_record`;
CREATE TABLE `repayment_record`  (
  `repay_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '还款记录ID',
  `loan_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '关联贷款ID',
  `repay_amount` decimal(18, 2) NOT NULL COMMENT '还款金额',
  `repay_time` timestamp NOT NULL COMMENT '还款时间',
  `repay_type` enum('正常还款','提前还款','逾期还款') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '正常还款',
  `is_late` tinyint(1) NULL DEFAULT 0 COMMENT '是否逾期还款（超过约定日）',
  `late_days` int NULL DEFAULT 0 COMMENT '本次逾期天数（如有）',
  PRIMARY KEY (`repay_id`) USING BTREE,
  INDEX `idx_loan`(`loan_id` ASC) USING BTREE,
  CONSTRAINT `repayment_record_ibfk_1` FOREIGN KEY (`loan_id`) REFERENCES `loan_info` (`loan_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '还款记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of repayment_record
-- ----------------------------
INSERT INTO `repayment_record` VALUES ('REP001', 'LOAN001', 8000.00, '2026-02-01 10:00:00', '正常还款', 0, 0);
INSERT INTO `repayment_record` VALUES ('REP002', 'LOAN001', 8000.00, '2026-03-01 10:00:00', '正常还款', 0, 0);
INSERT INTO `repayment_record` VALUES ('REP003', 'LOAN001', 8000.00, '2026-04-01 10:00:00', '正常还款', 0, 0);
INSERT INTO `repayment_record` VALUES ('REP004', 'LOAN002', 8000.00, '2026-04-01 10:00:00', '逾期还款', 1, 30);
INSERT INTO `repayment_record` VALUES ('REP005', 'LOAN002', 8000.00, '2026-05-01 10:00:00', '正常还款', 0, 0);
INSERT INTO `repayment_record` VALUES ('REP006', 'LOAN003', 10000.00, '2026-07-01 10:00:00', '正常还款', 0, 0);

-- ----------------------------
-- Table structure for risk_action_log
-- ----------------------------
DROP TABLE IF EXISTS `risk_action_log`;
CREATE TABLE `risk_action_log`  (
  `log_id` bigint NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `operator` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '操作人(admin/system/ai_agent)',
  `action_type` enum('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '操作类型',
  `target_type` enum('rule','case','blacklist') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '对象类型',
  `target_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '对象ID',
  `before_value` json NULL COMMENT '变更前 (NULL=新增)',
  `after_value` json NULL COMMENT '变更后 (NULL=删除)',
  `ip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '操作IP',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  PRIMARY KEY (`log_id`) USING BTREE,
  INDEX `idx_action_log_operator`(`operator` ASC) USING BTREE,
  INDEX `idx_action_log_target`(`target_type` ASC, `target_id` ASC) USING BTREE,
  INDEX `idx_action_log_create_time`(`create_time` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '风控操作审计日志表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_action_log
-- ----------------------------

-- ----------------------------
-- Table structure for risk_alert
-- ----------------------------
DROP TABLE IF EXISTS `risk_alert`;
CREATE TABLE `risk_alert`  (
  `alert_id` bigint NOT NULL AUTO_INCREMENT COMMENT '告警ID',
  `alert_type` enum('BUSINESS','MODEL','SYSTEM','SECURITY') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '告警分类',
  `alert_level` enum('P0','P1','P2','P3') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '告警等级 (P0=致命, P3=提示)',
  `alert_title` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '告警标题',
  `alert_content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '告警详情',
  `metric_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '指标名(规则命中率/案件积压数等)',
  `metric_value` decimal(20, 6) NULL DEFAULT NULL COMMENT '触发值',
  `threshold` decimal(20, 6) NULL DEFAULT NULL COMMENT '阈值',
  `status` enum('PENDING','HANDLING','RESOLVED','IGNORED') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'PENDING' COMMENT '处理状态',
  `handler` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '处理人',
  `resolve_time` datetime NULL DEFAULT NULL COMMENT '解决时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '告警时间',
  PRIMARY KEY (`alert_id`) USING BTREE,
  INDEX `idx_alert_status`(`status` ASC) USING BTREE,
  INDEX `idx_alert_level`(`alert_level` ASC) USING BTREE,
  INDEX `idx_alert_create_time`(`create_time` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '风控告警记录表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_alert
-- ----------------------------

-- ----------------------------
-- Table structure for risk_assessment
-- ----------------------------
DROP TABLE IF EXISTS `risk_assessment`;
CREATE TABLE `risk_assessment`  (
  `assessment_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '评估ID',
  `event_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '关联事件ID',
  `user_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户ID',
  `rule_results` json NULL COMMENT '规则结果',
  `rule_count` int NULL DEFAULT 0 COMMENT '命中规则数',
  `final_score` int NOT NULL COMMENT '最终评分(0-100)',
  `risk_level` enum('低','中','高','极高') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '风险等级',
  `decision` enum('通过','标记','人工审核','拒绝') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '决策',
  `ml_score` decimal(5, 4) NULL DEFAULT NULL COMMENT 'XGBoost 拒绝概率 [0,1](NULL=未加载)',
  `ml_decision` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'ML 维度决策(通过/标记/人工审核/拒绝)',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`assessment_id`) USING BTREE,
  INDEX `idx_risk_assessment_user_id`(`user_id` ASC) USING BTREE,
  INDEX `idx_risk_assessment_decision`(`decision` ASC) USING BTREE,
  INDEX `idx_risk_assessment_create_time`(`create_time` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '风控评估结果表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_assessment
-- ----------------------------

-- ----------------------------
-- Table structure for risk_blacklist
-- ----------------------------
DROP TABLE IF EXISTS `risk_blacklist`;
CREATE TABLE `risk_blacklist`  (
  `blacklist_id` bigint NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
  `blacklist_type` enum('身份证','手机号','账户ID','IP地址','设备指纹','商户号','国家地区') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '黑名单类型',
  `blacklist_value` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '黑名单值（敏感信息加密存储）',
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '加入原因',
  `expire_time` datetime NULL DEFAULT NULL COMMENT '过期时间（NULL=永久）',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `deleted_at` datetime NULL DEFAULT NULL COMMENT '软删除时间（NULL=未删）',
  PRIMARY KEY (`blacklist_id`) USING BTREE,
  UNIQUE INDEX `idx_blacklist_type_value`(`blacklist_type` ASC, `blacklist_value` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '金融风控黑名单表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_blacklist
-- ----------------------------

-- ----------------------------
-- Table structure for risk_case
-- ----------------------------
DROP TABLE IF EXISTS `risk_case`;
CREATE TABLE `risk_case`  (
  `case_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '案件ID',
  `assessment_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '关联评估ID',
  `user_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户ID',
  `case_status` enum('待审核','审核中','已通过','已拒绝','已关闭') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '待审核' COMMENT '案件状态',
  `case_category` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '案件分类（交易欺诈/信贷欺诈/反洗钱/行为异常/合规制裁）',
  `risk_detail` json NULL COMMENT '风险详情（包含命中规则、金额、对手方等）',
  `source_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '原始业务ID（交易流水号/贷款编号/操作日志ID等）',
  `event_type` enum('交易','转账','取现','贷款申请','账户变更','登录','反洗钱预警') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '触发案件的事件类型（与risk_event一致）',
  `reviewer` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '审核人',
  `review_comment` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '审核意见',
  `review_time` datetime NULL DEFAULT NULL COMMENT '审核时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`case_id`) USING BTREE,
  INDEX `idx_risk_case_status`(`case_status` ASC) USING BTREE,
  INDEX `idx_risk_case_user_id`(`user_id` ASC) USING BTREE,
  INDEX `idx_risk_case_source_id`(`source_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '风控案件表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_case
-- ----------------------------

-- ----------------------------
-- Table structure for risk_event
-- ----------------------------
DROP TABLE IF EXISTS `risk_event`;
CREATE TABLE `risk_event`  (
  `event_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '事件ID',
  `event_type` enum('交易','转账','取现','贷款申请','账户变更','登录','反洗钱预警') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '事件类型',
  `event_source_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '关联业务ID（交易流水号/贷款编号/操作日志ID等）',
  `user_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户ID（对应账户ID）',
  `event_data` json NULL COMMENT '事件快照（关键字段JSON）',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`event_id`) USING BTREE,
  INDEX `idx_risk_event_user_id`(`user_id` ASC) USING BTREE,
  INDEX `idx_risk_event_create_time`(`create_time` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '风控事件审计表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_event
-- ----------------------------
INSERT INTO `risk_event` VALUES ('EVT20260811001', '交易', 'TXN001', 'ACC001', '{\"ip\": \"192.168.1.10\", \"channel\": \"快捷支付\", \"merchant\": \"沃尔玛超市\", \"txn_type\": \"消费支付\", \"txn_amount\": 356.00}', '2026-08-10 18:30:00');
INSERT INTO `risk_event` VALUES ('EVT20260811002', '转账', 'TXN005', 'ACC002', '{\"ip\": \"192.168.2.10\", \"channel\": \"网上银行PC\", \"to_name\": \"王芳\", \"from_type\": \"企业\", \"to_account\": \"ACC003\", \"txn_amount\": 600000.00}', '2026-08-11 09:00:00');
INSERT INTO `risk_event` VALUES ('EVT20260811003', '交易', 'TXN006', 'ACC003', '{\"ip\": \"10.0.0.10\", \"hour\": 3, \"channel\": \"快捷支付\", \"merchant\": \"淘宝商城\", \"txn_type\": \"消费支付\", \"txn_amount\": 15000.00}', '2026-08-11 03:30:00');
INSERT INTO `risk_event` VALUES ('EVT20260811004', '交易', 'TXN008', 'ACC004', '{\"channel\": \"快捷支付\", \"merchant\": \"苹果商城\", \"txn_time\": \"2026-08-11 08:00:05\", \"txn_type\": \"消费支付\", \"txn_amount\": 9999.00, \"request_time\": \"2026-08-11 08:00:02\"}', '2026-08-11 08:00:05');
INSERT INTO `risk_event` VALUES ('EVT20260811005', '交易', 'TXN011', 'ACC005', '{\"status\": \"失败\", \"channel\": \"手机银行APP\", \"txn_type\": \"转账\", \"fail_count\": 3, \"txn_amount\": 1000.00, \"fail_reason\": \"密码错误\"}', '2026-08-11 07:10:00');
INSERT INTO `risk_event` VALUES ('EVT20260811006', '转账', 'TXN012', 'ACC006', '{\"channel\": \"手机银行APP\", \"to_name\": \"韩冰\", \"to_account\": \"ACC015\", \"txn_amount\": 50000.00, \"last_txn_days\": 102}', '2026-08-11 10:00:00');
INSERT INTO `risk_event` VALUES ('EVT20260811007', '贷款申请', 'LOAN004', 'ACC007', '{\"lender\": \"微粒贷\", \"loan_amount\": 30000.00, \"loan_purpose\": \"消费\", \"overdue_flag\": 1, \"existing_loans\": 3}', '2026-08-10 12:00:00');
INSERT INTO `risk_event` VALUES ('EVT20260811008', '账户变更', 'OP_20260809_001', 'ACC013', '{\"op_time\": \"2026-08-09 11:00:00\", \"op_type\": \"修改密码\", \"client_type\": \"Web\", \"change_count_7d\": 3}', '2026-08-09 11:00:00');
INSERT INTO `risk_event` VALUES ('EVT20260811009', '登录', 'LOGIN_20260811_001', 'ACC009', '{\"ip\": \"10.0.0.20\", \"device_env\": \"模拟器\", \"login_time\": \"2026-08-11 12:50:00\", \"client_type\": \"H5\"}', '2026-08-11 12:50:00');
INSERT INTO `risk_event` VALUES ('EVT20260811010', '反洗钱预警', 'AML_ALERT_001', 'ACC010', '{\"total_in\": 53000.00, \"alert_reason\": \"30天内接收≥3个非关联方大额转账\", \"rule_trigger\": \"RA003\", \"counterparty_count\": 3}', '2026-08-11 15:00:00');
INSERT INTO `risk_event` VALUES ('EVT20260811011', '取现', 'TXN_ATM_001', 'ACC006', '{\"channel\": \"ATM\", \"cash_type\": \"人民币\", \"txn_amount\": 20000.00, \"atm_location\": \"上海市浦东新区\"}', '2026-08-10 14:00:00');
INSERT INTO `risk_event` VALUES ('EVT20260811012', '交易', 'TXN014', 'ACC008', '{\"channel\": \"POS刷卡\", \"merchant\": \"加油站\", \"txn_type\": \"消费支付\", \"txn_amount\": 450.00, \"credit_usage_rate\": 95}', '2026-08-11 09:00:00');

-- ----------------------------
-- Table structure for risk_feature
-- ----------------------------
DROP TABLE IF EXISTS `risk_feature`;
CREATE TABLE `risk_feature`  (
  `feature_id` bigint NOT NULL AUTO_INCREMENT COMMENT '特征ID',
  `event_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '关联事件ID（触发特征计算的事件）',
  `entity_type` enum('账户','交易','设备','IP','贷款','操作日志') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '实体类型',
  `entity_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '实体ID',
  `feature_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '特征名称',
  `feature_value` decimal(15, 4) NULL DEFAULT NULL COMMENT '特征值（数值型）',
  `feature_value_str` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '特征值（字符串型，适用于分类）',
  `compute_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '计算时间',
  PRIMARY KEY (`feature_id`) USING BTREE,
  INDEX `idx_risk_feature_event_id`(`event_id` ASC) USING BTREE,
  INDEX `idx_risk_feature_entity`(`entity_type` ASC, `entity_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 17 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '风控特征快照表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_feature
-- ----------------------------
INSERT INTO `risk_feature` VALUES (1, 'EVT20260811001', '账户', 'ACC001', 'txn_cnt_7d', 8.0000, NULL, '2026-08-10 18:30:00');
INSERT INTO `risk_feature` VALUES (2, 'EVT20260811001', '账户', 'ACC001', 'avg_txn_amount', 1200.0000, NULL, '2026-08-10 18:30:00');
INSERT INTO `risk_feature` VALUES (3, 'EVT20260811003', '账户', 'ACC003', 'txn_amount_30d', 23190.0000, NULL, '2026-08-11 03:30:00');
INSERT INTO `risk_feature` VALUES (4, 'EVT20260811003', '账户', 'ACC003', 'night_txn_cnt_7d', 5.0000, NULL, '2026-08-11 03:30:00');
INSERT INTO `risk_feature` VALUES (5, 'EVT20260811012', '账户', 'ACC008', 'credit_usage_rate', 95.0000, NULL, '2026-08-11 09:00:00');
INSERT INTO `risk_feature` VALUES (6, 'EVT20260811007', '账户', 'ACC007', 'unsettled_lender_count', 3.0000, NULL, '2026-08-10 12:00:00');
INSERT INTO `risk_feature` VALUES (7, 'EVT20260811010', '账户', 'ACC015', 'total_in_amount', 2000000.0000, NULL, '2026-08-11 16:00:00');
INSERT INTO `risk_feature` VALUES (8, 'EVT20260811004', '交易', 'TXN008', 'operation_interval_sec', 3.0000, NULL, '2026-08-11 08:00:05');
INSERT INTO `risk_feature` VALUES (9, 'EVT20260811002', '交易', 'TXN005', 'is_public_to_private', 1.0000, NULL, '2026-08-11 09:00:00');
INSERT INTO `risk_feature` VALUES (10, 'EVT20260811003', '交易', 'TXN006', 'is_night_txn', 1.0000, NULL, '2026-08-11 03:30:00');
INSERT INTO `risk_feature` VALUES (11, 'EVT20260811009', '设备', 'DEV_SHARED', 'device_account_count', 2.0000, NULL, '2026-08-11 10:00:00');
INSERT INTO `risk_feature` VALUES (12, 'EVT20260811009', '设备', 'DEV_009', 'device_env', NULL, '模拟器', '2026-08-11 12:50:00');
INSERT INTO `risk_feature` VALUES (13, 'EVT20260811009', 'IP', '10.0.0.20', 'ip_in_blacklist', 0.0000, NULL, '2026-08-11 12:50:00');
INSERT INTO `risk_feature` VALUES (14, 'EVT20260811007', '贷款', 'LOAN001', 'remaining_principal_ratio', 0.8000, NULL, '2026-08-10 12:00:00');
INSERT INTO `risk_feature` VALUES (15, 'EVT20260811008', '操作日志', 'OP_20260809_001', 'modify_info_7d', 3.0000, NULL, '2026-08-09 11:00:00');
INSERT INTO `risk_feature` VALUES (16, 'EVT20260811010', '账户', 'ACC010', 'distinct_counterparty_30d', 4.0000, NULL, '2026-08-11 15:00:00');

-- ----------------------------
-- Table structure for risk_rule
-- ----------------------------
DROP TABLE IF EXISTS `risk_rule`;
CREATE TABLE `risk_rule`  (
  `rule_id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `rule_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `rule_category` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `event_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `rule_condition` json NULL,
  `risk_level` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `risk_score` int NULL DEFAULT NULL,
  `action` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `is_enabled` tinyint(1) NULL DEFAULT NULL,
  `priority` int NULL DEFAULT NULL,
  `description` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  PRIMARY KEY (`rule_id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_rule
-- ----------------------------
INSERT INTO `risk_rule` VALUES ('RA001', '单日累计现金存取≥5万元', '反洗钱', '反洗钱', '{\"op\": \">=\", \"field\": \"daily_cash_total\", \"value\": 50000}', '中', 65, '标记关注', 1, 70, '触发大额现金交易报告');
INSERT INTO `risk_rule` VALUES ('RA002', '资金到账后5分钟内转出（快进快出）', '反洗钱', '反洗钱', '{\"op\": \"<=\", \"field\": \"hold_minutes\", \"value\": 5}', '高', 85, '人工复核', 1, 85, '快进快出，典型洗钱特征');
INSERT INTO `risk_rule` VALUES ('RA003', '接收≥3个非关联方大额转账（单笔≥1万）', '反洗钱', '反洗钱', '{\"type\": \"and\", \"conditions\": [{\"op\": \">=\", \"field\": \"large_incoming_count\", \"value\": 3}, {\"op\": \">=\", \"field\": \"per_txn_amount\", \"value\": 10000}]}', '高', 88, '人工复核', 1, 80, '多人汇款，疑似非法集资');
INSERT INTO `risk_rule` VALUES ('RA004', '对手方位于制裁国家/地区', '反洗钱', '反洗钱', '{\"op\": \"in\", \"field\": \"country_code\", \"value\": [\"IRN\", \"PRK\", \"SYR\"]}', '高', 100, '一票否决', 1, 99, '涉制裁国家，必须拦截');
INSERT INTO `risk_rule` VALUES ('RA005', '公转私单笔≥50万元', '反洗钱', '反洗钱', '{\"type\": \"and\", \"conditions\": [{\"op\": \"=\", \"field\": \"from_account_type\", \"value\": \"企业\"}, {\"op\": \"=\", \"field\": \"to_account_type\", \"value\": \"个人\"}, {\"op\": \">=\", \"field\": \"txn_amount\", \"value\": 500000}]}', '高', 90, '人工复核', 1, 85, '大额公转私，需核实用途');
INSERT INTO `risk_rule` VALUES ('RA006', '累计转入资金≥100万元（高净值）', '反洗钱', '反洗钱', '{\"op\": \">=\", \"field\": \"total_in_amount\", \"value\": 1000000}', '低', 30, '标记关注', 1, 50, '高净值客户，加强尽调');
INSERT INTO `risk_rule` VALUES ('RA007', '单日转账笔数≥50笔（同RF008）', '反洗钱', '反洗钱', '{\"op\": \">=\", \"field\": \"daily_transfer_count\", \"value\": 50}', '高', 85, '一票否决', 1, 90, '批量转账，需立即上报');
INSERT INTO `risk_rule` VALUES ('RB001', '沉睡账户（≥90天无交易）突发≥1万元转出', '行为异常', '账户行为', '{\"type\": \"and\", \"conditions\": [{\"op\": \">=\", \"field\": \"last_txn_days\", \"value\": 90}, {\"op\": \">=\", \"field\": \"txn_amount\", \"value\": 10000}]}', '高', 78, '人工复核', 1, 80, '账户长期不动，突然大额转出，疑似盗用');
INSERT INTO `risk_rule` VALUES ('RB002', '7天内修改关键信息≥2次', '行为异常', '账户行为', '{\"op\": \">=\", \"field\": \"modify_info_7d\", \"value\": 2}', '中', 68, '标记关注', 1, 70, '频繁修改个人信息，账号可能被操控');
INSERT INTO `risk_rule` VALUES ('RB003', '使用模拟器/VPN等异常设备环境', '行为异常', '账户行为', '{\"op\": \"in\", \"field\": \"device_env\", \"value\": [\"模拟器\", \"VPN\", \"越狱\"]}', '高', 82, '拦截', 1, 85, '通过黑产工具操作，高风险');
INSERT INTO `risk_rule` VALUES ('RB004', '找回密码/修改信息后1小时内发起转账', '行为异常', '账户行为', '{\"op\": \"<=\", \"field\": \"operation_to_txn_minutes\", \"value\": 60}', '高', 80, '拦截', 1, 80, '敏感操作后立即转账，疑似盗用');
INSERT INTO `risk_rule` VALUES ('RB005', '同一设备关联账户≥3个（同RF006）', '行为异常', '账户行为', '{\"op\": \">=\", \"field\": \"device_account_count\", \"value\": 3}', '高', 75, '拦截', 1, 80, '多账户共用设备，涉嫌养号');
INSERT INTO `risk_rule` VALUES ('RB006', '新注册用户首单≥5000元', '行为异常', '账户行为', '{\"type\": \"and\", \"conditions\": [{\"op\": \"=\", \"field\": \"is_new_user\", \"value\": true}, {\"op\": \">=\", \"field\": \"txn_amount\", \"value\": 5000}]}', '中', 65, '标记关注', 1, 60, '新用户首笔大额，需核实身份');
INSERT INTO `risk_rule` VALUES ('RB007', '近3个月地址变更≥3次（多地域登录）', '行为异常', '账户行为', '{\"op\": \">=\", \"field\": \"address_change_3m\", \"value\": 3}', '中', 60, '标记关注', 1, 65, '频繁更换地址/属地，可能被盗');
INSERT INTO `risk_rule` VALUES ('RC001', '近3个月征信查询≥6次（未批贷）', '信贷审批', '信贷审批', '{\"type\": \"and\", \"conditions\": [{\"op\": \">=\", \"field\": \"credit_inquiry_3m\", \"value\": 6}, {\"op\": \"=\", \"field\": \"is_approved\", \"value\": false}]}', '高', 75, '标记关注', 1, 85, '频繁查询但未批贷，多头借贷迹象');
INSERT INTO `risk_rule` VALUES ('RC002', '信用卡使用率≥90%持续3个月', '信贷审批', '信贷审批', '{\"type\": \"and\", \"conditions\": [{\"op\": \">=\", \"field\": \"credit_usage_rate\", \"value\": 0.9}, {\"op\": \">=\", \"field\": \"duration_months\", \"value\": 3}]}', '中', 68, '标记关注', 1, 70, '长期高额透支，资金链紧张');
INSERT INTO `risk_rule` VALUES ('RC003', '申请贷款金额≥月收入20倍', '信贷审批', '信贷审批', '{\"op\": \">=\", \"field\": \"loan_to_income_ratio\", \"value\": 20}', '高', 90, '一票否决', 1, 90, '负债远超偿还能力');
INSERT INTO `risk_rule` VALUES ('RC004', '贷款用途为投资/购房（消费贷违规）', '信贷审批', '信贷审批', '{\"op\": \"in\", \"field\": \"loan_purpose\", \"value\": [\"投资\", \"购房\", \"炒股\"]}', '高', 95, '一票否决', 1, 95, '消费贷流入禁止领域');
INSERT INTO `risk_rule` VALUES ('RC005', '近6个月逾期≥30天且金额≥1000元', '信贷审批', '信贷审批', '{\"type\": \"and\", \"conditions\": [{\"op\": \">=\", \"field\": \"overdue_days\", \"value\": 30}, {\"op\": \">=\", \"field\": \"overdue_amount\", \"value\": 1000}]}', '高', 80, '标记关注', 1, 80, '严重逾期记录');
INSERT INTO `risk_rule` VALUES ('RC006', '在≥3家机构有未结清贷款', '信贷审批', '信贷审批', '{\"op\": \">=\", \"field\": \"unsettled_lender_count\", \"value\": 3}', '中', 70, '人工复核', 1, 75, '多头借贷，需审慎评估');
INSERT INTO `risk_rule` VALUES ('RF001', '单笔交易金额≥5万（无卡/快捷）', '交易反欺诈', '交易', '{\"type\": \"and\", \"conditions\": [{\"op\": \">=\", \"field\": \"txn_amount\", \"value\": 50000}, {\"op\": \"=\", \"field\": \"channel_type\", \"value\": \"线上\"}]}', '中', 60, '人工复核', 1, 80, '触发大额线上交易，需人工确认');
INSERT INTO `risk_rule` VALUES ('RF002', '单笔交易金额≥20万（非柜面）', '交易反欺诈', '交易', '{\"type\": \"and\", \"conditions\": [{\"op\": \">=\", \"field\": \"txn_amount\", \"value\": 200000}, {\"op\": \"=\", \"field\": \"is_counter\", \"value\": 0}]}', '高', 95, '一票否决', 1, 90, '非柜面巨额交易，直接拦截');
INSERT INTO `risk_rule` VALUES ('RF003', '凌晨0-6点首笔大额交易（≥1万）', '交易反欺诈', '交易', '{\"type\": \"and\", \"conditions\": [{\"op\": \"between\", \"field\": \"hour\", \"value\": [0, 6]}, {\"op\": \">=\", \"field\": \"txn_amount\", \"value\": 10000}, {\"op\": \"=\", \"field\": \"is_first_large\", \"value\": true}]}', '中', 70, '人工复核', 1, 75, '凌晨时段首次大额交易，需核实');
INSERT INTO `risk_rule` VALUES ('RF004', '操作间隔≤3秒（疑似程序化）', '交易反欺诈', '交易', '{\"op\": \"<=\", \"field\": \"operation_interval_sec\", \"value\": 3}', '高', 80, '拦截', 1, 85, '极速操作，疑似机器/AI自动交易');
INSERT INTO `risk_rule` VALUES ('RF005', '单日交易失败≥3次', '交易反欺诈', '交易', '{\"op\": \">=\", \"field\": \"daily_fail_count\", \"value\": 3}', '中', 65, '标记关注', 1, 70, '同一账户当日多次失败，可能撞库');
INSERT INTO `risk_rule` VALUES ('RF006', '同一设备关联账户≥3个', '交易反欺诈', '交易', '{\"op\": \">=\", \"field\": \"device_account_count\", \"value\": 3}', '高', 75, '拦截', 1, 80, '多账户共用设备，疑似团伙欺诈');
INSERT INTO `risk_rule` VALUES ('RF007', '30天内向新开户（≤7天）对手转账≥3笔', '交易反欺诈', '交易', '{\"type\": \"and\", \"conditions\": [{\"op\": \"<=\", \"field\": \"counterparty_reg_days\", \"value\": 7}, {\"op\": \">=\", \"field\": \"txn_count_30d_to_new\", \"value\": 3}]}', '中', 68, '人工复核', 1, 70, '频繁向新账户转账，疑似洗钱');
INSERT INTO `risk_rule` VALUES ('RF008', '单日转账笔数≥50笔', '交易反欺诈', '交易', '{\"op\": \">=\", \"field\": \"daily_transfer_count\", \"value\": 50}', '高', 85, '一票否决', 1, 90, '单日批量转账，高度疑似洗钱');

-- ----------------------------
-- Table structure for risk_user_profile
-- ----------------------------
DROP TABLE IF EXISTS `risk_user_profile`;
CREATE TABLE `risk_user_profile`  (
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '账户ID',
  `register_days` int NULL DEFAULT 0 COMMENT '注册天数',
  `kyc_level` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '未认证' COMMENT 'KYC等级',
  `account_type` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '个人' COMMENT '账户类型',
  `monthly_income` decimal(18, 2) NULL DEFAULT NULL COMMENT '月收入(元)',
  `employment_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '职业状态',
  `txn_cnt_7d` int NULL DEFAULT 0 COMMENT '近7天交易笔数',
  `txn_cnt_30d` int NULL DEFAULT 0 COMMENT '近30天交易笔数',
  `txn_amount_30d` decimal(18, 2) NULL DEFAULT 0.00 COMMENT '近30天交易总金额',
  `avg_txn_amount` decimal(18, 2) NULL DEFAULT 0.00 COMMENT '历史平均交易金额（全生命周期）',
  `max_single_amount` decimal(18, 2) NULL DEFAULT 0.00 COMMENT '历史最大单笔交易金额',
  `total_in_amount` decimal(18, 2) NULL DEFAULT 0.00 COMMENT '历史累计入账总额',
  `total_out_amount` decimal(18, 2) NULL DEFAULT 0.00 COMMENT '历史累计出账总额',
  `daily_fail_count` int NULL DEFAULT 0 COMMENT '当日交易失败次数',
  `night_txn_cnt_7d` int NULL DEFAULT 0 COMMENT '近7天凌晨(0-6点)交易笔数',
  `high_freq_cnt_30d` int NULL DEFAULT 0 COMMENT '近30天快进快出次数（入金后5分钟内转出）',
  `distinct_counterparty_30d` int NULL DEFAULT 0 COMMENT '近30天不同交易对手数',
  `distinct_device_30d` int NULL DEFAULT 0 COMMENT '近30天不同设备数',
  `device_account_count` int NULL DEFAULT 0 COMMENT '同一设备关联账户总数（全局）',
  `credit_inquiry_3m` int NULL DEFAULT 0 COMMENT '近3个月征信查询次数',
  `credit_usage_rate` decimal(5, 2) NULL DEFAULT 0.00 COMMENT '信用卡使用率（百分比）',
  `unsettled_lender_count` int NULL DEFAULT 0 COMMENT '未结清贷款机构数',
  `loan_to_income_ratio` decimal(10, 2) NULL DEFAULT 0.00 COMMENT '贷款总额/月收入倍数',
  `has_overdue_30d` tinyint(1) NULL DEFAULT 0 COMMENT '是否有逾期≥30天记录',
  `last_txn_time` timestamp NULL DEFAULT NULL COMMENT '最后一次交易时间',
  `last_txn_days` int NULL DEFAULT 9999 COMMENT '距上次交易天数（用于沉睡判断）',
  `modify_info_7d` int NULL DEFAULT 0 COMMENT '近7天修改关键信息次数',
  `address_change_3m` int NULL DEFAULT 0 COMMENT '近3个月地址/属地变更次数',
  `operation_to_txn_minutes` int NULL DEFAULT NULL COMMENT '敏感操作（改密/找回）到最近交易间隔分钟数',
  `is_new_user` tinyint(1) NULL DEFAULT 0 COMMENT '是否新用户（注册<30天）',
  `is_high_net_worth` tinyint(1) NULL DEFAULT 0 COMMENT '是否高净值（累计入账>=100万）',
  `is_sleeping` tinyint(1) NULL DEFAULT 0 COMMENT '是否沉睡账户（上次交易≥90天）',
  `device_risk_env` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '正常' COMMENT '设备环境风险（正常/模拟器/VPN/越狱）',
  `risk_level` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '低' COMMENT '综合风险等级（低/中/高/黑名单）',
  `risk_score` int NULL DEFAULT 0 COMMENT '综合风险评分（0-1000）',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '特征更新时间',
  PRIMARY KEY (`account_id`) USING BTREE,
  INDEX `idx_risk_level`(`risk_level` ASC) USING BTREE,
  INDEX `idx_risk_score`(`risk_score` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户风险画像表（宽表）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of risk_user_profile
-- ----------------------------
INSERT INTO `risk_user_profile` VALUES ('ACC001', 588, '高级认证', '个人', 15000.00, '在职', 8, 12, 356.00, 1200.00, 15000.00, 250000.00, 0.00, 0, 0, 0, 3, 1, 1, 0, 40.00, 0, 0.00, 0, '2026-08-11 08:15:00', 0, 0, 1, NULL, 0, 1, 0, '正常', '低', 200, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC002', 1170, '高级认证', '企业', 80000.00, '在职', 4, 6, 668000.00, 850000.00, 600000.00, 5000000.00, 0.00, 0, 0, 0, 3, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-11 09:00:00', 0, 0, 1, NULL, 0, 1, 0, '正常', '中', 650, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC003', 710, '基础认证', '个人', 8000.00, '自由职业', 5, 8, 23190.00, 800.00, 15000.00, 120000.00, 0.00, 0, 5, 0, 4, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-11 03:30:00', 0, 0, 1, NULL, 0, 0, 0, '正常', '中', 580, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC004', 822, '高级认证', '个人', 20000.00, '在职', 5, 8, 32109.00, 4000.00, 12800.00, 800000.00, 0.00, 0, 0, 0, 4, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-11 08:00:05', 0, 0, 1, 30, 0, 0, 0, '正常', '高', 820, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC005', 540, '基础认证', '个人', 6000.00, '在职', 4, 6, 3635.00, 500.00, 2500.00, 30000.00, 0.00, 3, 0, 0, 3, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-11 07:10:00', 0, 0, 1, NULL, 0, 0, 0, '正常', '中', 750, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC006', 5936, '高级认证', '个人', 10000.00, '退休', 1, 1, 50000.00, 2000.00, 50000.00, 500000.00, 0.00, 0, 0, 0, 1, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-11 10:00:00', 0, 0, 1, NULL, 0, 0, 1, '正常', '高', 780, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC007', 1280, '高级认证', '个人', 12000.00, '在职', 4, 7, 48700.00, 6000.00, 25000.00, 400000.00, 0.00, 0, 0, 0, 5, 1, 1, 0, 75.00, 3, 15.00, 1, '2026-08-10 18:00:00', 0, 0, 1, NULL, 0, 0, 0, '正常', '高', 880, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC008', 1420, '基础认证', '个人', 9000.00, '在职', 5, 8, 7197.00, 800.00, 6000.00, 150000.00, 0.00, 0, 0, 0, 5, 1, 1, 0, 95.00, 0, 0.00, 0, '2026-08-11 09:00:00', 0, 0, 1, NULL, 0, 0, 0, '正常', '中', 680, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC009', 210, '未认证', '个人', 5000.00, '学生', 4, 6, 9050.00, 300.00, 5000.00, 10000.00, 0.00, 0, 0, 0, 3, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-11 13:00:00', 0, 0, 1, NULL, 0, 0, 0, '模拟器', '高', 820, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC010', 390, '基础认证', '个人', 7000.00, '自由职业', 5, 8, 95000.00, 2000.00, 25000.00, 350000.00, 0.00, 0, 0, 0, 4, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-11 15:00:00', 0, 0, 1, NULL, 0, 0, 0, '正常', '高', 880, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC011', 222, '未认证', '个人', 3000.00, '学生', 4, 5, 167.00, 50.00, 100.00, 5000.00, 0.00, 0, 0, 0, 2, 1, 2, 0, 0.00, 0, 0.00, 0, '2026-08-11 10:00:00', 0, 0, 0, NULL, 1, 0, 0, '正常', '高', 650, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC012', 208, '未认证', '个人', 0.00, '无业', 3, 4, 355.00, 50.00, 200.00, 2000.00, 0.00, 0, 0, 0, 2, 1, 2, 0, 0.00, 0, 0.00, 0, '2026-08-11 10:05:00', 0, 0, 0, NULL, 1, 0, 0, '正常', '黑名单', 900, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC013', 2330, '基础认证', '个人', 15000.00, '在职', 4, 6, 3140.00, 1000.00, 1800.00, 600000.00, 0.00, 0, 0, 0, 4, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-10 20:00:00', 0, 3, 2, NULL, 0, 0, 0, '正常', '中', 680, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC014', 490, '高级认证', '个人', 25000.00, '在职', 4, 7, 39150.00, 5000.00, 30000.00, 300000.00, 0.00, 0, 0, 0, 4, 1, 1, 7, 0.00, 0, 0.00, 0, '2026-08-10 11:00:00', 0, 0, 1, NULL, 0, 0, 0, '正常', '中', 750, '2026-08-12 00:45:49');
INSERT INTO `risk_user_profile` VALUES ('ACC015', 680, '高级认证', '企业', 100000.00, '在职', 4, 6, 1288500.00, 300000.00, 1000000.00, 2000000.00, 0.00, 0, 0, 0, 3, 1, 1, 0, 0.00, 0, 0.00, 0, '2026-08-11 16:00:00', 0, 0, 0, NULL, 0, 1, 0, '正常', '低', 300, '2026-08-12 00:45:49');

-- ----------------------------
-- Table structure for transaction_order
-- ----------------------------
DROP TABLE IF EXISTS `transaction_order`;
CREATE TABLE `transaction_order`  (
  `txn_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '交易流水号',
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '发起方账户ID',
  `counterparty_account` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '对手方账户ID',
  `counterparty_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '对手方户名',
  `txn_type_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '交易类型',
  `channel_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '交易渠道',
  `txn_amount` decimal(18, 2) NOT NULL COMMENT '交易金额（元）',
  `txn_currency` varchar(3) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'CNY' COMMENT '币种',
  `txn_time` timestamp NOT NULL COMMENT '交易完成时间（银行端）',
  `request_time` timestamp NULL DEFAULT NULL COMMENT '用户发起请求时间（前端埋点，用于计算间隔）',
  `txn_status` enum('处理中','成功','失败','冲正','可疑冻结') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '处理中' COMMENT '交易状态',
  `is_overseas` tinyint(1) NULL DEFAULT 0 COMMENT '是否境外交易',
  `country_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'CN' COMMENT '交易对手所在国家代码（新增）',
  `device_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '设备指纹ID',
  `device_env` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '设备环境（模拟器/越狱/VPN/正常/新增）',
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '交易IP地址',
  `gps_location` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'GPS位置',
  `merchant_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '商户号（消费场景）',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注/用途说明',
  PRIMARY KEY (`txn_id`) USING BTREE,
  INDEX `idx_account_time`(`account_id` ASC, `txn_time` ASC) USING BTREE,
  INDEX `idx_counterparty`(`counterparty_account` ASC) USING BTREE,
  INDEX `idx_txn_time`(`txn_time` ASC) USING BTREE,
  INDEX `idx_status`(`txn_status` ASC) USING BTREE,
  INDEX `transaction_order_ibfk_2`(`txn_type_code` ASC) USING BTREE,
  INDEX `transaction_order_ibfk_3`(`channel_code` ASC) USING BTREE,
  CONSTRAINT `transaction_order_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `account_info` (`account_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `transaction_order_ibfk_2` FOREIGN KEY (`txn_type_code`) REFERENCES `transaction_type` (`txn_type_code`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `transaction_order_ibfk_3` FOREIGN KEY (`channel_code`) REFERENCES `product_channel` (`channel_code`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '交易订单主表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of transaction_order
-- ----------------------------
INSERT INTO `transaction_order` VALUES ('TXN001', 'ACC001', 'MCH001', '沃尔玛超市', 'T003', 'CH005', 356.00, 'CNY', '2026-08-10 18:30:00', '2026-08-10 18:29:58', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', 'M001', '超市购物');
INSERT INTO `transaction_order` VALUES ('TXN002', 'ACC001', 'MCH002', '星巴克咖啡', 'T003', 'CH005', 42.00, 'CNY', '2026-08-11 08:15:00', '2026-08-11 08:14:57', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', 'M002', '早餐咖啡');
INSERT INTO `transaction_order` VALUES ('TXN003', 'ACC001', 'ACC015', '韩冰', 'T001', 'CH001', 15000.00, 'CNY', '2026-08-09 10:00:00', '2026-08-09 09:59:55', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', NULL, '朋友借款还款');
INSERT INTO `transaction_order` VALUES ('TXN004', 'ACC001', 'MCH003', '京东商城', 'T003', 'CH005', 2399.00, 'CNY', '2026-08-08 20:00:00', '2026-08-08 19:59:50', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', 'M003', '购买手机');
INSERT INTO `transaction_order` VALUES ('TXN005', 'ACC002', 'ACC003', '王芳', 'T001', 'CH002', 600000.00, 'CNY', '2026-08-11 09:00:00', '2026-08-11 08:59:50', '成功', 0, 'CN', 'DEV_002', '正常', '192.168.2.10', '39.904,116.407', NULL, '工程款结算');
INSERT INTO `transaction_order` VALUES ('TXN006', 'ACC003', 'MCH004', '淘宝商城', 'T003', 'CH005', 15000.00, 'CNY', '2026-08-11 03:30:00', '2026-08-11 03:29:50', '成功', 0, 'CN', 'DEV_003', '正常', '10.0.0.10', '39.904,116.407', 'M004', '夜间大额购物');
INSERT INTO `transaction_order` VALUES ('TXN007', 'ACC003', 'MCH005', '美团外卖', 'T003', 'CH005', 45.00, 'CNY', '2026-08-11 02:00:00', '2026-08-11 01:59:55', '成功', 0, 'CN', 'DEV_003', '正常', '10.0.0.10', '39.904,116.407', 'M005', '宵夜');
INSERT INTO `transaction_order` VALUES ('TXN008', 'ACC004', 'MCH006', '苹果商城', 'T003', 'CH005', 9999.00, 'CNY', '2026-08-11 08:00:05', '2026-08-11 08:00:02', '成功', 0, 'CN', 'DEV_004', '正常', '172.16.0.10', '31.230,121.473', 'M006', '秒杀手机');
INSERT INTO `transaction_order` VALUES ('TXN009', 'ACC005', 'ACC001', '张伟', 'T001', 'CH001', 1000.00, 'CNY', '2026-08-11 07:00:00', '2026-08-11 06:59:50', '失败', 0, 'CN', 'DEV_005', '正常', '192.168.3.10', '23.129,113.264', NULL, '密码错误1');
INSERT INTO `transaction_order` VALUES ('TXN010', 'ACC005', 'ACC001', '张伟', 'T001', 'CH001', 1000.00, 'CNY', '2026-08-11 07:05:00', '2026-08-11 07:04:50', '失败', 0, 'CN', 'DEV_005', '正常', '192.168.3.10', '23.129,113.264', NULL, '密码错误2');
INSERT INTO `transaction_order` VALUES ('TXN011', 'ACC005', 'ACC001', '张伟', 'T001', 'CH001', 1000.00, 'CNY', '2026-08-11 07:10:00', '2026-08-11 07:09:50', '失败', 0, 'CN', 'DEV_005', '正常', '192.168.3.10', '23.129,113.264', NULL, '密码错误3');
INSERT INTO `transaction_order` VALUES ('TXN012', 'ACC006', 'ACC015', '韩冰', 'T001', 'CH001', 50000.00, 'CNY', '2026-08-11 10:00:00', '2026-08-11 09:59:50', '成功', 0, 'CN', 'DEV_006', '正常', '172.16.1.10', '31.230,121.473', NULL, '沉睡后突然转出');
INSERT INTO `transaction_order` VALUES ('TXN013', 'ACC007', 'MCH007', '商场消费', 'T003', 'CH004', 8500.00, 'CNY', '2026-08-10 18:00:00', '2026-08-10 17:59:50', '成功', 0, 'CN', 'DEV_007', '正常', '192.168.4.10', '22.543,114.058', 'M007', '奢侈品消费');
INSERT INTO `transaction_order` VALUES ('TXN014', 'ACC008', 'MCH008', '加油站', 'T003', 'CH004', 450.00, 'CNY', '2026-08-11 09:00:00', '2026-08-11 08:59:50', '成功', 0, 'CN', 'DEV_008', '正常', '192.168.5.10', '23.129,113.264', 'M008', '加油');
INSERT INTO `transaction_order` VALUES ('TXN015', 'ACC009', 'MCH009', '游戏平台', 'T003', 'CH005', 5000.00, 'CNY', '2026-08-11 13:00:00', '2026-08-11 12:59:50', '成功', 0, 'CN', 'DEV_009', '模拟器', '10.0.0.20', '39.904,116.407', 'M009', '模拟器充值');
INSERT INTO `transaction_order` VALUES ('TXN016', 'ACC010', 'ACC003', '王芳', 'T002', 'CH001', 20000.00, 'CNY', '2026-08-11 14:00:00', '2026-08-11 13:59:50', '成功', 0, 'CN', 'DEV_010', '正常', '192.168.6.10', '22.543,114.058', NULL, '对手方1');
INSERT INTO `transaction_order` VALUES ('TXN017', 'ACC010', 'ACC007', '吴敏', 'T002', 'CH001', 15000.00, 'CNY', '2026-08-11 14:30:00', '2026-08-11 14:29:50', '成功', 0, 'CN', 'DEV_010', '正常', '192.168.6.10', '22.543,114.058', NULL, '对手方2');
INSERT INTO `transaction_order` VALUES ('TXN018', 'ACC010', 'ACC013', '卫东', 'T002', 'CH001', 18000.00, 'CNY', '2026-08-11 15:00:00', '2026-08-11 14:59:50', '成功', 0, 'CN', 'DEV_010', '正常', '192.168.6.10', '22.543,114.058', NULL, '对手方3');
INSERT INTO `transaction_order` VALUES ('TXN019', 'ACC011', 'MCH010', '拼多多', 'T003', 'CH005', 100.00, 'CNY', '2026-08-11 10:00:00', '2026-08-11 09:59:50', '成功', 0, 'CN', 'DEV_SHARED', '正常', '192.168.7.10', '39.904,116.407', 'M010', '购物');
INSERT INTO `transaction_order` VALUES ('TXN020', 'ACC012', 'MCH010', '拼多多', 'T003', 'CH005', 200.00, 'CNY', '2026-08-11 10:05:00', '2026-08-11 10:04:50', '成功', 0, 'CN', 'DEV_SHARED', '正常', '192.168.7.10', '39.904,116.407', 'M010', '共用设备购物');
INSERT INTO `transaction_order` VALUES ('TXN021', 'ACC013', 'MCH011', '酒店消费', 'T003', 'CH005', 1200.00, 'CNY', '2026-08-10 20:00:00', '2026-08-10 19:59:50', '成功', 0, 'CN', 'DEV_013', '正常', '192.168.8.10', '31.230,121.473', 'M011', '住宿');
INSERT INTO `transaction_order` VALUES ('TXN022', 'ACC014', 'MCH012', '家装公司', 'T003', 'CH004', 30000.00, 'CNY', '2026-08-10 11:00:00', '2026-08-10 10:59:50', '成功', 0, 'CN', 'DEV_014', '正常', '192.168.9.10', '23.129,113.264', 'M012', '装修首付款');
INSERT INTO `transaction_order` VALUES ('TXN023', 'ACC015', 'ACC002', '李强', 'T002', 'CH002', 1000000.00, 'CNY', '2026-08-11 16:00:00', '2026-08-11 15:59:50', '成功', 0, 'CN', 'DEV_015', '正常', '192.168.10.10', '22.543,114.058', NULL, '货款回收');
INSERT INTO `transaction_order` VALUES ('TXN024', 'ACC001', 'MCH013', '便利店', 'T003', 'CH005', 15.50, 'CNY', '2026-08-10 07:00:00', '2026-08-10 06:59:50', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', 'M013', '早餐');
INSERT INTO `transaction_order` VALUES ('TXN025', 'ACC001', 'MCH014', '地铁', 'T003', 'CH005', 5.00, 'CNY', '2026-08-10 08:00:00', '2026-08-10 07:59:50', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', 'M014', '交通');
INSERT INTO `transaction_order` VALUES ('TXN026', 'ACC003', 'MCH015', '药店', 'T003', 'CH005', 89.00, 'CNY', '2026-08-10 22:00:00', '2026-08-10 21:59:50', '成功', 0, 'CN', 'DEV_003', '正常', '10.0.0.10', '39.904,116.407', 'M015', '夜间买药');
INSERT INTO `transaction_order` VALUES ('TXN027', 'ACC004', 'MCH016', '餐厅', 'T003', 'CH005', 230.00, 'CNY', '2026-08-10 12:00:00', '2026-08-10 11:59:50', '成功', 0, 'CN', 'DEV_004', '正常', '172.16.0.10', '31.230,121.473', 'M016', '午餐');
INSERT INTO `transaction_order` VALUES ('TXN028', 'ACC007', 'MCH017', '服装店', 'T003', 'CH004', 3200.00, 'CNY', '2026-08-09 15:00:00', '2026-08-09 14:59:50', '成功', 0, 'CN', 'DEV_007', '正常', '192.168.4.10', '22.543,114.058', 'M017', '买衣服');
INSERT INTO `transaction_order` VALUES ('TXN029', 'ACC008', 'MCH018', '超市', 'T003', 'CH005', 210.00, 'CNY', '2026-08-10 16:00:00', '2026-08-10 15:59:50', '成功', 0, 'CN', 'DEV_008', '正常', '192.168.5.10', '23.129,113.264', 'M018', '日用品');
INSERT INTO `transaction_order` VALUES ('TXN030', 'ACC013', 'MCH019', '理发店', 'T003', 'CH005', 60.00, 'CNY', '2026-08-09 19:00:00', '2026-08-09 18:59:50', '成功', 0, 'CN', 'DEV_013', '正常', '192.168.8.10', '31.230,121.473', 'M019', '理发');
INSERT INTO `transaction_order` VALUES ('TXN031', 'ACC014', 'MCH020', '书店', 'T003', 'CH005', 120.00, 'CNY', '2026-08-09 14:00:00', '2026-08-09 13:59:50', '成功', 0, 'CN', 'DEV_014', '正常', '192.168.9.10', '23.129,113.264', 'M020', '买书');
INSERT INTO `transaction_order` VALUES ('TXN032', 'ACC015', 'MCH021', '电子市场', 'T003', 'CH005', 4500.00, 'CNY', '2026-08-10 15:00:00', '2026-08-10 14:59:50', '成功', 0, 'CN', 'DEV_015', '正常', '192.168.10.10', '22.543,114.058', 'M021', '采购');
INSERT INTO `transaction_order` VALUES ('TXN033', 'ACC002', 'MCH022', '物业费', 'T003', 'CH005', 3000.00, 'CNY', '2026-08-10 08:00:00', '2026-08-10 07:59:50', '成功', 0, 'CN', 'DEV_002', '正常', '192.168.2.10', '39.904,116.407', 'M022', '公司物业');
INSERT INTO `transaction_order` VALUES ('TXN034', 'ACC005', 'MCH023', '话费充值', 'T003', 'CH005', 100.00, 'CNY', '2026-08-10 09:00:00', '2026-08-10 08:59:50', '成功', 0, 'CN', 'DEV_005', '正常', '192.168.3.10', '23.129,113.264', 'M023', '话费');
INSERT INTO `transaction_order` VALUES ('TXN035', 'ACC006', 'MCH024', '医院', 'T003', 'CH004', 800.00, 'CNY', '2026-05-01 10:00:00', '2026-05-01 09:59:50', '成功', 0, 'CN', 'DEV_006', '正常', '172.16.1.10', '31.230,121.473', 'M024', '挂号费');
INSERT INTO `transaction_order` VALUES ('TXN036', 'ACC009', 'MCH025', '网吧', 'T003', 'CH005', 50.00, 'CNY', '2026-08-10 22:00:00', '2026-08-10 21:59:50', '成功', 0, 'CN', 'DEV_009', '正常', '10.0.0.20', '39.904,116.407', 'M025', '上网');
INSERT INTO `transaction_order` VALUES ('TXN037', 'ACC011', 'MCH026', '奶茶店', 'T003', 'CH005', 35.00, 'CNY', '2026-08-10 16:00:00', '2026-08-10 15:59:50', '成功', 0, 'CN', 'DEV_SHARED', '正常', '192.168.7.10', '39.904,116.407', 'M026', '奶茶');
INSERT INTO `transaction_order` VALUES ('TXN038', 'ACC012', 'MCH027', '蛋糕店', 'T003', 'CH005', 80.00, 'CNY', '2026-08-10 17:00:00', '2026-08-10 16:59:50', '成功', 0, 'CN', 'DEV_SHARED', '正常', '192.168.7.10', '39.904,116.407', 'M027', '蛋糕');
INSERT INTO `transaction_order` VALUES ('TXN039', 'ACC001', 'MCH028', '电影票', 'T003', 'CH005', 120.00, 'CNY', '2026-08-07 20:00:00', '2026-08-07 19:59:50', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', 'M028', '电影');
INSERT INTO `transaction_order` VALUES ('TXN040', 'ACC002', 'ACC005', '孙丽', 'T001', 'CH002', 20000.00, 'CNY', '2026-08-08 11:00:00', '2026-08-08 10:59:50', '成功', 0, 'CN', 'DEV_002', '正常', '192.168.2.10', '39.904,116.407', NULL, '报销');
INSERT INTO `transaction_order` VALUES ('TXN041', 'ACC003', 'ACC010', '冯丽', 'T001', 'CH001', 8000.00, 'CNY', '2026-08-10 01:00:00', '2026-08-10 00:59:50', '成功', 0, 'CN', 'DEV_003', '正常', '10.0.0.10', '39.904,116.407', NULL, '夜间转账');
INSERT INTO `transaction_order` VALUES ('TXN042', 'ACC004', 'MCH029', '数码店', 'T003', 'CH005', 6700.00, 'CNY', '2026-08-09 11:00:00', '2026-08-09 10:59:50', '成功', 0, 'CN', 'DEV_004', '正常', '172.16.0.10', '31.230,121.473', 'M029', '买耳机');
INSERT INTO `transaction_order` VALUES ('TXN043', 'ACC007', 'MCH030', '健身房', 'T003', 'CH005', 3000.00, 'CNY', '2026-08-08 19:00:00', '2026-08-08 18:59:50', '成功', 0, 'CN', 'DEV_007', '正常', '192.168.4.10', '22.543,114.058', 'M030', '健身年卡');
INSERT INTO `transaction_order` VALUES ('TXN044', 'ACC008', 'MCH031', '水果店', 'T003', 'CH005', 158.00, 'CNY', '2026-08-09 18:00:00', '2026-08-09 17:59:50', '成功', 0, 'CN', 'DEV_008', '正常', '192.168.5.10', '23.129,113.264', 'M031', '水果');
INSERT INTO `transaction_order` VALUES ('TXN045', 'ACC013', 'MCH032', '洗车店', 'T003', 'CH005', 80.00, 'CNY', '2026-08-08 16:00:00', '2026-08-08 15:59:50', '成功', 0, 'CN', 'DEV_013', '正常', '192.168.8.10', '31.230,121.473', 'M032', '洗车');
INSERT INTO `transaction_order` VALUES ('TXN046', 'ACC014', 'MCH033', '眼镜店', 'T003', 'CH005', 600.00, 'CNY', '2026-08-07 12:00:00', '2026-08-07 11:59:50', '成功', 0, 'CN', 'DEV_014', '正常', '192.168.9.10', '23.129,113.264', 'M033', '配镜');
INSERT INTO `transaction_order` VALUES ('TXN047', 'ACC015', 'ACC001', '张伟', 'T001', 'CH002', 50000.00, 'CNY', '2026-08-09 14:00:00', '2026-08-09 13:59:50', '成功', 0, 'CN', 'DEV_015', '正常', '192.168.10.10', '22.543,114.058', NULL, '转账');
INSERT INTO `transaction_order` VALUES ('TXN048', 'ACC001', 'MCH034', '宠物店', 'T003', 'CH005', 200.00, 'CNY', '2026-08-06 10:00:00', '2026-08-06 09:59:50', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', 'M034', '宠物粮');
INSERT INTO `transaction_order` VALUES ('TXN049', 'ACC002', 'ACC007', '吴敏', 'T001', 'CH002', 150000.00, 'CNY', '2026-08-07 09:00:00', '2026-08-07 08:59:50', '成功', 0, 'CN', 'DEV_002', '正常', '192.168.2.10', '39.904,116.407', NULL, '业务往来');
INSERT INTO `transaction_order` VALUES ('TXN050', 'ACC003', 'MCH035', '夜间药店', 'T003', 'CH005', 56.00, 'CNY', '2026-08-09 04:00:00', '2026-08-09 03:59:50', '成功', 0, 'CN', 'DEV_003', '正常', '10.0.0.10', '39.904,116.407', 'M035', '买药');
INSERT INTO `transaction_order` VALUES ('TXN051', 'ACC004', 'MCH036', '鲜花店', 'T003', 'CH005', 180.00, 'CNY', '2026-08-08 17:00:00', '2026-08-08 16:59:50', '成功', 0, 'CN', 'DEV_004', '正常', '172.16.0.10', '31.230,121.473', 'M036', '鲜花');
INSERT INTO `transaction_order` VALUES ('TXN052', 'ACC005', 'MCH037', '文具店', 'T003', 'CH005', 35.00, 'CNY', '2026-08-09 10:00:00', '2026-08-09 09:59:50', '成功', 0, 'CN', 'DEV_005', '正常', '192.168.3.10', '23.129,113.264', 'M037', '文具');
INSERT INTO `transaction_order` VALUES ('TXN053', 'ACC006', 'MCH038', '物业费', 'T003', 'CH005', 1500.00, 'CNY', '2026-05-15 09:00:00', '2026-05-15 08:59:50', '成功', 0, 'CN', 'DEV_006', '正常', '172.16.1.10', '31.230,121.473', 'M038', '物业费');
INSERT INTO `transaction_order` VALUES ('TXN054', 'ACC007', 'MCH039', '家具店', 'T003', 'CH004', 12000.00, 'CNY', '2026-08-07 14:00:00', '2026-08-07 13:59:50', '成功', 0, 'CN', 'DEV_007', '正常', '192.168.4.10', '22.543,114.058', 'M039', '买家具');
INSERT INTO `transaction_order` VALUES ('TXN055', 'ACC008', 'MCH040', '餐饮店', 'T003', 'CH005', 320.00, 'CNY', '2026-08-08 12:00:00', '2026-08-08 11:59:50', '成功', 0, 'CN', 'DEV_008', '正常', '192.168.5.10', '23.129,113.264', 'M040', '聚餐');
INSERT INTO `transaction_order` VALUES ('TXN056', 'ACC009', 'MCH041', '游戏充值', 'T003', 'CH005', 1000.00, 'CNY', '2026-08-10 23:00:00', '2026-08-10 22:59:50', '成功', 0, 'CN', 'DEV_009', '模拟器', '10.0.0.20', '39.904,116.407', 'M041', '游戏点券');
INSERT INTO `transaction_order` VALUES ('TXN057', 'ACC010', 'ACC004', '赵磊', 'T001', 'CH001', 5000.00, 'CNY', '2026-08-10 16:00:00', '2026-08-10 15:59:50', '成功', 0, 'CN', 'DEV_010', '正常', '192.168.6.10', '22.543,114.058', NULL, '还款');
INSERT INTO `transaction_order` VALUES ('TXN058', 'ACC011', 'MCH042', '便利店', 'T003', 'CH005', 12.00, 'CNY', '2026-08-09 08:00:00', '2026-08-09 07:59:50', '成功', 0, 'CN', 'DEV_SHARED', '正常', '192.168.7.10', '39.904,116.407', 'M042', '买水');
INSERT INTO `transaction_order` VALUES ('TXN059', 'ACC012', 'MCH043', '零食店', 'T003', 'CH005', 45.00, 'CNY', '2026-08-09 09:00:00', '2026-08-09 08:59:50', '成功', 0, 'CN', 'DEV_SHARED', '正常', '192.168.7.10', '39.904,116.407', 'M043', '零食');
INSERT INTO `transaction_order` VALUES ('TXN060', 'ACC013', 'MCH044', '汽车保养', 'T003', 'CH005', 1800.00, 'CNY', '2026-08-07 10:00:00', '2026-08-07 09:59:50', '成功', 0, 'CN', 'DEV_013', '正常', '192.168.8.10', '31.230,121.473', 'M044', '保养');
INSERT INTO `transaction_order` VALUES ('TXN061', 'ACC014', 'MCH045', '办公用品', 'T003', 'CH005', 430.00, 'CNY', '2026-08-06 09:00:00', '2026-08-06 08:59:50', '成功', 0, 'CN', 'DEV_014', '正常', '192.168.9.10', '23.129,113.264', 'M045', '办公用品');
INSERT INTO `transaction_order` VALUES ('TXN062', 'ACC015', 'ACC003', '王芳', 'T001', 'CH002', 30000.00, 'CNY', '2026-08-08 10:00:00', '2026-08-08 09:59:50', '成功', 0, 'CN', 'DEV_015', '正常', '192.168.10.10', '22.543,114.058', NULL, '转账');
INSERT INTO `transaction_order` VALUES ('TXN063', 'ACC001', 'MCH046', '咖啡店', 'T003', 'CH005', 38.00, 'CNY', '2026-08-05 08:00:00', '2026-08-05 07:59:50', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', 'M046', '咖啡');
INSERT INTO `transaction_order` VALUES ('TXN064', 'ACC002', 'MCH047', '办公房租', 'T003', 'CH005', 45000.00, 'CNY', '2026-08-01 09:00:00', '2026-08-01 08:59:50', '成功', 0, 'CN', 'DEV_002', '正常', '192.168.2.10', '39.904,116.407', 'M047', '房租');
INSERT INTO `transaction_order` VALUES ('TXN065', 'ACC004', 'MCH048', '电子产品', 'T003', 'CH005', 12800.00, 'CNY', '2026-08-07 15:00:00', '2026-08-07 14:59:50', '成功', 0, 'CN', 'DEV_004', '正常', '172.16.0.10', '31.230,121.473', 'M048', '笔记本');
INSERT INTO `transaction_order` VALUES ('TXN066', 'ACC007', 'MCH049', '珠宝店', 'T003', 'CH004', 25000.00, 'CNY', '2026-08-06 16:00:00', '2026-08-06 15:59:50', '成功', 0, 'CN', 'DEV_007', '正常', '192.168.4.10', '22.543,114.058', 'M049', '首饰');
INSERT INTO `transaction_order` VALUES ('TXN067', 'ACC008', 'MCH050', '家电城', 'T003', 'CH005', 6000.00, 'CNY', '2026-08-07 14:00:00', '2026-08-07 13:59:50', '成功', 0, 'CN', 'DEV_008', '正常', '192.168.5.10', '23.129,113.264', 'M050', '电视');
INSERT INTO `transaction_order` VALUES ('TXN068', 'ACC010', 'ACC013', '卫东', 'T001', 'CH001', 12000.00, 'CNY', '2026-08-09 12:00:00', '2026-08-09 11:59:50', '成功', 0, 'CN', 'DEV_010', '正常', '192.168.6.10', '22.543,114.058', NULL, '借款');
INSERT INTO `transaction_order` VALUES ('TXN069', 'ACC013', 'MCH051', '健身房续费', 'T003', 'CH005', 2000.00, 'CNY', '2026-08-06 18:00:00', '2026-08-06 17:59:50', '成功', 0, 'CN', 'DEV_013', '正常', '192.168.8.10', '31.230,121.473', 'M051', '健身');
INSERT INTO `transaction_order` VALUES ('TXN070', 'ACC014', 'MCH052', '教育机构', 'T003', 'CH005', 8000.00, 'CNY', '2026-08-05 10:00:00', '2026-08-05 09:59:50', '成功', 0, 'CN', 'DEV_014', '正常', '192.168.9.10', '23.129,113.264', 'M052', '培训费');
INSERT INTO `transaction_order` VALUES ('TXN071', 'ACC015', 'MCH053', '建筑材料', 'T003', 'CH005', 200000.00, 'CNY', '2026-08-07 11:00:00', '2026-08-07 10:59:50', '成功', 0, 'CN', 'DEV_015', '正常', '192.168.10.10', '22.543,114.058', 'M053', '建材');
INSERT INTO `transaction_order` VALUES ('TXN072', 'ACC001', 'ACC006', '周明', 'T001', 'CH001', 3000.00, 'CNY', '2026-08-04 15:00:00', '2026-08-04 14:59:50', '成功', 0, 'CN', 'DEV_001', '正常', '192.168.1.10', '22.543,114.058', NULL, '还款');
INSERT INTO `transaction_order` VALUES ('TXN073', 'ACC003', 'ACC011', '陈勇', 'T001', 'CH001', 2000.00, 'CNY', '2026-08-08 02:00:00', '2026-08-08 01:59:50', '成功', 0, 'CN', 'DEV_003', '正常', '10.0.0.10', '39.904,116.407', NULL, '夜间转账');
INSERT INTO `transaction_order` VALUES ('TXN074', 'ACC005', 'MCH054', '医疗费用', 'T003', 'CH005', 2500.00, 'CNY', '2026-08-08 08:00:00', '2026-08-08 07:59:50', '成功', 0, 'CN', 'DEV_005', '正常', '192.168.3.10', '23.129,113.264', 'M054', '看病');
INSERT INTO `transaction_order` VALUES ('TXN075', 'ACC009', 'ACC010', '冯丽', 'T001', 'CH001', 3000.00, 'CNY', '2026-08-10 21:00:00', '2026-08-10 20:59:50', '成功', 0, 'CN', 'DEV_009', '模拟器', '10.0.0.20', '39.904,116.407', NULL, '转账');
INSERT INTO `transaction_order` VALUES ('TXN076', 'ACC011', 'ACC015', '韩冰', 'T001', 'CH001', 1500.00, 'CNY', '2026-08-08 14:00:00', '2026-08-08 13:59:50', '成功', 0, 'CN', 'DEV_SHARED', '正常', '192.168.7.10', '39.904,116.407', NULL, '转账');
INSERT INTO `transaction_order` VALUES ('TXN077', 'ACC012', 'MCH055', '外卖', 'T003', 'CH005', 30.00, 'CNY', '2026-08-08 12:00:00', '2026-08-08 11:59:50', '成功', 0, 'CN', 'DEV_SHARED', '正常', '192.168.7.10', '39.904,116.407', 'M055', '午餐');
INSERT INTO `transaction_order` VALUES ('TXN078', 'ACC004', 'MCH056', '机票', 'T003', 'CH005', 2400.00, 'CNY', '2026-08-06 20:00:00', '2026-08-06 19:59:50', '成功', 0, 'CN', 'DEV_004', '正常', '172.16.0.10', '31.230,121.473', 'M056', '机票');
INSERT INTO `transaction_order` VALUES ('TXN079', 'ACC008', 'MCH057', '超市', 'T003', 'CH005', 89.00, 'CNY', '2026-08-06 17:00:00', '2026-08-06 16:59:50', '成功', 0, 'CN', 'DEV_008', '正常', '192.168.5.10', '23.129,113.264', 'M057', '购物');
INSERT INTO `transaction_order` VALUES ('TXN080', 'ACC010', 'ACC002', '李强', 'T001', 'CH001', 25000.00, 'CNY', '2026-08-08 13:00:00', '2026-08-08 12:59:50', '成功', 0, 'CN', 'DEV_010', '正常', '192.168.6.10', '22.543,114.058', NULL, '货款');

-- ----------------------------
-- Table structure for transaction_type
-- ----------------------------
DROP TABLE IF EXISTS `transaction_type`;
CREATE TABLE `transaction_type`  (
  `txn_type_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '交易类型编码',
  `txn_type_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '交易类型名称',
  `is_credit` tinyint(1) NULL DEFAULT 0 COMMENT '是否贷记（入账）',
  `is_debit` tinyint(1) NULL DEFAULT 1 COMMENT '是否借记（出账）',
  `is_cash` tinyint(1) NULL DEFAULT 0 COMMENT '是否现金交易',
  PRIMARY KEY (`txn_type_code`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '交易类型表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of transaction_type
-- ----------------------------
INSERT INTO `transaction_type` VALUES ('T001', '转账汇款', 0, 1, 0);
INSERT INTO `transaction_type` VALUES ('T002', '转入收款', 1, 0, 0);
INSERT INTO `transaction_type` VALUES ('T003', '消费支付', 0, 1, 0);
INSERT INTO `transaction_type` VALUES ('T004', '现金取款', 0, 1, 1);
INSERT INTO `transaction_type` VALUES ('T005', '现金存款', 1, 0, 1);
INSERT INTO `transaction_type` VALUES ('T006', '理财申购', 0, 1, 0);
INSERT INTO `transaction_type` VALUES ('T007', '理财赎回', 1, 0, 0);
INSERT INTO `transaction_type` VALUES ('T008', '贷款放款', 1, 0, 0);

-- ----------------------------
-- Table structure for user_info
-- ----------------------------
DROP TABLE IF EXISTS `user_info`;
CREATE TABLE `user_info`  (
  `user_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '客户ID（全局唯一，关联账户）',
  `full_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '法定姓名（与身份证一致）',
  `id_card_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '身份证号（AES-256加密存储）',
  `phone_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '手机号（AES-256加密存储）',
  `email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '电子邮箱（加密存储）',
  `gender` enum('M','F','U') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'U' COMMENT '性别：M男/F女/U未知',
  `birth_date` date NOT NULL COMMENT '出生日期',
  `nationality` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'CN' COMMENT '国籍（CN-中国）',
  `education` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '学历（博士/硕士/本科/大专/高中及以下）',
  `occupation` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '职业类别（公务员/企业职员/自由职业/学生/退休/无业）',
  `annual_income` decimal(18, 2) NULL DEFAULT NULL COMMENT '年收入（元）',
  `marital_status` enum('未婚','已婚','离异','丧偶') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '婚姻状况',
  `emergency_contact_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '紧急联系人姓名',
  `emergency_contact_phone` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '紧急联系人电话（加密）',
  `kyc_status` enum('未认证','基础认证','高级认证') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '未认证' COMMENT 'KYC认证等级（监管核心字段）',
  `risk_tolerance` enum('保守型','稳健型','进取型') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '风险承受能力（合规适当性管理）',
  `is_politically_exposed` tinyint(1) NULL DEFAULT 0 COMMENT '是否为政治敏感人物(PEP)（反洗钱关键）',
  `register_source` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'APP' COMMENT '注册渠道（APP/Web/柜面/第三方）',
  `register_ip` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '注册IP地址',
  `register_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
  `last_login_time` timestamp NULL DEFAULT NULL COMMENT '最后登录时间',
  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '信息更新时间',
  PRIMARY KEY (`user_id`) USING BTREE,
  UNIQUE INDEX `uk_id_card`(`id_card_no` ASC) USING BTREE COMMENT '身份证唯一索引（加密后仍可去重）',
  UNIQUE INDEX `uk_phone`(`phone_no` ASC) USING BTREE COMMENT '手机号唯一索引',
  INDEX `idx_kyc_status`(`kyc_status` ASC) USING BTREE,
  INDEX `idx_register_time`(`register_time` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '客户基础信息表（符合央行KYC与反洗钱要求）' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of user_info
-- ----------------------------
INSERT INTO `user_info` VALUES ('ACC001', '张伟', 'ENC_110101199001011234', 'ENC_13800000001', 'zhangwei@email.com', 'M', '1990-01-01', 'CN', '本科', '企业职员', 180000.00, '已婚', '李梅', 'ENC_13900000001', '高级认证', '稳健型', 0, 'APP', '192.168.1.10', '2024-01-01 10:00:00', '2026-08-11 08:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC002', '李强', 'ENC_110101198512152345', 'ENC_13800000002', 'liqiang@company.com', 'M', '1985-12-15', 'CN', '硕士', '企业主', 960000.00, '已婚', '王芳', 'ENC_13900000002', '高级认证', '进取型', 0, 'Web', '192.168.2.10', '2023-06-01 14:00:00', '2026-08-11 08:30:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC003', '王芳', 'ENC_110101199205203456', 'ENC_13800000003', 'wangfang@email.com', 'F', '1992-05-20', 'CN', '大专', '自由职业', 96000.00, '未婚', '刘洋', 'ENC_13900000003', '基础认证', '稳健型', 0, 'APP', '10.0.0.10', '2024-09-01 08:00:00', '2026-08-11 01:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC004', '赵磊', 'ENC_110101198808184567', 'ENC_13800000004', 'zhaolei@email.com', 'M', '1988-08-18', 'CN', '硕士', '企业职员', 240000.00, '已婚', '孙悦', 'ENC_13900000004', '高级认证', '进取型', 0, 'APP', '172.16.0.10', '2023-11-11 11:00:00', '2026-08-11 07:30:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC005', '孙丽', 'ENC_110101199607225678', 'ENC_13800000005', 'sunli@email.com', 'F', '1996-07-22', 'CN', '本科', '企业职员', 72000.00, '未婚', '周涛', 'ENC_13900000005', '基础认证', '保守型', 0, 'APP', '192.168.3.10', '2025-02-14 09:00:00', '2026-08-11 07:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC006', '周明', 'ENC_110101197309016789', 'ENC_13800000006', 'zhouming@email.com', 'M', '1973-09-01', 'CN', '大专', '退休', 120000.00, '已婚', '吴静', 'ENC_13900000006', '高级认证', '保守型', 0, '柜面', '172.16.1.10', '2010-05-01 09:00:00', '2026-05-01 10:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC007', '吴敏', 'ENC_110101198910103456', 'ENC_13800000007', 'wumin@email.com', 'F', '1989-10-10', 'CN', '本科', '企业职员', 144000.00, '已婚', '郑浩', 'ENC_13900000007', '高级认证', '稳健型', 0, 'APP', '192.168.4.10', '2023-01-01 10:00:00', '2026-08-10 12:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC008', '郑浩', 'ENC_110101199503124567', 'ENC_13800000008', 'zhenghao@email.com', 'M', '1995-03-12', 'CN', '本科', '企业职员', 108000.00, '已婚', '孙丽', 'ENC_13900000008', '基础认证', '稳健型', 0, 'APP', '192.168.5.10', '2022-08-15 15:00:00', '2026-08-11 09:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC009', '钱华', 'ENC_110101198601135678', 'ENC_13800000009', 'qianhua@email.com', 'M', '1986-01-13', 'CN', '本科', '学生', 60000.00, '未婚', '李娜', 'ENC_13900000009', '未认证', '进取型', 0, 'H5', '10.0.0.20', '2025-12-01 20:00:00', '2026-08-11 12:50:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC010', '冯丽', 'ENC_110101199108145678', 'ENC_13800000010', 'fengli@email.com', 'F', '1991-08-14', 'CN', '大专', '自由职业', 84000.00, '离异', '赵岩', 'ENC_13900000010', '基础认证', '进取型', 0, 'APP', '192.168.6.10', '2024-07-01 16:00:00', '2026-08-11 14:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC011', '陈勇', 'ENC_110101198712156789', 'ENC_13800000011', 'chenyong@email.com', 'M', '1987-12-15', 'CN', '高中', '学生', 36000.00, '未婚', '刘芳', 'ENC_13900000011', '未认证', '进取型', 0, 'APP', '192.168.7.10', '2026-01-01 00:00:00', '2026-08-10 16:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC012', '褚霞', 'ENC_110101199309166789', 'ENC_13800000012', 'chuxia@email.com', 'F', '1993-09-16', 'CN', '高中', '无业', 0.00, '未婚', '陈刚', 'ENC_13900000012', '未认证', NULL, 0, 'APP', '192.168.7.10', '2026-01-15 00:00:00', '2026-08-10 17:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC013', '卫东', 'ENC_110101197405175678', 'ENC_13800000013', 'weidong@email.com', 'M', '1974-05-17', 'CN', '硕士', '企业职员', 180000.00, '已婚', '王琳', 'ENC_13900000013', '基础认证', '稳健型', 0, 'Web', '192.168.8.10', '2020-03-01 08:00:00', '2026-08-10 18:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC014', '蒋欣', 'ENC_110101198806187890', 'ENC_13800000014', 'jiangxin@email.com', 'F', '1988-06-18', 'CN', '硕士', '企业职员', 300000.00, '已婚', '张宇', 'ENC_13900000014', '高级认证', '进取型', 0, 'APP', '192.168.9.10', '2024-04-01 09:00:00', '2026-08-10 11:00:00', '2026-08-12 00:53:38');
INSERT INTO `user_info` VALUES ('ACC015', '韩冰', 'ENC_110101199511198901', 'ENC_13800000015', 'hanbing@company.com', 'M', '1995-11-19', 'CN', '硕士', '企业主', 1200000.00, '已婚', '赵雪', 'ENC_13900000015', '高级认证', '进取型', 0, 'Web', '192.168.10.10', '2023-10-01 10:00:00', '2026-08-11 16:00:00', '2026-08-12 00:53:38');

-- ----------------------------
-- Table structure for user_operation_log
-- ----------------------------
DROP TABLE IF EXISTS `user_operation_log`;
CREATE TABLE `user_operation_log`  (
  `op_id` bigint NOT NULL AUTO_INCREMENT,
  `account_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `op_type` enum('登录','修改密码','修改手机号','修改邮箱','找回密码','绑定银行卡','解绑设备','修改支付密码') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '操作类型',
  `op_time` timestamp NOT NULL COMMENT '操作时间',
  `op_result` enum('成功','失败') CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '成功',
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `device_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `client_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '客户端类型（APP/H5/Web）',
  PRIMARY KEY (`op_id`) USING BTREE,
  INDEX `idx_account_time`(`account_id` ASC, `op_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 9 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户操作日志表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of user_operation_log
-- ----------------------------
INSERT INTO `user_operation_log` VALUES (1, 'ACC013', '修改密码', '2026-08-05 09:00:00', '成功', '192.168.8.10', 'DEV_013', 'APP');
INSERT INTO `user_operation_log` VALUES (2, 'ACC013', '修改密码', '2026-08-08 10:00:00', '成功', '192.168.8.10', 'DEV_013', 'APP');
INSERT INTO `user_operation_log` VALUES (3, 'ACC013', '修改手机号', '2026-08-09 11:00:00', '成功', '192.168.8.10', 'DEV_013', 'Web');
INSERT INTO `user_operation_log` VALUES (4, 'ACC004', '找回密码', '2026-08-11 07:30:00', '成功', '172.16.0.10', 'DEV_004', 'APP');
INSERT INTO `user_operation_log` VALUES (5, 'ACC009', '登录', '2026-08-11 12:50:00', '成功', '10.0.0.20', 'DEV_009', 'H5');
INSERT INTO `user_operation_log` VALUES (6, 'ACC001', '登录', '2026-08-11 08:00:00', '成功', '192.168.1.10', 'DEV_001', 'APP');
INSERT INTO `user_operation_log` VALUES (7, 'ACC002', '登录', '2026-08-11 08:30:00', '成功', '192.168.2.10', 'DEV_002', 'Web');
INSERT INTO `user_operation_log` VALUES (8, 'ACC003', '登录', '2026-08-11 01:00:00', '成功', '10.0.0.10', 'DEV_003', 'APP');

SET FOREIGN_KEY_CHECKS = 1;

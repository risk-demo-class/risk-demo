-- ============================================
-- 银行风控系统 - 业务测试数据
-- 8 张表, 含正常用户和 5 种风险模式用户
-- ============================================

USE bank_risk;

SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 1. IP 地理位置 (需先插入)
-- ============================
INSERT IGNORE INTO ip_geo_location (ip, country, province, city, isp, is_proxy, is_tor) VALUES
('192.168.1.1', '中国', '北京', '北京', '联通', 0, 0),
('10.0.0.1', '中国', '上海', '上海', '电信', 0, 0),
('172.16.0.1', '中国', '广东', '广州', '移动', 0, 0),
('203.0.113.1', '中国', '浙江', '杭州', '联通', 0, 0),
('198.51.100.1', '中国', '江苏', '南京', '电信', 0, 0),
('185.220.101.1', '德国', NULL, NULL, 'Unknown', 1, 1),
('91.121.100.1', '法国', NULL, NULL, 'OVH', 1, 0),
('45.33.32.156', '美国', 'California', 'San Jose', 'Linode', 1, 0),
('222.73.55.1', '中国', '福建', '福州', '电信', 0, 0),
('218.75.100.1', '中国', '浙江', '宁波', '移动', 0, 0),
('61.160.200.1', '中国', '江苏', '苏州', '联通', 0, 0),
('113.87.180.1', '中国', '广东', '深圳', '电信', 0, 0);

-- ============================
-- 2. 用户信息 (8 个, 含 5 个 RISK 风险用户)
-- ============================
INSERT IGNORE INTO user_info (user_id, name, id_card_hash, credit_score, register_at, kyc_level) VALUES
('U1001', '张三', 'a1b2c3d4e5f6...hash1', 720, '2023-06-15 10:00:00', 'L3'),
('U1002', '李四', 'b2c3d4e5f6a7...hash2', 680, '2023-08-20 14:30:00', 'L2'),
('U1003', '王五', 'c3d4e5f6a7b8...hash3', 550, '2024-01-10 09:00:00', 'L1'),
('RISK001', '赵六-异地大额', 'd4e5f6a7b8c9...hash4', 650, DATE_SUB(NOW(), INTERVAL 180 DAY), 'L2'),
('RISK002', '钱七-凌晨密集', 'e5f6a7b8c9d0...hash5', 580, DATE_SUB(NOW(), INTERVAL 90 DAY), 'L2'),
('RISK003', '孙八-新设备大额', 'f6a7b8c9d0e1...hash6', 620, DATE_SUB(NOW(), INTERVAL 30 DAY), 'L1'),
('RISK004', '周九-多卡归集', 'a7b8c9d0e1f2...hash7', 500, DATE_SUB(NOW(), INTERVAL 200 DAY), 'L2'),
('RISK005', '吴十-代理IP', 'b8c9d0e1f2a3...hash8', 600, DATE_SUB(NOW(), INTERVAL 60 DAY), 'L1');

-- ============================
-- 3. 设备指纹
-- ============================
INSERT IGNORE INTO device_fingerprint (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser) VALUES
('DEV_A001', 'U1001', 'fp_hash_001', '2023-06-15 10:05:00', NOW(), 'iOS 17', 'Safari'),
('DEV_A002', 'U1001', 'fp_hash_002', '2024-03-01 08:00:00', NOW(), 'Windows 11', 'Chrome'),
('DEV_B001', 'U1002', 'fp_hash_003', '2023-08-20 14:35:00', NOW(), 'Android 14', 'Chrome'),
('DEV_C001', 'U1003', 'fp_hash_004', '2024-01-10 09:05:00', NOW(), 'Windows 10', 'Edge'),
('DEV_R001', 'RISK001', 'fp_hash_005', DATE_SUB(NOW(), INTERVAL 180 DAY), NOW(), 'iOS 17', 'Safari'),
('DEV_R002', 'RISK002', 'fp_hash_006', DATE_SUB(NOW(), INTERVAL 90 DAY), NOW(), 'Android 14', 'Chrome'),
('DEV_R003', 'RISK003', 'fp_hash_007', DATE_SUB(NOW(), INTERVAL 25 DAY), NOW(), 'Windows 11', 'Chrome'),
('DEV_R004', 'RISK004', 'fp_hash_008', DATE_SUB(NOW(), INTERVAL 200 DAY), NOW(), 'iOS 17', 'Safari'),
('DEV_R005', 'RISK005', 'fp_hash_009', DATE_SUB(NOW(), INTERVAL 60 DAY), NOW(), 'Android 14', 'Firefox'),
('DEV_R005B', 'RISK005', 'fp_hash_010', DATE_SUB(NOW(), INTERVAL 30 DAY), NOW(), 'Windows 10', 'Chrome');

-- ============================
-- 4. 黑名单扩展
-- ============================
INSERT IGNORE INTO blacklist_extra (type, value, reason) VALUES
('IP', '185.220.101.1', '已知代理IP池'),
('银行卡号', 'card_hash_bad_001', '历史欺诈卡号'),
('设备指纹', 'fp_hash_fraud', '疑似欺诈设备');

-- ============================
-- 5. 银行卡 (每用户 1-4 张)
-- ============================
INSERT IGNORE INTO bank_card (card_id, user_id, card_no_hash, bank_code, card_type, credit_limit) VALUES
('CARD_U1_A', 'U1001', 'card_hash_u1a', 'ICBC', '借记卡', 0),
('CARD_U1_B', 'U1001', 'card_hash_u1b', 'CCB', '信用卡', 50000),
('CARD_U2_A', 'U1002', 'card_hash_u2a', 'ABC', '借记卡', 0),
('CARD_U2_B', 'U1002', 'card_hash_u2b', 'BC', '信用卡', 30000),
('CARD_U3_A', 'U1003', 'card_hash_u3a', 'ICBC', '借记卡', 0),
('CARD_R1_A', 'RISK001', 'card_hash_r1a', 'CCB', '借记卡', 0),
('CARD_R1_B', 'RISK001', 'card_hash_r1b', 'ICBC', '信用卡', 80000),
('CARD_R2_A', 'RISK002', 'card_hash_r2a', 'ABC', '借记卡', 0),
('CARD_R2_B', 'RISK002', 'card_hash_r2b', 'BC', '信用卡', 20000),
('CARD_R2_C', 'RISK002', 'card_hash_r2c', 'ICBC', '借记卡', 0),
('CARD_R3_A', 'RISK003', 'card_hash_r3a', 'CCB', '借记卡', 0),
('CARD_R4_A', 'RISK004', 'card_hash_r4a', 'ICBC', '借记卡', 0),
('CARD_R4_B', 'RISK004', 'card_hash_r4b', 'ABC', '借记卡', 0),
('CARD_R4_C', 'RISK004', 'card_hash_r4c', 'BC', '借记卡', 0),
('CARD_R4_D', 'RISK004', 'card_hash_r4d', 'CCB', '借记卡', 0),
('CARD_R5_A', 'RISK005', 'card_hash_r5a', 'ABC', '借记卡', 0);

-- ============================
-- 6. 登录日志
-- ============================
INSERT IGNORE INTO login_log (login_id, user_id, device_id, ip, geo, success, login_at) VALUES
-- U1001 正常
('LOG_U1_01', 'U1001', 'DEV_A001', '192.168.1.1', '北京', 1, DATE_SUB(NOW(), INTERVAL 1 HOUR)),
('LOG_U1_02', 'U1001', 'DEV_A002', '192.168.1.1', '北京', 1, DATE_SUB(NOW(), INTERVAL 1 DAY)),
('LOG_U1_03', 'U1001', 'DEV_A001', '192.168.1.1', '北京', 1, DATE_SUB(NOW(), INTERVAL 3 DAY)),
('LOG_U1_04', 'U1001', 'DEV_A001', '192.168.1.1', '北京', 1, DATE_SUB(NOW(), INTERVAL 7 DAY)),
('LOG_U1_05', 'U1001', 'DEV_A001', '192.168.1.1', '北京', 1, DATE_SUB(NOW(), INTERVAL 14 DAY)),
-- RISK001: 登录IP=广州(与常用城市北京不同) — R001
('LOG_R1_01', 'RISK001', 'DEV_R001', '172.16.0.1', '广东广州', 1, DATE_SUB(NOW(), INTERVAL 2 HOUR)),
('LOG_R1_02', 'RISK001', 'DEV_R001', '192.168.1.1', '北京', 1, DATE_SUB(NOW(), INTERVAL 10 DAY)),
('LOG_R1_03', 'RISK001', 'DEV_R001', '192.168.1.1', '北京', 1, DATE_SUB(NOW(), INTERVAL 15 DAY)),
('LOG_R1_04', 'RISK001', 'DEV_R001', '192.168.1.1', '北京', 1, DATE_SUB(NOW(), INTERVAL 20 DAY)),
-- RISK002: 凌晨操作 — R002
('LOG_R2_01', 'RISK002', 'DEV_R002', '10.0.0.1', '上海', 1, DATE_ADD(CURDATE(), INTERVAL 3 HOUR)),
('LOG_R2_02', 'RISK002', 'DEV_R002', '10.0.0.1', '上海', 1, DATE_ADD(CURDATE(), INTERVAL 2 HOUR)),
('LOG_R2_03', 'RISK002', 'DEV_R002', '10.0.0.1', '上海', 1, DATE_ADD(CURDATE(), INTERVAL 1 HOUR)),
-- RISK003: 新设备用户
('LOG_R3_01', 'RISK003', 'DEV_R003', '203.0.113.1', '浙江杭州', 1, DATE_SUB(NOW(), INTERVAL 1 HOUR)),
('LOG_R3_02', 'RISK003', 'DEV_R003', '203.0.113.1', '浙江杭州', 1, DATE_SUB(NOW(), INTERVAL 2 DAY)),
-- RISK004: 多卡归集
('LOG_R4_01', 'RISK004', 'DEV_R004', '198.51.100.1', '江苏南京', 1, DATE_SUB(NOW(), INTERVAL 3 HOUR)),
('LOG_R4_02', 'RISK004', 'DEV_R004', '198.51.100.1', '江苏南京', 1, DATE_SUB(NOW(), INTERVAL 1 DAY)),
-- RISK005: 代理IP — R025
('LOG_R5_01', 'RISK005', 'DEV_R005', '185.220.101.1', NULL, 1, DATE_SUB(NOW(), INTERVAL 30 MINUTE)),
('LOG_R5_02', 'RISK005', 'DEV_R005', '185.220.101.1', NULL, 1, DATE_SUB(NOW(), INTERVAL 1 HOUR)),
('LOG_R5_03', 'RISK005', 'DEV_R005B', '45.33.32.156', NULL, 1, DATE_SUB(NOW(), INTERVAL 2 HOUR));

-- ============================
-- 7. 交易记录
-- ============================
INSERT IGNORE INTO `transaction` (txn_id, from_card, to_card, amount, channel, device_id, ip, geo, create_time) VALUES
-- U1001 正常交易
('TXN_U1_01', 'CARD_U1_A', 'CARD_U2_A', 5000.00, '手机银行', 'DEV_A001', '192.168.1.1', '北京', DATE_SUB(NOW(), INTERVAL 2 HOUR)),
('TXN_U1_02', 'CARD_U1_A', 'CARD_U2_A', 3000.00, '网银', 'DEV_A002', '192.168.1.1', '北京', DATE_SUB(NOW(), INTERVAL 1 DAY)),
('TXN_U1_03', 'CARD_U1_B', 'CARD_U2_B', 8000.00, '手机银行', 'DEV_A001', '192.168.1.1', '北京', DATE_SUB(NOW(), INTERVAL 3 DAY)),
-- RISK001: 2笔跨省大额(>5万+登录IP=广州≠北京) — R001
('TXN_R1_01', 'CARD_R1_A', 'CARD_R1_B', 60000.00, '网银', 'DEV_R001', '172.16.0.1', '广东广州', DATE_SUB(NOW(), INTERVAL 1 HOUR)),
('TXN_R1_02', 'CARD_R1_A', 'CARD_R2_A', 55000.00, '手机银行', 'DEV_R001', '172.16.0.1', '广东广州', DATE_SUB(NOW(), INTERVAL 30 MINUTE)),
-- RISK002: 3笔凌晨交易 (当前凌晨3点) — R002
('TXN_R2_01', 'CARD_R2_A', 'CARD_R2_B', 2000.00, '手机银行', 'DEV_R002', '10.0.0.1', '上海', DATE_ADD(CURDATE(), INTERVAL 3 HOUR)),
('TXN_R2_02', 'CARD_R2_A', 'CARD_R2_C', 5000.00, '手机银行', 'DEV_R002', '10.0.0.1', '上海', DATE_ADD(CURDATE(), INTERVAL 190 MINUTE)),
('TXN_R2_03', 'CARD_R2_B', 'CARD_R2_C', 3000.00, '手机银行', 'DEV_R002', '10.0.0.1', '上海', DATE_ADD(CURDATE(), INTERVAL 200 MINUTE)),
-- RISK003: 1笔大额(仅1设备+注册<30天+金额>3万) — R005
('TXN_R3_01', 'CARD_R3_A', 'CARD_R1_A', 35000.00, '网银', 'DEV_R003', '203.0.113.1', '浙江杭州', DATE_SUB(NOW(), INTERVAL 30 MINUTE)),
-- RISK004: 5笔1小时内转入同一卡 — R008
('TXN_R4_01', 'CARD_R4_A', 'CARD_R4_D', 10000.00, '手机银行', 'DEV_R004', '198.51.100.1', '江苏南京', DATE_SUB(NOW(), INTERVAL 1 HOUR)),
('TXN_R4_02', 'CARD_R4_B', 'CARD_R4_D', 20000.00, '手机银行', 'DEV_R004', '198.51.100.1', '江苏南京', DATE_SUB(NOW(), INTERVAL 45 MINUTE)),
('TXN_R4_03', 'CARD_R4_C', 'CARD_R4_D', 15000.00, '手机银行', 'DEV_R004', '198.51.100.1', '江苏南京', DATE_SUB(NOW(), INTERVAL 30 MINUTE)),
('TXN_R4_04', 'CARD_R4_A', 'CARD_R4_D', 5000.00, '手机银行', 'DEV_R004', '198.51.100.1', '江苏南京', DATE_SUB(NOW(), INTERVAL 15 MINUTE)),
('TXN_R4_05', 'CARD_R4_B', 'CARD_R4_D', 8000.00, '手机银行', 'DEV_R004', '198.51.100.1', '江苏南京', DATE_SUB(NOW(), INTERVAL 5 MINUTE)),
-- 正常交易
('TXN_U2_01', 'CARD_U2_A', 'CARD_U1_A', 2000.00, 'ATM', NULL, '10.0.0.1', '上海', DATE_SUB(NOW(), INTERVAL 7 DAY)),
('TXN_U3_01', 'CARD_U3_A', 'CARD_U2_A', 1000.00, '柜台', NULL, NULL, NULL, DATE_SUB(NOW(), INTERVAL 14 DAY));

-- ============================
-- 8. 贷款申请
-- ============================
INSERT IGNORE INTO loan_application (loan_id, user_id, amount, term_months, purpose, monthly_income, debt_ratio, status, create_time) VALUES
('LOAN_U1_01', 'U1001', 100000.00, 12, '装修', 15000.00, 0.20, '通过', DATE_SUB(NOW(), INTERVAL 30 DAY)),
('LOAN_U2_01', 'U1002', 50000.00, 6, '教育', 12000.00, 0.15, '通过', DATE_SUB(NOW(), INTERVAL 60 DAY)),
('LOAN_U3_01', 'U1003', 20000.00, 3, '消费', 8000.00, 0.10, '待审核', DATE_SUB(NOW(), INTERVAL 5 DAY)),
('LOAN_R4_01', 'RISK004', 50000.00, 12, '经营周转', 10000.00, 0.35, '通过', DATE_SUB(NOW(), INTERVAL 10 DAY)),
('LOAN_R4_02', 'RISK004', 30000.00, 6, '消费', 10000.00, 0.35, '通过', DATE_SUB(NOW(), INTERVAL 7 DAY)),
('LOAN_R4_03', 'RISK004', 80000.00, 24, '装修', 10000.00, 0.35, '待审核', DATE_SUB(NOW(), INTERVAL 2 DAY));

SET FOREIGN_KEY_CHECKS = 1;
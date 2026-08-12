-- ============================================
-- 银行风控系统 - 初始业务数据 (打样数据)
-- 完整批量数据由 scripts/gen_bank_data.py 生成
-- 此处仅保证: 页面演示 + 规则命中示例有数据可用
-- ============================================

USE risk_bank;

-- ---------- 1. 用户 (正常 + 高风险打样) ----------
INSERT INTO user_info (user_id, name, id_card_hash, credit_score, register_at, kyc_level) VALUES
('U0001', '张伟',   'HASH_0001_0001', 720, DATE_SUB(NOW(), INTERVAL 500 DAY), 3),
('U0002', '李娜',   'HASH_0002_0002', 680, DATE_SUB(NOW(), INTERVAL 300 DAY), 2),
('U0003', '王强',   'HASH_0003_0003', 650, DATE_SUB(NOW(), INTERVAL 200 DAY), 2),
('U0004', '刘洋',   'HASH_0004_0004', 590, DATE_SUB(NOW(), INTERVAL 90 DAY),  2),
('RISK001', '赵敏', 'HASH_5001_5001', 380, DATE_SUB(NOW(), INTERVAL 20 DAY),  1),
('RISK002', '孙磊', 'HASH_5002_5002', 420, DATE_SUB(NOW(), INTERVAL 15 DAY),  1);

-- ---------- 2. 银行卡 ----------
INSERT INTO bank_card (card_id, user_id, card_no_hash, bank_code, card_type, credit_limit) VALUES
('card_u0001_d1', 'U0001', 'CARDHASH_0001', 'ICBC', '借记卡', 0),
('card_u0001_c1', 'U0001', 'CARDHASH_0002', 'ICBC', '信用卡', 50000),
('card_u0002_d1', 'U0002', 'CARDHASH_0003', 'CCB',  '借记卡', 0),
('card_u0003_d1', 'U0003', 'CARDHASH_0004', 'ABC',  '借记卡', 0),
('card_u0004_d1', 'U0004', 'CARDHASH_0005', 'BOC',  '借记卡', 0),
('card_risk001_d1', 'RISK001', 'CARDHASH_5001', 'CMB', '借记卡', 0),
('card_risk002_d1', 'RISK002', 'CARDHASH_5002', 'CMB', '借记卡', 0);

-- ---------- 3. 交易 (正常几笔 + RISK 异地大额/黑卡示例) ----------
INSERT INTO transaction (txn_id, from_card, to_card, amount, channel, device_id, ip, geo, txn_time) VALUES
('txn_demo_001', 'card_u0001_d1', 'card_u0002_d1', 1200.00, 'APP',  'dev_apple_01', '10.1.1.10',  '广东-深圳', DATE_SUB(NOW(), INTERVAL 2 HOUR)),
('txn_demo_002', 'card_u0001_d1', 'card_u0003_d1', 3500.00, '网银', 'dev_apple_01', '10.1.1.10',  '广东-深圳', DATE_SUB(NOW(), INTERVAL 1 DAY)),
('txn_demo_003', 'card_u0002_d1', 'card_u0001_d1', 800.00,  'APP',  'dev_huawei_01','10.2.2.20',  '上海-上海', DATE_SUB(NOW(), INTERVAL 3 HOUR)),
('txn_demo_004', 'card_u0001_c1', NULL,          2600.00, 'APP',  'dev_apple_01', '10.1.1.10',  '广东-深圳', DATE_SUB(NOW(), INTERVAL 5 HOUR)),
('txn_demo_risk1', 'card_risk001_d1', 'card_u0002_d1', 88000.00, '第三方', 'dev_emulator_01', '45.155.204.5', '黑龙江-哈尔滨', DATE_SUB(NOW(), INTERVAL 30 MINUTE)),
('txn_demo_risk2', 'card_risk002_d1', 'card_black_0001', 60000.00, 'APP', 'dev_emulator_02', '45.155.204.6', '北京-北京', DATE_SUB(NOW(), INTERVAL 1 HOUR));

-- ---------- 4. 贷款申请 ----------
INSERT INTO loan_application (loan_id, user_id, amount, term_months, purpose, monthly_income, debt_ratio, apply_time) VALUES
('loan_demo_001', 'U0001', 100000, 24, '装修', 20000, 0.2500, DATE_SUB(NOW(), INTERVAL 10 DAY)),
('loan_demo_002', 'U0002', 50000,  12, '购车', 15000, 0.3500, DATE_SUB(NOW(), INTERVAL 5 DAY)),
('loan_demo_risk1', 'RISK001', 300000, 36, '投资', 5000, 0.8500, DATE_SUB(NOW(), INTERVAL 1 DAY)),
('loan_demo_risk2', 'RISK002', 200000, 24, '周转', 6000, 0.7800, DATE_SUB(NOW(), INTERVAL 1 DAY));

-- ---------- 5. 登录日志 ----------
INSERT INTO login_log (login_id, user_id, device_id, ip, geo, success, login_at) VALUES
('login_demo_001', 'U0001', 'dev_apple_01',  '10.1.1.10',  '广东-深圳', 1, DATE_SUB(NOW(), INTERVAL 3 HOUR)),
('login_demo_002', 'U0001', 'dev_apple_01',  '10.1.1.10',  '广东-深圳', 1, DATE_SUB(NOW(), INTERVAL 2 DAY)),
('login_demo_003', 'U0002', 'dev_huawei_01', '10.2.2.20',  '上海-上海', 1, DATE_SUB(NOW(), INTERVAL 4 HOUR)),
('login_demo_004', 'U0003', 'dev_xiaomi_01', '10.3.3.30',  '北京-北京', 1, DATE_SUB(NOW(), INTERVAL 1 DAY)),
('login_demo_risk1', 'RISK001', 'dev_emulator_01', '45.155.204.5', '黑龙江-哈尔滨', 1, DATE_SUB(NOW(), INTERVAL 30 MINUTE)),
('login_demo_risk2', 'RISK001', 'dev_emulator_01', '45.155.204.5', '黑龙江-哈尔滨', 0, DATE_SUB(NOW(), INTERVAL 35 MINUTE)),
('login_demo_risk3', 'RISK001', 'dev_emulator_01', '45.155.204.5', '黑龙江-哈尔滨', 0, DATE_SUB(NOW(), INTERVAL 40 MINUTE));

-- ---------- 6. 设备指纹 ----------
INSERT INTO device_fingerprint (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser) VALUES
('dev_apple_01',   'U0001',      'FPHASH_0001', DATE_SUB(NOW(), INTERVAL 400 DAY), NOW(), 'iOS 17',      'Safari'),
('dev_huawei_01',  'U0002',      'FPHASH_0002', DATE_SUB(NOW(), INTERVAL 250 DAY), NOW(), 'HarmonyOS 4', 'Chrome'),
('dev_xiaomi_01',  'U0003',      'FPHASH_0003', DATE_SUB(NOW(), INTERVAL 180 DAY), NOW(), 'Android 14',  'Chrome'),
('dev_emulator_01','RISK001',    'FPHASH_5001', DATE_SUB(NOW(), INTERVAL 5 DAY),  NOW(), 'Android 10',  'Chrome'),
('dev_emulator_02','RISK002',    'FPHASH_5002', DATE_SUB(NOW(), INTERVAL 3 DAY),  NOW(), 'Android 10',  'Chrome');

-- ---------- 7. IP 地理位置 (含代理/秒拨 IP) ----------
INSERT INTO ip_geo_location (ip, country, province, city, isp, is_proxy, is_tor) VALUES
('10.1.1.10',  '中国', '广东',   '深圳',   '中国电信', 0, 0),
('10.2.2.20',  '中国', '上海',   '上海',   '中国联通', 0, 0),
('10.3.3.30',  '中国', '北京',   '北京',   '中国移动', 0, 0),
('45.155.204.5','美国', 'California', 'LA', 'ProxyLayer', 1, 1),
('45.155.204.6','美国', 'California', 'LA', 'ProxyLayer', 1, 0);

-- ---------- 8. 黑名单扩展 (黑卡/代理IP示例) ----------
INSERT INTO blacklist_extra (type, value, reason, expire_at) VALUES
('银行卡号', 'card_black_0001', '涉案诈骗归集卡 (监管止付名单)', NULL),
('IP',       '45.155.204.6',   '秒拨代理池 IP', NULL);

-- ============================================
-- 银行风控系统 - 预置风控规则数据
-- 覆盖四大场景: 登录 / 转账 / 贷款 / 信用卡
-- 共 15 条规则 (R001-R035, PRD 第 6 节)
-- ============================================

-- 转账场景 (7 条)
INSERT IGNORE INTO `rule_config` (`rule_id`, `rule_name`, `scene`, `conditions`, `risk_level`, `decision`, `action`, `priority`, `status`, `operator`) VALUES
('R001', '异地大额转账', '转账',
 '{"geo_mismatch": true, "min_amount": 50000, "compare_field": "common_city"}',
 4, 'REJECT', 'STOP_PAYMENT', 1, 1, 'admin'),

('R002', '凌晨密集操作', '转账',
 '{"hour_range": [0, 5], "window_minutes": 60, "min_txn_count": 3}',
 3, 'MANUAL', 'TAG', 5, 1, 'admin'),

('R005', '新设备大额', '转账',
 '{"device_age_days": 7, "min_amount": 30000, "compare_op": "<"}',
 3, 'MANUAL', 'TAG', 10, 1, 'admin'),

('R008', '多卡归集', '转账',
 '{"window_minutes": 60, "min_card_count": 3, "same_to_card": true}',
 4, 'REJECT', 'STOP_PAYMENT', 2, 1, 'admin'),

('R010', '试探后大额', '转账',
 '{"window_hours": 24, "small_max_amount": 100, "min_small_count": 2, "subsequent_min_amount": 10000, "same_counterparty": true}',
 3, 'MANUAL', 'TAG', 8, 1, 'admin'),

('R028', '涉诈收款', '转账',
 '{"hit_blacklist": true, "blacklist_source": "公安涉诈", "dimension": "to_card"}',
 4, 'REJECT', 'REPORT', 1, 1, 'admin'),

('R030', '黑卡拦截', '转账',
 '{"hit_blacklist": true, "dimension": "to_card_no", "blacklist_type": "银行卡号"}',
 4, 'REJECT', 'STOP_PAYMENT', 1, 1, 'admin'),

-- 登录场景 (3 条)
('R003', '盗号快速改绑', '登录',
 '{"new_device": true, "geo_mismatch": true, "window_minutes": 30, "subsequent_actions": ["CHANGE_PWD", "CHANGE_PHONE"]}',
 4, 'REJECT', 'FREEZE', 1, 1, 'admin'),

('R018', '设备多人共用', '登录',
 '{"min_user_count": 5, "same_device": true}',
 2, 'PASS', 'TAG', 20, 1, 'admin'),

('R025', 'IP代理/秒拨', '登录',
 '{"ip_check": true, "hit_proxy": true, "sources": ["代理库", "Tor出口"]}',
 2, 'CHALLENGE', 'TAG', 15, 1, 'admin'),

-- 贷款场景 (5 条)
('R012', '信贷申请突击', '贷款',
 '{"window_months": 1, "min_institution_count": 3}',
 3, 'MANUAL', 'TAG', 5, 1, 'admin'),

('R015', '放款即转', '贷款',
 '{"within_hours": 24, "transfer_ratio": 0.90, "to_non_self": true}',
 4, 'REJECT', 'FREEZE', 1, 1, 'admin'),

('R020', '多头查询', '贷款',
 '{"window_months": 1, "min_credit_queries": 6}',
 3, 'MANUAL', 'TAG', 5, 1, 'admin'),

('R033', '团伙申请', '贷款',
 '{"same_device_or_ip": true, "min_applicant_count": 3}',
 3, 'MANUAL', 'TAG', 5, 1, 'admin'),

('R035', '收入与征信不符', '贷款',
 '{"income_gap_ratio": 0.30, "has_tax_proof": false, "compare_field": "credit_income"}',
 3, 'MANUAL', 'TAG', 8, 1, 'admin'),

-- 信用卡场景 (1 条)
('R022', '养卡套现', '信用卡',
 '{"window_months": 1, "same_merchant_min_txn": 5, "cumulative_ratio": 0.80, "compare_field": "credit_limit"}',
 2, 'PASS', 'LIMIT', 10, 1, 'admin');

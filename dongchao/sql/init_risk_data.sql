-- ============================================
-- 银行风控系统 - 预置规则数据 (8 条)
-- 覆盖 6 大风险场景 (R001-R030)
-- ============================================
-- R001        转账风险 (异地大额转账)
-- R002        交易风险 (凌晨密集操作)
-- R005        设备风险 (新设备大额)
-- R008        转账风险 (多卡归集)
-- R012        信贷风险 (信贷申请突击)
-- R018        设备风险 (设备多人共用)
-- R025        IP风险 (IP代理秒拨)
-- R030        转账风险 (黑卡拦截)
-- ============================================

USE bank_risk;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- R001 异地大额转账 (转账风险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '异地大额转账', '转账风险', '转账',
 '{"and": [{"field": "order_txn_cross_city", "op": "==", "value": 1}, {"field": "order_txn_amount", "op": ">=", "value": 50000}]}',
 '极高', 95, '拒绝', 1, 100,
 '登录城市与常用城市不一致且转账金额≥5万');

-- ============================
-- R002 凌晨密集操作 (交易风险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '凌晨密集操作', '交易风险', '转账',
 '{"and": [{"field": "order_txn_hour", "op": "between", "value": [0, 5]}, {"field": "order_txn_hourly_count", "op": ">=", "value": 3}]}',
 '高', 75, '人工审核', 1, 90,
 '凌晨0-5点且1小时内≥3笔交易');

-- ============================
-- R005 新设备大额 (设备风险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '新设备大额转账', '设备风险', '转账',
 '{"and": [{"field": "user_device_count", "op": "<=", "value": 1}, {"field": "order_txn_amount", "op": ">=", "value": 30000}]}',
 '高', 70, '人工审核', 1, 85,
 '用户仅1个关联设备且单笔转账≥3万');

-- ============================
-- R008 多卡归集 (转账风险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '多卡归集洗钱', '转账风险', '转账',
 '{"field": "order_txn_hourly_count", "op": ">=", "value": 5}',
 '极高', 92, '拒绝', 1, 95,
 '1小时内≥5笔交易,疑似多卡归集洗钱');

-- ============================
-- R012 信贷申请突击 (信贷风险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '信贷申请突击', '信贷风险', '贷款申请',
 '{"field": "user_loan_count", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 85,
 '当月已申请≥3家不同机构贷款');

-- ============================
-- R018 设备多人共用 (设备风险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '设备多人共用', '设备风险', '登录',
 '{"field": "user_device_count", "op": ">=", "value": 5}',
 '中', 50, '标记', 1, 60,
 '同一用户关联≥5个不同设备');

-- ============================
-- R025 IP代理秒拨 (IP风险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', 'IP代理秒拨', 'IP风险', '登录',
 '{"field": "addr_ip_is_proxy", "op": "==", "value": 1}',
 '中', 45, '标记', 1, 55,
 '登录IP命中代理库/Tor出口');

-- ============================
-- R030 黑卡拦截 (转账风险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑卡拦截', '转账风险', '转账',
 '{"field": "order_txn_amount", "op": ">=", "value": 100000}',
 '极高', 98, '拒绝', 1, 100,
 '单笔转账≥10万, 配合黑名单前置拦截');
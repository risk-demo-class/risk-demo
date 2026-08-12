-- ============================================
-- 银行风控系统 - 预置规则数据初始化
-- 12 条规则覆盖 4 大银行风险场景 (转账/登录/贷款申请/信用卡)
-- 每条规则均给出行业有效性说明 (description)
-- ============================================================
-- R001  异地大额转账         (交易风险, 极高/拒绝)
-- R002  凌晨密集操作         (交易风险, 高/人工审核)
-- R003  深夜异常登录         (账户风险, 高/人工审核)
-- R005  新设备信用卡大额   (设备风险, 高/人工审核, 分数84=人工审核档)
-- R008  多卡归集             (交易风险, 极高/拒绝)
-- R010  高负债大额申贷       (信贷风险, 高/人工审核)
-- R012  信贷申请突击         (信贷风险, 高/人工审核)
-- R015  低信用分大额交易     (账户风险, 高/人工审核)
-- R018  设备多人共用         (设备风险, 中/标记)
-- R020  登录异常后大额转账   (网络风险, 高/人工审核)
-- R025  IP 代理/秒拨         (网络风险, 中/标记)
-- R030  黑卡拦截             (交易风险, 极高/拒绝)
-- ============================================================

USE risk_bank;

-- 关外键约束 (允许 TRUNCATE 被外键引用的表; risk_action_log.target_id 引用 risk_rule.rule_id)
SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联表 risk_action_log 的历史记录)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

-- 恢复外键约束
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 交易风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '异地大额转账', '交易风险', '转账',
 '{"and": [{"field": "txn_city_match", "op": "==", "value": 1}, {"field": "txn_amount", "op": ">=", "value": 50000}]}',
 '极高', 92, '拒绝', 1, 100,
 '交易城市非常用城市且单笔≥5万元，符合"异地+大额"电信诈骗/盗转典型特征，银行对非常用地大额转账执行限额与拦截');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '凌晨密集操作', '交易风险', '转账',
 '{"and": [{"field": "txn_is_night", "op": "==", "value": 1}, {"field": "txn_1h_count", "op": ">=", "value": 3}]}',
 '高', 68, '人工审核', 1, 82,
 '凌晨0-5点 1 小时内交易≥3 笔，黑产常深夜试探小额转出验证账户可用性，需人工核实');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '多卡归集', '交易风险', '转账',
 '{"field": "txn_1h_into_count", "op": ">=", "value": 3}',
 '极高', 90, '拒绝', 1, 98,
 '1 小时内 ≥3 张不同付款卡转入同一收款卡，是典型的"多卡归集"洗钱/跑分特征，银行反洗钱模型直接拦截');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑卡拦截', '交易风险', '转账',
 '{"field": "txn_to_card_black", "op": "==", "value": 1}',
 '极高', 95, '拒绝', 1, 100,
 '收款卡命中黑名单（涉案卡/诈骗资金归集卡），监管要求涉诈账户即时止付，一票否决');

-- ============================
-- 账户风险 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '深夜异常登录', '账户风险', '登录',
 '{"and": [{"field": "login_is_night", "op": "==", "value": 1}, {"field": "user_failed_login_7d", "op": ">=", "value": 3}]}',
 '高', 65, '人工审核', 1, 80,
 '凌晨登录且近 7 天已失败≥3 次，符合撞库/暴力破解后深夜登录特征，需短信/人工二次核验');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R015', '低信用分大额交易', '账户风险', '转账',
 '{"and": [{"field": "user_credit_score", "op": "<", "value": 500}, {"field": "txn_amount", "op": ">=", "value": 20000}]}',
 '高', 82, '人工审核', 1, 84,
 '人行信用分<500 属高风险客群，单笔≥2 万元交易超出其偿付能力预期，存在出借账户/被诱导转账风险');

-- ============================
-- 信贷风险 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '高负债大额申贷', '信贷风险', '贷款申请',
 '{"and": [{"field": "loan_debt_ratio", "op": ">=", "value": 0.6}, {"field": "loan_amount_income_ratio", "op": ">=", "value": 5}]}',
 '高', 85, '人工审核', 1, 86,
 '负债率≥60% 且 申请额/月收入≥5 倍，偿债能力严重不足，银行授信审批需人工评估还款来源');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '信贷申请突击', '信贷风险', '贷款申请',
 '{"field": "loan_month_count", "op": ">=", "value": 3}',
 '高', 80, '人工审核', 1, 85,
 '当月贷款申请≥3 次，多头借贷/资金链断裂信号，征信查询次数过多也会拉低授信评分');

-- ============================
-- 设备风险 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '新设备信用卡大额', '设备风险', '信用卡',
 '{"and": [{"field": "card_device_new", "op": "==", "value": 1}, {"field": "card_amount", "op": ">=", "value": 30000}]}',
 '高', 84, '人工审核', 1, 85,
 '设备首次出现<7 天即用信用卡发起≥3 万元大额交易，新设备+大额是盗刷的高发组合，银行对新设备执行限额与人工核验');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '设备多人共用', '设备风险', '通用',
 '{"or": [{"field": "txn_device_user_count", "op": ">=", "value": 5}, {"field": "login_device_user_count", "op": ">=", "value": 5}]}',
 '中', 42, '标记', 1, 55,
 '同一设备关联≥5 个不同用户，黑产工作室一台设备批量操控多账户，标记后纳入设备画像持续监控');

-- ============================
-- 网络风险 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R020', '登录异常后大额转账', '网络风险', '转账',
 '{"and": [{"field": "user_failed_login_7d", "op": ">=", "value": 3}, {"field": "txn_amount", "op": ">=", "value": 10000}]}',
 '高', 80, '人工审核', 1, 83,
 '近 7 天登录失败≥3 次后发起≥1 万元转账，暴力破解/撞库后紧接着大额转款是盗转链条的典型前兆');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', 'IP 代理/秒拨', '网络风险', '通用',
 '{"or": [{"field": "txn_geo_risk", "op": "==", "value": 1}, {"field": "login_geo_risk", "op": "==", "value": 1}, {"field": "loan_geo_risk", "op": "==", "value": 1}]}',
 '中', 40, '标记', 1, 50,
 '交易/登录/申贷 IP 命中代理库、Tor 出口或 IP 黑名单，秒拨代理是黑产绕过风控的基础设施，标记后联动设备画像');

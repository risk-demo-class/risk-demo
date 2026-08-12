-- ============================================
-- 银行信贷风控系统 - 预置风控规则 (R001-R030)
-- 6 大场景: 欺诈 6 / 信用 6 / 反洗钱 4 / 账户 5 / 贷后 5 / 合规 4
-- 条件字段全部引用银行 25 维特征 (cust_/loan_/dev_)
-- 极高规则 3 条 (R102/R202/R502) 触发一票否决
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 清空旧规则与审计日志 (P4-L1: risk_action_log.target_id 引用 rule_id, 先清日志)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

-- ============================
-- 场景一: 欺诈风险 (6 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R101', '多头借贷', '欺诈风险', '贷款申请',
 '{"field": "cust_loans_7d", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 90,
 '近 7 天申请 3 笔以上, 存在多头借贷欺诈风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R102', '严重多头借贷', '欺诈风险', '贷款申请',
 '{"field": "cust_loans_30d", "op": ">=", "value": 8}',
 '极高', 90, '拒绝', 1, 95,
 '近 30 天申请 8 笔以上, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R103', '团伙申请特征', '欺诈风险', '贷款申请',
 '{"and": [{"field": "cust_loans_7d", "op": ">=", "value": 2}, {"field": "dev_ip_province_count", "op": ">=", "value": 3}]}',
 '高', 75, '人工审核', 1, 85,
 '短期多笔申请且 IP 跨 3 省, 疑似团伙');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R104', '设备聚集异常', '欺诈风险', '贷款申请',
 '{"field": "dev_device_count", "op": ">=", "value": 4}',
 '高', 70, '人工审核', 1, 75,
 '客户使用 4 台以上设备申请, 反欺诈信号');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R105', '新设备申请', '欺诈风险', '贷款申请',
 '{"and": [{"field": "dev_is_new", "op": "==", "value": 1}, {"field": "cust_total_loans", "op": ">", "value": 0}]}',
 '中', 45, '标记', 1, 60,
 '老客户首次用新设备申请, 需关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R106', '跨省批量申请', '欺诈风险', '贷款申请',
 '{"and": [{"field": "cust_total_loans", "op": ">=", "value": 5}, {"field": "dev_ip_province_count", "op": ">=", "value": 4}]}',
 '高', 80, '人工审核', 1, 80,
 '多笔申请且 IP 跨 4 省, 批量操作特征');

-- ============================
-- 场景二: 信用风险 (6 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R201', '负债率过高', '信用风险', '贷款申请',
 '{"field": "loan_debt_ratio", "op": ">=", "value": 0.5}',
 '高', 75, '人工审核', 1, 90,
 '现有负债超过申请金额 50%, 还款能力不足');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R202', '严重负债', '信用风险', '贷款申请',
 '{"field": "loan_debt_ratio", "op": ">=", "value": 0.8}',
 '极高', 90, '拒绝', 1, 95,
 '负债率 80%+, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R203', '收入负债比超标', '信用风险', '贷款申请',
 '{"field": "loan_income_debt_ratio", "op": ">=", "value": 0.6}',
 '高', 70, '人工审核', 1, 85,
 '现有负债超过年收入 60%');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R204', '历史逾期占比高', '信用风险', '贷款申请',
 '{"field": "cust_overdue_rate", "op": ">=", "value": 0.3}',
 '高', 80, '人工审核', 1, 80,
 '历史申请逾期率 30%+, 违约风险高');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R205', '多次逾期记录', '信用风险', '贷款申请',
 '{"field": "cust_overdue_count", "op": ">=", "value": 2}',
 '高', 75, '人工审核', 1, 75,
 '历史逾期 2 次以上');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R206', '贷款收入比过高', '信用风险', '贷款申请',
 '{"field": "loan_to_income", "op": ">=", "value": 0.8}',
 '中', 55, '标记', 1, 60,
 '申请金额接近年收入 80%, 杠杆偏高');

-- ============================
-- 场景三: 反洗钱 (4 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R301', '频繁大额申请', '反洗钱', '贷款申请',
 '{"and": [{"field": "loan_amount", "op": ">=", "value": 100000}, {"field": "cust_total_loans", "op": ">=", "value": 6}]}',
 '高', 75, '人工审核', 1, 85,
 '大额+高频申请, 疑似洗钱通道');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R302', '快进快出', '反洗钱', '贷款申请',
 '{"field": "loan_apply_interval_sec", "op": "between", "value": [0, 60]}',
 '高', 80, '人工审核', 1, 90,
 '距上次申请不足 60 秒, 疑似自动化批量操作');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R303', '拆分交易', '反洗钱', '贷款申请',
 '{"and": [{"field": "cust_loans_7d", "op": ">=", "value": 3}, {"field": "loan_amount", "op": ">=", "value": 50000}]}',
 '高', 70, '人工审核', 1, 75,
 '短期多笔 5 万+ 申请, 疑似拆分规避监测');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R304', '夜间大额申请', '反洗钱', '贷款申请',
 '{"and": [{"field": "loan_apply_is_night", "op": "==", "value": 1}, {"field": "loan_amount", "op": ">=", "value": 100000}]}',
 '中', 60, '人工审核', 1, 65,
 '深夜 10 万+ 大额申请, 非正常作息');

-- ============================
-- 场景四: 账户风险 (5 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R401', '新设备异常登录', '账户风险', '贷款申请',
 '{"and": [{"field": "dev_is_new", "op": "==", "value": 1}, {"field": "cust_total_loans", "op": ">=", "value": 1}]}',
 '高', 70, '人工审核', 1, 80,
 '老客户新设备申请, 疑似账户被盗');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R402', '频繁申请', '账户风险', '贷款申请',
 '{"field": "cust_loans_30d", "op": ">=", "value": 5}',
 '高', 75, '人工审核', 1, 75,
 '近 30 天申请 5 笔以上, 账户异常活跃');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R403', '夜间申请', '账户风险', '贷款申请',
 '{"field": "loan_apply_is_night", "op": "==", "value": 1}',
 '低', 30, '标记', 1, 50,
 '0-6 点申请, 低度关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R404', '多产品申请', '账户风险', '贷款申请',
 '{"field": "loan_apply_product_count", "op": ">=", "value": 3}',
 '中', 50, '标记', 1, 60,
 '同时申请 3 个以上产品, 需求异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R405', '设备跨省登录', '账户风险', '贷款申请',
 '{"field": "dev_ip_province_count", "op": ">=", "value": 2}',
 '中', 40, '标记', 1, 55,
 '申请 IP 跨 2 省以上, 位置漂移');

-- ============================
-- 场景五: 贷后风险 (5 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R501', '历史逾期记录', '贷后风险', '还款',
 '{"field": "cust_overdue_count", "op": ">=", "value": 1}',
 '高', 70, '人工审核', 1, 85,
 '客户存在历史逾期, 贷后重点关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R502', '逾期率高', '贷后风险', '还款',
 '{"field": "cust_overdue_rate", "op": ">=", "value": 0.5}',
 '极高', 90, '拒绝', 1, 95,
 '逾期率 50%+, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R503', '失联风险', '贷后风险', '还款',
 '{"field": "cust_contact_count", "op": "<=", "value": 1}',
 '低', 30, '标记', 1, 50,
 '联系信息过少, 催收可达性差');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R504', '逾期金额大', '贷后风险', '还款',
 '{"field": "cust_overdue_amount", "op": ">=", "value": 50000}',
 '高', 75, '人工审核', 1, 75,
 '累计逾期金额 5 万+, 损失敞口大');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R505', '多次被拒后再次申请', '贷后风险', '贷款申请',
 '{"field": "cust_reject_count", "op": ">=", "value": 3}',
 '中', 55, '人工审核', 1, 65,
 '被拒 3 次以上仍反复申请');

-- ============================
-- 场景六: 合规风险 (4 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R601', '客户投诉频发', '合规风险', '客户投诉',
 '{"field": "cust_complaint_count", "op": ">=", "value": 3}',
 '中', 50, '人工审核', 1, 70,
 '投诉 3 次以上, 合规与舆情风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R602', '被拒史过长', '合规风险', '贷款申请',
 '{"field": "cust_reject_count", "op": ">=", "value": 4}',
 '高', 70, '人工审核', 1, 75,
 '被拒 4 次以上, 审慎准入');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R603', 'IP 漂移严重', '合规风险', '贷款申请',
 '{"field": "dev_ip_province_count", "op": ">=", "value": 5}',
 '高', 75, '人工审核', 1, 70,
 '申请 IP 跨 5 省, 位置真实性存疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R604', '投诉+被拒组合', '合规风险', '通用',
 '{"and": [{"field": "cust_complaint_count", "op": ">=", "value": 2}, {"field": "cust_reject_count", "op": ">=", "value": 2}]}',
 '高', 70, '人工审核', 1, 65,
 '投诉与拒绝历史叠加, 综合合规信号');

SET FOREIGN_KEY_CHECKS = 1;
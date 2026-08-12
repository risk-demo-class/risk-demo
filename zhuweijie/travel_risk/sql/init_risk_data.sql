-- ============================================
-- 旅游风控系统 - 预置规则数据初始化
-- 12 条规则覆盖 6 大风险场景 (R001-R012)
-- ============================================
-- R001-R002  签证欺诈  (拒签拦截 / 短期多国)
-- R003-R004  机票囤积  (黄牛囤票 / 凌晨突击下单)
-- R005       行程风险  (大额跨境游)
-- R006       账户风险  (新用户大单)
-- R007       签证欺诈  (黑护照拦截)
-- R008       行程风险  (乘客国籍与目的地不符)
-- R009       账户风险  (多次取消订单)
-- R010       酒店滥用  (节假日囤房)
-- R011       支付风险  (高舱位大额)
-- R012       行程风险  (目的地高风险国家)
-- ============================================

SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

SET FOREIGN_KEY_CHECKS = 1;

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '拒签历史拦截', '签证欺诈', '签证申请',
 '{"field": "user_visa_reject_count", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 100,
 '90天内签证被拒≥2次仍反复申请，直接拒绝');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '短期多国签证', '签证欺诈', '签证申请',
 '{"field": "user_country_count", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 90,
 '短期申请≥3个不同国家签证，疑似签证黄牛/移民中介');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '黄牛囤票', '机票囤积', '机票预订',
 '{"field": "same_flight_booking_count", "op": ">=", "value": 5}',
 '极高', 95, '拒绝', 1, 100,
 '同一航班同时段预订≥5张，疑似黄牛囤票');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R004', '凌晨突击下单', '机票囤积', '通用',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_days_to_depart", "op": "<", "value": 7}]}',
 '中', 40, '标记', 1, 50,
 '凌晨0-5点下单且行程<7天，突击出行疑似代刷');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '大额跨境游', '行程风险', '跟团游预订',
 '{"field": "order_total_amount", "op": ">=", "value": 50000}',
 '高', 70, '人工审核', 1, 85,
 '单笔跨境跟团游订单≥5万元，资金与行程需人工核验');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R006', '新用户大单', '账户风险', '通用',
 '{"and": [{"field": "account_age_days", "op": "<", "value": 7}, {"field": "order_total_amount", "op": ">=", "value": 10000}]}',
 '中', 50, '标记', 1, 60,
 '注册<7天且订单≥1万元，疑似批量注册薅羊毛');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '黑护照拦截', '签证欺诈', '通用',
 '{"field": "user_blacklist_hit", "op": "==", "value": 1}',
 '极高', 95, '拒绝', 1, 100,
 '用户或本单乘客证件命中黑名单(挂失/假护照)，直接拒绝');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '乘客国籍与目的地不符', '行程风险', '机票预订',
 '{"field": "passenger_nationality_match", "op": "==", "value": 0}',
 '中', 35, '标记', 1, 40,
 '乘客国籍与目的地不匹配，需关注代订/身份冒用');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R009', '多次取消订单', '账户风险', '通用',
 '{"field": "user_cancel_count", "op": ">=", "value": 3}',
 '高', 65, '人工审核', 1, 70,
 '累计取消订单≥3次，疑似退改签滥用');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '节假日囤房', '酒店滥用', '酒店预订',
 '{"and": [{"field": "order_is_holiday", "op": "==", "value": 1}, {"field": "order_hotel_rooms", "op": ">=", "value": 3}]}',
 '高', 65, '人工审核', 1, 75,
 '节假日预订≥3间房，疑似酒店囤房倒卖');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R011', '高舱位大额订单', '支付风险', '机票预订',
 '{"and": [{"field": "order_cabin_class", "op": ">=", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 20000}]}',
 '高', 70, '人工审核', 1, 65,
 '公务/头等舱且订单≥2万元，支付来源需核验');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '目的地高风险国家', '行程风险', '通用',
 '{"field": "dest_is_high_risk", "op": "==", "value": 1}',
 '高', 70, '人工审核', 1, 80,
 '目的地为高风险/制裁国家，需人工核验行程真实性');
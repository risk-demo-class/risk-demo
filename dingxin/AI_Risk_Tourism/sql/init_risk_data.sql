-- ============================================
-- 旅游风控系统 - 预置规则数据初始化
-- 12 条规则覆盖 6 大旅游风险场景 (R001-R034 旅游版)
-- 场景分布:
--   R001/R002       签证风险 (拒签拦截 / 短期多国)
--   R005/R025/R032  预订欺诈 (大额跨境 / 新用户大单 / 单人大量乘客)
--   R008/R033/R034  设备风险 (黄牛囤票 / 临行改签 / 酒店倒卖)
--   R012            预订欺诈 (0 点突击下单)
--   R018            账户风险 (乘客信息不一致)
--   R030            黑名单风险 (黑护照拦截)
--   R031            退改滥用 (高频退改)
-- ============================================

USE tourism;

SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联审计日志)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 签证风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '拒签历史拦截', '签证风险', '签证申请',
 '{"field": "user_visa_reject_90d", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 100,
 '90天内签证被拒≥2次, 疑似恶意申请, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '短期多国签证', '签证风险', '签证申请',
 '{"field": "user_visa_countries_30d", "op": ">=", "value": 3}',
 '高', 75, '人工审核', 1, 90,
 '30天内申请≥3个不同国家签证, 疑似签证黄牛');

-- ============================
-- 预订欺诈
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '大额跨境游', '预订欺诈', '预订下单',
 '{"field": "order_total_amount", "op": ">=", "value": 50000}',
 '高', 80, '人工审核', 1, 85,
 '单笔订单≥5万元, 大额跨境游需人工审核');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '0点突击下单', '预订欺诈', '预订下单',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_trip_days", "op": "<", "value": 7}]}',
 '中', 40, '标记', 1, 50,
 '凌晨1-5点下单且行程<7天, 突击下单标记关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '新用户大单', '预订欺诈', '预订下单',
 '{"and": [{"field": "user_account_age_days", "op": "<", "value": 7}, {"field": "order_total_amount", "op": ">=", "value": 10000}]}',
 '中', 50, '标记', 1, 60,
 '注册<7天且订单≥1万元, 新用户大额订单');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R032', '单人大量乘客', '预订欺诈', '预订下单',
 '{"and": [{"field": "order_passenger_count", "op": ">=", "value": 5}, {"field": "trip_distinct_passenger_count", "op": ">=", "value": 5}]}',
 '中', 45, '标记', 1, 55,
 '单人账号大量乘客, 疑似代订/凑单');

-- ============================
-- 设备风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '黄牛囤票', '设备风险', '预订下单',
 '{"field": "trip_same_flight_1h", "op": ">=", "value": 5}',
 '极高', 92, '拒绝', 1, 98,
 '同一账号1小时内预订≥5张同航班, 疑似黄牛囤票, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R033', '临行改签', '设备风险', '退改申请',
 '{"and": [{"field": "order_is_urgent", "op": "==", "value": 1}, {"field": "order_is_flight", "op": "==", "value": 1}]}',
 '中', 45, '标记', 1, 55,
 '临近出行改签机票, 疑似票贩子倒票');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R034', '酒店倒卖', '设备风险', '预订下单',
 '{"field": "trip_same_hotel_1h", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 80,
 '同一账号1小时内预订≥3间同酒店, 疑似酒店倒卖');

-- ============================
-- 账户风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '乘客信息不一致', '账户风险', '预订下单',
 '{"field": "trip_passenger_match_rate", "op": "<", "value": 0.3}',
 '中', 45, '标记', 1, 55,
 '订单乘客证件与历史乘客匹配率<30%, 疑似身份冒用');

-- ============================
-- 退改滥用
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R031', '高频退改滥用', '退改滥用', '退改申请',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.5}, {"field": "user_total_orders", "op": ">=", "value": 5}]}',
 '高', 70, '人工审核', 1, 80,
 '退改率≥50%且订单≥5, 疑似恶意退改');

-- ============================
-- 黑名单风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑护照拦截', '黑名单风险', '预订下单',
 '{"field": "trip_blacklist_passport_count", "op": ">=", "value": 1}',
 '极高', 95, '拒绝', 1, 100,
 '订单乘客证件命中黑名单, 一票否决');

-- ============================================
-- 风控黑名单权威数据 (与 blacklist_extra 台账镜像, 决策只读本表)
-- 注意: 必须等 risk_blacklist 建表后才能插入, 所以放在规则后面
-- ============================================
INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason) VALUES
('护照号', 'E11223344', '涉骗护照(种子演示数据)'),
('护照号', 'E99999999', '涉黑护照'),
('签证号', 'VISA_BLACK_001', '签证造假'),
('设备指纹', 'DEVICE_BLACK_001', '黄牛设备'),
('设备指纹', 'DEVICE_BLACK_002', '批量注册设备');

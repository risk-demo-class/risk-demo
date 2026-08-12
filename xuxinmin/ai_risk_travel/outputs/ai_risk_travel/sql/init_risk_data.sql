-- ============================================================
-- 旅游风控系统 - 预置规则数据初始化 (11 条行业规则)
-- 覆盖 6 大风险场景: 预订欺诈 / 支付风险 / 账户风险 / 签证欺诈 / 退改签滥用 / 乘客风险
-- 规则条件里的字段名 = app/engine/feature.py 计算的特征名
-- ============================================================

-- 关外键约束 (允许 TRUNCATE 被外键引用的表)
SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 签证欺诈 (2 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '拒签历史拦截', '签证欺诈', '签证申请',
 '{"field": "user_visa_reject_count_90d", "op": ">=", "value": 2}',
 '极高', 100, '拒绝', 1, 100,
 '用户 90 天内签证被拒≥2 次, 疑似恶意刷签, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '短期多国签证', '签证欺诈', '签证申请',
 '{"field": "user_visa_countries_30d", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 80,
 '30 天内申请≥3 个不同国家签证, 疑似签证中介洗客');

-- ============================
-- 场景二: 预订欺诈 (5 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '大额跨境游', '预订欺诈', '预订',
 '{"field": "order_total_amount", "op": ">", "value": 50000}',
 '高', 70, '人工审核', 1, 60,
 '单笔订单>50000 元, 大额跨境消费需人工审核');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '黄牛囤票', '预订欺诈', '预订',
 '{"field": "order_flight_count", "op": ">=", "value": 5}',
 '极高', 95, '拒绝', 1, 100,
 '同一订单关联≥5 个航班, 疑似黄牛囤票, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '0点突击下单', '预订欺诈', '预订',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_is_urgent", "op": "==", "value": 1}]}',
 '中', 40, '标记', 1, 40,
 '凌晨 1-5 点下单 + 行程<7 天, 疑似抢低价票倒卖');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '新用户大单', '账户风险', '通用',
 '{"and": [{"field": "user_account_age_days", "op": "<", "value": 7}, {"field": "order_total_amount", "op": ">", "value": 10000}]}',
 '中', 50, '标记', 1, 55,
 '注册<7 天 + 订单>10000 元, 新号大额消费需关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R035', '多人跟团大单', '预订欺诈', '预订',
 '{"and": [{"field": "order_passenger_count", "op": ">=", "value": 8}, {"field": "order_total_amount", "op": ">", "value": 20000}]}',
 '高', 75, '人工审核', 1, 65,
 '乘客≥8 人且金额>20000, 疑似旅行社代订/倒票');

-- ============================
-- 场景三: 乘客风险 (2 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '乘客信息不一致', '乘客风险', '预订',
 '{"field": "pax_id_consistency", "op": "<", "value": 0.3}',
 '中', 50, '标记', 1, 50,
 '订单乘客证件号与历史乘客匹配率<30%, 疑似盗用证件代订');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑护照拦截', '乘客风险', '预订',
 '{"field": "pax_blacklist_hits", "op": ">", "value": 0}',
 '极高', 100, '拒绝', 1, 100,
 '乘客证件号命中黑名单, 一票否决');

-- ============================
-- 场景四: 退改签滥用 (1 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R020', '高频退订', '退改签滥用', '退改签',
 '{"field": "user_refund_count", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 70,
 '用户退改签≥3 次, 疑似退改套利/恶意占位');

-- ============================
-- 场景五: 支付风险 (1 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R040', '深夜大额支付', '支付风险', '支付',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">", "value": 30000}]}',
 '高', 70, '人工审核', 1, 60,
 '凌晨 1-5 点支付大额订单, 疑似盗刷/突击消费');

-- 总览: 11 条规则 (R001/R002/R005/R008/R012/R018/R020/R025/R030/R035/R040)

-- ============================
-- 演示黑名单种子数据 (RISK007 黑护照拦截用)
-- 类型: 护照号 / 设备指纹
-- ============================

INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time) VALUES
('护照号', 'PBLK00000000001', '演示: 黑护照拦截', NULL);

INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time) VALUES
('设备指纹', 'DEV_RISK_BOT', '演示: 疑似黄牛设备', NULL);

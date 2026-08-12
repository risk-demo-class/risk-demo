-- ============================================
-- 旅游风控系统 - 预置规则数据初始化
-- 8 条业务规则 (R001-R008), 对应任务书场景 A.2 + 1-业务说明.md 欺诈场景
-- ============================================================
-- R001  拒签历史拦截    (签证风险, 极高/拒绝)
-- R002  短期多国签证    (签证风险, 高/人工审核)
-- R003  黄牛囤票拦截    (黄牛囤票, 极高/拒绝)
-- R004  0点突击下单     (黄牛囤票, 中/标记)
-- R005  大额跨境游      (订单欺诈, 高/人工审核)
-- R006  新用户大单      (订单欺诈, 中/标记)
-- R007  乘客信息不一致  (订单欺诈, 中/标记)
-- R008  高频退改嫌疑    (退改欺诈, 高/人工审核)
-- ============================================================

USE ecs;

-- 关外键约束 (允许 TRUNCATE 被外键引用的表; P4-L1 risk_action_log.target_id 引用 risk_rule.rule_id)
SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联表 risk_action_log 的历史记录)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;  -- P4-L1 审计日志表, 也清空避免外键指向已删 rule_id

-- 恢复外键约束
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- R001 拒签历史拦截: 90 天内拒签 >= 2 次 (签证欺诈/非法移民链条)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '拒签历史拦截', '签证风险', '签证申请',
 '{"field": "user_visa_reject_count", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 100,
 '用户签证拒签次数>=2次，材料造假/非法移民嫌疑，一票否决');

-- ============================
-- R002 短期多国签证: 30 天内申请 >= 3 个不同国家
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '短期多国签证', '签证风险', '签证申请',
 '{"field": "user_visa_multi_country_30d", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 90,
 '30天内申请>=3个不同国家签证，疑似批量代办/非法移民');

-- ============================
-- R003 黄牛囤票拦截: 同一航班 1 小时窗口内预订 >= 5 张
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '黄牛囤票拦截', '黄牛囤票', '通用',
 '{"field": "order_same_flight_1h_count", "op": ">=", "value": 5}',
 '极高', 95, '拒绝', 1, 100,
 '同一航班1小时内预订>=5张，占座囤票倒卖，一票否决');

-- ============================
-- R004 0点突击下单: 凌晨 1-5 点下单 + 行程 < 7 天
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R004', '0点突击下单', '黄牛囤票', '通用',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_trip_days", "op": "<", "value": 7}]}',
 '中', 45, '标记', 1, 50,
 '凌晨1-5点下单且行程<7天，疑似突击抢票');

-- ============================
-- R005 大额跨境游: 出境订单金额 > 20000
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '大额跨境游', '订单欺诈', '通用',
 '{"and": [{"field": "order_is_international", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">", "value": 20000}]}',
 '高', 72, '人工审核', 1, 80,
 '单笔出境订单>20000元，大额跨境游人工审核');

-- ============================
-- R006 新用户大单: 注册 < 7 天 + 订单 > 10000
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R006', '新用户大单', '订单欺诈', '通用',
 '{"and": [{"field": "user_account_age_days", "op": "<", "value": 7}, {"field": "order_total_amount", "op": ">", "value": 10000}]}',
 '中', 55, '标记', 1, 60,
 '注册<7天的新用户下单>10000元，疑似黑产小号');

-- ============================
-- R007 乘客信息不一致: 本单新乘客占比 >= 70%
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '乘客信息不一致', '订单欺诈', '通用',
 '{"field": "order_new_passenger_rate", "op": ">=", "value": 0.7}',
 '中', 50, '标记', 1, 55,
 '订单乘客证件号与历史乘客匹配<30%，疑似盗用证件/代购');

-- ============================
-- R008 高频退改嫌疑: 退改率 >= 50%
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '高频退改嫌疑', '退改欺诈', '退改签申请',
 '{"field": "user_refund_rate", "op": ">=", "value": 0.5}',
 '高', 75, '人工审核', 1, 85,
 '用户退改率>=50%，疑似病退材料造假/恶意退款');

-- ============================================
-- 制造业风控系统 - 预置规则数据初始化
-- 13 条规则覆盖 6 大风险场景 (R001-R026, 编号沿用任务书 D.2)
-- ============================================================
-- R001-R002  串货风险/保修滥用 (2 条)
-- R003-R020  订货欺诈  (7 条: R003/R005/R007/R010/R012/R018/R020)
-- R025       经销商资质 (1 条)
-- R026       区域风险   (1 条)
-- 通用规则: R015 高保修率经销商
-- ============================================================

USE ecs;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 串货风险 (1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '跨区串货举报', '串货风险', '串货举报',
 '{"field": "order_report_count", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 100,
 '同一订单被举报跨区销售>=2次, 渠道串货实锤, 一票否决');

-- ============================
-- 场景二: 保修滥用 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '保修期外高频保修', '保修滥用', '保修申请',
 '{"and": [{"field": "order_is_out_of_warranty", "op": "==", "value": 1}, {"field": "order_sn_repair_count_90d", "op": ">=", "value": 2}]}',
 '高', 75, '人工审核', 1, 85,
 '设备已过保修期且 1 个月内申请>=2次保修, 疑似把付费维修转嫁厂商');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R015', '高保修率经销商', '保修滥用', '通用',
 '{"and": [{"field": "user_warranty_rate", "op": ">=", "value": 0.8}, {"field": "user_total_orders", "op": ">=", "value": 3}]}',
 '极高', 90, '拒绝', 1, 95,
 '经销商保修率>=80% 且订单>=3, 保修滥用模式, 一票否决');

-- ============================
-- 场景三: 订货欺诈 (6条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '大额采购订单', '订货欺诈', '采购订单',
 '{"field": "order_total_amount", "op": ">=", "value": 800000}',
 '高', 65, '人工审核', 1, 70,
 '单笔采购订单>=80万元, 需人工核实采购用途');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '大额经销商囤货', '订货欺诈', '经销商订货',
 '{"field": "order_total_amount", "op": ">=", "value": 1000000}',
 '高', 70, '人工审核', 1, 75,
 '单笔订货>=100万元, 疑似囤货套返利');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '30天高频订货', '订货欺诈', '经销商订货',
 '{"field": "user_orders_30d", "op": ">=", "value": 30}',
 '极高', 90, '拒绝', 1, 95,
 '30天内订货>=30单, 严重刷单/拆单嫌疑, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '凌晨突击订货', '订货欺诈', '经销商订货',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '中', 30, '标记', 1, 40,
 '凌晨0-6点下单, 标记关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '新经销商大单', '经销商资质', '经销商订货',
 '{"and": [{"field": "user_total_orders", "op": "<=", "value": 2}, {"field": "order_total_amount", "op": ">=", "value": 500000}]}',
 '中', 55, '标记', 1, 60,
 '历史订货<=2单且当前订单>=50万元, 新经销商大单风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R020', '异常低价订货', '订货欺诈', '经销商订货',
 '{"field": "order_msrp_ratio", "op": "<=", "value": 0.5}',
 '中', 50, '标记', 1, 55,
 '成交价<=MSRP 50%, 疑似低价串货/洗货');

-- ============================
-- 场景四: 维修欺诈 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '套保嫌疑', '维修欺诈', '售后维修',
 '{"field": "order_sn_repair_count_90d", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 100,
 '同一设备SN 90天内>=2次维修, 套保嫌疑, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '维修费用异常', '维修欺诈', '售后维修',
 '{"field": "order_repair_cost_ratio", "op": ">=", "value": 0.6}',
 '中', 45, '标记', 1, 50,
 '单次维修费用>设备MSRP 60%, 疑似虚报工时/配件');

-- ============================
-- 场景五: 经销商资质 (1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '经销商资质过期', '经销商资质', '经销商订货',
 '{"field": "user_dealer_contract_expired", "op": "==", "value": 1}',
 '中', 40, '标记', 1, 45,
 '经销合同已到期仍有订货, 资质异常');

-- ============================
-- 场景六: 区域风险 (1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R026', '跨区发货大单', '区域风险', '经销商订货',
 '{"and": [{"field": "order_ship_region_match", "op": "==", "value": 0}, {"field": "order_total_amount", "op": ">=", "value": 300000}]}',
 '高', 65, '人工审核', 1, 70,
 '订单发货区域!=经销商授权区域 且 金额>=30万元, 串货嫌疑');

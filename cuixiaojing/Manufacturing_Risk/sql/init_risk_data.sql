-- ============================================================
-- 制造业风控系统 - 预置规则数据初始化
-- 8 条规则覆盖说明书 D.2 全部业务规则 (R001/R002/R005/R008/R012/R018/R025/R030)
-- ============================================================

USE manufacturing_risk;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 串货风险
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '跨区串货举报', '串货风险', '串货举报',
 '{"field": "order_cross_region_report_count", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 100,
 '同一订单被举报跨区销售≥2次, 一票否决');

-- ============================
-- 保修滥用
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '保修期外高频保修', '保修滥用', '保修申请',
 '{"and": [{"field": "warranty_is_expired", "op": "==", "value": 1}, {"field": "warranty_apply_count_30d", "op": ">=", "value": 2}]}',
 '高', 75, '人工审核', 1, 90,
 '设备已过保修 + 1个月内申请≥2次, 疑似蹭保修');

-- ============================
-- 囤货风险
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '大额经销商囤货', '囤货风险', '经销商订货',
 '{"field": "order_total_amount", "op": ">", "value": 1000000}',
 '高', 70, '人工审核', 1, 80,
 '单笔订单>100万, 疑似囤货/窜货');

-- ============================
-- 维修异常
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '套保嫌疑', '维修异常', '售后维修',
 '{"field": "sn_repair_count_90d", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 95,
 '同一设备SN 90天内维修≥2次, 疑似套取保修, 一票否决');

-- ============================
-- 囤货风险 / 新经销商
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '新经销商大单', '囤货风险', '经销商订货',
 '{"and": [{"field": "dealer_contract_days", "op": "<", "value": 30}, {"field": "order_is_first", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">", "value": 500000}]}',
 '中', 50, '标记', 1, 70,
 '签约<30天 + 首单>50万, 新经销商异常大单');

-- ============================
-- 维修异常
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '维修费用异常', '维修异常', '售后维修',
 '{"field": "repair_cost_msrp_ratio", "op": ">", "value": 0.6}',
 '中', 55, '标记', 1, 60,
 '单次维修费用>设备MSRP 60%, 维修费用异常偏高');

-- ============================
-- 资质风险
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '经销商资质过期', '资质风险', '经销商订货',
 '{"field": "dealer_contract_expired", "op": "==", "value": 1}',
 '中', 50, '标记', 1, 65,
 '合同到期仍有订单, 经销商资质过期');

-- ============================
-- 综合风险 (黑名单拦截)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑经销商拦截', '综合风险', '通用',
 '{"field": "dealer_blacklist_hit", "op": "==", "value": 1}',
 '极高', 98, '拒绝', 1, 100,
 'dealer_id 在黑名单(风控黑名单或业务黑名单), 一票否决');

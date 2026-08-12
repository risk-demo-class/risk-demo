-- ============================================
-- 制造业风控系统 - 预置规则数据初始化 (16 条)
-- 覆盖 6 大制造业风险场景 (R001-R030)
-- ============================================================
-- R001/R004/R015  串货风险   (跨区串货举报 / 跨区大额 / 新区域首单大额)
-- R002/R006/R008  保修风险   (保修期外高频 / 高保修率 / 套保嫌疑)
-- R003/R005/R012/R029  订货风险 (夜间批量 / 大额囤货 / 新经销商大单 / 首单大额)
-- R007/R018       维修风险   (累计维修费过高 / 单次维修费异常)
-- R010/R020       账户风险   (多区域发货 / 高均价异常)
-- R025            资质风险   (经销商资质过期)
-- R030            账户风险   (黑经销商特征综合)
-- ============================================================

USE mfg_risk;

SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联审计日志)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 串货风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '跨区串货举报拦截', '串货风险', '跨区串货举报',
 '{"field": "order_cross_report_count", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 100,
 '同一订单被跨区串货举报>=2次，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R004', '跨区发货大额订单', '串货风险', '经销商订货',
 '{"and": [{"field": "order_is_cross_region", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 5000000}]}',
 '高', 70, '人工审核', 1, 85,
 '发货区域与授权区域不一致且订单>=500万元，疑似跨区串货');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R015', '新区域首单大额', '串货风险', '经销商订货',
 '{"and": [{"field": "addr_ship_is_new", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 3000000}]}',
 '高', 70, '人工审核', 1, 80,
 '经销商首次向新区域发货且订单>=300万元，串货高风险信号');

-- ============================
-- 保修风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '保修期外高频保修', '保修风险', '设备保修',
 '{"and": [{"field": "user_out_warranty_count", "op": ">=", "value": 1}, {"field": "order_warranty_30d", "op": ">=", "value": 2}]}',
 '高', 70, '人工审核', 1, 88,
 '设备已过保修期且近30天同设备保修>=2次，疑似套保');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R006', '高保修率经销商', '保修风险', '设备保修',
 '{"and": [{"field": "user_warranty_rate", "op": ">=", "value": 0.5}, {"field": "user_total_orders", "op": ">=", "value": 3}]}',
 '高', 65, '人工审核', 1, 75,
 '保修率>=50%且订货>=3单，保修行为异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '套保嫌疑', '保修风险', '设备保修',
 '{"field": "order_warranty_90d", "op": ">=", "value": 2}',
 '极高', 92, '拒绝', 1, 97,
 '同一设备SN近90天保修>=2次，疑似套保骗保，一票否决');

-- ============================
-- 订货风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '夜间批量订货', '订货风险', '经销商订货',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_quantity", "op": ">=", "value": 50}]}',
 '中', 40, '标记', 1, 50,
 '凌晨0-6点下单且数量>=50台，异常批量订货');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '大额经销商囤货', '订货风险', '经销商订货',
 '{"field": "order_quantity", "op": ">", "value": 100}',
 '高', 70, '人工审核', 1, 90,
 '单笔订货数量>100台，疑似囤货/倒卖');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '新经销商大单', '订货风险', '经销商订货',
 '{"and": [{"field": "user_contract_age_days", "op": "<", "value": 30}, {"field": "order_quantity", "op": ">", "value": 50}]}',
 '中', 45, '标记', 1, 60,
 '签约<30天且单笔订货>50台，新经销商大单需关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R029', '新经销商首单大额', '订货风险', '经销商订货',
 '{"and": [{"field": "user_total_orders", "op": "<=", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 3000000}]}',
 '高', 75, '人工审核', 1, 82,
 '历史订货<=1单且当前订单>=300万元，首单大额风险');

-- ============================
-- 维修风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '累计维修费用过高', '维修风险', '设备保修',
 '{"field": "user_repair_cost_total", "op": ">=", "value": 500000}',
 '高', 60, '人工审核', 1, 70,
 '累计维修费用>=50万元，维修成本异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '维修费用异常', '维修风险', '设备保修',
 '{"field": "order_repair_cost_ratio", "op": ">", "value": 0.6}',
 '中', 50, '标记', 1, 65,
 '单次维修费用>设备MSRP的60%，维修费虚高嫌疑');

-- ============================
-- 账户风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '多区域发货经销商', '账户风险', '通用',
 '{"field": "addr_ship_region_count", "op": ">=", "value": 5}',
 '中', 35, '标记', 1, 45,
 '经销商历史发货区域>=5个，跨区经营/串货嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R020', '高均价异常经销商', '账户风险', '经销商订货',
 '{"field": "user_avg_order_amount", "op": ">=", "value": 12000000}',
 '中', 40, '标记', 1, 55,
 '经销商平均订货金额>=1200万元，采购行为异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑经销商特征综合', '账户风险', '通用',
 '{"and": [{"field": "user_cross_report_count", "op": ">=", "value": 4}, {"field": "user_total_orders", "op": ">=", "value": 3}]}',
 '极高', 96, '拒绝', 1, 98,
 '被串货举报>=4次且订货>=3单，综合黑经销商特征，一票否决');

-- ============================
-- 资质风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '经销商资质过期仍订货', '资质风险', '经销商订货',
 '{"field": "order_contract_expired", "op": "==", "value": 1}',
 '中', 55, '标记', 1, 62,
 '经销商合同已到期仍下订货单，资质风险');

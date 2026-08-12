-- ============================================
-- 物流风控系统 - 预置业务规则 (R001-R009)
-- 规则字段: rule_condition 是 JSON 条件表达式, 求值逻辑在 app/engine/rule.py
-- 特征字段: 25 维物流特征 (见 app/engine/feature.py 与 ml_model.FEATURE_COLUMNS)
-- ============================================

USE tour_risk;

INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
-- R001: 危险品瞒报 (含电池/化学品但未如实申报) → 一票否决
('R001', '危险品瞒报', '危险品防控', '寄件',
 '{"field": "shipment_undeclared_flag", "op": "==", "value": 1}',
 '极高', 95, '拒绝', 1, 100, '运单含电池/化学品但未如实申报危险品, 一票否决'),

-- R002: 高频寄件 (近 7 天 >= 10 单) → 人工审核
('R002', '高频寄件', '寄递行为', '通用',
 '{"field": "user_shipment_7d", "op": ">=", "value": 10}',
 '高', 70, '人工审核', 1, 90, '近 7 天寄件 >= 10 单, 疑似刷单/黄牛寄件'),

-- R003: 凌晨批量寄件 (近 30 天 >= 20 单 + 夜间下单) → 拒绝
('R003', '凌晨批量寄件', '寄递行为', '寄件',
 '{"and": [{"field": "user_shipment_30d", "op": ">=", "value": 20}, {"field": "shipment_is_night", "op": "==", "value": 1}]}',
 '极高', 90, '拒绝', 1, 95, '凌晨批量寄件, 疑似黑产批量操作'),

-- R005: 大额代收货款 (COD 金额 >= 5000) → 人工审核
('R005', '大额代收货款', '代收货款', '代收货款',
 '{"field": "shipment_cod_amount", "op": ">=", "value": 5000}',
 '高', 70, '人工审核', 1, 85, '代收货款金额 >= 5000 元, 资金风险高'),

-- R008: 代收拒收率高 (历史拒收率 >= 50%) → 人工审核
('R008', '代收拒收率高', '代收货款', '代收货款',
 '{"field": "user_cod_reject_rate", "op": ">=", "value": 0.5}',
 '高', 75, '人工审核', 1, 80, '用户代收货款拒收率 >= 50%, 疑似恶意拒收'),

-- R010: 未实名寄件 → 标记
('R010', '未实名寄件', '账户风险', '寄件',
 '{"field": "user_real_name_status", "op": "==", "value": 0}',
 '中', 40, '标记', 1, 60, '寄件人未实名, 无法溯源'),

-- R012: 跨境价值虚报 (申报价值 <= 100 但重量 >= 5kg) → 标记
('R012', '跨境价值虚报', '跨境申报', '跨境申报',
 '{"and": [{"field": "shipment_is_cross_border", "op": "==", "value": 1}, {"field": "shipment_declared_value", "op": "<=", "value": 100}, {"field": "shipment_weight_kg", "op": ">=", "value": 5}]}',
 '中', 55, '标记', 1, 70, '跨境包裹价值与重量不匹配, 疑似低报价值'),

-- R018: 新地址大额 COD (地址新 + COD >= 3000) → 标记
('R018', '新地址大额COD', '地址风险', '代收货款',
 '{"and": [{"field": "addr_is_new", "op": "==", "value": 1}, {"field": "shipment_cod_amount", "op": ">=", "value": 3000}]}',
 '中', 55, '标记', 1, 65, '新收件地址 + 大额代收, 疑似钓鱼地址'),

-- R025: 新用户大单 (注册 < 7 天 + 申报价值 >= 10000) → 标记
('R025', '新用户大单', '账户风险', '通用',
 '{"and": [{"field": "user_account_age_days", "op": "<=", "value": 7}, {"field": "shipment_declared_value", "op": ">=", "value": 10000}]}',
 '中', 50, '标记', 1, 55, '新账号寄递高价值物品, 风险未知');

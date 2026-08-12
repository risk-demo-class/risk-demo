-- ============================================
-- 物流风控系统 - 预置规则数据初始化
-- 8 条物流规则覆盖 4 大物流场景 (R001-R030 保留原编号, 语义全部物流化)
-- ============================================================
-- R001  寄递实名   实名不一致       (parcel_pickup)
-- R002  危险品申报 危险品瞒报       (dangerous_declare)
-- R005  跨境合规   跨境违禁品       (cross_border_ship)
-- R008  代收货款   COD 卷款         (cod_settlement)
-- R012  寄递行为   同地址高频寄件   (通用)
-- R018  寄递行为   改派异常(高频换收件人) (parcel_pickup)
-- R025  寄递实名   大额低报         (parcel_pickup)
-- R030  地址风险   黑地址拦截       (通用, 一票否决)
-- ============================================================
-- 特征名与 app/engine/feature.py + ml_model.py::FEATURE_COLUMNS (25 维) 对齐:
--   用户 10: user_account_age_days/user_real_name_verified/user_is_enterprise/
--            user_total_parcel_count/user_total_parcel_count_30d/
--            user_total_parcel_count_7d/user_avg_declared_value/
--            user_distinct_receiver_count/user_cod_overdue_count/user_blacklist_hit_count
--   包裹 8:  order_weight_kg/order_declared_value/order_value_per_kg/order_piece_count/
--            order_is_international/order_is_dangerous_declared/order_has_cod/order_cod_amount
--   地址 7:  addr_sender_province/addr_receiver_province/addr_is_cross_province/
--            addr_same_address_sender_count_24h/addr_address_blacklist_hit/
--            addr_is_proxy_received/addr_sender_is_blacklisted
-- ============================================================

-- 关外键约束 (允许 TRUNCATE 被外键引用的表; risk_action_log.target_id 引用 risk_rule.rule_id)
SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联表 risk_action_log 的历史记录)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;  -- 审计日志表, 也清空避免外键指向已删 rule_id

-- 恢复外键约束
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- R001 实名不一致 (寄递实名)
-- 寄件人未实名认证 或 寄件地址命中黑名单 → 揽收前拦截核验
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '实名不一致（未实名认证/寄件地址黑名单）', '寄递实名', 'parcel_pickup',
 '{"or": [
   {"field": "user_real_name_verified", "op": "==", "value": 0},
   {"field": "addr_sender_is_blacklisted", "op": "==", "value": 1}
 ]}',
 '高', 70, '人工审核', 1, 85,
 '寄件人未实名认证 或 寄件地址命中黑名单，实名不一致风险');

-- ============================
-- R002 危险品瞒报 (危险品申报)
-- 申报危险品 但 价值密度异常低 (大重量低申报价值 → 疑似瞒报/夹带)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '危险品瞒报（价值密度异常低）', '危险品申报', 'dangerous_declare',
 '{"and": [
   {"field": "order_is_dangerous_declared", "op": "==", "value": 1},
   {"field": "order_value_per_kg", "op": "<", "value": 50}
 ]}',
 '高', 75, '人工审核', 1, 90,
 '申报危险品但每公斤申报价值低于50元，疑似瞒报价值/夹带违禁品');

-- ============================
-- R005 跨境违禁品 (跨境合规)
-- 国际件 + 危险品申报 → 跨境渠道通常禁运危险品, 一票否决
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '跨境违禁品（国际件申报危险品）', '跨境合规', 'cross_border_ship',
 '{"and": [
   {"field": "order_is_international", "op": "==", "value": 1},
   {"field": "order_is_dangerous_declared", "op": "==", "value": 1}
 ]}',
 '极高', 95, '拒绝', 1, 100,
 '国际件申报危险品，跨境运输违禁，一票否决');

-- ============================
-- R008 COD 卷款 (代收货款)
-- 用户有 COD 逾期记录 + 大额代收 → 卷款跑路风险, 一票否决
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', 'COD 卷款（逾期+大额代收）', '代收货款', 'cod_settlement',
 '{"and": [
   {"field": "user_cod_overdue_count", "op": ">=", "value": 1},
   {"field": "order_cod_amount", "op": ">=", "value": 1000}
 ]}',
 '极高', 92, '拒绝', 1, 98,
 '历史 COD 逾期记录且本次代收≥1000元，卷款风险高，一票否决');

-- ============================
-- R012 同地址高频寄件 (寄递行为)
-- 24 小时内同一寄件地址寄件≥3 次 → 疑似刷单/空包测试
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '同地址高频寄件（24h≥3）', '寄递行为', '通用',
 '{"field": "addr_same_address_sender_count_24h", "op": ">=", "value": 3}',
 '高', 65, '人工审核', 1, 75,
 '24小时内同一寄件地址寄件≥3次，疑似刷单/空包');

-- ============================
-- R018 改派异常 (寄递行为)
-- 高频更换收件人 (≥3 个不同收件人) + 高申报价值 → 改派/代收异常
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '改派异常（频繁更换收件人+高价值）', '寄递行为', 'parcel_pickup',
 '{"and": [
   {"field": "user_distinct_receiver_count", "op": ">=", "value": 3},
   {"field": "order_declared_value", "op": ">=", "value": 2000}
 ]}',
 '高', 70, '人工审核', 1, 80,
 '频繁更换收件人且本次申报价值≥2000元，改派/异常代收风险');

-- ============================
-- R025 大额低报 (寄递实名)
-- 申报价值高 但 价值密度极低 (重量/申报不匹配 → 低报海关/保险)
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '大额低报（申报与重量不匹配）', '寄递实名', 'parcel_pickup',
 '{"and": [
   {"field": "order_declared_value", "op": ">=", "value": 3000},
   {"field": "order_value_per_kg", "op": "<", "value": 100}
 ]}',
 '高', 80, '人工审核', 1, 88,
 '申报价值≥3000元但每公斤申报价值低于100元，重量与价值不匹配，疑似低报');

-- ============================
-- R030 黑地址拦截 (地址风险)
-- 收件地址命中黑名单 → 一票否决, 不再走 7 步决策
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑地址拦截（收件地址命中黑名单）', '地址风险', '通用',
 '{"field": "addr_address_blacklist_hit", "op": ">=", "value": 1}',
 '极高', 95, '拒绝', 1, 100,
 '收件地址命中黑名单，一票否决');

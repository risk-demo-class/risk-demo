-- ============================================
-- 物流行业风控系统 - 预置规则数据初始化
-- 28 条规则覆盖 6 大物流风险场景 (L_R001-L_R030)
-- ============================================
-- L_R001-L_R005  危险品瞒报 / 申报价值欺诈
-- L_R006-L_R009  高频寄件 / 刷单风险
-- L_R010-L_R013  账户风险 (取消率 / 投诉 / 多地址)
-- L_R014-L_R017  取消运单滥用
-- L_R018-L_R021  地址风险
-- L_R022-L_R024  投诉风险
-- L_R025-L_R030  综合 / 新用户 / 实名风险
-- ============================================

USE ecs;

SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 申报价值欺诈 (5 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R001', '单笔超高申报价值运单', '危险品瞒报', 'shipment_create',
 '{"field": "order_total_amount", "op": ">=", "value": 5000}',
 '高', 70, '人工审核', 1, 90,
 '单笔申报价值≥5000元, 可能存在瞒报/虚报风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R002', '单笔极端高额申报运单', '危险品瞒报', 'shipment_create',
 '{"field": "order_total_amount", "op": ">=", "value": 12000}',
 '极高', 95, '拒绝', 1, 100,
 '单笔申报价值≥12000元, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R003', '深夜寄件', '危险品瞒报', 'shipment_create',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '中', 30, '标记', 1, 40,
 '凌晨0-6点寄件, 标记关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R004', '多物品种类运单', '危险品瞒报', 'shipment_create',
 '{"field": "order_category_count", "op": ">=", "value": 3}',
 '高', 60, '人工审核', 1, 70,
 '单票物品类别≥3种, 疑似夹带违禁品');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R005', '大量物品运单 (疑似刷单)', '危险品瞒报', 'shipment_create',
 '{"field": "order_sku_count", "op": ">=", "value": 8}',
 '高', 65, '人工审核', 1, 60,
 '单票物品总数≥8件, 疑似批量刷单');

-- ============================
-- 场景二: 高频寄件 / 刷单风险 (4 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R006', '用户7天内高频寄件', '跨境申报', 'shipment_create',
 '{"field": "user_orders_7d", "op": ">=", "value": 5}',
 '高', 70, '人工审核', 1, 80,
 '7天内寄件≥5次, 疑似刷单');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R007', '用户30天内大量寄件', '跨境申报', 'shipment_create',
 '{"field": "user_orders_30d", "op": ">=", "value": 12}',
 '极高', 90, '拒绝', 1, 95,
 '30天内寄件≥12次, 严重刷单嫌疑, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R008', '申报价值远超用户平均', '跨境申报', 'shipment_create',
 '{"and": [{"field": "order_total_amount", "op": ">=", "value": 2000}, {"field": "user_avg_order_amount", "op": "<", "value": 500}]}',
 '高', 65, '人工审核', 1, 75,
 '当前申报≥2000且用户历史平均<500, 行为异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R009', '用户累计申报异常', '跨境申报', '通用',
 '{"field": "user_total_amount", "op": ">=", "value": 30000}',
 '中', 40, '标记', 1, 50,
 '用户累计申报≥3万元, 标记为高价值用户');

-- ============================
-- 场景三: 账户风险 (4 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R010', '高取消率用户', '实名核验', '通用',
 '{"and": [{"field": "user_cancel_count", "op": ">=", "value": 3}, {"field": "user_total_orders", "op": ">=", "value": 5}]}',
 '中', 45, '标记', 1, 55,
 '取消运单≥3次且总运单≥5, 取消行为异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R011', '新用户大额寄件', '实名核验', 'shipment_create',
 '{"and": [{"field": "user_total_orders", "op": "<=", "value": 2}, {"field": "order_total_amount", "op": ">=", "value": 3000}]}',
 '高', 75, '人工审核', 1, 85,
 '历史运单≤2且当前申报≥3000元, 新用户大额风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R012', '用户有大量投诉记录', '实名核验', '通用',
 '{"field": "user_complaint_count", "op": ">=", "value": 2}',
 '高', 60, '人工审核', 1, 65,
 '投诉次数≥2, 账户存在风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R013', '多地址用户', '地址风险', '通用',
 '{"field": "user_address_count", "op": ">=", "value": 5}',
 '中', 35, '标记', 1, 45,
 '用户收货地址≥5个, 关注账户共享可能');

-- ============================
-- 场景四: 取消运单滥用 (4 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R014', '高取消率寄件人', '地址风险', 'shipment_cancel',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.5}, {"field": "user_total_orders", "op": ">=", "value": 5}]}',
 '高', 70, '人工审核', 1, 80,
 '取消率≥50%且运单≥5单, 疑似恶意取消');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R015', '极端取消率用户', '地址风险', 'shipment_cancel',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.8}, {"field": "user_total_orders", "op": ">=", "value": 3}]}',
 '极高', 92, '拒绝', 1, 98,
 '取消率≥80%且运单≥3单, 严重滥用, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R016', '高投诉率用户', '实名核验', '通用',
 '{"and": [{"field": "user_postsale_rate", "op": ">=", "value": 0.4}, {"field": "user_total_orders", "op": ">=", "value": 5}]}',
 '中', 50, '标记', 1, 60,
 '投诉率≥40%且运单≥5, 投诉行为需关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R017', '高取消申报价值用户', '跨境申报', '通用',
 '{"field": "user_refund_amount", "op": ">=", "value": 5000}',
 '高', 55, '人工审核', 1, 55,
 '累计取消运单申报价值≥5000元, 金额异常');

-- ============================
-- 场景五: 地址风险 (4 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R018', '新目的地址寄件', '地址风险', 'shipment_create',
 '{"field": "addr_is_new", "op": "==", "value": 1}',
 '低', 15, '通过', 1, 20,
 '使用新目的地址寄件, 低风险标记');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R019', '新地址+大额申报', '地址风险', 'shipment_create',
 '{"and": [{"field": "addr_is_new", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 2000}]}',
 '高', 70, '人工审核', 1, 82,
 '新地址且申报价值≥2000元, 地址欺诈风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R020', '多省份地址用户', '地址风险', '通用',
 '{"field": "addr_province_count", "op": ">=", "value": 3}',
 '中', 40, '标记', 1, 50,
 '用户地址覆盖≥3个省份, 地址分散异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R021', '大量地址用户+高申报', '地址风险', 'shipment_create',
 '{"and": [{"field": "addr_total_count", "op": ">=", "value": 4}, {"field": "order_total_amount", "op": ">=", "value": 1500}]}',
 '高', 65, '人工审核', 1, 70,
 '地址≥4个且申报≥1500元, 疑似代收/转单');

-- ============================
-- 场景六: 投诉风险 (3 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R022', '有投诉记录用户寄件', '地址风险', 'shipment_create',
 '{"field": "user_complaint_count", "op": ">=", "value": 1}',
 '低', 20, '通过', 1, 30,
 '有物流投诉记录的用户寄件, 低风险标记');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R023', '高频投诉用户', '实名核验', 'shipment_cancel',
 '{"field": "user_complaint_count", "op": ">=", "value": 3}',
 '高', 60, '人工审核', 1, 70,
 '投诉次数≥3次, 疑似恶意投诉');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R024', '代收货款大额签收', '跨境申报', 'shipment_receive',
 '{"field": "order_total_amount", "op": ">=", "value": 5000}',
 '高', 65, '人工审核', 1, 72,
 '代收货款类大额运单签收, 关注资金风险');

-- ============================
-- 综合 / 新用户 / 深夜签收 (6 条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R025', '极小申报价值运单 (疑似刷单测试)', '跨境申报', 'shipment_create',
 '{"field": "order_total_amount", "op": "<=", "value": 20}',
 '高', 50, '人工审核', 1, 85,
 '申报价值≤20元, 疑似刷单测试或恶意占库存');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R026', '收货地址数过多 (>10)', '地址风险', '通用',
 '{"field": "user_address_count", "op": ">", "value": 10}',
 '高', 55, '人工审核', 1, 60,
 '用户收货地址超过10个, 疑似批量小号注册');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R027', '新地址 + 多次换地址', '地址风险', 'shipment_create',
 '{"and": [{"field": "addr_is_new", "op": "==", "value": 1}, {"field": "user_address_count", "op": ">=", "value": 4}]}',
 '高', 55, '人工审核', 1, 65,
 '首次用新地址寄件 + 用户地址≥4个, 疑似恶意换地址');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R028', '深夜签收', '实名核验', 'shipment_receive',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '中', 30, '标记', 1, 40,
 '凌晨0-6点签收, 标记关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R029', '新用户首单大额 (零评估历史)', '实名核验', 'shipment_create',
 '{"and": [{"field": "assessment_count", "op": "==", "value": 0}, {"field": "order_total_amount", "op": ">=", "value": 5000}]}',
 '高', 70, '人工审核', 1, 75,
 '新注册用户 (无评估历史) 首单≥5000, 高风险信号');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L_R030', '综合高风险 (取消+大额+多地址)', '实名核验', '通用',
 '{"and": [
   {"field": "user_refund_rate", "op": ">=", "value": 0.5},
   {"field": "user_avg_order_amount", "op": ">=", "value": 2000},
   {"field": "user_address_count", "op": ">=", "value": 3}
 ]}',
 '极高', 90, '拒绝', 1, 95,
 '取消率≥50% 且 平均申报≥2000元 且 地址≥3个, 3 个高危条件 AND 触发一票否决');

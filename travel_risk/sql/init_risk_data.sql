-- ============================================
-- 旅游风控系统 - 预置规则数据初始化
-- 30 条规则覆盖 7 大旅游风险场景 (R001-R030)
-- ============================================
-- R001-R005  下单欺诈   (5 条)
-- R006-R009  支付风险   (4 条)
-- R010-R013  账户风险   (4 条)
-- R014-R018  退改滥用   (5 条)
-- R019-R022  出行人风险 (4 条)
-- R023-R026  供应商风险 (4 条, 目的地/临期/行程维度)
-- R027-R030  综合风险   (4 条, 多信号叠加)
-- ============================================

USE travel_risk;

SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 下单欺诈 (5条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '单笔高额旅游订单', '下单欺诈', '下单',
 '{"field": "order_total_amount", "op": ">=", "value": 20000}',
 '高', 70, '人工审核', 1, 90,
 '单笔旅游订单实付金额≥20000元，可能存在盗刷/欺诈风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '单笔极端高额旅游订单', '下单欺诈', '下单',
 '{"field": "order_total_amount", "op": ">=", "value": 50000}',
 '极高', 95, '拒绝', 1, 100,
 '单笔旅游订单实付金额≥50000元，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '深夜下单', '下单欺诈', '下单',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '中', 30, '标记', 1, 40,
 '凌晨0-6点下单，标记关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R004', '极速支付', '下单欺诈', '下单',
 '{"field": "order_pay_interval_sec", "op": "between", "value": [0, 5]}',
 '高', 60, '人工审核', 1, 70,
 '下单到支付间隔≤5秒，疑似机器下单');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '高折扣率订单', '下单欺诈', '下单',
 '{"field": "order_discount_rate", "op": ">=", "value": 0.7}',
 '高', 65, '人工审核', 1, 60,
 '订单折扣率≥70%，疑似利用优惠漏洞');

-- ============================
-- 场景二: 支付风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R006', '用户7天内高频下单', '支付风险', '支付',
 '{"field": "user_bookings_7d", "op": ">=", "value": 10}',
 '高', 70, '人工审核', 1, 80,
 '7天内旅游下单≥10次，疑似刷单/占位');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '用户30天内大量下单', '支付风险', '支付',
 '{"field": "user_bookings_30d", "op": ">=", "value": 30}',
 '极高', 90, '拒绝', 1, 95,
 '30天内下单≥30次，严重刷单/黄牛嫌疑，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '订单金额远超用户平均', '支付风险', '支付',
 '{"and": [{"field": "user_total_bookings", "op": ">=", "value": 3}, {"field": "order_total_amount", "op": ">=", "value": 50000}, {"field": "user_avg_order_amount", "op": ">", "value": 0}]}',
 '高', 60, '人工审核', 1, 75,
 '订单金额远超用户历史平均消费水平，疑似盗刷');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R009', '新用户首单大额', '支付风险', '支付',
 '{"and": [{"field": "user_total_bookings", "op": "<=", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 10000}]}',
 '高', 65, '人工审核', 1, 70,
 '新用户首单金额≥10000元，盗刷风险高');

-- ============================
-- 场景三: 账户风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '高退改率用户', '账户风险', '通用',
 '{"field": "user_refund_rate", "op": ">=", "value": 0.3}',
 '高', 60, '人工审核', 1, 80,
 '历史退改率≥30%，存在恶意退改/薅羊毛嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R011', '极高退改率用户', '账户风险', '通用',
 '{"field": "user_refund_rate", "op": ">=", "value": 0.5}',
 '极高', 90, '拒绝', 1, 95,
 '历史退改率≥50%，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '多设备登录', '账户风险', '注册',
 '{"field": "user_device_count", "op": ">=", "value": 3}',
 '中', 40, '标记', 1, 50,
 '绑定设备数≥3，疑似养号/多开');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R013', '设备聚集', '账户风险', '注册',
 '{"field": "user_device_count", "op": ">=", "value": 5}',
 '高', 60, '人工审核', 1, 60,
 '绑定设备数≥5，疑似批量注册/设备农场');

-- ============================
-- 场景四: 退改滥用 (5条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R014', '频繁退改', '退改滥用', '退改申请',
 '{"field": "user_refund_change_count", "op": ">=", "value": 3}',
 '高', 65, '人工审核', 1, 80,
 '历史退改次数≥3次，疑似恶意退改');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R015', '退改金额高', '退改滥用', '退改申请',
 '{"field": "user_refund_amount", "op": ">=", "value": 5000}',
 '高', 60, '人工审核', 1, 70,
 '历史退改金额≥5000元，资金异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R016', '频繁理赔', '退改滥用', '理赔申请',
 '{"field": "user_claim_count", "op": ">=", "value": 2}',
 '高', 65, '人工审核', 1, 85,
 '历史理赔次数≥2次，疑似骗保');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R017', '高理赔率', '退改滥用', '理赔申请',
 '{"field": "user_claim_rate", "op": ">=", "value": 0.3}',
 '极高', 90, '拒绝', 1, 95,
 '理赔率≥30%，严重骗保嫌疑，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '多次投诉', '退改滥用', '投诉',
 '{"field": "user_complaint_count", "op": ">=", "value": 3}',
 '高', 60, '人工审核', 1, 70,
 '历史投诉次数≥3次，存在恶意投诉/纠纷风险');

-- ============================
-- 场景五: 出行人风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R019', '单笔订单出行人过多', '出行人风险', '下单',
 '{"field": "order_traveler_count", "op": ">=", "value": 8}',
 '高', 60, '人工审核', 1, 75,
 '单笔订单出行人≥8人，疑似批量囤票');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R020', '出行人手机号过多', '出行人风险', '下单',
 '{"field": "traveler_phone_count", "op": ">=", "value": 4}',
 '高', 65, '人工审核', 1, 70,
 '单笔订单不同出行人手机号≥4个，疑似拼凑身份');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R021', '新出行人过多', '出行人风险', '下单',
 '{"field": "traveler_new_count", "op": ">=", "value": 6}',
 '中', 40, '标记', 1, 50,
 '单笔订单首次出行人≥6人，身份真实性待核');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R022', '累计出行人过多', '出行人风险', '下单',
 '{"field": "user_traveler_count", "op": ">=", "value": 20}',
 '高', 60, '人工审核', 1, 65,
 '账号累计出行人≥20人，疑似代订/黄牛账号');

-- ============================
-- 场景六: 供应商风险 (4条, 目的地/临期/行程维度)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R023', '出境游大额订单', '供应商风险', '下单',
 '{"and": [{"field": "order_is_overseas", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 30000}]}',
 '高', 70, '人工审核', 1, 85,
 '出境游订单金额≥30000元，跨境欺诈风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R024', '出境游多人同行', '供应商风险', '下单',
 '{"and": [{"field": "order_is_overseas", "op": "==", "value": 1}, {"field": "order_traveler_count", "op": ">=", "value": 5}]}',
 '中', 40, '标记', 1, 55,
 '出境游出行人≥5人，重点核验签证材料');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '临期预订', '供应商风险', '下单',
 '{"field": "order_lead_days", "op": "<=", "value": 1}',
 '中', 40, '标记', 1, 55,
 '距出发≤1天才预订，疑似临期盗刷/占位');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R026', '超短行程大额', '供应商风险', '下单',
 '{"and": [{"field": "order_trip_days", "op": "<=", "value": 2}, {"field": "order_total_amount", "op": ">=", "value": 20000}]}',
 '高', 65, '人工审核', 1, 70,
 '行程≤2天但金额≥20000元，价格与行程严重不符');

-- ============================
-- 场景七: 综合风险 (4条, 多信号叠加)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R027', '多信号叠加高危', '综合风险', '通用',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.3}, {"field": "user_claim_count", "op": ">=", "value": 1}, {"field": "user_device_count", "op": ">=", "value": 2}]}',
 '极高', 95, '拒绝', 1, 100,
 '高退改率+理赔+多设备三重信号叠加，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R028', '疑似刷评', '综合风险', '投诉',
 '{"and": [{"field": "user_review_count", "op": ">=", "value": 10}, {"field": "user_total_bookings", "op": "<=", "value": 5}]}',
 '中', 40, '标记', 1, 45,
 '点评数≥10但订单数≤5，疑似刷单刷评');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R029', '夜间大额下单', '综合风险', '下单',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 10000}]}',
 '高', 65, '人工审核', 1, 65,
 '凌晨下单且金额≥10000元，盗刷高发场景');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '新出行人出境游', '综合风险', '下单',
 '{"and": [{"field": "traveler_new_count", "op": ">=", "value": 3}, {"field": "order_is_overseas", "op": "==", "value": 1}]}',
 '高', 60, '人工审核', 1, 60,
 '新出行人≥3且出境游，需核验出行人真实身份');

-- 旅游 OTA 风控规则。核心表枚举保持不变，全部使用“通用”事件类型，
-- 由 25 维旅游特征判断适用场景。

UPDATE risk_rule
SET is_enabled = 0
WHERE deleted_at IS NULL;

INSERT INTO risk_rule
    (rule_id, rule_name, rule_category, event_type, rule_condition,
     risk_level, risk_score, action, is_enabled, priority, description, deleted_at)
VALUES
('R001', '拒签历史拦截', '账户风险', '通用',
 '{"field":"user_postsale_count","op":">=","value":2}',
 '极高', 95, '拒绝', 1, 100,
 '用户近90天累计拒签历史不少于2次，一票否决。', NULL),

('R002', '短期多国签证', '账户风险', '通用',
 '{"field":"user_cancel_count","op":">=","value":3}',
 '高', 75, '人工审核', 1, 90,
 '用户近30天签证申请涉及至少3个不同目的国。', NULL),

('R005', '大额跨境游', '订单欺诈', '通用',
 '{"field":"order_total_amount","op":">","value":50000}',
 '高', 70, '人工审核', 1, 80,
 '单笔旅游订单金额超过50000元。', NULL),

('R008', '黄牛囤票', '订单欺诈', '通用',
 '{"field":"order_sku_count","op":">=","value":5}',
 '极高', 95, '拒绝', 1, 95,
 '同一用户一小时内预订同一航班累计不少于5张票。', NULL),

('R012', '0点突击下单', '订单欺诈', '通用',
 '{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_pay_interval_sec","op":"<","value":7}]}',
 '中', 45, '标记', 1, 50,
 '凌晨1至5点下单，且距离出发不足7天。', NULL),

('R018', '乘客信息不一致', '账户风险', '通用',
 '{"and":[{"field":"user_address_count","op":">=","value":1},{"field":"order_item_count","op":">","value":0},{"field":"order_discount_rate","op":"<","value":0.3}]}',
 '中', 40, '标记', 1, 45,
 '本单乘客证件与该用户历史乘客证件匹配率低于30%。', NULL),

('R025', '新用户大单', '账户风险', '通用',
 '{"and":[{"field":"order_discount_amount","op":"<","value":7},{"field":"order_total_amount","op":">","value":10000}]}',
 '中', 50, '标记', 1, 60,
 '注册不足7天的新用户提交金额超过10000元的订单。', NULL),

('R030', '黑护照拦截', '账户风险', '通用',
 '{"field":"user_complaint_count","op":">=","value":1}',
 '极高', 100, '拒绝', 1, 110,
 '用户历史或本单乘客护照命中有效业务黑名单。', NULL)
ON DUPLICATE KEY UPDATE
    rule_name = VALUES(rule_name),
    rule_category = VALUES(rule_category),
    event_type = VALUES(event_type),
    rule_condition = VALUES(rule_condition),
    risk_level = VALUES(risk_level),
    risk_score = VALUES(risk_score),
    action = VALUES(action),
    is_enabled = VALUES(is_enabled),
    priority = VALUES(priority),
    description = VALUES(description),
    deleted_at = NULL;

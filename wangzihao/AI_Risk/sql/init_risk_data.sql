-- 制造业设备经销商风控系统 - 第一版 7 条 JSON 风控规则
-- 黑经销商不做规则：继续由 process_event 第 3 步以 risk_blacklist.“用户”前置拦截。
-- 当前连接数据库由 scripts/init_db.py 的 --db 决定。

USE ecs;

TRUNCATE TABLE risk_rule;

INSERT INTO risk_rule
(rule_id, rule_name, rule_category, event_type, rule_condition, risk_level,
 risk_score, action, is_enabled, priority, description)
VALUES
('R001', '跨区域串货拦截', '物流风险', '物流投诉',
 '{"and":[{"field":"addr_is_new","op":"==","value":1},{"field":"order_discount_rate","op":"==","value":1}]}',
 '极高', 95, '拒绝', 1, 100,
 '制造业语义：设备实际区域与授权或预期区域不一致。两个区域异常槽位均为1时拒绝；黑经销商仍由前置黑名单处理。'),

('R002', '经销商累计高频保修', '售后滥用', '售后申请',
 '{"field":"user_postsale_count","op":">=","value":10}',
 '高', 70, '人工审核', 1, 80,
 '制造业语义：同一经销商累计保修申请达到10次。当前25维没有近7天保修次数，因此第一版使用累计次数，不伪造时间窗口。'),

('R003', '新经销商大额采购', '订单欺诈', '下单',
 '{"and":[{"field":"user_cancel_count","op":"<","value":30},{"field":"order_total_amount","op":">=","value":1000000}]}',
 '高', 75, '人工审核', 1, 90,
 '制造业语义：合作不足30天且当前采购金额不少于100万元。user_cancel_count兼容槽位在制造业中表示合作天数。'),

('R004', '老旧设备高额保修', '售后滥用', '售后申请',
 '{"and":[{"field":"order_pay_interval_sec","op":">=","value":157680000},{"field":"order_total_amount","op":">=","value":100000}]}',
 '高', 75, '人工审核', 1, 85,
 '制造业语义：设备年龄至少5年（按365天/年折算157680000秒）且当前索赔金额不少于10万元。'),

('R005', '经销商多异常区域暴露', '地址风险', '通用',
 '{"and":[{"field":"addr_province_count","op":">=","value":2},{"field":"addr_total_count","op":">=","value":5}]}',
 '高', 65, '人工审核', 1, 70,
 '制造业语义：经销商历史至少出现2个异常区域，且授权、交付、举报区域触点累计至少5个，替代当前特征无法可靠表达的多经销商地址集中规则。'),

('R006', '同设备重复保修拦截', '售后滥用', '售后申请',
 '{"field":"order_sku_count","op":">=","value":3}',
 '极高', 92, '拒绝', 1, 95,
 '制造业语义：当前保修设备历史保修申请达到3次。order_sku_count在保修事件中表示同设备历史保修次数。'),

('R007', '高额保修缺少材料', '售后滥用', '售后申请',
 '{"and":[{"field":"order_total_amount","op":">=","value":100000},{"field":"order_category_count","op":"==","value":0}]}',
 '中', 45, '标记', 1, 60,
 '制造业语义：当前索赔金额不少于10万元且照片材料数量为0。order_category_count在保修事件中表示照片数量。');

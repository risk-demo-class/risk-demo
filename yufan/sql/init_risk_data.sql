-- 教育行业风控规则初始化（12 条）
-- 为保持老师 risk_rule 核心表不变，底层分类沿用原枚举，展示层在阶段 11 映射为教育名称。
USE ecs;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_action_log;
TRUNCATE TABLE risk_rule;
SET FOREIGN_KEY_CHECKS = 1;

INSERT INTO risk_rule
(rule_id, rule_name, rule_category, event_type, rule_condition, risk_level,
 risk_score, action, is_enabled, priority, description)
VALUES
('EDU001', '单笔超高额课程报名', '订单欺诈', '通用',
 '{"field":"order_total_amount","op":">=","value":10000}',
 '极高', 95, '拒绝', 1, 100, '单笔教育业务金额达到10000元，拒绝并进入案件审查'),

('EDU002', '七日短时大额连报', '订单欺诈', '通用',
 '{"and":[{"field":"user_orders_7d","op":">=","value":4},{"field":"user_total_amount","op":">=","value":30000}]}',
 '极高', 90, '拒绝', 1, 98, '7日内报名至少4次且累计金额达到30000元'),

('EDU003', '高比例频繁退费', '售后滥用', '通用',
 '{"and":[{"field":"user_refund_rate","op":">=","value":0.75},{"field":"user_refund_count","op":">=","value":3}]}',
 '极高', 92, '拒绝', 1, 97, '退费比例高且累计申请至少3次'),

('EDU004', '低学习时长反复退费', '售后滥用', '通用',
 '{"field":"user_postsale_count","op":">=","value":3}',
 '高', 75, '人工审核', 1, 90, '学习不足30分钟的退费申请累计至少3次'),

('EDU005', '累计退费金额异常', '售后滥用', '通用',
 '{"field":"user_refund_amount","op":">=","value":20000}',
 '高', 70, '人工审核', 1, 85, '累计申请退费金额达到20000元'),

('EDU006', '设备关联多账号', '地址风险', '通用',
 '{"field":"addr_total_count","op":">=","value":5}',
 '极高', 88, '拒绝', 1, 96, '同一设备关联至少5个教育账号，疑似工作室或代理学习'),

('EDU007', '设备关联多身份', '地址风险', '通用',
 '{"field":"addr_province_count","op":">=","value":5}',
 '高', 72, '人工审核', 1, 88, '同一设备关联至少5个不同实名身份'),

('EDU008', '异常大额直播打赏', '支付风险', '通用',
 '{"and":[{"field":"user_complaint_count","op":">=","value":1},{"field":"order_total_amount","op":">=","value":1000}]}',
 '极高', 94, '拒绝', 1, 99, '存在大额打赏历史且当前教育业务金额达到1000元'),

('EDU009', '夜间高额教育消费', '支付风险', '通用',
 '{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_total_amount","op":">=","value":3000}]}',
 '高', 65, '人工审核', 1, 75, '深夜发生3000元以上报名、退费或打赏'),

('EDU010', '低历史账号高额消费', '账户风险', '通用',
 '{"and":[{"field":"user_total_orders","op":"<=","value":1},{"field":"order_total_amount","op":">=","value":5000}]}',
 '高', 68, '人工审核', 1, 78, '报名历史不超过1笔但当前金额达到5000元'),

('EDU011', '共享设备代理学习', '物流风险', '通用',
 '{"and":[{"field":"addr_total_count","op":">=","value":5},{"field":"order_pay_interval_sec","op":">=","value":75}]}',
 '极高', 90, '拒绝', 1, 95, '共享设备关联多账号且学习完成率达到75%以上，疑似代理学习'),

('EDU012', '当前退费几乎未学习', '售后滥用', '通用',
 '{"and":[{"field":"user_refund_count","op":">=","value":2},{"field":"order_sku_count","op":"<=","value":5},{"field":"order_discount_rate","op":">=","value":0.8}]}',
 '高', 78, '人工审核', 1, 92, '多次退费且当前申请学习不足5分钟、退费比例达到80%');

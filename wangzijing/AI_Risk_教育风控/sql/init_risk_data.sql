-- 教育行业 EDU001-EDU008 规则种子。
-- 使用 upsert，可重复初始化；极高规则仍由 decision.py 一票否决保护。

INSERT INTO `risk_rule` (
    `rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`,
    `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`, `deleted_at`
) VALUES
('EDU001', '零学时大额退费', '退费滥用', '退费申请',
 '{"and":[{"field":"order_pay_interval_sec","op":"<","value":5},{"field":"order_total_amount","op":">=","value":1000}]}',
 '高', 70, '人工审核', 1, 80, '学习不足5分钟且申请退还大额课程费用，转人工核验学习与退费材料。', NULL),
('EDU002', '连环退费', '退费滥用', '退费申请',
 '{"and":[{"field":"user_postsale_count","op":">=","value":3},{"field":"user_refund_amount","op":">=","value":10000}]}',
 '高', 75, '人工审核', 1, 85, '同一用户累计至少3次退费申请且成功退费金额达到10000元。', NULL),
('EDU003', '极高退费率', '退费滥用', '通用',
 '{"and":[{"field":"user_total_orders","op":">=","value":3},{"field":"user_refund_rate","op":">=","value":0.5}]}',
 '极高', 95, '拒绝', 1, 100, '至少3次有效报名且成功退费率达到50%，作为明确高危退费模式。', NULL),
('EDU004', '同设备多账号', '设备风险', '通用',
 '{"field":"addr_province_count","op":">=","value":5}',
 '极高', 95, '拒绝', 1, 100, '当前设备指纹关联至少5个有效账号，疑似批量注册或团伙操作。', NULL),
('EDU005', '新设备大额报名', '设备风险', '课程报名',
 '{"and":[{"field":"addr_is_new","op":"==","value":1},{"field":"order_total_amount","op":">=","value":10000}]}',
 '高', 70, '人工审核', 1, 75, '首次出现不足7天的设备发起万元以上课程报名。', NULL),
('EDU006', '凌晨大额报名', '交易异常', '课程报名',
 '{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_total_amount","op":">=","value":5000}]}',
 '中', 45, '标记', 1, 60, '凌晨1点至5点发起5000元以上报名，记录标记供后续观察。', NULL),
('EDU007', '身份连续认证失败', '认证风险', '通用',
 '{"field":"user_complaint_count","op":">=","value":2}',
 '高', 70, '人工审核', 1, 90, '用户实名认证、学籍或学历认证累计失败至少2次。', NULL),
('EDU008', '超高金额报名', '交易异常', '课程报名',
 '{"field":"order_total_amount","op":">=","value":30000}',
 '极高', 95, '拒绝', 1, 100, '单笔课程报名实付金额达到30000元，触发极高风险保护。', NULL)
ON DUPLICATE KEY UPDATE
    `rule_name`=VALUES(`rule_name`),
    `rule_category`=VALUES(`rule_category`),
    `event_type`=VALUES(`event_type`),
    `rule_condition`=VALUES(`rule_condition`),
    `risk_level`=VALUES(`risk_level`),
    `risk_score`=VALUES(`risk_score`),
    `action`=VALUES(`action`),
    `is_enabled`=VALUES(`is_enabled`),
    `priority`=VALUES(`priority`),
    `description`=VALUES(`description`),
    `deleted_at`=NULL;

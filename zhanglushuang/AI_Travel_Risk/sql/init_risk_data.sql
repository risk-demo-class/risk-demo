-- ============================================================
-- 旅游出行风控规则初始化
-- 规则条件基于 config/features.yaml 的特征名
-- ============================================================

INSERT IGNORE INTO `risk_rule` (
    `rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`,
    `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`
) VALUES
(
    'R001', '拒签历史拦截', '签证风险', '签证申请',
    '{"field":"user_visa_reject_90d","op":">=","value":2}',
    '极高', 95, '拒绝', 1, 100, '90天内签证被拒>=2次'
),
(
    'R002', '短期多国签证', '签证风险', '签证申请',
    '{"field":"user_visa_countries_30d","op":">=","value":3}',
    '高', 80, '人工审核', 1, 90, '30天内申请>=3个国家签证'
),
(
    'R003', '连续退改套利', '退改滥用', '退改申请',
    '{"field":"user_consecutive_refund_change","op":">=","value":3}',
    '高', 75, '人工审核', 1, 90, '连续退改>=3次'
),
(
    'R004', '同设备多账号订酒店', '设备风险', '下单',
    '{"field":"device_hotel_account_count","op":">=","value":3}',
    '高', 75, '人工审核', 1, 85, '同一设备7天关联>=3个账号订酒店'
),
(
    'R005', '大额跨境游', '跨境风险', '下单',
    '{"field":"order_total_amount","op":">","value":50000}',
    '高', 70, '人工审核', 1, 80, '单笔订单超过50000元'
),
(
    'R006', '团票批量下单', '订单欺诈', '下单',
    '{"field":"same_pay_account_1h_orders","op":">=","value":5}',
    '极高', 95, '拒绝', 1, 100, '同一支付账号1小时下单>=5笔'
),
(
    'R007', '酒店预授权异常', '支付风险', '支付',
    '{"field":"order_preauth_diff","op":">","value":1000}',
    '高', 65, '人工审核', 1, 75, '酒店预授权与实际扣款差异异常'
),
(
    'R008', '黄牛囤票', '订单欺诈', '下单',
    '{"field":"same_flight_1h_bookings","op":">=","value":5}',
    '极高', 95, '拒绝', 1, 100, '同一航班1小时预订>=5张'
),
(
    'R012', '0点突击下单', '订单欺诈', '下单',
    '{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_trip_days","op":"<","value":7}]}',
    '中', 50, '标记', 1, 60, '凌晨下单且行程<7天'
),
(
    'R018', '乘客信息不一致', '订单欺诈', '下单',
    '{"field":"passenger_match_rate","op":"<","value":0.3}',
    '中', 45, '标记', 1, 55, '乘客与历史乘客匹配率<30%'
),
(
    'R025', '新用户大单', '账户风险', '下单',
    '{"and":[{"field":"user_total_orders","op":"<=","value":1},{"field":"order_total_amount","op":">","value":10000}]}',
    '中', 55, '标记', 1, 70, '注册时间短且订单金额大'
),
(
    'R040', '备注命中黄牛暗号', '订单欺诈', '下单',
    '{"field":"remark_llm_score","op":">=","value":80}',
    '高', 80, '人工审核', 1, 90, 'LLM识别订单备注为黄牛暗号'
),
(
    'R041', '违规拼团', '订单欺诈', '拼团报名',
    '{"field":"remark_illegal_group_buy_flag","op":"==","value":1}',
    '高', 80, '人工审核', 1, 90, 'LLM识别订单备注为违规拼团'
);

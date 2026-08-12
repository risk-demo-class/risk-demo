DELETE FROM risk_rule WHERE rule_id LIKE 'TR%';

INSERT INTO risk_rule(rule_id,rule_name,rule_category,event_type,rule_condition,risk_level,risk_score,action,is_enabled,priority,description) VALUES
('TR001','拒签历史拦截','签证风险','签证申请','{"field":"user_visa_reject_count_90d","op":">=","value":2}','极高',95,'拒绝',1,100,'90天内拒签至少2次'),
('TR002','短期多国签证','签证风险','签证申请','{"and":[{"field":"user_visa_apply_count_30d","op":">=","value":3},{"field":"user_country_count_30d","op":">=","value":3}]}','高',75,'人工审核',1,80,'30天申请多个国家签证'),
('TR003','大额跨境行程','行程风险','通用','{"and":[{"field":"order_is_cross_border","op":"==","value":1},{"field":"order_total_amount","op":">=","value":50000}]}','高',75,'人工审核',1,85,'大额跨境旅游订单'),
('TR004','黄牛囤票','票务欺诈','机票预订','{"field":"order_same_flight_count_1h","op":">=","value":5}','极高',95,'拒绝',1,100,'同支付账号一小时同航班至少5张票'),
('TR005','凌晨临期下单','行程风险','机票预订','{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_days_to_depart","op":"<","value":7}]}','中',45,'标记',1,55,'凌晨预订临期航班'),
('TR006','乘客信息异常','身份风险','机票预订','{"and":[{"field":"user_passenger_match_rate","op":"<","value":0.3},{"field":"order_passenger_count","op":">=","value":3}]}','中',45,'标记',1,50,'乘客与历史常用乘客差异大'),
('TR007','新用户大单','账户风险','通用','{"and":[{"field":"user_account_age_days","op":"<","value":7},{"field":"order_total_amount","op":">=","value":10000}]}','中',45,'标记',1,60,'注册不足7天的大额订单'),
('TR008','黑证件拦截','身份风险','通用','{"field":"addr_passport_blacklisted","op":"==","value":1}','极高',95,'拒绝',1,100,'乘客证件命中旅游黑名单');

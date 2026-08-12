-- ============================================
-- 旅游行业风控系统 - 预置规则与黑名单初始化
-- 25 条旅游业务规则 (R001-R025)
-- ============================================

USE ecs;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_action_log;
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_blacklist;
SET FOREIGN_KEY_CHECKS = 1;

INSERT INTO risk_rule
(rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description)
VALUES
('R001','拒签历史拦截','签证风险','签证申请','{"field":"user_visa_reject_count_90d","op":">=","value":2}','极高',95,'拒绝',1,100,'用户90天内签证拒签次数>=2，一票否决'),
('R002','短期多国签证','签证风险','签证申请','{"field":"user_visa_country_count_30d","op":">=","value":3}','高',75,'人工审核',1,90,'30天内申请3个及以上国家签证'),
('R003','高风险目的地','目的地风险','通用','{"field":"addr_destination_risk_score","op":">=","value":85}','高',70,'人工审核',1,80,'目的地风险分>=85'),
('R004','临期高风险目的地下单','旅游订单风险','旅游下单','{"and":[{"field":"order_days_to_departure","op":"<=","value":7},{"field":"order_destination_risk_score","op":">=","value":70}]}','高',78,'人工审核',1,88,'临近出行且目的地风险较高'),
('R005','大额跨境游','旅游订单风险','旅游下单','{"and":[{"field":"order_is_cross_border","op":"==","value":1},{"field":"order_total_amount","op":">=","value":50000}]}','高',76,'人工审核',1,86,'跨境旅游订单金额>=50000'),
('R006','超大额旅游订单','旅游订单风险','通用','{"field":"order_total_amount","op":">=","value":100000}','极高',92,'拒绝',1,98,'单笔旅游订单金额>=100000，一票否决'),
('R007','多人团单异常','旅游订单风险','旅游下单','{"and":[{"field":"order_passenger_count","op":">=","value":10},{"field":"order_total_amount","op":">=","value":30000}]}','高',72,'人工审核',1,82,'多人团单且金额较高'),
('R008','黄牛囤票','机票风险','机票预订','{"field":"order_same_flight_ticket_count_1h","op":">=","value":5}','极高',96,'拒绝',1,100,'同支付账号1小时同航班票数>=5，一票否决'),
('R009','临期机票大单','机票风险','机票预订','{"and":[{"field":"order_days_to_departure","op":"<=","value":3},{"field":"order_total_amount","op":">=","value":15000}]}','高',72,'人工审核',1,80,'临近出发的大额机票订单'),
('R010','高端酒店临期预订','酒店风险','酒店预订','{"field":"order_high_value_hotel_near_departure","op":"==","value":1}','高',70,'人工审核',1,78,'临期高价酒店预订'),
('R011','高频下单','账户风险','通用','{"field":"user_orders_7d","op":">=","value":8}','中',55,'标记',1,60,'近7天旅游订单数>=8'),
('R012','凌晨突击下单','旅游订单风险','通用','{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_trip_days","op":"<=","value":7}]}','中',50,'标记',1,58,'凌晨下单且行程较短'),
('R013','短期订单激增','账户风险','通用','{"field":"user_orders_30d","op":">=","value":20}','中',58,'标记',1,62,'近30天订单数>=20'),
('R014','退款率偏高','售后滥用','售后申请','{"field":"user_refund_rate_90d","op":">=","value":0.4}','中',55,'标记',1,65,'90天退款率>=40%'),
('R015','退款率极高','售后滥用','售后申请','{"field":"user_refund_rate_90d","op":">=","value":0.8}','极高',90,'拒绝',1,95,'90天退款率>=80%，一票否决'),
('R016','高频退款','售后滥用','售后申请','{"field":"user_refund_count_90d","op":">=","value":5}','高',68,'人工审核',1,75,'90天退款次数>=5'),
('R017','投诉高发用户','投诉风险','投诉','{"field":"user_complaint_count_90d","op":">=","value":4}','中',55,'标记',1,60,'90天投诉次数>=4'),
('R018','乘客信息不一致','账户风险','通用','{"field":"order_passenger_match_rate","op":"<","value":0.3}','中',58,'标记',1,66,'本单旅客与历史旅客匹配率<30%'),
('R019','多旅客新用户','账户风险','旅游下单','{"and":[{"field":"user_account_age_days","op":"<","value":7},{"field":"order_passenger_count","op":">=","value":5}]}','中',58,'标记',1,68,'新账号一次绑定多名旅客'),
('R020','高价值新客','账户风险','通用','{"and":[{"field":"user_account_age_days","op":"<","value":30},{"field":"order_total_amount","op":">=","value":20000}]}','高',70,'人工审核',1,76,'注册30天内用户提交高价值订单'),
('R021','目的地高风险大单','目的地风险','通用','{"and":[{"field":"order_destination_risk_score","op":">=","value":80},{"field":"order_total_amount","op":">=","value":30000}]}','极高',90,'拒绝',1,94,'高风险目的地叠加大额订单，一票否决'),
('R022','投诉后立即售后','售后滥用','售后申请','{"and":[{"field":"user_complaint_count_90d","op":">=","value":2},{"field":"order_refund_amount_rate","op":">=","value":0.8}]}','高',72,'人工审核',1,74,'投诉与高额退款叠加'),
('R023','高频旅客绑定','账户风险','通用','{"field":"user_passenger_count_30d","op":">=","value":12}','中',56,'标记',1,64,'30天关联旅客数>=12'),
('R024','签证拒签后大额下单','签证风险','旅游下单','{"and":[{"field":"user_visa_reject_count_90d","op":">=","value":1},{"field":"order_total_amount","op":">=","value":20000}]}','高',74,'人工审核',1,84,'拒签后仍提交大额订单'),
('R025','新用户大单','账户风险','通用','{"and":[{"field":"user_account_age_days","op":"<","value":7},{"field":"order_total_amount","op":">=","value":10000}]}','中',58,'标记',1,70,'注册7天内用户提交万元以上订单');

INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time)
VALUES
('用户','TU0001','演示用户黑名单',NULL),
('手机号','13900000000','演示手机号黑名单',NULL),
('护照号','P86000042','演示护照黑名单',NULL),
('支付账号','pay_0001@wallet','演示支付账号黑名单',NULL),
('设备指纹','dev_0001','演示设备指纹黑名单',NULL),
('IP','172.1.5.11','演示IP黑名单',NULL),
('订单','TO00001','演示订单黑名单',NULL);

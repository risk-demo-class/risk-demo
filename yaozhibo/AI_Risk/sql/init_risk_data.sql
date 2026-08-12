-- 在线教育风控预置规则：7 条
SET NAMES utf8mb4;

INSERT INTO `risk_rule`
(`rule_id`,`rule_name`,`rule_category`,`event_type`,`rule_condition`,`risk_level`,`risk_score`,`action`,`is_enabled`,`priority`,`description`) VALUES
('R001','刷单式报名','课程报名','COURSE_PURCHASE','{"and":[{"field":"course_new_account_purchase_count_7d","op":">=","value":5},{"field":"user_account_age_days","op":"<=","value":7}]}','高',70,'人工审核',1,90,'同一课程7天内多个新账号集中报名'),
('R002','0学时退费','课程退费','REFUND_REQUEST','{"and":[{"field":"refund_study_minutes","op":"<","value":5},{"field":"refund_amount","op":">","value":0}]}','高',75,'人工审核',1,95,'学习不足5分钟就申请退费'),
('R005','大额连报','课程报名','COURSE_PURCHASE','{"field":"user_purchase_amount_1h","op":">","value":30000}','高',75,'人工审核',1,85,'1小时内课程订单金额超过30000元'),
('R008','假学员或代理账号','设备异常','通用','{"field":"device_distinct_users_30d","op":">=","value":5}','极高',95,'拒绝',1,100,'同一设备关联5个及以上学员账号'),
('R012','退费连环','课程退费','REFUND_REQUEST','{"and":[{"field":"user_refund_count_90d","op":">=","value":3},{"field":"user_refund_amount_90d","op":">","value":10000}]}','中',55,'标记',1,75,'90天退费至少3次且金额超过10000元'),
('R025','学员身份不符','身份异常','COURSE_PURCHASE','{"and":[{"field":"user_role_teacher_flag","op":"==","value":1},{"field":"course_is_student_only","op":"==","value":1},{"field":"student_only_purchase_count_30d","op":">=","value":3}]}','高',65,'人工审核',1,80,'教师账号大量购买仅对学员开放的课程'),
('R030','黑学号或黑身份拦截','身份异常','通用','{"or":[{"field":"student_id_blacklisted","op":"==","value":1},{"field":"id_card_blacklisted","op":"==","value":1},{"field":"device_id_blacklisted","op":"==","value":1}]}','极高',100,'拒绝',1,110,'学号、身份证或设备命中教育黑名单')
ON DUPLICATE KEY UPDATE
`rule_name`=VALUES(`rule_name`), `rule_category`=VALUES(`rule_category`),
`event_type`=VALUES(`event_type`), `rule_condition`=VALUES(`rule_condition`),
`risk_level`=VALUES(`risk_level`), `risk_score`=VALUES(`risk_score`),
`action`=VALUES(`action`), `is_enabled`=VALUES(`is_enabled`),
`priority`=VALUES(`priority`), `description`=VALUES(`description`), `deleted_at`=NULL;

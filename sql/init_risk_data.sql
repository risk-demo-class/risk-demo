USE education_risk;

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('E001','新账号大额连报','报名欺诈','课程报名','{"and":[{"field":"user_account_age_days","op":"<","value":7},{"field":"order_total_amount","op":">=","value":10000}]}','高',75,'人工审核',1,90,'注册7天内报名金额达到1万元'),
('E002','凌晨大额课程报名','报名欺诈','课程报名','{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_total_amount","op":">=","value":30000}]}','极高',95,'拒绝',1,100,'凌晨进行3万元以上课程报名'),
('E003','同设备多学员','账号风险','通用','{"field":"user_device_user_count","op":">=","value":5}','极高',92,'拒绝',1,98,'同一设备关联5个以上学员账号'),
('E004','0学时退费','退费滥用','退费申请','{"field":"user_address_count","op":"<","value":5}','高',70,'人工审核',1,85,'学习总时长不足5分钟就申请退费'),
('E005','频繁退费','退费滥用','退费申请','{"and":[{"field":"user_refund_count","op":">=","value":3},{"field":"user_refund_amount","op":">=","value":10000}]}','中',55,'标记',1,65,'累计退费3次以上且金额超过1万元'),
('E006','退费率过高','退费滥用','退费申请','{"and":[{"field":"user_refund_rate","op":">=","value":0.8},{"field":"user_total_orders","op":">=","value":3}]}','极高',90,'拒绝',1,97,'报名3次以上且退费率达到80%'),
('E007','新账号直播大额打赏','直播风险','直播打赏','{"and":[{"field":"user_account_age_days","op":"<","value":30},{"field":"user_live_reward_30d","op":">=","value":5000}]}','高',70,'人工审核',1,80,'新注册账号大额直播打赏'),
('E008','老师购买学生课程','账号风险','课程报名','{"field":"addr_province_count","op":"==","value":0}','中',35,'标记',1,40,'实名状态异常或角色与课程不匹配');

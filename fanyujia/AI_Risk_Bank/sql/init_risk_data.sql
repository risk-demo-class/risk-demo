-- 银行风控预置规则：规则解释器保持通用 JSON 语义不变。
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
SET FOREIGN_KEY_CHECKS = 1;
INSERT INTO risk_rule(rule_id,rule_name,rule_category,event_type,rule_condition,risk_level,risk_score,action,is_enabled,priority,description) VALUES
('R001','异地大额转账','交易欺诈','转账','{"and":[{"field":"txn_amount","op":">=","value":50000},{"field":"txn_is_cross_geo","op":"==","value":1}]}','极高',95,'拒绝',1,100,'异地且单笔五万元以上转账'),
('R002','凌晨密集交易','交易欺诈','通用','{"and":[{"field":"txn_is_night","op":"==","value":1},{"field":"user_txn_count_1h","op":">=","value":3}]}','高',75,'人工审核',1,90,'凌晨一小时内多笔交易'),
('R003','新设备大额交易','设备风险','通用','{"and":[{"field":"user_new_device_flag","op":">=","value":1},{"field":"txn_amount","op":">=","value":30000}]}','高',85,'拒绝',1,95,'近期新设备发起大额交易'),
('R004','多卡资金归集','交易欺诈','转账','{"field":"txn_distinct_source_cards_1h","op":">=","value":5}','极高',95,'拒绝',1,100,'一小时多张卡向同一收款方归集'),
('R005','贷款申请突击','信贷风险','贷款申请','{"field":"user_loan_apply_count_30d","op":">=","value":3}','高',75,'人工审核',1,85,'三十天内多次申请贷款'),
('R006','设备多人共用','设备风险','通用','{"field":"device_linked_user_count","op":">=","value":5}','中',55,'标记',1,60,'同一设备关联多位用户'),
('R007','代理IP访问','网络风险','登录','{"field":"ip_is_proxy","op":"==","value":1}','中',50,'标记',1,70,'登录IP命中代理网络'),
('R008','Tor出口访问','网络风险','登录','{"field":"ip_is_tor","op":"==","value":1}','极高',90,'拒绝',1,100,'登录IP命中Tor出口');

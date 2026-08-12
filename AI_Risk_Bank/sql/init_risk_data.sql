USE ecs;
DELETE FROM risk_rule;
INSERT INTO risk_rule(rule_id,rule_name,rule_category,event_type,rule_condition,risk_level,risk_score,action,is_enabled,priority,description) VALUES
('R001','异地大额转账','交易反欺诈','大额转账','{"and":[{"field":"order_total_amount","op":">=","value":50000},{"field":"addr_province_count","op":">=","value":2}]}','极高',95,'拒绝',1,100,'登录/交易地域异常且金额超过五万元'),
('R002','凌晨密集操作','交易反欺诈','大额转账','{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_sku_count","op":">=","value":3}]}','高',82,'人工审核',1,90,'凌晨一小时内设备交易密集'),
('R005','新设备大额交易','设备风险','大额转账','{"and":[{"field":"addr_is_new","op":"==","value":1},{"field":"order_total_amount","op":">=","value":30000}]}','高',85,'人工审核',1,80,'新设备发起大额资金操作'),
('R008','多卡归集','交易反欺诈','大额转账','{"and":[{"field":"order_sku_count","op":">=","value":3},{"field":"order_total_amount","op":">=","value":30000}]}','极高',95,'拒绝',1,100,'短时多资金节点归集'),
('R012','信贷申请突击','信贷风险','贷款申请','{"and":[{"field":"user_postsale_count","op":">=","value":3},{"field":"order_total_amount","op":">=","value":100000}]}','高',80,'人工审核',1,70,'短期高频信贷申请'),
('R018','设备多人共用','设备风险','异常登录','{"field":"order_item_count","op":">=","value":5}','中',60,'标记',1,50,'同一设备关联多个客户'),
('R025','代理 IP/Tor','渠道风险','异常登录','{"field":"order_is_night","op":"==","value":1}','中',65,'标记',1,40,'高风险网络环境或异常时段登录'),
('R030','黑卡拦截','黑名单','大额转账','{"field":"order_discount_amount","op":">=","value":1}','极高',100,'拒绝',0,110,'银行黑卡由 bank_blacklist_extra 前置短路拦截；本规则停用，避免普通转账被误判'),
('R031','高负债贷款申请','信贷风险','贷款申请','{"field":"user_refund_rate","op":">=","value":0.5}','高',75,'人工审核',1,60,'历史异常交易比例较高且申请贷款'),
('R032','KYC不足高额度申请','账户安全','信用卡申请','{"and":[{"field":"order_total_amount","op":">=","value":50000},{"field":"user_complaint_count","op":">=","value":1}]}','高',75,'人工审核',1,60,'身份核验等级不足且申请高额度');


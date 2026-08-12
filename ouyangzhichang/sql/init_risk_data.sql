SET NAMES utf8mb4;
DELETE FROM risk_rule;
INSERT INTO risk_rule(rule_id,rule_name,rule_category,event_type,rule_condition,risk_level,risk_score,action,is_enabled,priority,description) VALUES
('L001','危险品瞒报','危险品风险','安检申报','{"and":[{"field":"shipment_declaration_mismatch","op":"==","value":1},{"field":"shipment_dangerous_flag","op":"==","value":1}]}','极高',100,'拒绝',1,100,'电池、化学品或液体未如实申报'),
('L002','跨境重量异常','跨境申报风险','跨境申报','{"field":"shipment_declared_weight_diff_rate","op":">=","value":0.5}','高',75,'人工审核',1,90,'实际重量与申报重量偏差达到50%'),
('L003','跨境低价申报','跨境申报风险','跨境申报','{"and":[{"field":"shipment_actual_weight","op":">=","value":10},{"field":"shipment_declared_value","op":"<","value":200}]}','高',70,'人工审核',1,80,'较重跨境件申报价值异常偏低'),
('L004','COD高拒收用户','代收货款风险','代收货款结算','{"and":[{"field":"sender_cod_refuse_count_90d","op":">=","value":3},{"field":"sender_cod_refuse_rate_90d","op":">=","value":0.5}]}','极高',95,'拒绝',1,95,'90天COD拒收次数和拒收率均异常'),
('L005','一小时高频寄件','寄件行为风险','寄件下单','{"field":"sender_shipments_1h","op":">=","value":10}','高',75,'人工审核',1,85,'一小时内创建十张以上运单'),
('L006','凌晨异常寄件','寄件行为风险','寄件下单','{"field":"sender_night_shipments_30d","op":">=","value":5}','中',45,'标记',1,50,'近30天凌晨寄件次数异常'),
('L007','多人共用风险地址','地址风险','通用','{"and":[{"field":"address_user_count_30d","op":">=","value":5},{"field":"address_is_remote_or_temporary","op":"==","value":1}]}','高',70,'人工审核',1,75,'多人共同使用临时或偏远地址'),
('L008','新账号高值跨境件','实名风险','跨境申报','{"and":[{"field":"sender_account_age_days","op":"<","value":7},{"field":"shipment_is_cross_border","op":"==","value":1},{"field":"shipment_declared_value","op":">=","value":10000}]}','高',80,'人工审核',1,88,'注册不足7天即寄送高值跨境件');

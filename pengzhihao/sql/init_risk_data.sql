-- 物流业务规则。核心 risk_rule 表及其 ENUM 不变，事件/分类通过适配层对外翻译。
DELETE FROM `risk_rule`;

INSERT INTO `risk_rule`
(`rule_id`,`rule_name`,`rule_category`,`event_type`,`rule_condition`,`risk_level`,`risk_score`,`action`,`is_enabled`,`priority`,`description`) VALUES
('L001','寄件人实名核验异常','账户风险','下单',
 JSON_OBJECT('field','user_complaint_count','op','>=','value',1),'极高',90,'拒绝',1,100,
 '寄件人未完成实名核验、证件过期或信息不符'),
('L002','疑似危险品瞒报','物流风险','支付',
 JSON_OBJECT('field','order_category_count','op','>=','value',1),'极高',95,'拒绝',1,110,
 '验视发现未申报锂电池、化学品等禁限寄物品'),
('L003','跨境包裹重量偏差','售后滥用','售后申请',
 JSON_OBJECT('field','order_discount_rate','op','>=','value',0.30),'极高',92,'拒绝',1,105,
 '实际重量与申报重量偏差达到30%'),
('L004','跨境高价值且重量异常','售后滥用','售后申请',
 JSON_OBJECT('and',JSON_ARRAY(
   JSON_OBJECT('field','order_total_amount','op','>=','value',1000),
   JSON_OBJECT('field','order_discount_rate','op','>=','value',0.20)
 )),'高',78,'人工审核',1,90,
 '高申报价值跨境件同时存在重量偏差'),
('L005','代收货款高拒收率','支付风险','物流投诉',
 JSON_OBJECT('and',JSON_ARRAY(
   JSON_OBJECT('field','user_refund_count','op','>=','value',3),
   JSON_OBJECT('field','user_refund_rate','op','>=','value',0.30)
 )),'极高',90,'拒绝',1,100,
 '寄件人历史COD拒收次数和拒收率同时异常'),
('L006','代收货款拒收敞口过高','支付风险','物流投诉',
 JSON_OBJECT('and',JSON_ARRAY(
   JSON_OBJECT('field','user_refund_amount','op','>=','value',3000),
   JSON_OBJECT('field','user_refund_rate','op','>=','value',0.30)
 )),'高',75,'人工审核',1,85,
 'COD拒收金额累计超过3000元'),
('L007','七日高频寄件','订单欺诈','下单',
 JSON_OBJECT('field','user_orders_7d','op','>=','value',12),'高',70,'人工审核',1,80,
 '近七日寄件次数达到12次'),
('L008','凌晨高频寄件','订单欺诈','下单',
 JSON_OBJECT('and',JSON_ARRAY(
   JSON_OBJECT('field','order_is_night','op','==','value',1),
   JSON_OBJECT('field','user_orders_7d','op','>=','value',8)
 )),'极高',88,'拒绝',1,95,
 '凌晨寄件且近七日寄件频繁'),
('L009','多人共用收件地址','地址风险','通用',
 JSON_OBJECT('field','addr_total_count','op','>=','value',5),'高',72,'人工审核',1,75,
 '同一标准化地址关联五个及以上寄件人'),
('L010','高风险新地址组合','地址风险','通用',
 JSON_OBJECT('and',JSON_ARRAY(
   JSON_OBJECT('field','addr_is_new','op','==','value',1),
   JSON_OBJECT('field','user_orders_7d','op','>=','value',5)
 )),'高',68,'人工审核',1,70,
 '临时、偏远或首次使用地址叠加近期频繁寄件');

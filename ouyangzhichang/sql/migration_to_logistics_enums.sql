-- 仅供保留已有数据库数据时使用；全新课堂环境优先执行 init_db.py --reset --yes。
USE ecs;
ALTER TABLE risk_rule MODIFY rule_category ENUM('实名风险','危险品风险','跨境申报风险','代收货款风险','地址风险','寄件行为风险') NOT NULL;
ALTER TABLE risk_rule MODIFY event_type ENUM('寄件下单','安检申报','跨境申报','签收处理','代收货款结算','通用') NOT NULL DEFAULT '通用';
ALTER TABLE risk_event MODIFY event_type ENUM('寄件下单','安检申报','跨境申报','签收处理','代收货款结算') NOT NULL;
ALTER TABLE risk_feature MODIFY entity_type ENUM('寄件人','运单','地址') NOT NULL;
ALTER TABLE risk_case MODIFY event_type ENUM('寄件下单','安检申报','跨境申报','签收处理','代收货款结算') NULL;
ALTER TABLE risk_blacklist MODIFY blacklist_type ENUM('寄件人','收件人','手机号','证件号','地址','设备指纹','跨境收件方') NOT NULL;

-- 最小银行演示数据；完整可重复数据由 scripts/gen_business_data.py 生成。
INSERT IGNORE INTO bank_user_info VALUES
('U0001','张三','id_hash_u1',720,'2024-01-01 09:00:00',3,20000,0.20,'上海', '正常'),
('U0002','李四','id_hash_u2',580,'2025-07-01 09:00:00',2,8000,0.55,'北京', '正常'),
('U0003','王五','id_hash_u3',650,'2023-05-01 09:00:00',3,15000,0.35,'广州', '正常');
INSERT IGNORE INTO bank_card VALUES
('CARD001','U0001','card_hash_001','CMB','信用卡',50000,'2024-01-01 09:00:00'),
('CARD002','U0002','card_hash_002','ICBC','储蓄卡',20000,'2025-07-01 09:00:00'),
('CARD003','U0003','card_hash_003','CCB','信用卡',30000,'2023-05-01 09:00:00');
INSERT IGNORE INTO ip_geo_location VALUES
('10.0.0.1','中国','上海','上海','ISP-A',0,0),('10.0.0.99','中国','北京','北京','Proxy',1,0),('10.0.0.66','德国','柏林','柏林','Tor',0,1);
INSERT IGNORE INTO device_fingerprint(device_id,user_id,fingerprint_hash,first_seen,last_seen,os,browser) VALUES
('DEV001','U0001','fp001','2024-01-01 09:00:00','2026-08-01 09:00:00','Android','Chrome'),
('DEV002','U0002','fp002','2026-08-01 09:00:00','2026-08-10 09:00:00','iOS','Safari');
INSERT IGNORE INTO payee_relationship(user_id,payee_id,payee_card_hash,first_txn_at,last_txn_at,txn_count,total_amount) VALUES
('U0001','P001','payee_hash_001','2025-01-01 09:00:00','2026-08-01 09:00:00',10,12000);

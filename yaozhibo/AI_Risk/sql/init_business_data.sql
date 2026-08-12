-- 在线教育业务种子数据：正常用户 + A~F 可解释风险用户
SET NAMES utf8mb4;

INSERT IGNORE INTO `user_info`
(`user_id`,`name`,`role`,`student_id`,`id_card_hash`,`real_name_status`,`register_at`,`device_id`) VALUES
('T001','王老师','teacher',NULL,SHA2('ID-T001',256),'VERIFIED','2025-01-01 08:00:00','DEV-TEACHER-1'),
('A001','正常学员A','student','STU-A001',SHA2('ID-A001',256),'VERIFIED','2025-01-10 09:00:00','DEV-A001'),
('B001','零学时退费B','student','STU-B001',SHA2('ID-B001',256),'VERIFIED','2026-07-01 09:00:00','DEV-B001'),
('C001','连环退费C','student','STU-C001',SHA2('ID-C001',256),'VERIFIED','2025-06-01 09:00:00','DEV-C001'),
('D001','代理账号D1','student','STU-D001',SHA2('ID-D001',256),'VERIFIED','2026-08-08 09:00:00','DEV-SHARED-D'),
('D002','代理账号D2','student','STU-D002',SHA2('ID-D002',256),'VERIFIED','2026-08-08 09:05:00','DEV-SHARED-D'),
('D003','代理账号D3','student','STU-D003',SHA2('ID-D003',256),'VERIFIED','2026-08-08 09:10:00','DEV-SHARED-D'),
('D004','代理账号D4','student','STU-D004',SHA2('ID-D004',256),'VERIFIED','2026-08-08 09:15:00','DEV-SHARED-D'),
('D005','代理账号D5','student','STU-D005',SHA2('ID-D005',256),'VERIFIED','2026-08-08 09:20:00','DEV-SHARED-D'),
('D006','代理账号D6','student','STU-D006',SHA2('ID-D006',256),'VERIFIED','2026-08-08 09:25:00','DEV-SHARED-D'),
('E001','大额连报E','student','STU-E001',SHA2('ID-E001',256),'VERIFIED','2026-08-09 08:00:00','DEV-E001'),
('F001','黑学号F','student','STU-F001',SHA2('ID-F001',256),'VERIFIED','2025-04-01 08:00:00','DEV-F001');

INSERT IGNORE INTO `course`
(`course_id`,`name`,`category`,`price`,`teacher_id`,`total_hours`,`audience_role`,`status`) VALUES
('CRS001','Python风控入门','编程',3999.00,'T001',60,'student','ACTIVE'),
('CRS002','AI数据分析','人工智能',8999.00,'T001',80,'student','ACTIVE'),
('CRS003','XGBoost实战','机器学习',9999.00,'T001',72,'student','ACTIVE'),
('CRS004','家庭教育公开课','素质教育',999.00,'T001',12,'all','ACTIVE');

INSERT IGNORE INTO `order_info`
(`order_id`,`user_id`,`course_id`,`order_type`,`total_amount`,`payment_status`,`study_goal`,`expected_finish_days`,`created_at`) VALUES
('ORD-A001','A001','CRS001','PURCHASE',3999.00,'PAID','系统学习',90,'2026-08-01 10:00:00'),
('ORD-B001','B001','CRS002','PURCHASE',8999.00,'PAID','试学',30,'2026-08-10 10:00:00'),
('ORD-C001','C001','CRS001','PURCHASE',3999.00,'REFUNDED','转行',60,'2026-06-01 09:00:00'),
('ORD-C002','C001','CRS002','PURCHASE',8999.00,'REFUNDED','转行',60,'2026-06-20 09:00:00'),
('ORD-C003','C001','CRS003','PURCHASE',9999.00,'REFUNDED','转行',60,'2026-07-20 09:00:00'),
('ORD-D001','D001','CRS001','PURCHASE',3999.00,'PAID','学习',90,'2026-08-10 11:00:00'),
('ORD-E001','E001','CRS001','PURCHASE',8000.00,'PAID','快速学习',30,'2026-08-10 12:00:00'),
('ORD-E002','E001','CRS002','PURCHASE',9000.00,'PAID','快速学习',30,'2026-08-10 12:10:00'),
('ORD-E003','E001','CRS003','PURCHASE',10000.00,'PAID','快速学习',30,'2026-08-10 12:20:00'),
('ORD-E004','E001','CRS002','PURCHASE',9000.00,'PAID','快速学习',30,'2026-08-10 12:30:00'),
('ORD-F001','F001','CRS001','PURCHASE',3999.00,'PAID','学习',90,'2026-08-10 13:00:00');

INSERT IGNORE INTO `learning_progress`
(`progress_id`,`user_id`,`course_id`,`order_id`,`total_minutes`,`completion_rate`,`last_active_at`,`created_at`) VALUES
('PRG-A001','A001','CRS001','ORD-A001',1200,0.4500,'2026-08-10 20:00:00','2026-08-01 10:05:00'),
('PRG-B001','B001','CRS002','ORD-B001',1,0.0010,'2026-08-10 10:02:00','2026-08-10 10:01:00'),
('PRG-D001','D001','CRS001','ORD-D001',10,0.0100,'2026-08-10 11:20:00','2026-08-10 11:01:00');

INSERT IGNORE INTO `refund_request`
(`refund_id`,`order_id`,`user_id`,`reason`,`study_minutes_before_refund`,`refund_amount`,`status`,`created_at`) VALUES
('REF-B001','ORD-B001','B001','购买后立即退费',1,8999.00,'PENDING','2026-08-10 10:03:00'),
('REF-C001','ORD-C001','C001','连环退费-1',20,3999.00,'APPROVED','2026-06-02 09:00:00'),
('REF-C002','ORD-C002','C001','连环退费-2',30,8999.00,'APPROVED','2026-06-21 09:00:00'),
('REF-C003','ORD-C003','C001','连环退费-3',40,9999.00,'PENDING','2026-07-21 09:00:00');

INSERT IGNORE INTO `blacklist_extra`
(`type`,`value`,`reason`,`status`,`expire_at`) VALUES
('student_id','STU-F001','教学演示：历史欺诈学号','ACTIVE',NULL);

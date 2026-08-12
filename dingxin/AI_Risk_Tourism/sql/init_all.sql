-- ============================================
-- 旅游风控系统 - 全量初始化 SQL (Docker entrypoint 用)
-- 由 4 个分片 SQL 拼接: 业务表/业务数据/风控表/风控规则
-- ============================================

-- ============================================
-- 旅游风控系统 - 业务表 DDL 初始化脚本
-- 创建 8 张旅游业务表 (任务书场景 A 必须 7 张 + 退改单 1 张)
-- 独立数据库 tourism, 与电商基线 ecs 完全隔离
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 1. 用户信息表 (实名状态 / VIP / 账号年龄)
-- ============================
CREATE TABLE IF NOT EXISTS `user_info` (
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `real_name_status` int NOT NULL DEFAULT 0 COMMENT '实名状态 0=未实名 1=已实名',
  `vip_level` int NOT NULL DEFAULT 0 COMMENT 'VIP等级 0-4',
  `account_age_days` int NOT NULL DEFAULT 0 COMMENT '账号年龄(天)',
  `register_time` datetime NOT NULL COMMENT '注册时间',
  PRIMARY KEY (`user_id`),
  KEY `idx_real_name_status` (`real_name_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游用户信息表';

-- ============================
-- 2. 订单表 (目的地/出行日期/乘客数)
-- ============================
CREATE TABLE IF NOT EXISTS `order_info` (
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `order_type` enum('机票','酒店','签证','跟团游') NOT NULL COMMENT '订单类型',
  `total_amount` decimal(10,2) NOT NULL COMMENT '订单金额',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `depart_date` datetime NOT NULL COMMENT '出发日期',
  `return_date` datetime NOT NULL COMMENT '返程日期',
  `passenger_count` int NOT NULL DEFAULT 1 COMMENT '乘客数',
  `create_time` datetime NOT NULL COMMENT '下单时间',
  `order_status` enum('已支付','已完成','已取消','已退改') NOT NULL DEFAULT '已支付' COMMENT '订单状态',
  PRIMARY KEY (`order_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_dest_country` (`dest_country`),
  KEY `idx_create_time` (`create_time`),
  CONSTRAINT `order_info_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游订单表';

-- ============================
-- 3. 乘客信息表 (1 订单 N 乘客)
-- ============================
CREATE TABLE IF NOT EXISTS `passenger_info` (
  `passenger_id` varchar(50) NOT NULL COMMENT '乘客ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `name` varchar(50) NOT NULL COMMENT '姓名',
  `id_type` enum('身份证','护照','港澳通行证','台胞证') NOT NULL DEFAULT '身份证' COMMENT '证件类型',
  `id_number` varchar(50) NOT NULL COMMENT '证件号',
  `nationality` varchar(50) NOT NULL COMMENT '国籍',
  `age` int NOT NULL DEFAULT 0 COMMENT '年龄',
  PRIMARY KEY (`passenger_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_id_number` (`id_number`),
  CONSTRAINT `passenger_info_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='乘客信息表';

-- ============================
-- 4. 签证申请表 (拒签历史)
-- ============================
CREATE TABLE IF NOT EXISTS `visa_application` (
  `visa_id` varchar(50) NOT NULL COMMENT '签证申请ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `dest_country` varchar(50) NOT NULL COMMENT '目的地国家',
  `visa_type` enum('旅游签证','商务签证','留学签证','探亲签证') NOT NULL DEFAULT '旅游签证' COMMENT '签证类型',
  `reject_history` int NOT NULL DEFAULT 0 COMMENT '历史拒签次数',
  `submit_time` datetime NOT NULL COMMENT '提交时间',
  PRIMARY KEY (`visa_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_dest_country` (`dest_country`),
  CONSTRAINT `visa_application_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='签证申请表';

-- ============================
-- 5. 酒店预订表
-- ============================
CREATE TABLE IF NOT EXISTS `booking_hotel` (
  `booking_id` varchar(50) NOT NULL COMMENT '酒店预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `hotel_id` varchar(50) NOT NULL COMMENT '酒店ID',
  `check_in` datetime NOT NULL COMMENT '入住时间',
  `check_out` datetime NOT NULL COMMENT '离店时间',
  `room_count` int NOT NULL DEFAULT 1 COMMENT '房间数',
  `is_refundable` int NOT NULL DEFAULT 1 COMMENT '是否可退 1=可退 0=不可退',
  PRIMARY KEY (`booking_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_hotel_id` (`hotel_id`),
  CONSTRAINT `booking_hotel_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='酒店预订表';

-- ============================
-- 6. 机票预订表 (同航班高频 = 黄牛囤票)
-- ============================
CREATE TABLE IF NOT EXISTS `booking_flight` (
  `booking_id` varchar(50) NOT NULL COMMENT '机票预订ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `flight_no` varchar(20) NOT NULL COMMENT '航班号',
  `depart_airport` varchar(50) NOT NULL COMMENT '出发机场',
  `arrive_airport` varchar(50) NOT NULL COMMENT '到达机场',
  `cabin_class` enum('经济舱','商务舱','头等舱') NOT NULL DEFAULT '经济舱' COMMENT '舱位',
  PRIMARY KEY (`booking_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_flight_no` (`flight_no`),
  CONSTRAINT `booking_flight_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机票预订表';

-- ============================
-- 7. 退改申请表 (第 8 张表, "退改申请"事件校验实体)
-- ============================
CREATE TABLE IF NOT EXISTS `order_refund` (
  `refund_id` varchar(50) NOT NULL COMMENT '退改单ID',
  `order_id` varchar(50) NOT NULL COMMENT '订单ID',
  `user_id` varchar(50) NOT NULL COMMENT '用户ID',
  `refund_amount` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT '退改金额',
  `refund_type` enum('退款','改期','换乘客') NOT NULL DEFAULT '退款' COMMENT '退改类型',
  `refund_status` enum('处理中','已完成','已驳回') NOT NULL DEFAULT '处理中' COMMENT '退改状态',
  `apply_time` datetime NOT NULL COMMENT '申请时间',
  PRIMARY KEY (`refund_id`),
  KEY `idx_order_id` (`order_id`),
  KEY `idx_user_id` (`user_id`),
  CONSTRAINT `order_refund_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `order_info` (`order_id`),
  CONSTRAINT `order_refund_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `user_info` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='旅游退改申请表';

-- ============================
-- 8. 业务侧黑名单台账 (决策权威是 risk_blacklist, 本表是业务镜像)
-- ============================
CREATE TABLE IF NOT EXISTS `blacklist_extra` (
  `entry_id` bigint NOT NULL AUTO_INCREMENT COMMENT '条目ID',
  `type` enum('护照号','签证号','设备指纹') NOT NULL COMMENT '黑名单类型',
  `value` varchar(200) NOT NULL COMMENT '黑名单值',
  `reason` varchar(500) DEFAULT NULL COMMENT '加入原因',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间(NULL=永久)',
  `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`entry_id`),
  UNIQUE KEY `idx_blacklist_extra_type_value` (`type`,`value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务侧黑名单台账表';

SET FOREIGN_KEY_CHECKS = 1;


-- ============================================
-- 旅游风控系统 - 业务数据初始化
-- 125 条种子数据 (10 用户 + 20 订单 + 30 乘客 + 20 签证 + 15 酒店 + 15 机票 + 10 退改 + 5 扩展黑名单)
-- 风险画像由 scripts/gen_risky_users.py 注入, 这里只保证基础业务可跑
-- ============================================

SET NAMES utf8mb4;

-- ============================
-- 1. 用户 (10)
-- ============================
INSERT INTO `user_info` (`user_id`, `name`, `real_name_status`, `vip_level`, `account_age_days`, `register_time`) VALUES
('U1001', '张三', 1, 2, 400, DATE_SUB(NOW(), INTERVAL 400 DAY)),
('U1002', '李四', 1, 1, 300, DATE_SUB(NOW(), INTERVAL 300 DAY)),
('U1003', '王五', 0, 0, 200, DATE_SUB(NOW(), INTERVAL 200 DAY)),
('U1004', '赵六', 1, 3, 500, DATE_SUB(NOW(), INTERVAL 500 DAY)),
('U1005', '孙七', 1, 0, 150, DATE_SUB(NOW(), INTERVAL 150 DAY)),
('U1006', '周八', 1, 2, 350, DATE_SUB(NOW(), INTERVAL 350 DAY)),
('U1007', '吴九', 0, 0, 60,  DATE_SUB(NOW(), INTERVAL 60 DAY)),
('U1008', '郑十', 1, 1, 280, DATE_SUB(NOW(), INTERVAL 280 DAY)),
('U1009', '钱十一', 1, 0, 5,   DATE_SUB(NOW(), INTERVAL 5 DAY)),
('U1010', '冯十二', 1, 4, 700, DATE_SUB(NOW(), INTERVAL 700 DAY));

-- ============================
-- 2. 订单 (20)
-- ============================
INSERT INTO `order_info` (`order_id`, `user_id`, `order_type`, `total_amount`, `dest_country`, `depart_date`, `return_date`, `passenger_count`, `create_time`, `order_status`) VALUES
('ORD_T001', 'U1001', '机票', 5200.00, '日本',     DATE_ADD(NOW(), INTERVAL 30 DAY), DATE_ADD(NOW(), INTERVAL 37 DAY), 2, DATE_SUB(NOW(), INTERVAL 20 DAY), '已支付'),
('ORD_T002', 'U1002', '酒店', 3600.00, '泰国',     DATE_ADD(NOW(), INTERVAL 45 DAY), DATE_ADD(NOW(), INTERVAL 50 DAY), 2, DATE_SUB(NOW(), INTERVAL 15 DAY), '已支付'),
('ORD_T003', 'U1003', '签证', 1500.00, '法国',     DATE_ADD(NOW(), INTERVAL 60 DAY), DATE_ADD(NOW(), INTERVAL 67 DAY), 1, DATE_SUB(NOW(), INTERVAL 10 DAY), '已支付'),
('ORD_T004', 'U1004', '跟团游', 28000.00, '新加坡', DATE_ADD(NOW(), INTERVAL 20 DAY), DATE_ADD(NOW(), INTERVAL 26 DAY), 3, DATE_SUB(NOW(), INTERVAL 30 DAY), '已完成'),
('ORD_T005', 'U1005', '机票', 8800.00, '韩国',     DATE_ADD(NOW(), INTERVAL 40 DAY), DATE_ADD(NOW(), INTERVAL 45 DAY), 2, DATE_SUB(NOW(), INTERVAL 25 DAY), '已支付'),
('ORD_T006', 'U1006', '酒店', 4200.00, '马来西亚', DATE_ADD(NOW(), INTERVAL 35 DAY), DATE_ADD(NOW(), INTERVAL 40 DAY), 2, DATE_SUB(NOW(), INTERVAL 18 DAY), '已支付'),
('ORD_T007', 'U1007', '机票', 12000.00, '美国',    DATE_ADD(NOW(), INTERVAL 50 DAY), DATE_ADD(NOW(), INTERVAL 65 DAY), 1, DATE_SUB(NOW(), INTERVAL 3 DAY), '已支付'),
('ORD_T008', 'U1008', '跟团游', 15000.00, '日本',  DATE_ADD(NOW(), INTERVAL 25 DAY), DATE_ADD(NOW(), INTERVAL 30 DAY), 2, DATE_SUB(NOW(), INTERVAL 12 DAY), '已支付'),
('ORD_T009', 'U1009', '机票', 18000.00, '法国',    DATE_ADD(NOW(), INTERVAL 15 DAY), DATE_ADD(NOW(), INTERVAL 22 DAY), 2, DATE_SUB(NOW(), INTERVAL 2 DAY), '已支付'),
('ORD_T010', 'U1010', '跟团游', 60000.00, '冰岛',  DATE_ADD(NOW(), INTERVAL 55 DAY), DATE_ADD(NOW(), INTERVAL 62 DAY), 2, DATE_SUB(NOW(), INTERVAL 8 DAY), '已支付'),
('ORD_T011', 'U1001', '酒店', 2600.00, '日本',     DATE_ADD(NOW(), INTERVAL 31 DAY), DATE_ADD(NOW(), INTERVAL 36 DAY), 2, DATE_SUB(NOW(), INTERVAL 19 DAY), '已支付'),
('ORD_T012', 'U1002', '机票', 4100.00, '泰国',     DATE_ADD(NOW(), INTERVAL 46 DAY), DATE_ADD(NOW(), INTERVAL 49 DAY), 1, DATE_SUB(NOW(), INTERVAL 14 DAY), '已完成'),
('ORD_T013', 'U1003', '酒店', 1800.00, '韩国',     DATE_ADD(NOW(), INTERVAL 33 DAY), DATE_ADD(NOW(), INTERVAL 38 DAY), 1, DATE_SUB(NOW(), INTERVAL 9 DAY), '已支付'),
('ORD_T014', 'U1004', '签证', 1200.00, '日本',     DATE_ADD(NOW(), INTERVAL 41 DAY), DATE_ADD(NOW(), INTERVAL 48 DAY), 1, DATE_SUB(NOW(), INTERVAL 28 DAY), '已完成'),
('ORD_T015', 'U1005', '跟团游', 9900.00, '泰国',   DATE_ADD(NOW(), INTERVAL 22 DAY), DATE_ADD(NOW(), INTERVAL 27 DAY), 2, DATE_SUB(NOW(), INTERVAL 24 DAY), '已退改'),
('ORD_T016', 'U1006', '机票', 6800.00, '新加坡',   DATE_ADD(NOW(), INTERVAL 38 DAY), DATE_ADD(NOW(), INTERVAL 43 DAY), 2, DATE_SUB(NOW(), INTERVAL 17 DAY), '已支付'),
('ORD_T017', 'U1007', '酒店', 3000.00, '日本',     DATE_ADD(NOW(), INTERVAL 26 DAY), DATE_ADD(NOW(), INTERVAL 29 DAY), 1, DATE_SUB(NOW(), INTERVAL 6 DAY), '已支付'),
('ORD_T018', 'U1008', '签证', 1000.00, '泰国',     DATE_ADD(NOW(), INTERVAL 48 DAY), DATE_ADD(NOW(), INTERVAL 55 DAY), 1, DATE_SUB(NOW(), INTERVAL 11 DAY), '已支付'),
('ORD_T019', 'U1009', '酒店', 2200.00, '韩国',     DATE_ADD(NOW(), INTERVAL 44 DAY), DATE_ADD(NOW(), INTERVAL 49 DAY), 2, DATE_SUB(NOW(), INTERVAL 1 DAY), '已支付'),
('ORD_T020', 'U1010', '机票', 35000.00, '瑞士',    DATE_ADD(NOW(), INTERVAL 70 DAY), DATE_ADD(NOW(), INTERVAL 78 DAY), 2, DATE_SUB(NOW(), INTERVAL 5 DAY), '已支付');

-- ============================
-- 3. 乘客 (30, 含 1 个黑护照用于 R030 演示)
-- ============================
INSERT INTO `passenger_info` (`passenger_id`, `order_id`, `name`, `id_type`, `id_number`, `nationality`, `age`) VALUES
('PSG_001', 'ORD_T001', '张三', '身份证', '110101199001011234', '中国', 35),
('PSG_002', 'ORD_T001', '张小明', '护照', 'E12345678', '中国', 28),
('PSG_003', 'ORD_T002', '李四', '身份证', '110101199202022345', '中国', 33),
('PSG_004', 'ORD_T002', '李小红', '护照', 'E23456789', '中国', 30),
('PSG_005', 'ORD_T003', '王五', '护照', 'E34567890', '中国', 40),
('PSG_006', 'ORD_T004', '赵六', '身份证', '110101198803033456', '中国', 38),
('PSG_007', 'ORD_T004', '赵小七', '护照', 'E45678901', '中国', 22),
('PSG_008', 'ORD_T004', '赵小八', '身份证', '110101199505054567', '中国', 31),
('PSG_009', 'ORD_T005', '孙七', '护照', 'E56789012', '中国', 45),
('PSG_010', 'ORD_T005', '孙小九', '身份证', '110101200106066789', '中国', 25),
('PSG_011', 'ORD_T006', '周八', '身份证', '110101199404047890', '中国', 32),
('PSG_012', 'ORD_T006', '周小十', '护照', 'E67890123', '中国', 27),
('PSG_013', 'ORD_T007', '吴九', '护照', 'E78901234', '中国', 29),
('PSG_014', 'ORD_T008', '郑十', '身份证', '110101199606068901', '中国', 30),
('PSG_015', 'ORD_T008', '郑小十一', '护照', 'E89012345', '中国', 24),
('PSG_016', 'ORD_T009', '钱十一', '护照', 'E90123456', '中国', 26),
('PSG_017', 'ORD_T009', '钱小十二', '护照', 'E01234567', '中国', 23),
('PSG_018', 'ORD_T010', '冯十二', '护照', 'E11223344', '中国', 50),
('PSG_019', 'ORD_T010', '冯小十三', '身份证', '110101198807071112', '中国', 37),
('PSG_020', 'ORD_T011', '张三', '身份证', '110101199001011234', '中国', 35),
('PSG_021', 'ORD_T011', '张小明', '护照', 'E12345678', '中国', 28),
('PSG_022', 'ORD_T012', '李四', '身份证', '110101199202022345', '中国', 33),
('PSG_023', 'ORD_T013', '王五', '护照', 'E34567890', '中国', 40),
('PSG_024', 'ORD_T014', '赵六', '身份证', '110101198803033456', '中国', 38),
('PSG_025', 'ORD_T015', '孙七', '护照', 'E56789012', '中国', 45),
('PSG_026', 'ORD_T015', '孙小九', '身份证', '110101200106066789', '中国', 25),
('PSG_027', 'ORD_T016', '周八', '身份证', '110101199404047890', '中国', 32),
('PSG_028', 'ORD_T016', '周小十', '护照', 'E67890123', '中国', 27),
('PSG_029', 'ORD_T017', '吴九', '护照', 'E78901234', '中国', 29),
('PSG_030', 'ORD_T020', '冯十二', '护照', 'E11223344', '中国', 50);

-- ============================
-- 4. 签证申请 (20)
-- ============================
INSERT INTO `visa_application` (`visa_id`, `user_id`, `dest_country`, `visa_type`, `reject_history`, `submit_time`) VALUES
('VISA_001', 'U1001', '日本', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 40 DAY)),
('VISA_002', 'U1001', '法国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 35 DAY)),
('VISA_003', 'U1002', '泰国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 30 DAY)),
('VISA_004', 'U1003', '法国', '旅游签证', 1, DATE_SUB(NOW(), INTERVAL 28 DAY)),
('VISA_005', 'U1003', '美国', '旅游签证', 2, DATE_SUB(NOW(), INTERVAL 20 DAY)),
('VISA_006', 'U1004', '新加坡', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 45 DAY)),
('VISA_007', 'U1005', '韩国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 32 DAY)),
('VISA_008', 'U1006', '马来西亚', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 26 DAY)),
('VISA_009', 'U1007', '美国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 22 DAY)),
('VISA_010', 'U1008', '日本', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 18 DAY)),
('VISA_011', 'U1009', '法国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 8 DAY)),
('VISA_012', 'U1010', '冰岛', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 12 DAY)),
('VISA_013', 'U1002', '日本', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 15 DAY)),
('VISA_014', 'U1004', '日本', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 10 DAY)),
('VISA_015', 'U1005', '泰国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 6 DAY)),
('VISA_016', 'U1006', '新加坡', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 5 DAY)),
('VISA_017', 'U1007', '韩国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 4 DAY)),
('VISA_018', 'U1008', '泰国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 3 DAY)),
('VISA_019', 'U1009', '韩国', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 2 DAY)),
('VISA_020', 'U1010', '瑞士', '旅游签证', 0, DATE_SUB(NOW(), INTERVAL 1 DAY));

-- ============================
-- 5. 酒店预订 (15)
-- ============================
INSERT INTO `booking_hotel` (`booking_id`, `order_id`, `hotel_id`, `check_in`, `check_out`, `room_count`, `is_refundable`) VALUES
('HTL_001', 'ORD_T002', 'H1001', DATE_ADD(NOW(), INTERVAL 45 DAY), DATE_ADD(NOW(), INTERVAL 50 DAY), 1, 1),
('HTL_002', 'ORD_T006', 'H1002', DATE_ADD(NOW(), INTERVAL 35 DAY), DATE_ADD(NOW(), INTERVAL 40 DAY), 1, 1),
('HTL_003', 'ORD_T011', 'H1001', DATE_ADD(NOW(), INTERVAL 31 DAY), DATE_ADD(NOW(), INTERVAL 36 DAY), 1, 1),
('HTL_004', 'ORD_T013', 'H1003', DATE_ADD(NOW(), INTERVAL 33 DAY), DATE_ADD(NOW(), INTERVAL 38 DAY), 1, 0),
('HTL_005', 'ORD_T017', 'H1004', DATE_ADD(NOW(), INTERVAL 26 DAY), DATE_ADD(NOW(), INTERVAL 29 DAY), 1, 1),
('HTL_006', 'ORD_T019', 'H1005', DATE_ADD(NOW(), INTERVAL 44 DAY), DATE_ADD(NOW(), INTERVAL 49 DAY), 1, 1),
('HTL_007', 'ORD_T004', 'H1006', DATE_ADD(NOW(), INTERVAL 20 DAY), DATE_ADD(NOW(), INTERVAL 26 DAY), 2, 1),
('HTL_008', 'ORD_T008', 'H1001', DATE_ADD(NOW(), INTERVAL 25 DAY), DATE_ADD(NOW(), INTERVAL 30 DAY), 1, 1),
('HTL_009', 'ORD_T010', 'H1007', DATE_ADD(NOW(), INTERVAL 55 DAY), DATE_ADD(NOW(), INTERVAL 62 DAY), 1, 1),
('HTL_010', 'ORD_T015', 'H1002', DATE_ADD(NOW(), INTERVAL 22 DAY), DATE_ADD(NOW(), INTERVAL 27 DAY), 1, 1),
('HTL_011', 'ORD_T005', 'H1008', DATE_ADD(NOW(), INTERVAL 40 DAY), DATE_ADD(NOW(), INTERVAL 45 DAY), 1, 1),
('HTL_012', 'ORD_T016', 'H1006', DATE_ADD(NOW(), INTERVAL 38 DAY), DATE_ADD(NOW(), INTERVAL 43 DAY), 1, 0),
('HTL_013', 'ORD_T001', 'H1009', DATE_ADD(NOW(), INTERVAL 30 DAY), DATE_ADD(NOW(), INTERVAL 37 DAY), 1, 1),
('HTL_014', 'ORD_T009', 'H1003', DATE_ADD(NOW(), INTERVAL 15 DAY), DATE_ADD(NOW(), INTERVAL 22 DAY), 1, 1),
('HTL_015', 'ORD_T020', 'H1007', DATE_ADD(NOW(), INTERVAL 70 DAY), DATE_ADD(NOW(), INTERVAL 78 DAY), 1, 1);

-- ============================
-- 6. 机票预订 (15)
-- ============================
INSERT INTO `booking_flight` (`booking_id`, `order_id`, `flight_no`, `depart_airport`, `arrive_airport`, `cabin_class`) VALUES
('FLT_001', 'ORD_T001', 'CA123', 'PEK', 'NRT', '经济舱'),
('FLT_002', 'ORD_T005', 'KE856', 'PVG', 'ICN', '经济舱'),
('FLT_003', 'ORD_T007', 'UA888', 'PEK', 'LAX', '商务舱'),
('FLT_004', 'ORD_T009', 'AF125', 'PVG', 'CDG', '经济舱'),
('FLT_005', 'ORD_T012', 'TG665', 'PVG', 'BKK', '经济舱'),
('FLT_006', 'ORD_T016', 'SQ831', 'SHA', 'SIN', '经济舱'),
('FLT_007', 'ORD_T020', 'LX189', 'PVG', 'ZRH', '商务舱'),
('FLT_008', 'ORD_T001', 'CA124', 'NRT', 'PEK', '经济舱'),
('FLT_009', 'ORD_T005', 'KE857', 'ICN', 'PVG', '经济舱'),
('FLT_010', 'ORD_T010', 'FI787', 'PVG', 'KEF', '经济舱'),
('FLT_011', 'ORD_T008', 'CA928', 'PEK', 'NRT', '经济舱'),
('FLT_012', 'ORD_T015', 'TG666', 'BKK', 'PVG', '经济舱'),
('FLT_013', 'ORD_T004', 'SQ802', 'PVG', 'SIN', '经济舱'),
('FLT_014', 'ORD_T018', 'CZ357', 'CAN', 'BKK', '经济舱'),
('FLT_015', 'ORD_T002', 'MU541', 'PVG', 'BKK', '经济舱');

-- ============================
-- 7. 退改申请 (10)
-- ============================
INSERT INTO `order_refund` (`refund_id`, `order_id`, `user_id`, `refund_amount`, `refund_type`, `refund_status`, `apply_time`) VALUES
('RFD_001', 'ORD_T015', 'U1005', 2000.00, '改期', '处理中', DATE_SUB(NOW(), INTERVAL 5 DAY)),
('RFD_002', 'ORD_T001', 'U1001', 0.00,   '换乘客', '已完成', DATE_SUB(NOW(), INTERVAL 12 DAY)),
('RFD_003', 'ORD_T005', 'U1005', 1500.00, '退款', '已完成', DATE_SUB(NOW(), INTERVAL 10 DAY)),
('RFD_004', 'ORD_T012', 'U1002', 800.00,  '退款', '已完成', DATE_SUB(NOW(), INTERVAL 9 DAY)),
('RFD_005', 'ORD_T014', 'U1004', 500.00,  '退款', '已驳回', DATE_SUB(NOW(), INTERVAL 8 DAY)),
('RFD_006', 'ORD_T016', 'U1006', 1200.00, '改期', '处理中', DATE_SUB(NOW(), INTERVAL 4 DAY)),
('RFD_007', 'ORD_T020', 'U1010', 5000.00, '退款', '处理中', DATE_SUB(NOW(), INTERVAL 3 DAY)),
('RFD_008', 'ORD_T008', 'U1008', 0.00,    '换乘客', '已完成', DATE_SUB(NOW(), INTERVAL 7 DAY)),
('RFD_009', 'ORD_T003', 'U1003', 300.00,  '退款', '已完成', DATE_SUB(NOW(), INTERVAL 6 DAY)),
('RFD_010', 'ORD_T010', 'U1010', 8000.00, '退款', '处理中', DATE_SUB(NOW(), INTERVAL 2 DAY));

-- ============================
-- 8. 业务侧黑名单台账 (5, 决策权威在 risk_blacklist, 见 init_risk_data.sql)
-- ============================
INSERT INTO `blacklist_extra` (`type`, `value`, `reason`, `expire_at`) VALUES
('护照号', 'E11223344', '涉骗护照(种子演示数据)', NULL),
('护照号', 'E99999999', '涉黑护照', NULL),
('签证号', 'VISA_BLACK_001', '签证造假', NULL),
('设备指纹', 'DEVICE_BLACK_001', '黄牛设备', NULL),
('设备指纹', 'DEVICE_BLACK_002', '批量注册设备', NULL);


-- ============================================
-- 旅游风控系统 - 风控表 DDL 初始化脚本
-- 在 ecs 数据库中创建 7 张新增风控表
-- ============================================

USE tourism;

-- 1. 风控规则配置表
CREATE TABLE IF NOT EXISTS `risk_rule` (
    `rule_id` VARCHAR(50) NOT NULL COMMENT '规则ID',
    `rule_name` VARCHAR(100) NOT NULL COMMENT '规则名称',
    `rule_category` ENUM('订单欺诈','支付风险','账户风险','售后滥用','地址风险','物流风险',
                         '预订欺诈','退改滥用','签证风险','设备风险','黑名单风险') NOT NULL COMMENT '风险场景分类',
    `event_type` ENUM('下单','支付','售后申请','物流投诉','通用',
                      '预订下单','退改申请','签证申请') NOT NULL DEFAULT '通用' COMMENT '适用事件类型',
    `rule_condition` JSON NOT NULL COMMENT '条件表达式',
    `risk_level` ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级',
    `risk_score` INT NOT NULL COMMENT '命中分值(0-100)',
    `action` ENUM('通过','标记','人工审核','拒绝') NOT NULL COMMENT '触发动作',
    `is_enabled` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `priority` INT DEFAULT 0 COMMENT '优先级(越高越先执行)',
    `description` TEXT COMMENT '规则描述',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 【P3-M9 2026-08-07】软删: NULL=未删, 有值=删除时间
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`rule_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控规则配置表';

-- 2. 风控事件审计表
CREATE TABLE IF NOT EXISTS `risk_event` (
    `event_id` VARCHAR(50) NOT NULL COMMENT '事件ID',
    `event_type` ENUM('下单','支付','售后申请','物流投诉','预订下单','退改申请','签证申请') NOT NULL COMMENT '事件类型',
    `event_source_id` VARCHAR(50) NOT NULL COMMENT '关联业务ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `event_data` JSON COMMENT '事件快照',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`event_id`),
    INDEX `idx_risk_event_user_id` (`user_id`),
    INDEX `idx_risk_event_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控事件审计表';

-- 3. 风控特征快照表
CREATE TABLE IF NOT EXISTS `risk_feature` (
    `feature_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '特征ID',
    `event_id` VARCHAR(50) NOT NULL COMMENT '关联事件ID',
    `entity_type` ENUM('用户','订单','地址') NOT NULL COMMENT '实体类型',
    `entity_id` VARCHAR(50) NOT NULL COMMENT '实体ID',
    `feature_name` VARCHAR(100) NOT NULL COMMENT '特征名称',
    `feature_value` DECIMAL(15,4) COMMENT '特征值',
    `compute_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '计算时间',
    PRIMARY KEY (`feature_id`),
    INDEX `idx_risk_feature_event_id` (`event_id`),
    INDEX `idx_risk_feature_entity` (`entity_type`, `entity_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控特征快照表';

-- 4. 风控评估结果表
CREATE TABLE IF NOT EXISTS `risk_assessment` (
    `assessment_id` VARCHAR(50) NOT NULL COMMENT '评估ID',
    `event_id` VARCHAR(50) NOT NULL COMMENT '关联事件ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `rule_results` JSON COMMENT '规则结果',
    `rule_count` INT DEFAULT 0 COMMENT '命中规则数',
    `final_score` INT NOT NULL COMMENT '最终评分(0-100)',
    `risk_level` ENUM('低','中','高','极高') NOT NULL COMMENT '风险等级',
    `decision` ENUM('通过','标记','人工审核','拒绝') NOT NULL COMMENT '决策',
    -- 【V2 2026-08-07】XGBoost 双轨融合字段: ml_score ∈ [0,1] = P(拒绝), ml_decision = ML 单维度决策
    `ml_score` DECIMAL(5,4) DEFAULT NULL COMMENT 'XGBoost 拒绝概率 [0,1](NULL=未加载)',
    `ml_decision` VARCHAR(10) DEFAULT NULL COMMENT 'ML 维度决策(通过/标记/人工审核/拒绝)',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`assessment_id`),
    INDEX `idx_risk_assessment_user_id` (`user_id`),
    INDEX `idx_risk_assessment_decision` (`decision`),
    INDEX `idx_risk_assessment_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控评估结果表';

-- 5. 风控案件表
CREATE TABLE IF NOT EXISTS `risk_case` (
    `case_id` VARCHAR(50) NOT NULL COMMENT '案件ID',
    `assessment_id` VARCHAR(50) NOT NULL COMMENT '关联评估ID',
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `case_status` ENUM('待审核','审核中','已通过','已拒绝','已关闭') NOT NULL DEFAULT '待审核' COMMENT '案件状态',
    `case_category` VARCHAR(50) DEFAULT NULL COMMENT '案件分类',
    `risk_detail` JSON COMMENT '风险详情',
    -- 【2026-08-07 补】业务回溯字段: decision.py 写入, "重做检查" 按钮回查用
    -- 之前漏在 DDL 里, 导致 ORM 查 risk_case.source_id 时报 1054 (修复: 合并自原 migration_add_case_source_id.sql)
    `source_id` VARCHAR(50) DEFAULT NULL COMMENT '原始业务ID(订单/售后/投诉ID), 重做检查时用',
    `event_type` ENUM('下单','支付','售后申请','物流投诉','预订下单','退改申请','签证申请') DEFAULT NULL COMMENT '触发案件的事件类型',
    `reviewer` VARCHAR(50) DEFAULT NULL COMMENT '审核人',
    `review_comment` TEXT COMMENT '审核意见',
    `review_time` DATETIME DEFAULT NULL COMMENT '审核时间',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`case_id`),
    INDEX `idx_risk_case_status` (`case_status`),
    INDEX `idx_risk_case_user_id` (`user_id`),
    INDEX `idx_risk_case_source_id` (`source_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控案件表';

-- 6. 风控黑名单表
CREATE TABLE IF NOT EXISTS `risk_blacklist` (
    `blacklist_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '黑名单ID',
    `blacklist_type` ENUM('用户','地址','手机号','护照号','签证号','设备指纹') NOT NULL COMMENT '黑名单类型',
    `blacklist_value` VARCHAR(200) NOT NULL COMMENT '黑名单值',
    `reason` TEXT COMMENT '加入原因',
    `expire_time` DATETIME DEFAULT NULL COMMENT '过期时间(NULL=永久)',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    -- 【P3-M9 2026-08-07】软删: NULL=未删, 有值=删除时间 (撞黑检查/列表查都加 WHERE deleted_at IS NULL)
    `deleted_at` DATETIME DEFAULT NULL COMMENT '软删除时间(NULL=未删)',
    PRIMARY KEY (`blacklist_id`),
    UNIQUE INDEX `idx_blacklist_type_value` (`blacklist_type`, `blacklist_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控黑名单表';

-- 7. 用户风险画像表
CREATE TABLE IF NOT EXISTS `risk_user_profile` (
    `user_id` VARCHAR(50) NOT NULL COMMENT '用户ID',
    `risk_score` INT DEFAULT 0 COMMENT '综合风险评分(0-100)',
    `risk_level` ENUM('低','中','高','极高') DEFAULT '低' COMMENT '风险等级',
    `total_orders` INT DEFAULT 0 COMMENT '总订单数',
    `total_refunds` INT DEFAULT 0 COMMENT '退款次数',
    `refund_rate` DECIMAL(5,4) DEFAULT 0 COMMENT '退款率',
    `avg_order_amount` DECIMAL(10,2) DEFAULT 0 COMMENT '平均订单金额',
    `address_count` INT DEFAULT 0 COMMENT '地址数量(旅游版映射: 历史去重乘客数)',
    `complaint_count` INT DEFAULT 0 COMMENT '投诉次数',
    `assessment_count` INT DEFAULT 0 COMMENT '评估次数',
    `last_assessment_time` DATETIME DEFAULT NULL COMMENT '最近评估时间',
    `profile_data` JSON COMMENT '扩展画像数据',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户风险画像表';


-- ============================================
-- 系统管理表 (P4-L1 / P4-L2 新增 2026-08-07)
-- 教学项目只加"系统管理"类表, 不动数据/特征
-- ============================================

-- 8. 操作审计日志表 (P4-L1)
-- 任何规则/案件/黑名单的变更都写一行, 出事能追责
-- 教学价值: 学员能讲"我设计的系统有完整审计日志" (合规 + 银保监要求)
CREATE TABLE IF NOT EXISTS `risk_action_log` (
    `log_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `operator` VARCHAR(50) NOT NULL COMMENT '操作人(admin/system/ai_agent)',
    `action_type` ENUM('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST') NOT NULL COMMENT '操作类型',
    `target_type` ENUM('rule','case','blacklist') NOT NULL COMMENT '对象类型',
    `target_id` VARCHAR(50) NOT NULL COMMENT '对象ID',
    `before_value` JSON COMMENT '变更前 (NULL=新增)',
    `after_value` JSON COMMENT '变更后 (NULL=删除)',
    `ip` VARCHAR(50) COMMENT '操作IP',
    `remark` VARCHAR(500) COMMENT '备注',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (`log_id`),
    INDEX `idx_action_log_operator` (`operator`),
    INDEX `idx_action_log_target` (`target_type`, `target_id`),
    INDEX `idx_action_log_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控操作审计日志表';

-- 9. 告警记录表 (P4-L2)
-- 风控系统自己发现异常的记录 (规则命中率突降/案件积压/撞黑失败率过高等)
-- 教学价值: 让学员理解"风控不是写完规则就完事, 要监控"
CREATE TABLE IF NOT EXISTS `risk_alert` (
    `alert_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '告警ID',
    `alert_type` ENUM('BUSINESS','MODEL','SYSTEM','SECURITY') NOT NULL COMMENT '告警分类',
    `alert_level` ENUM('P0','P1','P2','P3') NOT NULL COMMENT '告警等级 (P0=致命, P3=提示)',
    `alert_title` VARCHAR(200) NOT NULL COMMENT '告警标题',
    `alert_content` TEXT COMMENT '告警详情',
    `metric_name` VARCHAR(100) COMMENT '指标名(规则命中率/案件积压数等)',
    `metric_value` DECIMAL(20,6) COMMENT '触发值',
    `threshold` DECIMAL(20,6) COMMENT '阈值',
    `status` ENUM('PENDING','HANDLING','RESOLVED','IGNORED') DEFAULT 'PENDING' COMMENT '处理状态',
    `handler` VARCHAR(50) COMMENT '处理人',
    `resolve_time` DATETIME DEFAULT NULL COMMENT '解决时间',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '告警时间',
    PRIMARY KEY (`alert_id`),
    INDEX `idx_alert_status` (`status`),
    INDEX `idx_alert_level` (`alert_level`),
    INDEX `idx_alert_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风控告警记录表';


-- ============================================
-- 旅游风控系统 - 预置规则数据初始化
-- 12 条规则覆盖 6 大旅游风险场景 (R001-R034 旅游版)
-- 场景分布:
--   R001/R002       签证风险 (拒签拦截 / 短期多国)
--   R005/R025/R032  预订欺诈 (大额跨境 / 新用户大单 / 单人大量乘客)
--   R008/R033/R034  设备风险 (黄牛囤票 / 临行改签 / 酒店倒卖)
--   R012            预订欺诈 (0 点突击下单)
--   R018            账户风险 (乘客信息不一致)
--   R030            黑名单风险 (黑护照拦截)
--   R031            退改滥用 (高频退改)
-- ============================================

USE tourism;

SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联审计日志)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 签证风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '拒签历史拦截', '签证风险', '签证申请',
 '{"field": "user_visa_reject_90d", "op": ">=", "value": 2}',
 '极高', 95, '拒绝', 1, 100,
 '90天内签证被拒≥2次, 疑似恶意申请, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '短期多国签证', '签证风险', '签证申请',
 '{"field": "user_visa_countries_30d", "op": ">=", "value": 3}',
 '高', 75, '人工审核', 1, 90,
 '30天内申请≥3个不同国家签证, 疑似签证黄牛');

-- ============================
-- 预订欺诈
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '大额跨境游', '预订欺诈', '预订下单',
 '{"field": "order_total_amount", "op": ">=", "value": 50000}',
 '高', 80, '人工审核', 1, 85,
 '单笔订单≥5万元, 大额跨境游需人工审核');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '0点突击下单', '预订欺诈', '预订下单',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_trip_days", "op": "<", "value": 7}]}',
 '中', 40, '标记', 1, 50,
 '凌晨1-5点下单且行程<7天, 突击下单标记关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '新用户大单', '预订欺诈', '预订下单',
 '{"and": [{"field": "user_account_age_days", "op": "<", "value": 7}, {"field": "order_total_amount", "op": ">=", "value": 10000}]}',
 '中', 50, '标记', 1, 60,
 '注册<7天且订单≥1万元, 新用户大额订单');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R032', '单人大量乘客', '预订欺诈', '预订下单',
 '{"and": [{"field": "order_passenger_count", "op": ">=", "value": 5}, {"field": "trip_distinct_passenger_count", "op": ">=", "value": 5}]}',
 '中', 45, '标记', 1, 55,
 '单人账号大量乘客, 疑似代订/凑单');

-- ============================
-- 设备风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '黄牛囤票', '设备风险', '预订下单',
 '{"field": "trip_same_flight_1h", "op": ">=", "value": 5}',
 '极高', 92, '拒绝', 1, 98,
 '同一账号1小时内预订≥5张同航班, 疑似黄牛囤票, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R033', '临行改签', '设备风险', '退改申请',
 '{"and": [{"field": "order_is_urgent", "op": "==", "value": 1}, {"field": "order_is_flight", "op": "==", "value": 1}]}',
 '中', 45, '标记', 1, 55,
 '临近出行改签机票, 疑似票贩子倒票');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R034', '酒店倒卖', '设备风险', '预订下单',
 '{"field": "trip_same_hotel_1h", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 80,
 '同一账号1小时内预订≥3间同酒店, 疑似酒店倒卖');

-- ============================
-- 账户风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '乘客信息不一致', '账户风险', '预订下单',
 '{"field": "trip_passenger_match_rate", "op": "<", "value": 0.3}',
 '中', 45, '标记', 1, 55,
 '订单乘客证件与历史乘客匹配率<30%, 疑似身份冒用');

-- ============================
-- 退改滥用
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R031', '高频退改滥用', '退改滥用', '退改申请',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.5}, {"field": "user_total_orders", "op": ">=", "value": 5}]}',
 '高', 70, '人工审核', 1, 80,
 '退改率≥50%且订单≥5, 疑似恶意退改');

-- ============================
-- 黑名单风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑护照拦截', '黑名单风险', '预订下单',
 '{"field": "trip_blacklist_passport_count", "op": ">=", "value": 1}',
 '极高', 95, '拒绝', 1, 100,
 '订单乘客证件命中黑名单, 一票否决');

-- ============================================
-- 风控黑名单权威数据 (与 blacklist_extra 台账镜像, 决策只读本表)
-- 注意: 必须等 risk_blacklist 建表后才能插入, 所以放在规则后面
-- ============================================
INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason) VALUES
('护照号', 'E11223344', '涉骗护照(种子演示数据)'),
('护照号', 'E99999999', '涉黑护照'),
('签证号', 'VISA_BLACK_001', '签证造假'),
('设备指纹', 'DEVICE_BLACK_001', '黄牛设备'),
('设备指纹', 'DEVICE_BLACK_002', '批量注册设备');


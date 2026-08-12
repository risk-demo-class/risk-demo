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

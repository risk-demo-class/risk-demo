-- 制造业设备经销商风控系统 - 第一版业务测试数据
-- 覆盖正常、新注册、长期合作、大额采购、高额保修和跨区域举报场景。
-- 当前连接由 scripts/init_db.py 选择；本文件不得硬编码 USE 数据库。

SET NAMES utf8mb4;

INSERT IGNORE INTO `dealer`
(`dealer_id`, `name`, `level`, `region`, `authorized_at`, `contract_end`) VALUES
('DLR001', '华东精工设备有限公司', '核心', '华东', '2021-03-15', '2028-03-14'),
('DLR002', '新锐工业设备商行', '普通', '华北', '2026-08-01', '2027-07-31'),
('DLR003', '恒信装备集团有限公司', '战略', '华南', '2014-06-01', '2029-05-31'),
('DLR004', '西部机电经销有限公司', '普通', '西南', '2023-09-10', '2027-09-09');

INSERT IGNORE INTO `device`
(`device_id`, `sn`, `model`, `batch_no`, `factory_at`, `warranty_end`, `dealer_id`) VALUES
('DEV001', 'SN-CNC-A10001', 'CNC-A100', 'BATCH-2025-11', '2025-11-20', '2028-11-19', 'DLR001'),
('DEV002', 'SN-PUMP-P20001', 'PUMP-P200', 'BATCH-2017-03', '2017-03-12', '2020-03-11', 'DLR003'),
('DEV003', 'SN-ROBOT-R50001', 'ROBOT-R500', 'BATCH-2026-06', '2026-06-18', '2029-06-17', 'DLR002'),
('DEV004', 'SN-COMP-C30001', 'COMP-C300', 'BATCH-2024-08', '2024-08-08', '2027-08-07', 'DLR004'),
('DEV005', 'SN-LASER-L80001', 'LASER-L800', 'BATCH-2019-05', '2019-05-16', '2022-05-15', 'DLR003'),
('DEV006', 'SN-CNC-A10002', 'CNC-A100', 'BATCH-2026-07', '2026-07-10', '2029-07-09', NULL);

INSERT IGNORE INTO `purchase_order`
(`po_id`, `dealer_id`, `total_amount`, `items`, `ship_to`, `payment_term`, `create_time`) VALUES
('PO001', 'DLR001', 268000.00,
 JSON_ARRAY(JSON_OBJECT('device_id', 'DEV001', 'model', 'CNC-A100', 'quantity', 1, 'unit_price', 268000.00)),
 '华东-上海中心仓', '账期30天', '2026-07-12 09:30:00'),
('PO002', 'DLR002', 2860000.00,
 JSON_ARRAY(JSON_OBJECT('device_id', 'DEV003', 'model', 'ROBOT-R500', 'quantity', 4, 'unit_price', 715000.00)),
 '华北-北京临时交付点', '账期60天', '2026-08-05 01:18:00'),
('PO003', 'DLR003', 180000.00,
 JSON_ARRAY(JSON_OBJECT('device_id', 'DEV002', 'model', 'PUMP-P200', 'quantity', 3, 'unit_price', 60000.00)),
 '华南-广州战略经销仓', '预付', '2026-06-20 14:10:00'),
('PO004', 'DLR004', 420000.00,
 JSON_ARRAY(JSON_OBJECT('device_id', 'DEV004', 'model', 'COMP-C300', 'quantity', 2, 'unit_price', 210000.00)),
 '西南-成都授权仓', '账期30天', '2026-07-28 11:45:00');

INSERT IGNORE INTO `warranty_claim`
(`claim_id`, `device_id`, `dealer_id`, `fault_desc`, `claim_amount`, `photos`, `create_time`) VALUES
('CLM001', 'DEV001', 'DLR001', '主轴温度传感器间歇性报警，设备仍可运行', 6800.00,
 JSON_ARRAY('claim/CLM001/panel.jpg', 'claim/CLM001/sensor.jpg'), '2026-07-25 10:20:00'),
('CLM002', 'DEV005', 'DLR003', '激光发生器及控制单元同时损坏，申请整机核心模块更换', 386000.00,
 JSON_ARRAY('claim/CLM002/nameplate.jpg'), '2026-08-06 16:40:00'),
('CLM003', 'DEV003', 'DLR002', '机械臂末端定位偏差，申请现场校准服务', 12500.00,
 JSON_ARRAY('claim/CLM003/video-frame.jpg'), '2026-08-08 13:05:00');

INSERT IGNORE INTO `cross_region_report`
(`report_id`, `device_id`, `expected_region`, `actual_region`, `reporter_id`, `create_time`) VALUES
('CRR001', 'DEV001', '华东', '华东', 'INSPECTOR001', '2026-07-30 15:00:00'),
('CRR002', 'DEV004', '西南', '华北', 'DEALER-HOTLINE', '2026-08-07 18:25:00'),
('CRR003', 'DEV003', '华北', '华东', 'INSPECTOR002', '2026-08-09 09:12:00');

INSERT IGNORE INTO `blacklist_extra`
(`entry_id`, `type`, `value`, `reason`, `expire_at`) VALUES
(1, '统一社会信用代码', '91310000BLACK000001', '历史合同欺诈关联企业，永久关注', NULL),
(2, '银行账户', '6222000000000099999', '多家异常经销商共用收款账户', '2027-12-31 23:59:59'),
(3, '联系人手机号', '13900009999', '疑似批量注册经销商联系人', '2026-12-31 23:59:59');

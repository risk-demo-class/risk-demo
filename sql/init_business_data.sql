-- ============================================================
-- 医疗风控系统 - 业务表基础数据初始化 (场景 F)
-- 4 家医院 / 8 名医生 / 5 名普通参保人 + 少量挂号/处方/结算/药品订单演示数据
-- 高风险用户与批量数据由 scripts/gen_risky_users.py / gen_risk_data.py 生成
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 医院 (4 家, 跨省便于演示异地结算)
-- ============================
INSERT INTO `hospital` (`hospital_id`, `name`, `level`, `province`, `city`, `is_insured`) VALUES
('H001', '北京协和医院', '三甲', '北京', '北京', 1),
('H002', '北京朝阳医院', '二甲', '北京', '北京', 1),
('H003', '上海瑞金医院', '三甲', '上海', '上海', 1),
('H004', '广州中山医院', '三甲', '广东', '广州', 1);

-- ============================
-- 医生 (8 名)
-- ============================
INSERT INTO `doctor` (`doctor_id`, `name`, `hospital_id`, `department`, `title`, `license_no`) VALUES
('D001', '王建国', 'H001', '心血管内科', '主任医师', 'LIC-110001'),
('D002', '李秀兰', 'H001', '内分泌科', '副主任医师', 'LIC-110002'),
('D003', '张伟',   'H002', '呼吸内科', '主治医师', 'LIC-110003'),
('D004', '刘洋',   'H002', '消化内科', '主治医师', 'LIC-110004'),
('D005', '陈静',   'H003', '心血管内科', '主任医师', 'LIC-310001'),
('D006', '赵敏',   'H003', '神经内科', '副主任医师', 'LIC-310002'),
('D007', '孙磊',   'H004', '内分泌科', '主治医师', 'LIC-440001'),
('D008', '周芳',   'H004', '呼吸内科', '主任医师', 'LIC-440002');

-- ============================
-- 参保人 (5 名普通用户)
-- ============================
INSERT INTO `user_info` (`user_id`, `name`, `id_card_hash`, `medical_card_no`, `phone_no`, `insurance_type`, `insure_province`, `insure_city`, `register_at`) VALUES
('1001', '赵大勇', 'HASH-110101-0001', 'MC-1001', '13800000001', '城镇职工', '北京', '北京', DATE_SUB(NOW(), INTERVAL 400 DAY)),
('1002', '钱小红', 'HASH-110101-0002', 'MC-1002', '13800000002', '城乡居民', '北京', '北京', DATE_SUB(NOW(), INTERVAL 300 DAY)),
('1003', '孙美丽', 'HASH-310101-0003', 'MC-1003', '13800000003', '城镇职工', '上海', '上海', DATE_SUB(NOW(), INTERVAL 350 DAY)),
('1004', '李健康', 'HASH-310101-0004', 'MC-1004', '13800000004', '城镇职工', '上海', '上海', DATE_SUB(NOW(), INTERVAL 200 DAY)),
('1005', '周平安', 'HASH-440101-0005', 'MC-1005', '13800000005', '城乡居民', '广东', '广州', DATE_SUB(NOW(), INTERVAL 150 DAY));

-- ============================
-- 挂号 (演示数据)
-- ============================
INSERT INTO `appointment` (`appt_id`, `user_id`, `hospital_id`, `department`, `doctor_id`, `appt_time`, `pay_amount`, `appt_status`, `cancel_time`) VALUES
('APT-1001-01', '1001', 'H001', '心血管内科', 'D001', DATE_SUB(NOW(), INTERVAL 20 DAY), 50, '已就诊', NULL),
('APT-1001-02', '1001', 'H001', '内分泌科', 'D002', DATE_SUB(NOW(), INTERVAL 10 DAY), 50, '已就诊', NULL),
('APT-1002-01', '1002', 'H002', '呼吸内科', 'D003', DATE_SUB(NOW(), INTERVAL 8 DAY), 20, '已就诊', NULL),
('APT-1003-01', '1003', 'H003', '心血管内科', 'D005', DATE_SUB(NOW(), INTERVAL 5 DAY), 60, '已就诊', NULL),
('APT-1005-01', '1005', 'H004', '呼吸内科', 'D008', DATE_SUB(NOW(), INTERVAL 3 DAY), 40, '已就诊', NULL);

-- ============================
-- 处方 (演示数据)
-- ============================
INSERT INTO `prescription` (`rx_id`, `doctor_id`, `user_id`, `hospital_id`, `diagnosis_code`, `diagnosis_name`, `items`, `total_amount`, `is_insured`, `create_time`) VALUES
('RX-1001-01', 'D001', '1001', 'H001', 'I10', '原发性高血压', '[{"drug":"氨氯地平","qty":14}]', 120, 1, DATE_SUB(NOW(), INTERVAL 20 DAY)),
('RX-1001-02', 'D002', '1001', 'H001', 'E11', '2型糖尿病', '[{"drug":"二甲双胍","qty":28}]', 180, 1, DATE_SUB(NOW(), INTERVAL 10 DAY)),
('RX-1002-01', 'D003', '1002', 'H002', 'J45', '支气管哮喘', '[{"drug":"沙丁胺醇","qty":7}]', 90, 1, DATE_SUB(NOW(), INTERVAL 8 DAY)),
('RX-1003-01', 'D005', '1003', 'H003', 'I20', '心绞痛', '[{"drug":"硝酸甘油","qty":14}]', 150, 1, DATE_SUB(NOW(), INTERVAL 5 DAY)),
('RX-1005-01', 'D008', '1005', 'H004', 'J18', '肺炎', '[{"drug":"阿莫西林","qty":14}]', 110, 1, DATE_SUB(NOW(), INTERVAL 3 DAY));

-- ============================
-- 医保结算 (演示数据)
-- ============================
INSERT INTO `insurance_claim` (`claim_id`, `user_id`, `hospital_id`, `total_amount`, `insured_amount`, `self_amount`, `claim_status`, `submit_at`) VALUES
('CLM-1001-01', '1001', 'H001', 500, 400, 100, '已结算', DATE_SUB(NOW(), INTERVAL 20 DAY)),
('CLM-1001-02', '1001', 'H001', 600, 480, 120, '已结算', DATE_SUB(NOW(), INTERVAL 10 DAY)),
('CLM-1002-01', '1002', 'H002', 300, 240, 60,  '已结算', DATE_SUB(NOW(), INTERVAL 8 DAY)),
('CLM-1003-01', '1003', 'H003', 700, 560, 140, '已结算', DATE_SUB(NOW(), INTERVAL 5 DAY)),
('CLM-1005-01', '1005', 'H004', 400, 320, 80,  '已结算', DATE_SUB(NOW(), INTERVAL 3 DAY));

-- ============================
-- 药品订单 (演示数据, 收件人=患者本人)
-- ============================
INSERT INTO `drug_order` (`drug_order_id`, `rx_id`, `user_id`, `drug_name`, `quantity`, `drug_category`, `is_otc`, `receiver_name`, `total_amount`, `create_time`) VALUES
('DG-1001-01', 'RX-1001-01', '1001', '氨氯地平', 14, '处方药', 0, '赵大勇', 120, DATE_SUB(NOW(), INTERVAL 20 DAY)),
('DG-1001-02', 'RX-1001-02', '1001', '二甲双胍', 28, '处方药', 0, '赵大勇', 180, DATE_SUB(NOW(), INTERVAL 10 DAY)),
('DG-1002-01', 'RX-1002-01', '1002', '沙丁胺醇', 7,  '处方药', 0, '钱小红', 90,  DATE_SUB(NOW(), INTERVAL 8 DAY)),
('DG-1003-01', 'RX-1003-01', '1003', '硝酸甘油', 14, '处方药', 0, '孙美丽', 150, DATE_SUB(NOW(), INTERVAL 5 DAY)),
('DG-1005-01', 'RX-1005-01', '1005', '阿莫西林', 14, '处方药', 0, '周平安', 110, DATE_SUB(NOW(), INTERVAL 3 DAY));

-- ============================
-- 扩展黑名单 (业务侧演示)
-- ============================
INSERT INTO `blacklist_extra` (`type`, `value`, `reason`, `expire_at`, `create_time`) VALUES
('医保卡', 'MC-BLACK-001', '黑医保卡演示 (R008)', NULL, NOW());

SET FOREIGN_KEY_CHECKS = 1;
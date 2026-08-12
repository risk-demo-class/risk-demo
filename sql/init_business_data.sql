-- 最小化模拟数据：1 个正常报名、5 个共用设备报名、1 个黑名单报名。
INSERT OR IGNORE INTO course (course_id, name, category, price, teacher_id, total_hours)
VALUES ('CRS-PY-001', 'Python 数据分析实战', '职业技能', 1999, 'TCH-001', 36);

INSERT OR IGNORE INTO student (user_id, name_masked, student_id_hash)
VALUES
    ('STU-NORMAL-001', '李*', 'hash-STU-NORMAL-001'),
    ('STU-RISK-01', '张*', 'hash-STU-RISK-01'),
    ('STU-RISK-02', '张*', 'hash-STU-RISK-02'),
    ('STU-RISK-03', '张*', 'hash-STU-RISK-03'),
    ('STU-RISK-04', '张*', 'hash-STU-RISK-04'),
    ('STU-RISK-05', '张*', 'hash-STU-RISK-05'),
    ('STU-BLACK-001', '王*', 'hash-STU-BLACK-001');

INSERT OR IGNORE INTO enrollment (enrollment_id, user_id, course_id, paid_amount, discount_amount, status)
VALUES
    ('ENR-NORMAL-001', 'STU-NORMAL-001', 'CRS-PY-001', 1999, 0, '已报名'),
    ('ENR-RISK-001', 'STU-RISK-01', 'CRS-PY-001', 1999, 0, '已报名'),
    ('ENR-RISK-002', 'STU-RISK-02', 'CRS-PY-001', 1999, 0, '已报名'),
    ('ENR-RISK-003', 'STU-RISK-03', 'CRS-PY-001', 1999, 0, '已报名'),
    ('ENR-RISK-004', 'STU-RISK-04', 'CRS-PY-001', 1999, 0, '已报名'),
    ('ENR-RISK-005', 'STU-RISK-05', 'CRS-PY-001', 1999, 0, '已报名'),
    ('ENR-BLACK-001', 'STU-BLACK-001', 'CRS-PY-001', 1999, 0, '已报名');

INSERT OR IGNORE INTO device_binding (binding_id, user_id, device_fingerprint_hash, first_seen_at, last_seen_at)
VALUES
    ('DEV-NORMAL-001', 'STU-NORMAL-001', 'device-normal-hash', datetime('now'), datetime('now')),
    ('DEV-RISK-01', 'STU-RISK-01', 'device-shared-hash', datetime('now'), datetime('now')),
    ('DEV-RISK-02', 'STU-RISK-02', 'device-shared-hash', datetime('now'), datetime('now')),
    ('DEV-RISK-03', 'STU-RISK-03', 'device-shared-hash', datetime('now'), datetime('now')),
    ('DEV-RISK-04', 'STU-RISK-04', 'device-shared-hash', datetime('now'), datetime('now')),
    ('DEV-RISK-05', 'STU-RISK-05', 'device-shared-hash', datetime('now'), datetime('now')),
    ('DEV-BLACK-001', 'STU-BLACK-001', 'device-black-hash', datetime('now'), datetime('now'));

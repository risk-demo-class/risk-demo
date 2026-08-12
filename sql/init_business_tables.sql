-- 教育业务表（SQLite）：学生、课程、报名、学习、退费、学历认证、设备绑定。
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS student (
    user_id TEXT PRIMARY KEY,
    name_masked TEXT,
    role TEXT NOT NULL DEFAULT '学生',
    student_id_hash TEXT UNIQUE,
    real_name_status TEXT NOT NULL DEFAULT '未认证',
    register_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS course (
    course_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    teacher_id TEXT,
    total_hours INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollment (
    enrollment_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES student(user_id),
    course_id TEXT NOT NULL REFERENCES course(course_id),
    paid_amount REAL NOT NULL,
    discount_amount REAL NOT NULL DEFAULT 0,
    enroll_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    pay_at DATETIME,
    study_goal TEXT,
    status TEXT NOT NULL DEFAULT '已报名'
);
CREATE INDEX IF NOT EXISTS ix_enrollment_user_id ON enrollment(user_id);
CREATE INDEX IF NOT EXISTS ix_enrollment_course_id ON enrollment(course_id);
CREATE INDEX IF NOT EXISTS ix_enrollment_enroll_at ON enrollment(enroll_at);

CREATE TABLE IF NOT EXISTS learning_progress (
    progress_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES student(user_id),
    course_id TEXT NOT NULL REFERENCES course(course_id),
    total_minutes INTEGER NOT NULL DEFAULT 0,
    completion_rate REAL NOT NULL DEFAULT 0,
    last_active_at DATETIME
);

CREATE TABLE IF NOT EXISTS refund_request (
    refund_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES enrollment(enrollment_id),
    reason TEXT,
    study_minutes_before_refund INTEGER NOT NULL DEFAULT 0,
    refund_amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT '申请中',
    apply_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS credential_verification (
    verification_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES student(user_id),
    verification_type TEXT NOT NULL,
    id_card_hash TEXT,
    status TEXT NOT NULL DEFAULT '待审核',
    failure_reason TEXT,
    submit_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS device_binding (
    binding_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES student(user_id),
    device_fingerprint_hash TEXT NOT NULL,
    first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_device_binding_user_id ON device_binding(user_id);
CREATE INDEX IF NOT EXISTS ix_device_binding_hash ON device_binding(device_fingerprint_hash);

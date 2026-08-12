USE education_risk;

CREATE TABLE IF NOT EXISTS user_info (
  user_id VARCHAR(50) PRIMARY KEY, name VARCHAR(50) NOT NULL,
  role VARCHAR(20) NOT NULL, student_id VARCHAR(50) UNIQUE,
  real_name_status TINYINT NOT NULL DEFAULT 1, device_id VARCHAR(80) NOT NULL,
  register_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS course (
  course_id VARCHAR(50) PRIMARY KEY, name VARCHAR(100) NOT NULL, category VARCHAR(50) NOT NULL,
  price DECIMAL(10,2) NOT NULL, teacher_id VARCHAR(50) NOT NULL, total_hours INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS enrollment (
  enrollment_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, course_id VARCHAR(50) NOT NULL,
  total_amount DECIMAL(10,2) NOT NULL, payment_time DATETIME NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT '已报名', study_goal VARCHAR(100), INDEX idx_enrollment_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS learning_progress (
  progress_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, course_id VARCHAR(50) NOT NULL,
  total_minutes INT NOT NULL DEFAULT 0, completion_rate DECIMAL(5,4) NOT NULL DEFAULT 0,
  last_active_at DATETIME, INDEX idx_progress_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS refund_request (
  refund_id VARCHAR(50) PRIMARY KEY, enrollment_id VARCHAR(50) NOT NULL, user_id VARCHAR(50) NOT NULL,
  reason VARCHAR(200) NOT NULL, study_minutes_before_refund INT NOT NULL DEFAULT 0,
  refund_amount DECIMAL(10,2) NOT NULL, request_time DATETIME NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT '待审核', INDEX idx_refund_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS live_reward (
  reward_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL, teacher_id VARCHAR(50) NOT NULL,
  amount DECIMAL(10,2) NOT NULL, reward_time DATETIME NOT NULL, live_room_id VARCHAR(50) NOT NULL,
  INDEX idx_reward_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

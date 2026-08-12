USE education_risk;

CREATE TABLE risk_rule (
 rule_id VARCHAR(50) PRIMARY KEY, rule_name VARCHAR(100) NOT NULL,
 rule_category ENUM('报名欺诈','退费滥用','账号风险','直播风险') NOT NULL,
 event_type ENUM('课程报名','退费申请','直播打赏','通用') NOT NULL DEFAULT '通用',
 rule_condition JSON NOT NULL, risk_level ENUM('低','中','高','极高') NOT NULL,
 risk_score INT NOT NULL, action ENUM('通过','标记','人工审核','拒绝') NOT NULL,
 is_enabled TINYINT DEFAULT 1, priority INT DEFAULT 0, description TEXT,
 create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 deleted_at DATETIME DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE risk_event (
 event_id VARCHAR(50) PRIMARY KEY, event_type ENUM('课程报名','退费申请','直播打赏') NOT NULL,
 event_source_id VARCHAR(50) NOT NULL, user_id VARCHAR(50) NOT NULL, event_data JSON,
 create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, INDEX idx_risk_event_user_id(user_id), INDEX idx_risk_event_create_time(create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE risk_feature (
 feature_id BIGINT AUTO_INCREMENT PRIMARY KEY, event_id VARCHAR(50) NOT NULL,
 entity_type ENUM('用户','报名','设备') NOT NULL, entity_id VARCHAR(50) NOT NULL,
 feature_name VARCHAR(100) NOT NULL, feature_value DECIMAL(15,4), compute_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 INDEX idx_risk_feature_event_id(event_id), INDEX idx_risk_feature_entity(entity_type, entity_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE risk_assessment (
 assessment_id VARCHAR(50) PRIMARY KEY, event_id VARCHAR(50) NOT NULL, user_id VARCHAR(50) NOT NULL,
 rule_results JSON, rule_count INT DEFAULT 0, final_score INT NOT NULL,
 risk_level ENUM('低','中','高','极高') NOT NULL, decision ENUM('通过','标记','人工审核','拒绝') NOT NULL,
 ml_score DECIMAL(5,4), ml_decision VARCHAR(10), create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 INDEX idx_risk_assessment_user_id(user_id), INDEX idx_risk_assessment_decision(decision), INDEX idx_risk_assessment_create_time(create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE risk_case (
 case_id VARCHAR(50) PRIMARY KEY, assessment_id VARCHAR(50) NOT NULL, user_id VARCHAR(50) NOT NULL,
 case_status ENUM('待审核','审核中','已通过','已拒绝','已关闭') NOT NULL DEFAULT '待审核',
 case_category VARCHAR(50), risk_detail JSON, source_id VARCHAR(50),
 event_type ENUM('课程报名','退费申请','直播打赏'), reviewer VARCHAR(50), review_comment TEXT, review_time DATETIME,
 create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 INDEX idx_risk_case_status(case_status), INDEX idx_risk_case_user_id(user_id), INDEX idx_risk_case_source_id(source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE risk_blacklist (
 blacklist_id BIGINT AUTO_INCREMENT PRIMARY KEY, blacklist_type ENUM('用户','学号','设备指纹') NOT NULL,
 blacklist_value VARCHAR(200) NOT NULL, reason TEXT, expire_time DATETIME, create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 deleted_at DATETIME DEFAULT NULL, UNIQUE KEY idx_blacklist_type_value(blacklist_type, blacklist_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE risk_user_profile (
 user_id VARCHAR(50) PRIMARY KEY, risk_score INT DEFAULT 0, risk_level ENUM('低','中','高','极高') DEFAULT '低',
 total_orders INT DEFAULT 0, total_refunds INT DEFAULT 0, refund_rate DECIMAL(5,4) DEFAULT 0,
 avg_order_amount DECIMAL(10,2) DEFAULT 0, address_count INT DEFAULT 0, complaint_count INT DEFAULT 0,
 assessment_count INT DEFAULT 0, last_assessment_time DATETIME, profile_data JSON,
 update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE risk_action_log (
 log_id BIGINT AUTO_INCREMENT PRIMARY KEY, operator VARCHAR(50) NOT NULL,
 action_type ENUM('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST') NOT NULL,
 target_type ENUM('rule','case','blacklist') NOT NULL, target_id VARCHAR(50) NOT NULL,
 before_value JSON, after_value JSON, ip VARCHAR(50), remark VARCHAR(500), create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE risk_alert (
 alert_id BIGINT AUTO_INCREMENT PRIMARY KEY, alert_type ENUM('BUSINESS','MODEL','SYSTEM','SECURITY') NOT NULL,
 alert_level ENUM('P0','P1','P2','P3') NOT NULL, alert_title VARCHAR(200) NOT NULL, alert_content TEXT,
 metric_name VARCHAR(100), metric_value DECIMAL(20,6), threshold DECIMAL(20,6),
 status ENUM('PENDING','HANDLING','RESOLVED','IGNORED') DEFAULT 'PENDING', handler VARCHAR(50), resolve_time DATETIME,
 create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

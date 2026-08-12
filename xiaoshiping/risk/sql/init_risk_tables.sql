SET NAMES utf8mb4;
USE manufacturing_risk;
CREATE TABLE risk_rule (
  rule_id VARCHAR(20) PRIMARY KEY, rule_name VARCHAR(120) NOT NULL, event_type VARCHAR(60) NOT NULL,
  risk_category VARCHAR(40) NOT NULL, threshold_value DECIMAL(12,4), action VARCHAR(20) NOT NULL,
  score INT NOT NULL, enabled TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB;
CREATE TABLE risk_event (
  risk_event_id VARCHAR(20) PRIMARY KEY, event_id VARCHAR(20), entity_type VARCHAR(40) NOT NULL,
  entity_id VARCHAR(40) NOT NULL, rule_id VARCHAR(20), risk_category VARCHAR(40) NOT NULL,
  risk_score INT NOT NULL, decision VARCHAR(20) NOT NULL, event_at DATETIME NOT NULL,
  handled_status VARCHAR(20) NOT NULL, reason VARCHAR(255),
  FOREIGN KEY (event_id) REFERENCES business_event(event_id), FOREIGN KEY (rule_id) REFERENCES risk_rule(rule_id)
) ENGINE=InnoDB;
CREATE TABLE risk_assessment (
  assessment_id VARCHAR(30) PRIMARY KEY, event_id VARCHAR(20) NOT NULL, source_type VARCHAR(40) NOT NULL,
  source_id VARCHAR(40) NOT NULL, rule_score INT NOT NULL, ml_score DECIMAL(8,4), final_score INT NOT NULL,
  decision VARCHAR(20) NOT NULL, rule_hit_count INT NOT NULL, feature_json JSON NOT NULL,
  hit_rule_json JSON NOT NULL, create_time DATETIME NOT NULL, FOREIGN KEY (event_id) REFERENCES business_event(event_id)
) ENGINE=InnoDB;
CREATE TABLE risk_case (
  case_id VARCHAR(30) PRIMARY KEY, assessment_id VARCHAR(30) NOT NULL, source_type VARCHAR(40) NOT NULL,
  source_id VARCHAR(40) NOT NULL, risk_level VARCHAR(20) NOT NULL, status VARCHAR(20) NOT NULL,
  owner_team VARCHAR(40) NOT NULL, summary VARCHAR(255) NOT NULL, create_time DATETIME NOT NULL,
  update_time DATETIME NOT NULL, FOREIGN KEY (assessment_id) REFERENCES risk_assessment(assessment_id)
) ENGINE=InnoDB;


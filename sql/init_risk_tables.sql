-- 风控表：规则、黑名单、事件、特征快照、评估结果和案件。
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS risk_rule (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    rule_condition TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    action TEXT NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS risk_blacklist (
    blacklist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    blacklist_type TEXT NOT NULL,
    blacklist_value TEXT NOT NULL,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_risk_blacklist_value ON risk_blacklist(blacklist_type, blacklist_value);

CREATE TABLE IF NOT EXISTS risk_event (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    event_data TEXT NOT NULL DEFAULT '{}',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_feature (
    feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES risk_event(event_id),
    entity_type TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    feature_value REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_assessment (
    assessment_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES risk_event(event_id),
    user_id TEXT NOT NULL,
    final_score INTEGER NOT NULL,
    risk_level TEXT NOT NULL,
    decision TEXT NOT NULL,
    rule_results TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS risk_case (
    case_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL REFERENCES risk_assessment(assessment_id),
    source_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    case_status TEXT NOT NULL DEFAULT '待审核'
);

-- 与 app/seed.py 相同的测试规则和黑名单；条件字段统一使用旧项目风格的 op。
INSERT OR IGNORE INTO risk_rule (
    rule_id, rule_name, event_type, rule_condition, risk_score, action, is_enabled
) VALUES (
    'EDU-RULE-001',
    '七日内共享设备关联多个新报名账号',
    '课程报名',
    '{"field":"device_linked_users_7d","op":">=","value":5}',
    65,
    '人工审核',
    1
);

INSERT OR IGNORE INTO risk_blacklist (blacklist_type, blacklist_value, reason)
VALUES ('用户', 'STU-BLACK-001', '演示用已确认作弊账号');

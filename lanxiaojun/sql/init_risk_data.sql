-- ============================================
-- 教育风控系统 - 预置规则数据初始化
-- 30 条规则覆盖 8 大教育风控场景 (ER001-ER030)
-- ============================================================
-- ER001-ER004  注册风险  (4 条)
-- ER005-ER008  账号风险  (4 条, 含 ER015 合并)
-- ER009-ER011  营销作弊  (3 条)
-- ER012-ER015  刷课行为  (4 条)
-- ER016-ER019  退费欺诈  (4 条)
-- ER020-ER023  支付风险  (4 条)
-- ER024-ER026  内容安全  (3 条)
-- ER027-ER030  师资风险  (4 条)
-- ============================================================

SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 注册风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER001', '凌晨注册', '注册风险', 'register',
 '{"field": "user_reg_hour", "op": ">=", "value": 22}',
 '中', 30, '标记', 1, 40,
 '凌晨 22 点后注册，可能存在异常注册风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER002', '批量设备注册', '注册风险', 'register',
 '{"field": "behavior_device_count", "op": ">=", "value": 3}',
 '高', 60, '人工审核', 1, 80,
 '关联设备 ≥ 3 个，疑似批量注册小号');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER003', '实名+手机号不一致', '注册风险', 'real_name_auth',
 '{"and": [{"field": "user_is_real_name", "op": "==", "value": 0}, {"field": "user_account_age_days", "op": "<", "value": 1}]}',
 '高', 70, '人工审核', 1, 85,
 '注册当天就做实名认证，疑似使用他人身份信息');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER004', '学生身份异常', '注册风险', 'register',
 '{"field": "user_role_code", "op": "==", "value": 0}',
 '低', 15, '通过', 1, 20,
 '角色编码异常，无法归类的注册行为');

-- ============================
-- 场景二: 账号风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER005', '频繁更换设备', '账号风险', 'login',
 '{"field": "behavior_device_count", "op": ">=", "value": 4}',
 '高', 65, '人工审核', 1, 75,
 '关联设备 ≥ 5 个，账号共享或被盗风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER006', '投诉次数过多', '账号风险', 'complaint',
 '{"field": "user_complaint_count", "op": ">=", "value": 2}',
 '中', 45, '标记', 1, 70,
 '投诉次数 ≥ 2，关注投诉行为');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER007', '近 30 天大量报名不学习', '账号风险', 'purchase',
 '{"and": [{"field": "user_enrollments_30d", "op": ">=", "value": 6}, {"field": "user_avg_completion_rate", "op": "<", "value": 20}]}',
 '中', 50, '标记', 1, 80,
 '近 30 天报名 ≥ 6 门课但平均完成率 < 20%，低学习投入');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER008', '新账号立即报名高价课', '账号风险', 'purchase',
 '{"and": [{"field": "user_account_age_days", "op": "<=", "value": 1}, {"field": "course_price", "op": ">=", "value": 3000}]}',
 '高', 70, '人工审核', 1, 75,
 '注册当天报名 ≥ 3000 元课程，盗刷或盗号风险');

-- ============================
-- 场景三: 营销作弊 (3条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER009', '同一设备多账号领券', '营销作弊', 'coupon_claim',
 '{"field": "behavior_device_count", "op": ">=", "value": 2}',
 '中', 45, '标记', 1, 60,
 '同一设备多账号领券，刷券嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER010', '凌晨领券', '营销作弊', 'coupon_claim',
 '{"and": [{"field": "order_pay_hour", "op": ">=", "value": 22}, {"field": "user_account_age_days", "op": "<=", "value": 7}]}',
 '中', 40, '标记', 1, 50,
 '凌晨领券 + 注册 ≤ 7 天，疑似机器刷券');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER011', '极速报名支付', '营销作弊', 'purchase',
 '{"and": [{"field": "user_account_age_days", "op": "<=", "value": 1}, {"field": "user_payment_account_count", "op": ">=", "value": 3}]}',
 '高', 65, '人工审核', 1, 70,
 '注册当天绑定 ≥ 3 个支付账号，疑似黑产洗钱');

-- ============================
-- 场景四: 刷课行为 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER012', '极速刷课 (凌晨大量看课)', '刷课行为', 'course_watch',
 '{"and": [{"field": "behavior_night_session", "op": "==", "value": 1}, {"field": "behavior_today_minutes", "op": ">=", "value": 120}]}',
 '中', 50, '标记', 1, 60,
 '凌晨连续看课 ≥ 180 分钟，疑似机器刷课时');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER013', '完成率偏高 + 学习时间短', '刷课行为', 'course_watch',
 '{"and": [{"field": "user_avg_completion_rate", "op": ">=", "value": 80}, {"field": "behavior_today_minutes", "op": "<", "value": 90}]}',
 '中', 40, '标记', 1, 80,
 '完成率 ≥ 80% 但日学习时长 < 90 分钟，可能存在刷课行为');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER014', '同时学习大量课程', '刷课行为', 'course_watch',
 '{"field": "behavior_active_courses", "op": ">=", "value": 4}',
 '中', 40, '标记', 1, 50,
 '同时进行 ≥ 5 门课，疑似多开刷课');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER015', '刷课 + 多设备并行', '刷课行为', 'course_watch',
 '{"and": [{"field": "behavior_active_courses", "op": ">=", "value": 3}, {"field": "behavior_device_count", "op": ">=", "value": 2}]}',
 '高', 75, '人工审核', 1, 85,
 '多设备同时学多门课，疑似代挂/刷课团伙');

-- ============================
-- 场景五: 退费欺诈 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER016', '高退费率用户', '退费欺诈', 'refund_apply',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.3}, {"field": "user_total_enrollments", "op": ">=", "value": 5}]}',
 '中', 50, '标记', 1, 80,
 '退费率 ≥ 30% 且报名 ≥ 5 门，退费行为异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER017', '极端退费率用户', '退费欺诈', 'refund_apply',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.35}, {"field": "user_total_enrollments", "op": ">=", "value": 8}]}',
 '高', 75, '人工审核', 1, 95,
 '退费率 ≥ 35% 且报名 ≥ 8 门，退费行为异常需审核');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER018', '学完即退费', '退费欺诈', 'refund_apply',
 '{"and": [{"field": "user_avg_completion_rate", "op": ">=", "value": 80}, {"field": "user_refund_rate", "op": ">=", "value": 0.25}]}',
 '中', 50, '标记', 1, 75,
 '完成率 ≥ 80% 且退费率 ≥ 25%，关注学完就退模式');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER019', '累计退费金额异常', '退费欺诈', 'refund_apply',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.25}, {"field": "course_price", "op": ">=", "value": 3000}]}',
 '高', 60, '人工审核', 1, 65,
 '退费率 ≥ 40% 且课程价格 ≥ 5000 元，退费金额风险');

-- ============================
-- 场景六: 支付风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER020', '凌晨大额支付', '支付风险', 'purchase',
 '{"and": [{"field": "order_pay_hour", "op": ">=", "value": 22}, {"field": "order_amount", "op": ">=", "value": 5000}]}',
 '高', 70, '人工审核', 1, 80,
 '凌晨 (≥22点) 支付 ≥ 5000 元，盗刷风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER021', '单人绑定多支付账户', '支付风险', 'purchase',
 '{"field": "user_payment_account_count", "op": ">=", "value": 4}',
 '高', 55, '人工审核', 1, 65,
 '绑定 ≥ 4 个支付账户，代付洗钱嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER022', '大额课程深夜报名', '支付风险', 'purchase',
 '{"and": [{"field": "course_price", "op": ">=", "value": 10000}, {"field": "order_pay_hour", "op": ">=", "value": 23}]}',
 '极高', 95, '拒绝', 1, 100,
 '≥ 10000 元课程深夜报名，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER023', '高金额 + 新用户 + 凌晨', '支付风险', 'purchase',
 '{"and": [{"field": "order_amount", "op": ">=", "value": 3000}, {"field": "user_account_age_days", "op": "<=", "value": 3}, {"field": "order_pay_hour", "op": ">=", "value": 22}]}',
 '极高', 90, '拒绝', 1, 95,
 '全新用户 3 天内凌晨支付 ≥ 3000 元，盗刷一票否决');

-- ============================
-- 场景七: 内容安全 (3条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER024', '频繁投诉侵权盗版', '内容安全', 'complaint',
 '{"field": "user_complaint_count", "op": ">=", "value": 3}',
 '高', 60, '人工审核', 1, 70,
 '投诉次数 ≥ 5，疑似恶意投诉或版权风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER025', '投诉内容违规课程', '内容安全', 'complaint',
 '{"field": "user_complaint_count", "op": ">=", "value": 2}',
 '中', 35, '标记', 1, 40,
 '投诉 ≥ 2 次，关注内容合规');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER026', '课程高投诉率', '内容安全', 'complaint',
 '{"and": [{"field": "course_price", "op": ">=", "value": 1000}, {"field": "user_complaint_count", "op": ">=", "value": 1}]}',
 '低', 20, '通过', 1, 30,
 '价格 ≥ 1000 元课程有投诉，低风险标记');

-- ============================
-- 场景八: 师资风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER027', '低评分教师授课', '师资风险', 'purchase',
 '{"field": "course_teacher_rating", "op": "<", "value": 3.0}',
 '中', 30, '标记', 1, 40,
 '授课教师评分 < 3.0，教学质量风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER028', '新教师高价课', '师资风险', 'purchase',
 '{"and": [{"field": "course_teacher_rating", "op": "<", "value": 3.5}, {"field": "course_price", "op": ">=", "value": 5000}]}',
 '高', 60, '人工审核', 1, 70,
 '新入库教师 (评分 < 3.5) 开出 ≥ 5000 元高价课');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER029', '低评分教师大量开课', '师资风险', '通用',
 '{"and": [{"field": "course_teacher_rating", "op": "<", "value": 2.5}, {"field": "course_total_hours", "op": ">=", "value": 100}]}',
 '高', 65, '人工审核', 1, 75,
 '评分 < 2.5 但课时 ≥ 100，师资资质风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('ER030', '师资综合高风险', '师资风险', '通用',
 '{"and": [{"field": "course_teacher_rating", "op": "<", "value": 2.0}, {"field": "course_price", "op": ">=", "value": 3000}, {"field": "user_complaint_count", "op": ">=", "value": 2}]}',
 '极高', 88, '拒绝', 1, 95,
 '评分 < 2.0 + 价格 ≥ 3000 + 投诉 ≥ 2，师资与内容双高危一票否决');
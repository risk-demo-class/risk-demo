-- ============================================
-- 教育风控系统 - 预置规则数据初始化
-- 8 条规则覆盖 6 大风险场景 (R001-R008)
-- ============================================================
-- R001  报名欺诈 (刷单式报名)
-- R002  退费滥用 (0学时退费)
-- R003  报名欺诈 (大额连报)
-- R004  账户风险 (假学员代理)
-- R005  退费滥用 (退费连环)
-- R006  打赏风险 (直播打赏异常)
-- R007  账户风险 (学员身份不符)
-- R008  综合风险 (黑学号拦截)
-- ============================================================

USE ecs;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 报名欺诈 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '刷单式报名', '报名欺诈', '课程报名',
 '{"field": "user_enrollments_7d", "op": ">=", "value": 3}',
 '极高', 92, '拒绝', 1, 100,
 '7天内报名>=3门课，疑似刷单式报名，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '大额连报', '报名欺诈', '课程报名',
 '{"field": "order_total_amount", "op": ">=", "value": 30000}',
 '高', 70, '人工审核', 1, 90,
 '1小时内订单金额>=30000元，疑似大额连报欺诈');

-- ============================
-- 场景二: 退费滥用 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '0学时退费', '退费滥用', '退费申请',
 '{"and": [{"field": "order_total_amount", "op": ">=", "value": 500}, {"field": "user_avg_completion_rate", "op": "<=", "value": 0.01}]}',
 '高', 75, '人工审核', 1, 95,
 '学习时长<5分钟就申请退费，疑似薅羊毛');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '退费连环', '退费滥用', '退费申请',
 '{"and": [{"field": "user_refund_count", "op": ">=", "value": 3}, {"field": "user_refund_amount", "op": ">=", "value": 10000}]}',
 '中', 50, '标记', 1, 60,
 '累计退款>=3次且退款金额>=10000元，疑似退费连环套利');

-- ============================
-- 场景三: 账户风险 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R004', '假学员代理', '账户风险', '课程报名',
 '{"and": [{"field": "addr_device_count", "op": ">=", "value": 5}, {"field": "user_enrollments_7d", "op": ">=", "value": 1}]}',
 '极高', 90, '拒绝', 1, 98,
 '同一设备指纹关联>=5个学员账号，疑似假学员代理');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '学员身份不符', '账户风险', '课程报名',
 '{"field": "order_total_amount", "op": ">=", "value": 5000}',
 '中', 40, '标记', 1, 50,
 '高额订单标记，需人工核查学员身份是否匹配课程');

-- ============================
-- 场景四: 打赏风险 (1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R006', '直播打赏异常', '打赏风险', '直播打赏',
 '{"and": [{"field": "order_total_amount", "op": ">=", "value": 5000}, {"field": "user_enrollments_7d", "op": "<=", "value": 0}]}',
 '中', 45, '标记', 1, 55,
 '单场打赏>5000且账号注册<30天，疑似打赏洗钱');

-- ============================
-- 场景五: 综合风险 (1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '黑学号拦截', '综合风险', '通用',
 '{"field": "user_total_enrollments", "op": ">=", "value": 100}',
 '极高', 95, '拒绝', 1, 99,
 '用户累计报名>=100门课(极端异常)，一票否决');

-- ============================
-- 额外补充规则 (丰富规则库)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R009', '新账号高额报名', '报名欺诈', '课程报名',
 '{"and": [{"field": "user_total_enrollments", "op": "<=", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 5000}]}',
 '高', 65, '人工审核', 1, 85,
 '新用户首单>=5000元，疑似欺诈');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '高频退费用户', '退费滥用', '退费申请',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.5}, {"field": "user_total_enrollments", "op": ">=", "value": 3}]}',
 '高', 70, '人工审核', 1, 80,
 '退费率>=50%且报名>=3门课，疑似恶意退费');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R011', '完课率极低用户', '账户风险', '通用',
 '{"and": [{"field": "user_avg_completion_rate", "op": "<=", "value": 0.05}, {"field": "user_total_enrollments", "op": ">=", "value": 3}]}',
 '中', 45, '标记', 1, 55,
 '完课率<=5%但报名>=3门课，疑似薅羊毛');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '多设备登录', '账户风险', '通用',
 '{"field": "addr_device_count", "op": ">=", "value": 5}',
 '中', 35, '标记', 1, 45,
 '使用>=5个不同设备，疑似账号共享或被盗');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R013', '深夜报名', '报名欺诈', '课程报名',
 '{"field": "order_enroll_hour", "op": "between", "value": [0, 5]}',
 '低', 20, '通过', 1, 30,
 '凌晨0-5点报名，低风险标记');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R014', '超高金额课程', '报名欺诈', '课程报名',
 '{"field": "order_total_amount", "op": ">=", "value": 10000}',
 '极高', 90, '拒绝', 1, 95,
 '单笔订单>=10000元，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R015', '多课程类别', '报名欺诈', '课程报名',
 '{"field": "user_course_category_count", "op": ">=", "value": 4}',
 '中', 40, '标记', 1, 50,
 '报名课程类别>=4种，购买行为分散异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R016', '认证欺诈', '认证欺诈', '学历认证',
 '{"field": "user_total_enrollments", "op": "==", "value": 0}',
 '中', 40, '标记', 1, 50,
 '无报名记录的认证请求，疑似虚假认证');

-- ============================================
-- 教育风控系统 - 8 条预置风控规则 (R001-R008/R012/R018/R025/R030)
-- 规则遵循 JSON 条件表达式格式, 跟原电商系统 rule.py 的 evaluate_condition 兼容
-- ============================================

USE ecs;
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE `risk_rule`;
TRUNCATE TABLE `risk_action_log`;

-- ============================================
-- 极高风险 (直接拒绝) — 3 条
-- ============================================

-- R001: 刷单式报名 — 同一课程 7 天内 >=3 个新账号报名 → 拒绝
INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
('R001', '刷单式报名', '报名欺诈', '报名',
 '{"field": "course_new_students_7d", "op": ">=", "value": 3}',
 '极高', 95, '拒绝', 1, 100,
 '同一课程在 7 天内出现 3 个或以上新账号报名则判定为刷单, 直接拒绝');

-- R008: 假学员代理 — 同一设备指纹关联 >=5 个学员账号 → 拒绝
INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
('R008', '假学员代理', '身份异常', '报名',
 '{"field": "device_linked_students", "op": ">=", "value": 5}',
 '极高', 90, '拒绝', 1, 95,
 '同一设备指纹关联 5 个或以上学员账号则判定为虚假代理注册, 直接拒绝');

-- R030: 黑学号拦截 — 学号/身份证号命中黑名单 → 拒绝 (在 process_event 的 _check_all_blacklists 中实现)
INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
('R030', '黑学号拦截', '身份异常', '通用',
 '{"field": "is_blacklisted", "op": "==", "value": 1}',
 '极高', 100, '拒绝', 1, 100,
 '学员的学号或身份证号码命中系统黑名单则直接拒绝 (在 event pipeline 黑名单前置检查中拦截)');

-- ============================================
-- 高风险 (转人工审核) — 2 条
-- ============================================

-- R002: 0 学时退费 — 学习时长 < 5 分钟就申请退费 → 人工审核
INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
('R002', '0学时退费', '退费滥用', '退费申请',
 '{"field": "study_minutes_before_refund", "op": "<", "value": 5}',
 '高', 80, '人工审核', 1, 85,
 '学员课程学习时长不足 5 分钟且同时发起退款申请则标记为可疑退费, 转人工审核');

-- R005: 大额连报 — 同一用户 1 小时内累计订单 >= 30000 元 → 人工审核
INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
('R005', '大额连报', '报名欺诈', '报名',
 '{"field": "user_order_amount_1h", "op": ">=", "value": 30000}',
 '高', 75, '人工审核', 1, 80,
 '同一用户在 1 小时内累计订单金额超过 30000 元则标记为大额集中报名, 转人工审核');

-- ============================================
-- 中风险 (打标监控) — 3 条
-- ============================================

-- R012: 退费连环 — 90 天内退款 >=3 次 且 累计退款 >=10000 元 → 标记
INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
('R012', '退费连环', '退费滥用', '退费申请',
 '{"and": [{"field": "user_refund_count_90d", "op": ">=", "value": 3}, {"field": "user_refund_amount_90d", "op": ">=", "value": 10000}]}',
 '中', 65, '标记', 1, 70,
 '某用户在 90 天内退款次数达到 3 次或以上且累计退款金额超过 10000 元则标记为高频退费用户');

-- R018: 直播打赏异常 — 单场打赏 >=5000 元 且 注册 < 30 天 → 标记
INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
('R018', '直播打赏异常', '行为异常', '打赏',
 '{"and": [{"field": "donation_amount", "op": ">=", "value": 5000}, {"field": "user_days_since_register", "op": "<", "value": 30}]}',
 '中', 60, '标记', 1, 65,
 '某账号在单场直播中打赏金额超过 5000 元且注册时间不足 30 天则标记为新号高额打赏异常');

-- R025: 学员身份不符 — 老师角色 + 购买学生专属课程 → 标记
INSERT INTO `risk_rule` (`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`) VALUES
('R025', '学员身份不符', '身份异常', '报名',
 '{"and": [{"field": "user_is_teacher", "op": "==", "value": 1}, {"field": "course_is_student_only", "op": "==", "value": 1}]}',
 '中', 50, '标记', 1, 60,
 '用户角色为老师但购买了面向学生的课程则标记为身份与课程不匹配');

SET FOREIGN_KEY_CHECKS = 1;

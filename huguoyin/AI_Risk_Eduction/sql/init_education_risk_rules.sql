-- ============================================
-- 教育行业风控系统 - 指定规则数据初始化
-- 规则来源: 课程报名/退费/代学/直播打赏/身份黑名单核心风控场景
-- ============================================

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE `risk_action_log`;
TRUNCATE TABLE `risk_rule`;
SET FOREIGN_KEY_CHECKS = 1;

INSERT INTO `risk_rule`
(`rule_id`, `rule_name`, `rule_category`, `event_type`, `rule_condition`, `risk_level`, `risk_score`, `action`, `is_enabled`, `priority`, `description`)
VALUES
('R001', '刷单式报名', '刷单报名', '课程报名',
 '{"field":"same_course_new_accounts_7d","op":">=","value":3}',
 '极高', 95, '拒绝', 1, 100,
 '同一课程 7 天内 >= 3 个新账号报名, 疑似刷单式报名或批量导流套利'),

('R002', '0 学时退费', '退费风险', '退费申请',
 '{"field":"study_minutes_before_refund_min","op":"<","value":5}',
 '高', 80, '人工审核', 1, 95,
 '课程学习时长 < 5 分钟即申请退款, 需人工核查恶意退款或体验课套利'),

('R005', '大额连报', '连报风险', '课程报名',
 '{"field":"pay_amount_sum_1h","op":">","value":30000}',
 '高', 80, '人工审核', 1, 90,
 '1 小时内同一学员报名/支付金额 > 30000 元, 需核查资金来源、合同和监管账户'),

('R008', '假学员代理', '代学风险', '课程报名',
 '{"field":"same_device_student_count","op":">=","value":5}',
 '极高', 92, '拒绝', 1, 85,
 '同一设备指纹关联 >= 5 个学员账号, 疑似代理报名、代学或团伙账号'),

('R012', '退费连环', '退费风险', '退费申请',
 '{"and":[{"field":"refund_count_90d","op":">=","value":3},{"field":"refund_total_amount_90d","op":">","value":10000}]}',
 '中', 55, '标记', 1, 80,
 '90 天内退款 >= 3 次且累计退款金额 > 10000 元, 标记持续退费风险'),

('R018', '直播打赏异常', '直播打赏', '直播打赏',
 '{"and":[{"field":"max_live_reward_amount","op":">","value":5000},{"field":"account_age_days","op":"<","value":30}]}',
 '中', 55, '标记', 1, 75,
 '单场直播打赏 > 5000 且打赏账号注册 < 30 天, 标记未成年人或异常消费风险'),

('R025', '学员身份不符', '身份合规', '课程报名',
 '{"field":"teacher_buys_student_core_course","op":"==","value":1}',
 '中', 50, '标记', 1, 70,
 'role=老师但购买学生主课程, 标记身份与课程购买场景不一致'),

('R030', '黑学号拦截', '黑名单', '通用',
 '{"field":"blacklisted_identity","op":"==","value":1}',
 '极高', 100, '拒绝', 1, 65,
 '学号/身份证在黑名单, 直接拒绝并进入案件留痕');

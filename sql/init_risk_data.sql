-- ============================================================
-- 银行信贷风控系统 - 预置规则与黑名单初始化
-- 11 条银行业务规则 (R001-R011) + 4 条黑名单演示数据
--
-- 规则条件用 app/engine/feature.py 的 25 维特征名:
--   user_* 借款人维度 / order_* 事件维度 / addr_* 设备IP维度
-- ============================================================

USE ecs;

SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联表 risk_action_log 的历史记录)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
TRUNCATE TABLE risk_blacklist;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 规则: 信贷欺诈 (贷前)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '收入申报显著虚高', '信贷欺诈', '贷款申请',
 '{"field": "order_income_verify_gap", "op": ">=", "value": 1.0}',
 '极高', 95, '拒绝', 1, 100,
 '三源交叉核验: 申报收入 >= 2 倍核验收入, 材料造假/骗贷嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R004', '短期多头借贷', '信贷欺诈', '贷款申请',
 '{"field": "user_applications_60d", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 90,
 '近 60 天申请 >= 3 家/3 笔贷款, 多头借贷软欺诈');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '征信硬查询过多', '信贷欺诈', '贷款申请',
 '{"field": "order_hard_query_6m", "op": ">=", "value": 6}',
 '高', 68, '人工审核', 1, 75,
 '近 6 月征信硬查询 >= 6 次, 频繁申贷');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '新开户大额申请', '账户风险', '贷款申请',
 '{"and": [{"field": "user_account_age_days", "op": "<=", "value": 90}, {"field": "order_amount", "op": ">=", "value": 100000}]}',
 '高', 65, '人工审核', 1, 70,
 '开户不足 90 天 + 申请 >= 10 万, 疑似借壳/黑产包装');

-- ============================
-- 规则: 支付 / 转账风险 (贷中贷后)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '大额转账', '支付风险', '转账',
 '{"field": "order_amount", "op": ">=", "value": 100000}',
 '高', 65, '人工审核', 1, 80,
 '单笔转账 >= 10 万, 结合资金流向监控');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '凌晨高风险操作', '账户风险', '通用',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '中', 45, '标记', 1, 50,
 '0-5 点申请/转账/登录, 黑产作业时段');

-- ============================
-- 规则: 设备 / IP 风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R006', '设备多人共用', '设备风险', '通用',
 '{"field": "addr_device_share_count", "op": ">=", "value": 3}',
 '极高', 98, '拒绝', 1, 100,
 '同一设备关联 >= 3 个不同借款人, 团伙欺诈');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '代理/秒拨IP', '设备风险', '通用',
 '{"field": "addr_ip_risk", "op": "==", "value": 1}',
 '中', 50, '标记', 1, 60,
 '事件 IP 命中代理/Tor/境外库');

-- ============================
-- 规则: 贷后 / 关联风险
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R009', '征信五级分类异常', '贷后风险', '贷款申请',
 '{"field": "order_five_level_risk", "op": "==", "value": 1}',
 '极高', 92, '拒绝', 1, 95,
 '征信五级分类为关注/次级/可疑/损失, 不良记录');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '逾期借款人再申请', '贷后风险', '贷款申请',
 '{"field": "user_overdue_plan_count", "op": ">=", "value": 1}',
 '高', 72, '人工审核', 1, 85,
 '当前已有逾期还款计划仍再申请贷款');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R011', '关联关系密集', '关联风险', '贷款申请',
 '{"field": "user_relation_count", "op": ">=", "value": 3}',
 '中', 55, '标记', 1, 55,
 '借款人关联用户 >= 3, 知识图谱团伙信号');

-- ============================
-- 黑名单演示数据 (risk_blacklist, 撞黑前置拦截)
-- 值来自 scripts/gen_business_data.py seed=42 生成的数据
-- 重新造数后如不一致, 跑 scripts/gen_bank_risk_events.py 前改这里或直接用业务表 blacklist_extra
-- ============================

INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time) VALUES
('手机号', '14181960013', '团伙成员手机号(演示)', NULL);

INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time) VALUES
('身份证号', '42a6102d39067a95122661470225e6001236fabd5de3281d0810f8a7925e2d19', '伪造收入材料骗贷(演示)', NULL);

INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time) VALUES
('统一社会信用代码', '91510107EXU0RNKJGR', '空壳公司虚构经营资质(演示)', NULL);

INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time) VALUES
('银行卡号', '5fa4103bbae8e8ca405224e276a5dabb87bbb97e0ea04d68c7082fa56afd952b', '团伙收款账户(演示)', NULL);

-- ============================================
-- 银行风控系统 - 预置规则数据初始化 (v2: 字段名对齐 3 大特征族)
-- 8 条规则覆盖 4 大银行风险场景 (R001/R002/R005/R008/R012/R018/R025/R030)
-- ============================================================
-- R001  转账风险  异地大额转账        (极高/拒绝)
-- R002  账户风险  凌晨密集操作        (高/人工审核)
-- R005  设备风险  新设备大额          (高/人工审核)
-- R008  转账风险  多卡归集            (极高/拒绝)
-- R012  贷款风险  信贷申请突击        (高/人工审核)
-- R018  设备风险  设备多人共用        (中/标记)
-- R025  登录风险  IP代理秒拨          (中/标记)
-- R030  转账风险  黑卡拦截            (极高/拒绝)
--
-- 欺诈调研依据:
--   R001  公安部: "安全账户"骗局 → 异地大额转账是电诈洗钱核心特征
--   R002  电诈团伙: 凌晨自动化批量转账, 绕过人工风控时段
--   R005  贷款诈骗: 新设备+大额, 疑似盗卡或背债人操作
--   R008  自洗钱: 多卡归集到单一账户, 虚构交易掩盖资金来源 (上海浦东案)
--   R012  多头借贷: 征信白户当背债人, 月内突击申请多家机构 (北京钱某某案)
--   R018  U盾骗取: 团伙共用设备操作多个账户 (徐州U盾案)
--   R025  代理池: 秒拨IP绕过地域风控, Tor隐藏真实来源
--   R030  黑卡拦截: 收款卡涉诈/洗钱, 银联黑名单
-- ============================================================

USE bank_risk;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 转账风险场景 (3条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '异地大额转账', '转账风险', '转账',
 '{"and":[{"op":"==","field":"txn_geo_changed","value":1},{"op":">","field":"txn_amount","value":50000}]}',
 '极高', 95, '拒绝', 1, 10,
 '交易地与常用登录地不同 且 交易金额>5万, 疑似电诈"安全账户"洗钱, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '多卡归集', '转账风险', '转账',
 '{"op":">=","field":"txn_to_same_card_1h","value":3}',
 '极高', 90, '拒绝', 1, 40,
 '1小时内≥3笔转入同一卡, 疑似自洗钱归集, 一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑卡拦截', '转账风险', '转账',
 '{"op":"==","field":"to_card_blacklisted","value":1}',
 '极高', 100, '拒绝', 1, 80,
 '收款卡在黑名单中, 直接拦截, 一票否决');

-- ============================
-- 账户风险场景 (1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '凌晨密集操作', '账户风险', '转账',
 '{"and":[{"op":"==","field":"txn_is_night","value":1},{"op":">=","field":"txn_hour_freq","value":3}]}',
 '高', 70, '人工审核', 1, 20,
 '凌晨0-5点 且 1小时内交易≥3次, 疑似机器自动化批量操作');

-- ============================
-- 设备风险场景 (2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '新设备大额', '设备风险', '转账',
 '{"and":[{"op":"<","field":"txn_device_age_days","value":7},{"op":">","field":"txn_amount","value":30000}]}',
 '高', 75, '人工审核', 1, 30,
 '设备首次出现<7天 且 交易金额>3万, 疑似盗卡或背债人操作');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '设备多人共用', '设备风险', '登录',
 '{"op":">=","field":"dev_multi_user_count","value":5}',
 '中', 45, '标记', 1, 60,
 '同一设备关联≥5个用户, 疑似团伙共用设备 (U盾骗取模式)');

-- ============================
-- 贷款风险场景 (1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '信贷申请突击', '贷款风险', '贷款',
 '{"op":">=","field":"user_loan_count_6m","value":3}',
 '高', 70, '人工审核', 1, 50,
 '近6个月贷款申请≥3次, 疑似多头借贷/背债人欺诈申请');

-- ============================
-- 登录风险场景 (1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', 'IP代理秒拨', '登录风险', '登录',
 '{"or":[{"op":"==","field":"ip_is_proxy","value":1},{"op":"==","field":"ip_is_tor","value":1}]}',
 '中', 40, '标记', 1, 70,
 '登录IP为代理或Tor出口节点, 疑似秒拨代理池绕过地域风控');

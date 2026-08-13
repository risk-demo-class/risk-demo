-- 银行风控 Goal 3 规则与核心黑名单种子。
-- 11 个数据库规则由通用 rule engine 解析；黑卡走 process_event 前置短路。

INSERT INTO risk_rule
(rule_id, rule_name, rule_category, event_type, rule_condition, risk_level,
 risk_score, action, is_enabled, priority, description, deleted_at)
VALUES
('BANK_R001', '异地大额转账', '交易欺诈', '转账',
 '{"and":[{"field":"addr_is_unusual","op":"==","value":1},{"field":"order_event_amount","op":">","value":50000}]}',
 '极高', 95, '拒绝', 1, 100, '当前城市与历史常用城市不同，且转账金额超过 50000 元。', NULL),
('BANK_R002', '凌晨密集操作', '交易欺诈', '转账',
 '{"and":[{"field":"order_is_night","op":"==","value":1},{"field":"order_txn_count_1h","op":">=","value":3}]}',
 '高', 75, '人工审核', 1, 90, '0 至 5 点发生操作，且同一客户 1 小时内成功转账不少于 3 笔。', NULL),
('BANK_R003', '新设备大额', '账户接管', '转账',
 '{"and":[{"field":"order_new_device_days","op":"<","value":7},{"field":"order_event_amount","op":">","value":30000}]}',
 '高', 75, '人工审核', 1, 85, '设备首次出现不足 7 天，且本次转账金额超过 30000 元。', NULL),
('BANK_R004', '多卡归集', '交易欺诈', '转账',
 '{"field":"order_payee_card_count_1h","op":">=","value":3}',
 '极高', 95, '拒绝', 1, 95, '1 小时内至少 3 张不同付款卡向同一收款卡转入。', NULL),
('BANK_R005', '信贷申请突击', '信贷风险', '贷款申请',
 '{"field":"order_loan_institution_count_30d","op":">=","value":3}',
 '高', 75, '人工审核', 1, 80, '近 30 天向不少于 3 家虚构机构提交贷款申请。', NULL),
('BANK_R006', '设备多人共用', '设备风险', '通用',
 '{"field":"order_device_user_count","op":">=","value":5}',
 '中', 45, '标记', 1, 60, '同一设备指纹关联不少于 5 个客户账号。', NULL),
('BANK_R007', '代理/Tor IP', '账户接管', '通用',
 '{"or":[{"field":"addr_is_proxy","op":"==","value":1},{"field":"addr_is_tor","op":"==","value":1}]}',
 '中', 45, '标记', 1, 65, '当前或事件前最近可信登录环境命中代理或 Tor 标记。', NULL),
('BANK_R008', '新设备失败登录', '账户接管', '登录',
 '{"and":[{"field":"order_new_device_days","op":"<","value":7},{"field":"user_failed_login_count_30d","op":">=","value":2}]}',
 '中', 45, '标记', 1, 55, '近 7 天新设备登录，且近 30 天失败登录不少于 2 次（疑似撞库后成功登录）。', NULL),
('BANK_R009', '新设备批量绑卡', '卡片风险', '绑卡',
 '{"and":[{"field":"order_new_device_days","op":"<","value":7},{"field":"user_bound_card_count","op":">=","value":3}]}',
 '高', 65, '人工审核', 1, 75, '新设备上绑卡，且该客户已绑定不少于 3 张卡（疑似新设备批量养号）。', NULL),
('BANK_R010', '新账户新设备操作', '账户接管', '通用',
 '{"and":[{"field":"user_account_age_days","op":"<","value":7},{"field":"order_new_device_days","op":"<","value":7}]}',
 '中', 45, '标记', 1, 50, '注册不足 7 天的新账户使用新设备操作（新开户 + 新设备风险组合）。', NULL),
('BANK_R011', '代理网络新设备登录', '账户接管', '登录',
 '{"and":[{"field":"addr_is_proxy","op":"==","value":1},{"field":"order_new_device_days","op":"<","value":7}]}',
 '极高', 90, '拒绝', 1, 95, '经代理网络使用新设备登录，极高隐匿风险，一票否决直接拒绝。', NULL)
ON DUPLICATE KEY UPDATE
 rule_name=VALUES(rule_name), rule_category=VALUES(rule_category),
 event_type=VALUES(event_type), rule_condition=VALUES(rule_condition),
 risk_level=VALUES(risk_level), risk_score=VALUES(risk_score),
 action=VALUES(action), is_enabled=VALUES(is_enabled), priority=VALUES(priority),
 description=VALUES(description);

-- 黑卡是核心黑名单前置控制，不进入 rule engine。因此命中时 rule_count=0，
-- 但 blocked_by='银行卡号'、decision='拒绝'、final_score=100，语义可审计区分。
-- (P8 修复 2026-08-12): ON DUPLICATE 不复位 deleted_at, 用户软删的黑卡重跑 init 不会被复活。
INSERT INTO risk_blacklist
(blacklist_type, blacklist_value, reason, expire_time, deleted_at)
VALUES
('银行卡号', SHA2('DEMO_CARD_NO_020', 256),
 '教学黑卡：仅用于虚构收款卡前置拦截演示', '2027-12-31 23:59:59', NULL)
ON DUPLICATE KEY UPDATE
 reason=VALUES(reason), expire_time=VALUES(expire_time);

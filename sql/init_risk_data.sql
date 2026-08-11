-- ============================================================
-- 医疗风控系统 - 预置规则数据初始化 (场景 F)
-- 19 条特征规则 (R001-R020, R008 走黑名单机制) + 黑名单种子
-- 规则条件引用 25 维医疗特征 (feature.py / FEATURE_COLUMNS)
-- 场景参考: 国家医保局智能监管规则库 / 医保基金监管常见违规场景
-- ============================================================
-- R001-R007  医保/挂号/处方/药品 高风险 (7 条)
-- R008       黑医保卡 → 走 risk_blacklist 黑名单机制 (不写特征规则)
-- R009-R012  扩展规则 (4 条)
-- R013-R020  监管场景扩展 (8 条, 2026-08-11 新增)
-- ============================================================

USE ecs;

-- 关外键约束 (允许 TRUNCATE 被外键引用的表)
SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联表 risk_action_log 的历史记录)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

-- 恢复外键约束
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 医保结算 (R001 / R007 / R011)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '医保卡盗刷', '医保欺诈', '医保结算',
 '{"and": [{"field": "user_cross_hospital_count", "op": ">=", "value": 3}, {"field": "user_claim_count", "op": ">=", "value": 3}]}',
 '极高', 95, '拒绝', 1, 100,
 '同一医保卡累计在 ≥3 家不同医院结算且结算 ≥3 次，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '异地集中结算', '医保欺诈', '医保结算',
 '{"and": [{"field": "user_out_region_count", "op": ">=", "value": 1}, {"field": "user_claim_count", "op": ">=", "value": 3}, {"field": "user_total_claim_amount", "op": ">", "value": 10000}]}',
 '中', 55, '标记', 1, 60,
 '参保地 ≠ 就医地 + 1 个月内多次结算 + 累计超 1 万，疑似套取基金');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R011', '夜间结算异常', '医保欺诈', '医保结算',
 '{"and": [{"field": "order_is_night", "op": "==", "value": 1}, {"field": "order_claim_amount", "op": ">", "value": 2000}]}',
 '中', 50, '标记', 1, 60,
 '0-5 点非正常诊疗时段的高额结算');

-- ============================
-- 场景二: 处方审核 (R002 / R004 / R005 / R009 / R012)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '医生统方', '机构风险', '处方审核',
 '{"field": "order_doctor_daily_rx_count", "op": ">=", "value": 50}',
 '极高', 90, '人工审核', 1, 95,
 '同一医生 1 天内开具 ≥50 张处方，疑似利益输送');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R004', '处方超量', '处方风险', '处方审核',
 '{"field": "order_drug_count", "op": ">", "value": 30}',
 '极高', 95, '拒绝', 1, 100,
 '单张处方药品数量超临床常规上限，拒绝发药');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '虚假病历', '医保欺诈', '处方审核',
 '{"and": [{"field": "order_doctor_daily_rx_count", "op": ">=", "value": 5}, {"field": "user_visits_7d", "op": ">=", "value": 3}]}',
 '高', 70, '人工审核', 1, 85,
 '同一医生当日集中开方 + 用户近 7 天高频就诊，疑似虚构就诊');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R009', '无诊断开药', '处方风险', '处方审核',
 '{"and": [{"field": "order_dx_count", "op": "==", "value": 0}, {"field": "order_rx_item_count", "op": ">=", "value": 1}]}',
 '高', 70, '人工审核', 1, 85,
 '处方无诊断编码却开药，防无指征用药');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '医师跨院高频', '机构风险', '处方审核',
 '{"field": "order_doctor_cross_hospital_count", "op": ">=", "value": 3}',
 '高', 70, '人工审核', 1, 85,
 '同一医生 7 天内 ≥3 家不同医院出诊并开方，疑似挂证/统方');

-- ============================
-- 场景三: 挂号 (R003 / R010)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '挂号黄牛', '挂号风险', '挂号',
 '{"field": "user_cancel_appt_count", "op": ">=", "value": 5}',
 '高', 70, '人工审核', 1, 90,
 '同一用户 24 小时内取消挂号 ≥5 次，反复抢号转卖');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '同院高频挂号', '挂号风险', '挂号',
 '{"and": [{"field": "user_cancel_appt_count", "op": ">=", "value": 2}, {"field": "user_cancel_appt_rate", "op": ">=", "value": 0.5}]}',
 '中', 50, '标记', 1, 60,
 '高频挂号 + 高取消率，占号/抢号行为特征');

-- ============================
-- 场景四: 药品代购 (R006)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R006', '药品代购', '药品风险', '药品代购',
 '{"and": [{"field": "user_non_self_drug_count", "op": ">=", "value": 1}, {"field": "user_total_claim_amount", "op": ">", "value": 5000}]}',
 '中', 50, '标记', 1, 60,
 '处方药订单收件人 ≠ 患者本人 + 累计金额超 5000，疑似代购');

-- ============================
-- 场景五: 监管场景扩展 (R013-R020, 2026-08-11 新增)
-- 覆盖: 慢病超量购药 / 分解住院 / 重复开药 / 串换药品 / 虚报高报销 /
--       回流药倒卖 / 夜间频繁结算 / 异地大额结算
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R013', '慢病频繁购药', '处方风险', '处方审核',
 '{"and": [{"field": "user_rx_count", "op": ">=", "value": 12}, {"field": "user_visits_30d", "op": ">=", "value": 4}]}',
 '高', 75, '人工审核', 1, 80,
 '慢病患者近 30 天高频就诊且处方量大，疑似分解处方/超量购药套取慢病额度 (监管: 慢病超量购药)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R014', '分解住院结算', '医保欺诈', '医保结算',
 '{"and": [{"field": "user_claim_count", "op": ">=", "value": 6}, {"field": "user_avg_claim_amount", "op": "<", "value": 1500}]}',
 '高', 70, '人工审核', 1, 80,
 '结算次数多且单次金额偏低，疑似将住院分解为多次结算套取基金 (监管: 分解住院/分解收费)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R015', '重复购药', '药品风险', '药品代购',
 '{"and": [{"field": "user_drug_order_count", "op": ">=", "value": 5}, {"field": "user_rx_count", "op": ">=", "value": 5}]}',
 '高', 70, '人工审核', 1, 80,
 '处方多且药品订单多，疑似跨院/跨科重复开药购药 (监管: 重复开药/重复收费)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R016', '串换药品嫌疑', '药品风险', '药品代购',
 '{"and": [{"field": "order_drug_count", "op": ">=", "value": 20}, {"field": "order_claim_amount", "op": ">=", "value": 2000}]}',
 '高', 70, '人工审核', 1, 80,
 '单笔药品订单数量大且金额高，疑似串换药品/高价药套保 (监管: 串换药品/虚假购销)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R017', '异常高额报销', '医保欺诈', '医保结算',
 '{"and": [{"field": "order_claim_amount", "op": ">", "value": 3000}, {"field": "order_insured_rate", "op": ">=", "value": 0.9}]}',
 '高', 75, '人工审核', 1, 80,
 '单笔结算金额高且报销比例异常高，疑似虚报费用/超标准报销 (监管: 超标准收费/虚记多记)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '回流药倒卖', '药品风险', '药品代购',
 '{"and": [{"field": "user_non_self_drug_count", "op": ">=", "value": 2}, {"field": "user_drug_order_count", "op": ">=", "value": 3}]}',
 '高', 75, '人工审核', 1, 80,
 '多次非本人收药，疑似收集医保药品回流倒卖 (监管: 回流药/倒卖医保药品)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R019', '夜间频繁结算', '医保欺诈', '医保结算',
 '{"and": [{"field": "user_night_claim_count", "op": ">=", "value": 2}, {"field": "user_claim_count", "op": ">=", "value": 4}]}',
 '中', 55, '标记', 1, 60,
 '夜间结算次数多且结算频繁，疑似非正常诊疗时段套保 (监管: 虚假就医/挂床住院)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R020', '异地大额结算', '医保欺诈', '医保结算',
 '{"and": [{"field": "user_out_region_count", "op": ">=", "value": 2}, {"field": "user_max_claim_amount", "op": ">", "value": 5000}]}',
 '高', 75, '人工审核', 1, 80,
 '多次异地结算且单笔金额大，疑似异地套现/骗保 (监管: 异地就医骗保)');

-- ============================
-- R008 黑医保卡: 走黑名单机制 (risk_blacklist), 不写特征规则
-- ============================

INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason) VALUES
('医保卡', 'MC-BLACK-001', '黑医保卡演示 (R008)');

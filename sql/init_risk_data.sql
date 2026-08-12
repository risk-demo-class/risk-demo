-- ============================================
-- 医疗风控系统 - 预置规则数据初始化
-- 30 条规则覆盖 6 大风险场景 (R001-R030)
-- ============================================================
-- R001-R005  医保欺诈  (5 条, 含 R001 医保卡盗刷 / R025 异地集中结算 / R030 黑医保卡)
-- R006-R009  处方违规  (4 条, 含 R002 医生统方 / R008 处方超量 / R012 虚假病历)
-- R010-R013  挂号黄牛  (4 条, 含 R005 反复取消抢号)
-- R014-R017  药品代购  (4 条, 含 R018 收件人≠本人)
-- R018-R021  账户风险  (4 条)
-- R022-R024  机构风险  (3 条)
-- R026-R029  补充规则  (4 条, 高频大额结算/黄牛多院取消/代购他人收件/异地新患者)
-- 注: 编号里 R005/R012/R018/R025/R030 对齐需求文档的示例规则
-- ============================================================

USE medical_risk;

-- 关外键约束 (允许 TRUNCATE 被外键引用的表)
SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联表 risk_action_log 的历史记录)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
-- 风控黑名单也重置, 随后从行业黑名单登记簿 blacklist_extra 同步一份
-- (撞黑检查走 risk_blacklist; 本脚本在 init_business_data.sql 之后执行, 无顺序问题)
TRUNCATE TABLE risk_blacklist;

-- 恢复外键约束
SET FOREIGN_KEY_CHECKS = 1;

-- 行业黑名单 → 风控黑名单 同步 (4 类医疗黑名单: 医保卡号/身份证号/医生执业证/医院编码)
INSERT INTO risk_blacklist (blacklist_type, blacklist_value, reason, expire_time)
SELECT type, value, reason, expire_at FROM blacklist_extra;

-- ============================
-- 场景一: 医保欺诈 (5条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R001', '医保卡盗刷', '医保欺诈', '医保结算',
 '{"field": "user_claim_hospitals_1h", "op": ">=", "value": 3}',
 '极高', 95, '拒绝', 1, 100,
 '同一医保卡 1 小时内在 ≥3 家不同医院结算, 疑似盗刷, 一票否决 + 人工调查');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R003', '单笔高额结算', '医保欺诈', '医保结算',
 '{"field": "order_total_amount", "op": ">=", "value": 20000}',
 '高', 70, '人工审核', 1, 90,
 '单笔结算总费用 ≥2 万元, 需人工审核费用明细');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R004', '30天高频结算', '医保欺诈', '医保结算',
 '{"field": "user_claim_30d_count", "op": ">=", "value": 10}',
 '高', 65, '人工审核', 1, 85,
 '近 30 天结算 ≥10 次, 疑似频繁就医套取医保基金');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R025', '异地集中结算', '医保欺诈', '医保结算',
 '{"and": [{"field": "addr_cross_region", "op": "==", "value": 1}, {"field": "user_claim_30d_count", "op": ">=", "value": 3}, {"field": "user_claim_30d_amount", "op": ">=", "value": 10000}]}',
 '中', 50, '标记', 1, 70,
 '参保地 ≠ 就医地 + 近 30 天 ≥3 次结算 + 累计 >1 万, 异地集中结算标记');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R030', '黑医保卡', '医保欺诈', '通用',
 '{"field": "user_card_blacklist_hit", "op": "==", "value": 1}',
 '极高', 98, '拒绝', 1, 100,
 '患者医保卡号/身份证号命中行业黑名单, 一票否决直接拒绝');

-- ============================
-- 场景二: 处方违规 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R002', '医生统方', '处方违规', '处方开具',
 '{"and": [{"field": "order_doctor_rx_1d", "op": ">=", "value": 50}, {"field": "order_doctor_patient_1d", "op": ">=", "value": 10}]}',
 '极高', 92, '人工审核', 1, 98,
 '同一医生 1 天内开具 ≥50 张处方且涉及 ≥10 个不同患者, 疑似统方, 风控介入');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R008', '处方超量', '处方违规', '处方开具',
 '{"field": "order_drug_quantity", "op": ">", "value": 30}',
 '极高', 90, '拒绝', 1, 95,
 '单张处方药品数量 > 临床常规上限 (如阿普唑仑 > 30 片), 拒绝发药');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R012', '虚假病历', '处方违规', '处方开具',
 '{"field": "order_diagnosis_same_7d", "op": ">=", "value": 5}',
 '高', 70, '人工审核', 1, 85,
 '同一诊断编码 1 周内 ≥5 个不同患者 + 同一医生, 疑似虚假病历套保');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R009', '夜间开方', '处方违规', '处方开具',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '中', 30, '标记', 1, 40,
 '凌晨 0-6 点开方, 非门诊时段处方标记关注');

-- ============================
-- 场景三: 挂号黄牛 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R005', '挂号黄牛(反复取消)', '挂号黄牛', '挂号',
 '{"field": "user_cancel_24h", "op": ">=", "value": 5}',
 '高', 70, '人工审核', 1, 90,
 '同一手机号 24 小时内取消挂号 ≥5 次, 反复抢号转卖嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R010', '7天高频挂号', '挂号黄牛', '挂号',
 '{"field": "user_visits_7d", "op": ">=", "value": 8}',
 '中', 45, '标记', 1, 60,
 '近 7 天挂号 ≥8 次, 挂号频率异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R011', '高取消率患者', '挂号黄牛', '挂号',
 '{"and": [{"field": "user_cancel_count", "op": ">=", "value": 5}, {"field": "user_total_visits", "op": ">=", "value": 8}]}',
 '中', 40, '标记', 1, 55,
 '取消挂号 ≥5 次且总挂号 ≥8 次, 占号行为异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R013', '多医院分散挂号', '挂号黄牛', '挂号',
 '{"field": "user_hospital_count", "op": ">=", "value": 5}',
 '高', 55, '人工审核', 1, 65,
 '在 ≥5 家不同医院挂号, 疑似号贩子多院占号');

-- ============================
-- 场景四: 药品代购 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R018', '药品代购', '药品代购', '药品下单',
 '{"and": [{"field": "order_receiver_not_self", "op": "==", "value": 1}, {"field": "user_drug_amount", "op": ">", "value": 5000}]}',
 '中', 50, '标记', 1, 75,
 '处方药订单收件人 ≠ 患者本人 + 累计购药金额 > 5000, 疑似药品代购');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R014', '大批量购药', '药品代购', '药品下单',
 '{"field": "order_drug_quantity", "op": ">=", "value": 20}',
 '高', 60, '人工审核', 1, 80,
 '单笔药品订单数量 ≥20, 超出个人合理用药量');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R015', '累计购药金额过高', '药品代购', '药品下单',
 '{"field": "user_drug_amount", "op": ">=", "value": 20000}',
 '高', 65, '人工审核', 1, 70,
 '累计购药金额 ≥2 万, 药品流向异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R016', '夜间购药', '药品代购', '药品下单',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '低', 20, '标记', 1, 30,
 '凌晨 0-6 点下单购药, 低风险标记');

-- ============================
-- 场景五: 账户风险 (4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R006', '新患者高额结算', '账户风险', '医保结算',
 '{"and": [{"field": "user_total_visits", "op": "<=", "value": 2}, {"field": "order_total_amount", "op": ">=", "value": 10000}]}',
 '高', 75, '人工审核', 1, 88,
 '历史挂号 ≤2 次但单笔结算 ≥1 万, 新账户大额结算风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R007', '高频就诊(30天)', '账户风险', '通用',
 '{"field": "user_visits_30d", "op": ">=", "value": 15}',
 '中', 45, '标记', 1, 60,
 '近 30 天挂号 ≥15 次, 就诊频率异常 (可能出借医保卡)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R017', '多医院就诊患者', '账户风险', '通用',
 '{"field": "user_hospital_count", "op": ">=", "value": 6}',
 '中', 40, '标记', 1, 50,
 '就诊 ≥6 家不同医院, 关注医保卡出借/代开药可能');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R019', '结算金额远超均值', '账户风险', '医保结算',
 '{"and": [{"field": "order_total_amount", "op": ">=", "value": 8000}, {"field": "user_claim_count", "op": ">=", "value": 3}]}',
 '高', 60, '人工审核', 1, 72,
 '本次结算 ≥8000 且历史已有 ≥3 次结算, 费用水平异常');

-- ============================
-- 场景六: 机构风险 (3条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R020', '首次就诊即大额结算', '机构风险', '医保结算',
 '{"and": [{"field": "addr_is_new", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 15000}]}',
 '高', 65, '人工审核', 1, 78,
 '患者首次在该医院就诊即产生 ≥1.5 万结算, 疑似机构诱导住院套保');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R021', '异地就医结算', '机构风险', '医保结算',
 '{"field": "addr_cross_region", "op": "==", "value": 1}',
 '低', 15, '通过', 1, 20,
 '参保地 ≠ 就医地的普通结算, 低风险留痕');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R022', '高频就诊医院集中', '机构风险', '通用',
 '{"and": [{"field": "user_visits_30d", "op": ">=", "value": 10}, {"field": "user_hospital_count", "op": "<=", "value": 1}]}',
 '中', 40, '标记', 1, 55,
 '近 30 天 ≥10 次就诊且集中在同 1 家医院, 疑似机构拉客刷医保');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R023', '深夜挂号', '挂号黄牛', '挂号',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '低', 15, '标记', 1, 25,
 '凌晨 0-6 点挂号, 低风险留痕');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R024', '累计处方过多', '处方违规', '通用',
 '{"field": "user_rx_count", "op": ">=", "value": 10}',
 '中', 35, '标记', 1, 45,
 '患者累计处方 ≥10 张, 关注分解处方/重复开药');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R026', '高频大额结算', '医保欺诈', '医保结算',
 '{"and": [{"field": "user_claim_30d_count", "op": ">=", "value": 5}, {"field": "user_claim_30d_amount", "op": ">=", "value": 30000}]}',
 '高', 70, '人工审核', 1, 82,
 '近 30 天 ≥5 次结算且累计 ≥3 万, 疑似套取医保基金');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R027', '黄牛多院占号', '挂号黄牛', '挂号',
 '{"and": [{"field": "user_cancel_count", "op": ">=", "value": 8}, {"field": "user_hospital_count", "op": ">=", "value": 3}]}',
 '高', 65, '人工审核', 1, 76,
 '取消挂号 ≥8 次且涉及 ≥3 家医院, 多院占号转卖嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R028', '代购他人收件+批量', '药品代购', '药品下单',
 '{"and": [{"field": "order_receiver_not_self", "op": "==", "value": 1}, {"field": "order_drug_quantity", "op": ">=", "value": 10}]}',
 '高', 60, '人工审核', 1, 74,
 '收件人 ≠ 患者本人且单笔 ≥10 件, 代购批量采购嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('R029', '新患者异地结算', '机构风险', '医保结算',
 '{"and": [{"field": "addr_cross_region", "op": "==", "value": 1}, {"field": "user_total_visits", "op": "<=", "value": 2}]}',
 '中', 45, '标记', 1, 58,
 '新患者 (挂号≤2次) 首次就诊即异地结算, 关注虚假参保就医');

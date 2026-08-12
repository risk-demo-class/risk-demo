-- ============================================
-- 二手交易平台物流侧风控系统 - 预置规则数据初始化
-- 30 条规则覆盖 10 大物流风险场景 (L001-L030)
-- 三段式模型: 链路 A (卖家→验货中心) / 链路 B (验货中心→买家) / 链路 C (退货逆向)
-- ============================================================
-- L001-L004  空包/虚假发货 (链路 A)        (4 条)
-- L005-L008  物流调包 (链路 A→B)          (4 条)
-- L009-L012  验货质检舞弊 (验货中心)       (4 条)
-- L013-L016  退回假货/调包退货 (链路 C)    (4 条)
-- L017-L019  恶意退货/拒收 (链路 B↔C)     (3 条)
-- L020-L022  轨迹造假 (链路 A/B)          (3 条)
-- L023-L025  签收纠纷 (链路 B)            (3 条)
-- L026-L027  刷单/刷信誉 (链路 A)         (2 条)
-- L028-L029  寄件信息异常 (链路 A)        (2 条)
-- L030       费用争议 (全链路)             (1 条)
-- ============================================================

-- 注意: 目标数据库由 init_db.py 的 --db 参数连接指定, 这里无需 (也不能) 写 USE,
-- 否则会硬切回固定库名, 换环境必挂; aiomysql 走 prepared 协议也不支持 PREPARE 切库.
SET FOREIGN_KEY_CHECKS = 0;

-- 清空已有规则 (方便重复执行, 包括关联表 risk_action_log 的历史记录)
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;

-- 恢复外键约束
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 空包/虚假发货 (链路 A, 4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L001', '包裹重量异常轻', '空包虚假发货', '揽收入仓',
 '{"field": "cargo_weight", "op": "<=", "value": 0.1}',
 '高', 80, '人工审核', 1, 90,
 '揽收重量≤0.1kg，疑似空包，需开箱核查');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L002', '轻包裹高声明价值', '空包虚假发货', '揽收入仓',
 '{"and": [{"field": "cargo_weight", "op": "<=", "value": 0.2}, {"field": "declared_value", "op": ">=", "value": 2000}]}',
 '高', 85, '人工审核', 1, 92,
 '包裹≤0.2kg但声明价值≥2000元，空包+虚报价值嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L003', '卖家历史空包率高', '空包虚假发货', '揽收入仓',
 '{"field": "shipper_empty_pkg_rate", "op": ">=", "value": 0.2}',
 '极高', 92, '拒绝', 1, 98,
 '卖家历史空包率≥20%，空包欺诈一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L004', '高价值品类包裹重量偏离', '空包虚假发货', '揽收入仓',
 '{"and": [{"field": "cargo_category", "op": "in", "value": ["手机", "电脑", "相机"]}, {"field": "cargo_weight", "op": "<", "value": 0.15}]}',
 '高', 75, '人工审核', 1, 85,
 '手机/电脑/相机等品类包裹<0.15kg，重量与标称严重不符');

-- ============================
-- 场景二: 物流调包 (链路 A→B, 4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L005', '入出仓重量差过大', '物流调包', '出仓发货',
 '{"field": "inspection_weight_diff", "op": ">=", "value": 0.3}',
 '极高', 95, '拒绝', 1, 100,
 '出仓称重与入仓称重偏差≥0.3kg，疑似运输途中调包，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L006', '出仓序列号与入仓不一致', '物流调包', '出仓发货',
 '{"field": "imei_match_status", "op": "==", "value": 0}',
 '极高', 98, '拒绝', 1, 100,
 '出仓序列号与入仓登记序列号不一致，确认调包，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L007', '高溢价品类无封条出仓', '物流调包', '出仓发货',
 '{"and": [{"field": "cargo_category", "op": "in", "value": ["手机", "电脑", "相机", "奢侈品"]}, {"field": "has_seal", "op": "==", "value": 0}]}',
 '高', 70, '人工审核', 1, 80,
 '高溢价品类出仓未绑定封条/防拆贴，调包风险高');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L008', '运输轨迹节点称重异常', '物流调包', '运输中',
 '{"and": [{"field": "track_weight_deviation", "op": ">=", "value": 0.3}, {"field": "cargo_category", "op": "in", "value": ["手机", "电脑", "相机"]}]}',
 '高', 78, '人工审核', 1, 82,
 '运输途中节点称重与出仓重量偏差≥0.3kg且为高溢价品类，途中调包预警');

-- ============================
-- 场景三: 验货质检舞弊 (验货中心, 4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L009', '验货成色与卖家声明不符', '验货质检', '验货完成',
 '{"field": "grade_diff", "op": ">=", "value": 2}',
 '高', 68, '人工审核', 1, 78,
 '验货成色较卖家声明下调≥2级 (优→差)，卖家虚报成色');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L010', '验货功能检测异常', '验货质检', '验货完成',
 '{"field": "functional_result", "op": "==", "value": "异常"}',
 '高', 72, '人工审核', 1, 80,
 '验货功能检测异常，疑似故障机/翻新机');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L011', '验货耗时异常短', '验货质检', '验货完成',
 '{"field": "inspect_duration_min", "op": "<=", "value": 3}',
 '中', 45, '标记', 1, 55,
 '验货耗时≤3分钟，可能未真实检测 (虚假验货)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L012', '验货员历史成色差异率高', '验货质检', '验货完成',
 '{"field": "inspector_grade_diff_rate", "op": ">=", "value": 0.3}',
 '高', 65, '人工审核', 1, 72,
 '验货员出具优品但买家反馈非优品的比例≥30%，疑似验货舞弊');

-- ============================
-- 场景四: 退回假货/调包退货 (链路 C, 4条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L013', '退货重量与出仓重量差过大', '退回假货', '退货入仓验货',
 '{"field": "return_weight_diff", "op": ">=", "value": 0.3}',
 '极高', 95, '拒绝', 1, 100,
 '退货入仓重量与出仓重量偏差≥0.3kg，疑似退回假货/调包，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L014', '退货序列号与出仓不一致', '退回假货', '退货入仓验货',
 '{"field": "return_imei_match", "op": "==", "value": 0}',
 '极高', 98, '拒绝', 1, 100,
 '退货序列号与出仓序列号不一致，确认退回假货/自留真品，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L015', '退货成色较出仓降级', '退回假货', '退货入仓验货',
 '{"field": "return_grade_drop", "op": ">=", "value": 1}',
 '高', 70, '人工审核', 1, 80,
 '退货成色较出仓时降级≥1级，退回物品与寄出不一致');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L016', '高溢价品类退货集中', '退回假货', '退货入仓验货',
 '{"field": "buyer_high_value_return_rate", "op": ">=", "value": 0.5}',
 '高', 66, '人工审核', 1, 74,
 '买家退货集中高溢价品类 (手机/相机/奢侈品) 且占比≥50%，调包退回嫌疑');

-- ============================
-- 场景五: 恶意退货/拒收 (链路 B↔C, 3条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L017', '买家退货率过高', '恶意退货', '买家退回寄件',
 '{"field": "buyer_return_rate", "op": ">=", "value": 0.8}',
 '极高', 90, '拒绝', 1, 95,
 '买家历史退货率≥80%，恶意退货一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L018', '秒退 (签收后立即退货)', '恶意退货', '买家退回寄件',
 '{"field": "return_interval_hours", "op": "<", "value": 2}',
 '高', 62, '人工审核', 1, 70,
 '签收后2小时内发起退货，疑似预谋退货/未验货直接退回');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L019', '超长周期退货', '恶意退货', '买家退回寄件',
 '{"field": "return_interval_days", "op": ">", "value": 7}',
 '中', 45, '标记', 1, 50,
 '签收超过7天发起退货，疑似用完即退');

-- ============================
-- 场景六: 轨迹造假 (链路 A/B, 3条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L020', '轨迹事件缺失', '轨迹造假', '运输中',
 '{"field": "track_completeness", "op": "<", "value": 0.5}',
 '高', 68, '人工审核', 1, 75,
 '实际轨迹节点数/标准轨迹节点数<50%，轨迹不完整疑似造假');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L021', '揽收后无后续轨迹', '轨迹造假', '运输中',
 '{"and": [{"field": "track_completeness", "op": "==", "value": 0}, {"field": "segment", "op": "in", "value": [1, 2]}]}',
 '高', 74, '人工审核', 1, 80,
 '仅揽收无后续轨迹，疑似虚假发货/刷单轨迹');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L022', '轨迹节点时间异常', '轨迹造假', '运输中',
 '{"field": "track_time_anomaly", "op": "==", "value": 1}',
 '中', 48, '标记', 1, 55,
 '轨迹节点时间顺序/间隔异常，疑似伪造轨迹时间戳');

-- ============================
-- 场景七: 签收纠纷 (链路 B, 3条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L023', '高价值品类超时未签收', '签收风险', '派送中',
 '{"and": [{"field": "cargo_category", "op": "in", "value": ["手机", "电脑", "相机"]}, {"field": "deliver_delay_hours", "op": ">=", "value": 72}]}',
 '中', 42, '标记', 1, 50,
 '高溢价品类派送超72小时未签收，异常滞留');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L024', '买家秒签高价值包裹', '签收风险', '买家签收',
 '{"and": [{"field": "cargo_category", "op": "in", "value": ["手机", "电脑", "相机"]}, {"field": "sign_delay_minutes", "op": "<", "value": 5}]}',
 '高', 60, '人工审核', 1, 68,
 '高溢价品类签收后5分钟内确认收货，未验货直接签收嫌疑');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L025', '买家地址纠纷率高', '签收风险', '买家签收',
 '{"field": "buyer_addr_dispute_rate", "op": ">=", "value": 0.3}',
 '中', 44, '标记', 1, 52,
 '买家地址历史纠纷率高≥30%，地址风险标记');

-- ============================
-- 场景八: 刷单/刷信誉 (链路 A, 2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L026', '卖家高频寄件', '刷单刷信誉', '卖家下单寄件',
 '{"field": "shipper_waybills_7d", "op": ">=", "value": 10}',
 '高', 72, '人工审核', 1, 80,
 '卖家7天内寄件≥10次，疑似刷单');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L027', '卖家深夜高频寄件', '刷单刷信誉', '卖家下单寄件',
 '{"and": [{"field": "is_night_order", "op": "==", "value": 1}, {"field": "shipper_waybills_7d", "op": ">=", "value": 5}]}',
 '中', 46, '标记', 1, 55,
 '深夜寄件且7天≥5单，夜间批量寄件异常');

-- ============================
-- 场景九: 寄件信息异常 (链路 A, 2条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L028', '卖家序列号重复', '寄件信息异常', '卖家下单寄件',
 '{"field": "shipper_imei_dup_count", "op": ">=", "value": 2}',
 '高', 70, '人工审核', 1, 78,
 '同一序列号出现在该卖家多个运单中，一物多卖/刷单');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L029', '卖家实名异常', '寄件信息异常', '卖家下单寄件',
 '{"field": "shipper_is_verified", "op": "==", "value": 0}',
 '中', 40, '标记', 1, 45,
 '卖家未完成实名认证即寄件，实名合规风险');

-- ============================
-- 场景十: 费用争议 (全链路, 1条)
-- ============================

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L030', '保价金额异常高', '费用争议', '出仓发货',
 '{"field": "insurance_amount", "op": ">=", "value": 10000}',
 '中', 38, '标记', 1, 45,
 '保价金额≥10000元，高额保价需核对价值真实性');

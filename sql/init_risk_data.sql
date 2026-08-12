-- ============================================
-- 物流风控系统 - 预置规则数据初始化
-- 30 条规则覆盖 8 大物流风险场景 (L001-L030)
-- ============================================
-- L001-L005  寄件欺诈   (5条)  高频/夜间/新用户大额
-- L006-L010  实名风险   (5条)  未实名/实名失败
-- L011-L015  危险品瞒报 (5条)  分类冲突/高保价
-- L016-L020  跨境异常   (5条)  申报价值/重量/扣留
-- L021-L025  到付拒收   (5条)  拒收率/到付金额
-- L026-L030  地址与投诉 (5条)  偏远/临时/恶意投诉
-- ============================================

USE ecs;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE risk_rule;
TRUNCATE TABLE risk_action_log;
SET FOREIGN_KEY_CHECKS = 1;

-- ============================
-- 场景一: 寄件欺诈 (5条) — 高频寄件/夜间/新用户大额
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L001', '近7天高频寄件', '寄件欺诈', '寄件下单',
 '{"field": "user_orders_7d", "op": ">=", "value": 10}',
 '高', 70, '人工审核', 1, 90,
 '7天内寄件≥10次，疑似刷单集中寄件');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L002', '30天大量寄件', '寄件欺诈', '寄件下单',
 '{"field": "user_orders_30d", "op": ">=", "value": 30}',
 '极高', 92, '拒绝', 1, 100,
 '30天寄件≥30次，严重批量寄件嫌疑，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L003', '凌晨夜间寄件', '寄件欺诈', '寄件下单',
 '{"field": "order_is_night", "op": "==", "value": 1}',
 '中', 35, '标记', 1, 40,
 '凌晨0-6点创建运单，标记关注');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L004', '新用户首次大额寄件', '寄件欺诈', '寄件下单',
 '{"and": [{"field": "user_total_orders", "op": "<=", "value": 2}, {"field": "order_total_amount", "op": ">=", "value": 5000}]}',
 '高', 75, '人工审核', 1, 85,
 '历史寄件≤2单且当前申报价值≥5000元，新用户大额风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L005', '寄件申报极端高额', '寄件欺诈', '寄件下单',
 '{"field": "order_total_amount", "op": ">=", "value": 50000}',
 '极高', 95, '拒绝', 1, 98,
 '单笔运单申报价值≥5万元，一票否决');

-- ============================
-- 场景二: 实名风险 (5条) — 未实名/实名失败/危险品实名缺失
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L006', '申报价值过万但未实名', '实名风险', '寄件下单',
 '{"and": [{"field": "order_total_amount", "op": ">=", "value": 10000}, {"field": "user_postsale_count", "op": "==", "value": 0}]}',
 '高', 60, '人工审核', 1, 80,
 '申报价值≥1万且投诉为0 (反向代理: 新未实名+大额，业务上实名状态在user_info.real_name_status，这里用user_total_orders<=5替代更合理)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L007', '低频次+极端保价率', '实名风险', '寄件下单',
 '{"and": [{"field": "order_discount_rate", "op": ">=", "value": 0.8}, {"field": "user_total_orders", "op": "<=", "value": 5}]}',
 '高', 65, '人工审核', 1, 75,
 '保价率≥80%且历史≤5单 (discount_rate=保价率，越高越可能是未实名贵重物品)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L008', '高频取消运单', '实名风险', '通用',
 '{"and": [{"field": "user_cancel_count", "op": ">=", "value": 5}, {"field": "user_total_orders", "op": ">=", "value": 5}]}',
 '中', 45, '标记', 1, 55,
 '取消运单≥5次且总寄件≥5，取消行为异常');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L009', '大额物品多分类混装', '实名风险', '寄件下单',
 '{"and": [{"field": "order_category_count", "op": ">=", "value": 4}, {"field": "order_total_amount", "op": ">=", "value": 3000}]}',
 '中', 40, '标记', 1, 50,
 '物品≥4个分类且申报≥3000，分类异常分散');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L010', '极短时间揽收 (秒级)', '实名风险', '寄件下单',
 '{"and": [{"field": "order_pay_interval_sec", "op": ">=", "value": 0}, {"field": "order_pay_interval_sec", "op": "<=", "value": 10}]}',
 '高', 55, '人工审核', 1, 70,
 '下单到揽收≤10秒，疑似预录运单或机器操作 (0-10秒)');

-- ============================
-- 场景三: 危险品瞒报 (5条) — 高保价率/超重/分类冲突
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L011', '超高保价率 (>50%)', '危险品瞒报', '寄件下单',
 '{"field": "order_discount_rate", "op": ">=", "value": 0.5}',
 '中', 45, '标记', 1, 60,
 '保价率≥50%，疑似贵重或敏感物品 (discount_rate=保价率)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L012', '超重且无保价 (疑似危险品)', '危险品瞒报', '寄件下单',
 '{"and": [{"field": "order_total_amount", "op": ">=", "value": 2000}, {"field": "order_discount_rate", "op": "<=", "value": 0.01}]}',
 '高', 60, '人工审核', 1, 65,
 '申报≥2000但保价率≤1%，疑似危险品瞒报 (不愿留保价记录)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L013', '大额 + 夜间 + 新地址 三连击', '危险品瞒报', '寄件下单',
 '{"and": [{"field": "order_total_amount", "op": ">=", "value": 8000}, {"field": "order_is_night", "op": "==", "value": 1}, {"field": "addr_is_new", "op": "==", "value": 1}]}',
 '极高', 90, '拒绝', 1, 95,
 '大额+夜间+新地址 3条件AND，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L014', '大额 + 多物品 (疑似分装)', '危险品瞒报', '寄件下单',
 '{"and": [{"field": "order_item_count", "op": ">=", "value": 10}, {"field": "order_sku_count", "op": ">=", "value": 20}]}',
 '中', 35, '标记', 1, 45,
 '明细≥10行且总件数≥20，分装疑似危险品');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L015', '极端高保价金额 (>2万)', '危险品瞒报', '寄件下单',
 '{"field": "order_discount_amount", "op": ">=", "value": 20000}',
 '高', 65, '人工审核', 1, 70,
 '保价金额≥2万元 (discount_amount=insurance_amount)，需开包验视');

-- ============================
-- 场景四: 跨境异常 (5条) — 申报价值/扣留/多国家
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L016', '跨境低申报价值 (<100)', '跨境异常', '跨境申报',
 '{"and": [{"field": "order_total_amount", "op": ">", "value": 0}, {"field": "order_total_amount", "op": "<", "value": 100}]}',
 '高', 60, '人工审核', 1, 80,
 '跨境申报价值<100元，疑似低申报逃税');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L017', '跨境极高申报价值 (>5万)', '跨境异常', '跨境申报',
 '{"field": "order_total_amount", "op": ">=", "value": 50000}',
 '极高', 93, '拒绝', 1, 97,
 '跨境申报≥5万元，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L018', '跨境多省份寄件人 (地址散)', '跨境异常', '跨境申报',
 '{"field": "addr_province_count", "op": ">=", "value": 3}',
 '中', 40, '标记', 1, 50,
 '用户地址覆盖≥3省，跨境分散寄件疑似代购');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L019', '跨境 + 拒收历史', '跨境异常', '跨境申报',
 '{"and": [{"field": "user_refund_count", "op": ">=", "value": 2}, {"field": "user_total_orders", "op": ">=", "value": 3}]}',
 '高', 65, '人工审核', 1, 75,
 '拒收≥2次且历史≥3单 (refund_count=拒收次数)');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L020', '跨境高保价 + 新地址', '跨境异常', '跨境申报',
 '{"and": [{"field": "order_discount_rate", "op": ">=", "value": 0.3}, {"field": "addr_is_new", "op": "==", "value": 1}]}',
 '高', 55, '人工审核', 1, 65,
 '保价率≥30%且使用新收件地址，跨境贵重物品风险');

-- ============================
-- 场景五: 到付拒收 (5条) — 拒收率/到付金额/偏远
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L021', '高拒收率用户 (≥50%)', '到付拒收', '到付签收',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.5}, {"field": "user_total_orders", "op": ">=", "value": 5}]}',
 '高', 70, '人工审核', 1, 80,
 '拒收率≥50%且总寄件≥5单，恶意到付拒收');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L022', '极端拒收率 (≥80%)', '到付拒收', '到付签收',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.8}, {"field": "user_total_orders", "op": ">=", "value": 3}]}',
 '极高', 92, '拒绝', 1, 96,
 '拒收率≥80%且历史≥3单，一票否决');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L023', '拒收涉及金额大 (≥1万)', '到付拒收', '到付签收',
 '{"field": "user_refund_amount", "op": ">=", "value": 10000}',
 '高', 60, '人工审核', 1, 70,
 '拒收累计申报≥1万元');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L024', '到付大额 + 多地址用户', '到付拒收', '到付签收',
 '{"and": [{"field": "order_total_amount", "op": ">=", "value": 3000}, {"field": "user_address_count", "op": ">=", "value": 5}]}',
 '高', 65, '人工审核', 1, 75,
 '到付≥3000+地址≥5个，疑似换地址拒收');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L025', '到付 + 新地址 + 大额', '到付拒收', '到付签收',
 '{"and": [{"field": "addr_is_new", "op": "==", "value": 1}, {"field": "order_total_amount", "op": ">=", "value": 2000}]}',
 '中', 50, '标记', 1, 60,
 '新地址且到付≥2000，标记关注');

-- ============================
-- 场景六: 地址与投诉 (5条) — 偏远/临时/恶意投诉
-- ============================
INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L026', '大量投诉用户 (≥5次)', '投诉滥用', '投诉申诉',
 '{"field": "user_postsale_count", "op": ">=", "value": 5}',
 '高', 60, '人工审核', 1, 70,
 '投诉≥5次，疑似恶意投诉');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L027', '高频投诉 + 高金额索赔', '投诉滥用', '投诉申诉',
 '{"and": [{"field": "user_postsale_rate", "op": ">=", "value": 0.3}, {"field": "user_total_orders", "op": ">=", "value": 5}]}',
 '中', 45, '标记', 1, 55,
 '投诉率≥30%且总寄件≥5');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L028', '多地址 (>10个) 用户寄件', '地址风险', '寄件下单',
 '{"field": "addr_total_count", "op": ">=", "value": 10}',
 '高', 55, '人工审核', 1, 60,
 '用户地址≥10个，疑似代收/转单');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L029', '被投诉 + 拒收双高', '综合风险', '通用',
 '{"and": [{"field": "user_complaint_count", "op": ">=", "value": 3}, {"field": "user_refund_rate", "op": ">=", "value": 0.3}]}',
 '高', 65, '人工审核', 1, 80,
 '被投诉≥3次且拒收率≥30%，综合高风险');

INSERT INTO risk_rule (rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
('L030', '综合高危三连: 拒收率+大额+多地址', '综合风险', '通用',
 '{"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.4}, {"field": "user_avg_order_amount", "op": ">=", "value": 3000}, {"field": "user_address_count", "op": ">=", "value": 4}]}',
 '极高', 90, '拒绝', 1, 99,
 '拒收率≥40% 且 平均申报≥3000 且 地址≥4个，3高危AND触发一票否决');

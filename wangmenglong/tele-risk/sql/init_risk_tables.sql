-- =============================================================================
-- 电信风控系统 - 风控规则表 DDL + 12 条预置规则
-- 位置: tele-risk/sql/init_risk_tables.sql
-- 数据库: telecom (与业务表同库)
--
-- 规则覆盖 6 类欺诈 + 监管要求 (反诈法第9/10/12/16条):
--   通话欺诈(4): R001 GOIP短时高频 / R002 GOIP固定点位 / R008 新卡高频 / R012 短通话异常
--   设备欺诈(3): R003 猫池一机多卡 / R009 机卡异地+高频 / R011 频繁换机
--   账户风险(2): R004 一证多卡超限 / R010 活体核验未通过
--   国际来电(1): R005 国际诈骗来电高频 (反诈法第16条)
--   物联网(1):   R006 物联网流量突增 (反诈法第12条)
--   渠道异常(1): R007 渠道批量开卡 (反诈法第9条)
--
-- 极高(85-100) = 一票否决 → 关停号码
-- 高(60-84)    → 人工审核
-- 中(30-59)    → 标记
-- =============================================================================

USE `telecom`;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS telecom_risk_rule;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE telecom_risk_rule (
    rule_id        VARCHAR(20)  NOT NULL COMMENT '规则ID (R+3位)',
    rule_name      VARCHAR(80)  NOT NULL COMMENT '规则名称',
    rule_category  VARCHAR(30)  NOT NULL COMMENT '规则类别',
    event_type     VARCHAR(20)  NOT NULL DEFAULT '通用' COMMENT '事件类型 (开户/通话/国际来电/短信发送/物联网激活/通用)',
    rule_condition TEXT         NOT NULL COMMENT '条件 JSON',
    risk_level     VARCHAR(10)  NOT NULL COMMENT '风险等级 (低/中/高/极高)',
    risk_score     INT          NOT NULL COMMENT '风险分 (0-100)',
    action         VARCHAR(20)  NOT NULL COMMENT '处置动作 (通过/标记/人工审核/拒绝/关停号码/推送公安)',
    is_enabled     INT          NOT NULL DEFAULT 1 COMMENT '是否启用 (0/1)',
    priority       INT          NOT NULL DEFAULT 50 COMMENT '优先级 (高先匹配)',
    description    VARCHAR(200) DEFAULT NULL COMMENT '描述',
    create_time    DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deleted_at     DATETIME     DEFAULT NULL COMMENT '软删时间 (NULL=未删)',
    PRIMARY KEY (rule_id),
    KEY idx_rule_event (event_type, is_enabled),
    KEY idx_rule_priority (priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='电信风控规则表';

-- ============================================================
-- 12 条预置规则 (条件 JSON 用 feature.py 的 25 维特征字段)
-- ============================================================
INSERT INTO telecom_risk_rule
(rule_id, rule_name, rule_category, event_type, rule_condition, risk_level, risk_score, action, is_enabled, priority, description) VALUES
-- R001 GOIP 短时高频主叫: 1 小时内主叫 >= 20 次
('R001', 'GOIP短时高频主叫', '通话欺诈', '通话',
 '{"field":"cdr_out_count_1h","op":">=","value":20}',
 '高', 70, '人工审核', 1, 80, '反诈法第13条: 1小时内主叫超20次, GOIP虚拟拨号嫌疑'),

-- R002 GOIP 固定点位通信: 1h 主叫>=10 且只用 1 个基站 (设备位置固定)
('R002', 'GOIP固定点位通信', '通话欺诈', '通话',
 '{"and":[{"field":"cdr_distinct_cell_1h","op":"==","value":1},{"field":"cdr_out_count_1h","op":">=","value":10}]}',
 '极高', 95, '关停号码', 1, 100, '反诈法第13条: 固定点位高频通信, GOIP设备一票否决'),

-- R003 猫池一机多卡: 同一 IMEI 绑定 >= 5 张卡
('R003', '猫池一机多卡', '设备欺诈', '通话',
 '{"field":"dev_cards_on_imei","op":">=","value":5}',
 '极高', 95, '关停号码', 1, 100, '反诈法第13条: 一机多卡, 猫池养卡一票否决'),

-- R004 一证多卡超限: 同一客户名下 >= 5 张卡
('R004', '一证多卡超限', '账户风险', '开户',
 '{"field":"cust_card_count","op":">=","value":5}',
 '高', 70, '人工审核', 1, 85, '反诈法第10条: 开卡数量核验, 一证多卡'),

-- R005 国际诈骗来电高频: 24h 国际来电 >= 10 次
('R005', '国际诈骗来电高频', '国际来电', '国际来电',
 '{"field":"cdr_intl_incoming_24h","op":">=","value":10}',
 '极高', 90, '关停号码', 1, 95, '反诈法第16条: 国际来电路由高频, 诈骗一票否决'),

-- R006 物联网流量突增: 当天流量 / 历史均值 >= 10 倍
('R006', '物联网流量突增', '物联网滥用', '物联网激活',
 '{"field":"iot_data_burst_ratio","op":">=","value":10}',
 '高', 65, '人工审核', 1, 75, '反诈法第12条: 物联网卡风险评估, 流量异常突增'),

-- R007 渠道批量开卡: 渠道 1h 新开户 >= 8
('R007', '渠道批量开卡', '渠道异常', '开户',
 '{"field":"channel_open_count_1h","op":">=","value":8}',
 '高', 70, '人工审核', 1, 80, '反诈法第9条: 代理商管理, 渠道批量开卡异常'),

-- R008 新卡高频主叫: 开卡 <= 7 天 且 24h 主叫 >= 50
('R008', '新卡高频主叫', '通话欺诈', '通话',
 '{"and":[{"field":"card_age_days","op":"<=","value":7},{"field":"cdr_out_count_24h","op":">=","value":50}]}',
 '高', 65, '人工审核', 1, 75, '新卡短时间高频主叫, 养卡外呼嫌疑'),

-- R009 机卡异地+高频: 机卡异地 且 1h 主叫 >= 10
('R009', '机卡异地高频', '设备欺诈', '通话',
 '{"and":[{"field":"dev_card_imei_mismatch_flag","op":"==","value":1},{"field":"cdr_out_count_1h","op":">=","value":10}]}',
 '高', 60, '人工审核', 1, 70, '机卡位置分离 + 高频, GOIP/猫池辅助信号'),

-- R010 活体核验未通过: 实名核验失败
('R010', '活体核验未通过', '账户风险', '开户',
 '{"field":"cust_face_verify_passed","op":"==","value":0}',
 '中', 45, '标记', 1, 60, '反诈法第9条: 实名制, 活体核验未通过标记观察'),

-- R011 频繁换机: 30 天换机 >= 3 次
('R011', '频繁换机', '设备欺诈', '通话',
 '{"field":"dev_binding_changes_30d","op":">=","value":3}',
 '中', 40, '标记', 1, 55, '频繁更换设备, 号卡流转嫌疑'),

-- R012 短通话占比异常: 短通话占比 >= 0.8 且 24h 主叫 >= 30 (诈骗引流通常短通话)
('R012', '短通话占比异常', '通话欺诈', '通话',
 '{"and":[{"field":"cdr_short_call_ratio","op":">=","value":0.8},{"field":"cdr_out_count_24h","op":">=","value":30}]}',
 '高', 60, '人工审核', 1, 70, '高频短通话, 诈骗引流/吸费嫌疑'),

-- R013 话费套现: 1h 内充值 >= 3 次 且 转出金额占比 >= 50%
('R013', '话费套现高频转出', '资金风险', '账单',
 '{"and":[{"field":"bill_recharge_count_1h","op":">=","value":3},{"field":"bill_outflow_ratio","op":">=","value":0.5}]}',
 '极高', 90, '关停号码', 1, 90, '反诈法第14条: 高频充值+即时转出, 话费套现一票否决'),

-- R014 集团子号异常: 集团子号数 >= 8 且子号有高频外呼行为
('R014', '集团子号异常', '账户风险', '开户',
 '{"and":[{"field":"grp_sub_count","op":">=","value":8},{"field":"cdr_out_count_24h","op":">=","value":30}]}',
 '高', 65, '人工审核', 1, 75, '集团批量办卡+高频外呼, 疑似诈骗团伙'),

-- R015 凌晨密集呼叫: 凌晨(0-6点)1h 内主叫 >= 15 次
('R015', '凌晨密集呼叫', '通话欺诈', '通话',
 '{"field":"cdr_night_call_count","op":">=","value":15}',
 '高', 60, '人工审核', 1, 70, '凌晨时段密集呼叫, 疑似GOIP/诈骗引流');

-- 校验
SELECT rule_id, rule_name, rule_category, event_type, risk_level, risk_score, action, priority
FROM telecom_risk_rule
ORDER BY priority DESC, rule_id;

-- ============================================================
-- 系统管理表 (风控核心 9 张表补齐)
-- ============================================================

-- 8. 操作审计日志表
-- 任何规则/案件/黑名单的变更都写一行, 出事能追责
DROP TABLE IF EXISTS telecom_risk_action_log;

CREATE TABLE telecom_risk_action_log (
    log_id         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    operator       VARCHAR(50)  NOT NULL COMMENT '操作人(admin/system/ai_agent)',
    action_type    ENUM('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST','AUTO_HALT_CARD') NOT NULL COMMENT '操作类型',
    target_type    ENUM('rule','case','blacklist','assessment') NOT NULL COMMENT '对象类型',
    target_id      VARCHAR(50)  NOT NULL COMMENT '对象ID',
    before_value   JSON         COMMENT '变更前 (NULL=新增)',
    after_value    JSON         COMMENT '变更后 (NULL=删除)',
    ip             VARCHAR(50)  COMMENT '操作IP',
    remark         VARCHAR(500) COMMENT '备注',
    create_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (log_id),
    KEY idx_action_log_operator (operator),
    KEY idx_action_log_target (target_type, target_id),
    KEY idx_action_log_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='电信风控操作审计日志表';

-- 9. 告警记录表
-- 风控系统自己发现异常的记录 (规则命中率突降/案件积压/撞黑失败率过高等)
DROP TABLE IF EXISTS telecom_risk_alert;

CREATE TABLE telecom_risk_alert (
    alert_id       BIGINT       NOT NULL AUTO_INCREMENT COMMENT '告警ID',
    alert_type     ENUM('BUSINESS','MODEL','SYSTEM','SECURITY') NOT NULL COMMENT '告警分类',
    alert_level    ENUM('P0','P1','P2','P3') NOT NULL COMMENT '告警等级 (P0=致命, P3=提示)',
    alert_title    VARCHAR(200) NOT NULL COMMENT '告警标题',
    alert_content  TEXT         COMMENT '告警详情',
    metric_name    VARCHAR(100) COMMENT '指标名(规则命中率/案件积压数等)',
    metric_value   DECIMAL(20,6) COMMENT '触发值',
    threshold      DECIMAL(20,6) COMMENT '阈值',
    status         ENUM('PENDING','HANDLING','RESOLVED','IGNORED') DEFAULT 'PENDING' COMMENT '处理状态',
    handler        VARCHAR(50)  COMMENT '处理人',
    resolve_time   DATETIME     DEFAULT NULL COMMENT '解决时间',
    create_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '告警时间',
    PRIMARY KEY (alert_id),
    KEY idx_alert_status (status),
    KEY idx_alert_level (alert_level),
    KEY idx_alert_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='电信风控告警记录表';

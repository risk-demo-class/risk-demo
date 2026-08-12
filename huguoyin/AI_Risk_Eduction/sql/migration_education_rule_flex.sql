-- ============================================
-- 教育行业风控规则字段兼容迁移
-- 将旧电商枚举改为字符串, 支持课程报名/退费/证书核验等教育事件
-- ============================================

ALTER TABLE `risk_rule`
    MODIFY COLUMN `rule_category` VARCHAR(50) NOT NULL COMMENT '风险场景分类',
    MODIFY COLUMN `event_type` VARCHAR(30) NOT NULL DEFAULT '通用' COMMENT '适用事件类型';

ALTER TABLE `risk_event`
    MODIFY COLUMN `event_type` VARCHAR(30) NOT NULL COMMENT '事件类型';

ALTER TABLE `risk_case`
    MODIFY COLUMN `event_type` VARCHAR(30) DEFAULT NULL COMMENT '触发案件的事件类型';

-- ============================================
-- 教育风控系统 — 风险表 ENUM 迁移脚本
-- 将原有电商 ENUM 值扩展到教育领域
-- ============================================

USE ecs;

-- 1. risk_rule: 扩展 rule_category 和 event_type ENUM
ALTER TABLE `risk_rule`
    MODIFY COLUMN `rule_category` ENUM('订单欺诈','支付风险','账户风险','售后滥用','地址风险','物流风险','报名欺诈','退费滥用','身份异常','行为异常') NOT NULL COMMENT '风险场景分类',
    MODIFY COLUMN `event_type` ENUM('下单','支付','售后申请','物流投诉','报名','退费申请','打赏','通用') NOT NULL DEFAULT '通用' COMMENT '适用事件类型';

-- 2. risk_event: 扩展 event_type ENUM
ALTER TABLE `risk_event`
    MODIFY COLUMN `event_type` ENUM('下单','支付','售后申请','物流投诉','报名','退费申请','打赏') NOT NULL COMMENT '事件类型';

-- 3. risk_case: 扩展 event_type ENUM
ALTER TABLE `risk_case`
    MODIFY COLUMN `event_type` ENUM('下单','支付','售后申请','物流投诉','报名','退费申请','打赏') DEFAULT NULL COMMENT '触发案件的事件类型';

-- 4. risk_blacklist: 扩展 blacklist_type ENUM (新增学号、身份证号类型)
ALTER TABLE `risk_blacklist`
    MODIFY COLUMN `blacklist_type` ENUM('用户','地址','手机号','学号','身份证号','设备指纹') NOT NULL COMMENT '黑名单类型';

-- 5. risk_feature: 扩展 entity_type ENUM
ALTER TABLE `risk_feature`
    MODIFY COLUMN `entity_type` ENUM('用户','订单','地址','课程','设备') NOT NULL COMMENT '实体类型';

-- 6. 同步写入初始黑名单数据 (配合 R030 黑学号拦截)
INSERT IGNORE INTO `risk_blacklist` (`blacklist_type`, `blacklist_value`, `reason`, `expire_time`) VALUES
('学号', 'STU20240099', '历史欺诈账号 (来自 blacklist_extra)', NULL),
('身份证号', '330102199909090009', '虚假实名认证 (来自 blacklist_extra)', NULL);

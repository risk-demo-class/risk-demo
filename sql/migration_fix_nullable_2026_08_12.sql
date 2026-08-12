-- ============================================================
-- 银行风控项目 - 风控表可空性对齐迁移 (2026-08-12, P1-4)
-- 目的: DDL 与 ORM 可空性一致 (13 处列收紧为 NOT NULL DEFAULT)
-- 存量数据均有默认值, 迁移安全 (对应 sql/init_risk_tables.sql 已同步)
-- 执行: mysql -uroot -p123321 ecs < sql/migration_fix_nullable_2026_08_12.sql
-- ============================================================

ALTER TABLE `risk_rule` MODIFY COLUMN `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用';
ALTER TABLE `risk_rule` MODIFY COLUMN `priority` INT NOT NULL DEFAULT 0 COMMENT '优先级(越高越先执行)';
ALTER TABLE `risk_assessment` MODIFY COLUMN `rule_count` INT NOT NULL DEFAULT 0 COMMENT '命中规则数';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `risk_score` INT NOT NULL DEFAULT 0 COMMENT '综合风险评分(0-100)';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `risk_level` ENUM('低','中','高','极高') NOT NULL DEFAULT '低' COMMENT '风险等级';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `total_orders` INT NOT NULL DEFAULT 0 COMMENT '贷款申请笔数(银行语义)';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `total_refunds` INT NOT NULL DEFAULT 0 COMMENT '当前逾期期数(银行语义)';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `refund_rate` DECIMAL(5,4) NOT NULL DEFAULT 0 COMMENT '逾期风险度(银行语义, overdue/(overdue+1))';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `avg_order_amount` DECIMAL(10,2) NOT NULL DEFAULT 0 COMMENT '平均申请金额(银行语义)';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `address_count` INT NOT NULL DEFAULT 0 COMMENT '关联关系数(银行语义)';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `complaint_count` INT NOT NULL DEFAULT 0 COMMENT '征信近24月逾期次数(银行语义)';
ALTER TABLE `risk_user_profile` MODIFY COLUMN `assessment_count` INT NOT NULL DEFAULT 0 COMMENT '评估次数';
ALTER TABLE `risk_alert` MODIFY COLUMN `status` ENUM('PENDING','HANDLING','RESOLVED','IGNORED') NOT NULL DEFAULT 'PENDING' COMMENT '处理状态';

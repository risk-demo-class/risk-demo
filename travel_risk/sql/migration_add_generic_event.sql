-- ============================================
-- 迁移: 风控检查支持"通用"事件 (仅给用户ID/设备ID时使用)
-- 幂等: 重复执行无副作用 (用 INFORMATION_SCHEMA 判断)
-- ============================================

USE travel_risk;

SET @has_generic_event = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'travel_risk'
      AND TABLE_NAME = 'risk_event'
      AND COLUMN_NAME = 'event_type'
      AND COLUMN_TYPE LIKE '%通用%'
);

SET @ddl = IF(@has_generic_event = 0,
    "ALTER TABLE risk_event MODIFY COLUMN event_type ENUM('注册','下单','支付','退改申请','理赔申请','投诉','通用') NOT NULL COMMENT '事件类型'",
    "SELECT 'risk_event 已包含通用事件'"
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_generic_case = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'travel_risk'
      AND TABLE_NAME = 'risk_case'
      AND COLUMN_NAME = 'event_type'
      AND COLUMN_TYPE LIKE '%通用%'
);

SET @ddl2 = IF(@has_generic_case = 0,
    "ALTER TABLE risk_case MODIFY COLUMN event_type ENUM('注册','下单','支付','退改申请','理赔申请','投诉','通用') DEFAULT NULL COMMENT '触发案件的事件类型'",
    "SELECT 'risk_case 已包含通用事件'"
);
PREPARE stmt2 FROM @ddl2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

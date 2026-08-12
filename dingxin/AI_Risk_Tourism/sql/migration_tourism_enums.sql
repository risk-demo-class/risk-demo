-- ============================================
-- 旅游风控系统 - 风控表 ENUM 业务扩展迁移
-- 适用: 老环境 (风控 9 张表还是电商基线枚举) 升级到旅游版
-- 幂等性: ALTER TABLE ... MODIFY COLUMN ENUM(...) 重复执行无副作用
--         (枚举值集合相同则等价 no-op, MySQL 只会重写表结构)
-- 新装库无需本脚本: init_risk_tables.sql 已直接建旅游版枚举
-- ============================================

USE tourism;

-- 1. 规则类别: 追加旅游 5 类 (保留电商 6 类, 兼容旧数据)
ALTER TABLE `risk_rule`
  MODIFY COLUMN `rule_category` ENUM('订单欺诈','支付风险','账户风险','售后滥用','地址风险','物流风险',
                                     '预订欺诈','退改滥用','签证风险','设备风险','黑名单风险')
  NOT NULL COMMENT '风险场景分类';

-- 2. 规则适用事件类型: 追加 预订下单/退改申请/签证申请
ALTER TABLE `risk_rule`
  MODIFY COLUMN `event_type` ENUM('下单','支付','售后申请','物流投诉','通用',
                                  '预订下单','退改申请','签证申请')
  NOT NULL DEFAULT '通用' COMMENT '适用事件类型';

-- 3. 事件审计事件类型
ALTER TABLE `risk_event`
  MODIFY COLUMN `event_type` ENUM('下单','支付','售后申请','物流投诉',
                                  '预订下单','退改申请','签证申请')
  NOT NULL COMMENT '事件类型';

-- 4. 案件事件类型
ALTER TABLE `risk_case`
  MODIFY COLUMN `event_type` ENUM('下单','支付','售后申请','物流投诉',
                                  '预订下单','退改申请','签证申请')
  DEFAULT NULL COMMENT '触发案件的事件类型';

-- 5. 黑名单类型: 追加 护照号/签证号/设备指纹
ALTER TABLE `risk_blacklist`
  MODIFY COLUMN `blacklist_type` ENUM('用户','地址','手机号','护照号','签证号','设备指纹')
  NOT NULL COMMENT '黑名单类型';

-- =============================================================================
-- 电信风控系统 - 业务表 DDL (13 张)
-- 位置: tele-risk/sql/init_telecom_tables.sql
-- 数据库: telecom (复用 ai_risk 的 docker MySQL, 独立库)
-- 风格参照: ai_risk/sql/init_business_tables.sql (无外键约束, 逻辑关联, utf8mb4)
--
-- 设计原则 (为风控特征计算优化):
--   1. 号卡(msisdn)是核心枢纽, 所有事实表通过 msisdn/号码关联
--   2. CDR/SMS/流量等大表建 (号码, 时间) 复合索引 -> 时间窗口聚合快
--   3. customer.id_no / card.customer_id 索引 -> 一证多卡查询
--   4. card_device_binding (msisdn, imei) -> 一机多卡 / 机卡异地
--   5. service_order (channel_id, order_time) -> 渠道开卡量异常
-- =============================================================================

CREATE DATABASE IF NOT EXISTS `telecom`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE `telecom`;

-- 幂等: 重跑先 DROP (造数前清空, 生产慎用)
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS telecom_billing_record;
DROP TABLE IF EXISTS telecom_group_customer;
DROP TABLE IF EXISTS telecom_data_usage;
DROP TABLE IF EXISTS telecom_sms;
DROP TABLE IF EXISTS telecom_cdr;
DROP TABLE IF EXISTS telecom_service_order;
DROP TABLE IF EXISTS telecom_card_device_binding;
DROP TABLE IF EXISTS telecom_iot_card;
DROP TABLE IF EXISTS telecom_card;
DROP TABLE IF EXISTS telecom_plan;
DROP TABLE IF EXISTS telecom_device;
DROP TABLE IF EXISTS telecom_cell;
DROP TABLE IF EXISTS telecom_channel;
DROP TABLE IF EXISTS telecom_customer;
DROP TABLE IF EXISTS telecom_region;
SET FOREIGN_KEY_CHECKS = 1;


-- ============================================================
-- 1. 地区表 (省/市/区 标准化, 给基站/开卡地 JOIN 用)
-- ============================================================
CREATE TABLE telecom_region (
    province      VARCHAR(20)  NOT NULL COMMENT '省',
    city          VARCHAR(20)  NOT NULL COMMENT '市',
    district      VARCHAR(20)  NOT NULL COMMENT '区/县',
    PRIMARY KEY (province, city, district)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='地区表';


-- ============================================================
-- 2. 客户表 (实名信息, 1客户 N号卡)
--    风控要点: id_no 索引支撑"一证多卡"查询 (反诈法第10条)
-- ============================================================
CREATE TABLE telecom_customer (
    customer_id        VARCHAR(20)  NOT NULL COMMENT '客户ID (C+8位)',
    customer_type      ENUM('个人','企业') NOT NULL DEFAULT '个人' COMMENT '客户类型',
    id_type            ENUM('身份证','护照','营业执照') NOT NULL DEFAULT '身份证' COMMENT '证件类型',
    id_no              VARCHAR(32)  NOT NULL COMMENT '证件号 (一证多卡查询键)',
    real_name          VARCHAR(50)  NOT NULL COMMENT '实名姓名',
    gender             ENUM('男','女','未知') NOT NULL DEFAULT '未知' COMMENT '性别',
    birthday           DATE         DEFAULT NULL COMMENT '出生日期',
    face_verify_status ENUM('通过','未通过','未核验') NOT NULL DEFAULT '未核验' COMMENT '活体核验状态',
    register_time      DATETIME     NOT NULL COMMENT '注册时间',
    risk_tag           VARCHAR(20)  DEFAULT NULL COMMENT '风险标签 (正常/中风险/高风险/涉诈)',
    PRIMARY KEY (customer_id),
    UNIQUE KEY uk_id_no_type (id_no, id_type),
    KEY idx_customer_risk_tag (risk_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='客户实名信息表';


-- ============================================================
-- 3. 渠道表 (营业厅/代理商/线上, 反诈法第9条代理商管理)
--    风控要点: channel_id 支撑"渠道开卡量异常"特征
-- ============================================================
CREATE TABLE telecom_channel (
    channel_id     VARCHAR(20)  NOT NULL COMMENT '渠道ID (CH+4位)',
    channel_name   VARCHAR(80)  NOT NULL COMMENT '渠道名称',
    channel_type   ENUM('营业厅','代理商','线上自助') NOT NULL COMMENT '渠道类型',
    province       VARCHAR(20)  NOT NULL COMMENT '渠道所在省',
    agent_id       VARCHAR(20)  DEFAULT NULL COMMENT '代理商编号 (代理商类型必填)',
    status         ENUM('正常','停用','整改中') NOT NULL DEFAULT '正常' COMMENT '状态',
    open_date      DATE         NOT NULL COMMENT '开通日期',
    PRIMARY KEY (channel_id),
    KEY idx_channel_type_status (channel_type, status),
    KEY idx_channel_agent (agent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='渠道/代理商表';


-- ============================================================
-- 4. 基站表 (LAC/Cell-ID, CDR 定位用)
--    风控要点: 支撑"机卡异地""固定点位通信负荷激增"(GOIP识别)
-- ============================================================
CREATE TABLE telecom_cell (
    cell_id        VARCHAR(20)  NOT NULL COMMENT '基站标识 (CGI)',
    lac            VARCHAR(10)  NOT NULL COMMENT '位置区码',
    province       VARCHAR(20)  NOT NULL COMMENT '省',
    city           VARCHAR(20)  NOT NULL COMMENT '市',
    district       VARCHAR(20)  NOT NULL COMMENT '区/县',
    cell_type      ENUM('宏站','微站','室内分布') NOT NULL DEFAULT '宏站' COMMENT '基站类型',
    longitude      DECIMAL(10,6) DEFAULT NULL COMMENT '经度',
    latitude       DECIMAL(10,6) DEFAULT NULL COMMENT '纬度',
    PRIMARY KEY (cell_id),
    KEY idx_cell_lac (lac),
    KEY idx_cell_geo (province, city, district)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='基站表';


-- ============================================================
-- 5. 设备表 (IMEI + MAC 设备指纹)
--    风控要点: 支撑"一机多卡"(猫池识别) + MAC 维度换卡检测
-- ============================================================
CREATE TABLE telecom_device (
    imei           VARCHAR(15)  NOT NULL COMMENT '设备IMEI (15位)',
    mac_address    VARCHAR(17)  DEFAULT NULL COMMENT '设备MAC地址 (XX:XX:XX:XX:XX:XX)',
    brand          VARCHAR(30)  NOT NULL COMMENT '品牌',
    model          VARCHAR(60)  NOT NULL COMMENT '型号',
    os_type        ENUM('Android','iOS','HarmonyOS','其他') NOT NULL DEFAULT '其他' COMMENT '操作系统',
    first_seen_time DATETIME    NOT NULL COMMENT '首次出现时间',
    PRIMARY KEY (imei),
    KEY idx_device_mac (mac_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备表';


-- ============================================================
-- 6. 套餐表
-- ============================================================
CREATE TABLE telecom_plan (
    plan_id        VARCHAR(20)  NOT NULL COMMENT '套餐ID',
    plan_name      VARCHAR(60)  NOT NULL COMMENT '套餐名称',
    plan_type      ENUM('语音套餐','流量套餐','融合套餐','物联网套餐') NOT NULL COMMENT '套餐类型',
    monthly_fee    DECIMAL(8,2) NOT NULL COMMENT '月费(元)',
    data_quota_mb  INT          NOT NULL DEFAULT 0 COMMENT '流量配额(MB)',
    voice_quota_min INT         NOT NULL DEFAULT 0 COMMENT '语音配额(分钟)',
    sms_quota      INT          NOT NULL DEFAULT 0 COMMENT '短信配额(条)',
    PRIMARY KEY (plan_id),
    KEY idx_plan_type (plan_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='套餐表';


-- ============================================================
-- 7. 号卡表 (核心枢纽表, 1客户 N号卡, 1渠道 N号卡)
--    风控要点:
--      - imsi/iccid 唯一索引
--      - customer_id 索引 -> 一证多卡
--      - current_imei 索引 -> 一机多卡
--      - open_channel_id 索引 -> 渠道异常
--      - open_time / card_status 索引 -> 开卡时间窗 / 状态筛选
-- ============================================================
CREATE TABLE telecom_card (
    msisdn           VARCHAR(11)  NOT NULL COMMENT '手机号 (MSISDN, 11位)',
    imsi             VARCHAR(15)  NOT NULL COMMENT 'SIM 卡 IMSI',
    iccid            VARCHAR(20)  NOT NULL COMMENT 'SIM 序列号 ICCID',
    customer_id      VARCHAR(20)  NOT NULL COMMENT '客户ID (逻辑关联 telecom_customer)',
    current_imei     VARCHAR(15)  DEFAULT NULL COMMENT '当前绑定设备 IMEI',
    plan_id          VARCHAR(20)  NOT NULL COMMENT '套餐ID',
    open_channel_id  VARCHAR(20)  NOT NULL COMMENT '开卡渠道ID',
    open_time        DATETIME     NOT NULL COMMENT '开卡时间',
    open_province    VARCHAR(20)  NOT NULL COMMENT '开卡省',
    card_status      ENUM('正常','停机','暂停','已销户') NOT NULL DEFAULT '正常' COMMENT '号卡状态',
    roam_status      ENUM('归属地','省内漫游','省间漫游','国际漫游') NOT NULL DEFAULT '归属地' COMMENT '漫游状态',
    intl_call_enabled TINYINT(1)  NOT NULL DEFAULT 0 COMMENT '国际来去电是否开通 (0否1是)',
    is_iot           TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否物联网卡 (0否1是)',
    status_update_time DATETIME   NOT NULL COMMENT '状态更新时间',
    PRIMARY KEY (msisdn),
    UNIQUE KEY uk_imsi (imsi),
    UNIQUE KEY uk_iccid (iccid),
    KEY idx_card_customer (customer_id),
    KEY idx_card_imei (current_imei),
    KEY idx_card_channel (open_channel_id),
    KEY idx_card_open_time (open_time),
    KEY idx_card_status (card_status),
    KEY idx_card_iot (is_iot)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='号卡表 (核心)';


-- ============================================================
-- 8. 物联网卡扩展表 (1:1 对应 is_iot=1 的号卡)
--    风控要点: 机卡分离 / 场景不符 / 流量突增 (反诈法第12条)
-- ============================================================
CREATE TABLE telecom_iot_card (
    msisdn           VARCHAR(11)  NOT NULL COMMENT '号卡 (关联 telecom_card)',
    iot_scene        VARCHAR(30)  NOT NULL COMMENT '应用场景 (车联网/智能表计/POS/工业/其他)',
    bound_device_imei VARCHAR(15) DEFAULT NULL COMMENT '绑定设备 IMEI',
    device_type      VARCHAR(40)  NOT NULL COMMENT '设备类型',
    function_scope   ENUM('仅数据','仅短信','语音+数据','语音+数据+短信') NOT NULL DEFAULT '仅数据' COMMENT '限定功能',
    activate_time    DATETIME     NOT NULL COMMENT '激活时间',
    PRIMARY KEY (msisdn),
    KEY idx_iot_scene (iot_scene),
    KEY idx_iot_device (bound_device_imei)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物联网卡扩展表';


-- ============================================================
-- 9. 机卡绑定历史表 (号卡换设备的全历史)
--    风控要点: (imei) 聚合 -> 一机多卡; (msisdn,bind_time) -> 频繁换机
-- ============================================================
CREATE TABLE telecom_card_device_binding (
    bind_id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '绑定记录ID',
    msisdn           VARCHAR(11)  NOT NULL COMMENT '号卡',
    imei             VARCHAR(15)  NOT NULL COMMENT '设备IMEI',
    bind_time        DATETIME     NOT NULL COMMENT '绑定时间',
    unbind_time      DATETIME     DEFAULT NULL COMMENT '解绑时间 (NULL=当前绑定中)',
    bind_province    VARCHAR(20)  NOT NULL COMMENT '绑定时的省',
    PRIMARY KEY (bind_id),
    KEY idx_bind_msisdn_time (msisdn, bind_time),
    KEY idx_bind_imei (imei),
    KEY idx_bind_active (msisdn, unbind_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机卡绑定历史表';


-- ============================================================
-- 10. 通话记录表 CDR (核心事实表, 大表)
--     风控要点 (索引面向特征计算):
--       - (calling_no, start_time) -> 某号近N分钟主叫次数 (短时高频)
--       - (called_no, start_time)  -> 被叫聚合
--       - cell_id -> 固定点位通信负荷 (GOIP识别)
--       - roam_type / call_from_country -> 国际来电识别
-- ============================================================
CREATE TABLE telecom_cdr (
    cdr_id           BIGINT       NOT NULL AUTO_INCREMENT COMMENT 'CDR ID',
    calling_no       VARCHAR(11)  NOT NULL COMMENT '主叫号码',
    called_no        VARCHAR(20)  NOT NULL COMMENT '被叫号码 (可固话/国际号)',
    call_type        ENUM('主叫','被叫','呼转') NOT NULL DEFAULT '主叫' COMMENT '通话类型',
    start_time       DATETIME     NOT NULL COMMENT '通话开始时间',
    end_time         DATETIME     NOT NULL COMMENT '通话结束时间',
    duration         INT          NOT NULL DEFAULT 0 COMMENT '通话时长(秒)',
    cell_id          VARCHAR(20)  NOT NULL COMMENT '通话基站',
    imei             VARCHAR(15)  DEFAULT NULL COMMENT '通话时设备IMEI',
    roam_type        ENUM('本地','省内漫游','省间漫游','国际') NOT NULL DEFAULT '本地' COMMENT '漫游类型',
    call_from_country VARCHAR(40) DEFAULT NULL COMMENT '国际来电归属国家 (国际来电填)',
    PRIMARY KEY (cdr_id),
    KEY idx_cdr_calling_time (calling_no, start_time),
    KEY idx_cdr_called_time (called_no, start_time),
    KEY idx_cdr_start_time (start_time),
    KEY idx_cdr_cell (cell_id, start_time),
    KEY idx_cdr_roam (roam_type, start_time),
    KEY idx_cdr_imei (imei)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='通话记录表(CDR)';


-- ============================================================
-- 11. 短信记录表 (短信发送事实)
--     风控要点: (sending_no, send_time) -> 短时高频短信 (群发诈骗)
-- ============================================================
CREATE TABLE telecom_sms (
    sms_id           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '短信ID',
    sending_no       VARCHAR(11)  NOT NULL COMMENT '发送方号码',
    receiving_no     VARCHAR(20)  NOT NULL COMMENT '接收方号码',
    send_time        DATETIME     NOT NULL COMMENT '发送时间',
    sms_type         ENUM('普通短信','端口短信','国际短信') NOT NULL DEFAULT '普通短信' COMMENT '短信类型',
    cell_id          VARCHAR(20)  DEFAULT NULL COMMENT '基站',
    imei             VARCHAR(15)  DEFAULT NULL COMMENT '设备IMEI',
    PRIMARY KEY (sms_id),
    KEY idx_sms_sending_time (sending_no, send_time),
    KEY idx_sms_send_time (send_time),
    KEY idx_sms_type (sms_type, send_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='短信记录表';


-- ============================================================
-- 12. 流量使用表 (按天聚合, 1号卡 N天)
--     风控要点: (msisdn, usage_date) -> 流量突增 (物联网卡滥用)
-- ============================================================
CREATE TABLE telecom_data_usage (
    usage_id         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '记录ID',
    msisdn           VARCHAR(11)  NOT NULL COMMENT '号卡',
    usage_date       DATE         NOT NULL COMMENT '使用日期',
    data_volume_mb   INT          NOT NULL DEFAULT 0 COMMENT '当日流量(MB)',
    cell_id          VARCHAR(20)  DEFAULT NULL COMMENT '主要基站',
    roam_type        ENUM('本地','省内漫游','省间漫游','国际') NOT NULL DEFAULT '本地' COMMENT '漫游类型',
    PRIMARY KEY (usage_id),
    UNIQUE KEY uk_usage_card_date (msisdn, usage_date),
    KEY idx_usage_date (usage_date),
    KEY idx_usage_roam (roam_type, usage_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='流量使用表(按天聚合)';


-- ============================================================
-- 13. 业务办理记录表 (开户/补卡/销户/套餐变更/解除限制 等业务事件)
--     风控要点:
--       - (channel_id, order_time) -> 渠道开卡量异常 (反诈法第10条异常办卡)
--       - (customer_id, order_time) -> 一证频繁补卡销户
--       - (msisdn, order_time) -> 单卡业务轨迹
-- ============================================================
CREATE TABLE telecom_service_order (
    order_id         VARCHAR(30)  NOT NULL COMMENT '业务单号 (SO+时间戳)',
    msisdn           VARCHAR(11)  NOT NULL COMMENT '号卡',
    customer_id      VARCHAR(20)  NOT NULL COMMENT '客户ID',
    channel_id       VARCHAR(20)  NOT NULL COMMENT '办理渠道',
    order_type       ENUM('新开户','补卡','换卡','过户','销户','套餐变更','停复机','解除限制','实名核验') NOT NULL COMMENT '业务类型',
    order_time       DATETIME     NOT NULL COMMENT '办理时间',
    order_province   VARCHAR(20)  NOT NULL COMMENT '办理省',
    order_status     ENUM('成功','失败','审核中') NOT NULL DEFAULT '成功' COMMENT '办理状态',
    face_verify_result ENUM('通过','未通过','未核验') NOT NULL DEFAULT '未核验' COMMENT '活体核验结果',
    remark           VARCHAR(200) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (order_id),
    KEY idx_order_msisdn_time (msisdn, order_time),
    KEY idx_order_customer_time (customer_id, order_time),
    KEY idx_order_channel_time (channel_id, order_time),
    KEY idx_order_type_time (order_type, order_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务办理记录表';


-- ============================================================
-- 14. 话费账单表 (充值/消费/转出 → 话费套现识别)
--     风控要点:
--       - (msisdn, create_time) → 高频充值+即时转出 (反诈法第14条 资金监测)
--       - 充值后短时间内转出 = 套现特征
-- ============================================================
CREATE TABLE telecom_billing_record (
    record_id       BIGINT       NOT NULL AUTO_INCREMENT COMMENT '账单记录ID',
    msisdn          VARCHAR(11)  NOT NULL COMMENT '号卡',
    bill_month      VARCHAR(7)   NOT NULL COMMENT '账期 (YYYY-MM)',
    bill_type       ENUM('充值','消费','转出','退款','调账') NOT NULL COMMENT '账单类型',
    amount          DECIMAL(10,2) NOT NULL COMMENT '金额(元, 正数)',
    balance_before  DECIMAL(10,2) DEFAULT NULL COMMENT '变动前余额',
    balance_after   DECIMAL(10,2) DEFAULT NULL COMMENT '变动后余额',
    pay_channel     VARCHAR(20)  DEFAULT NULL COMMENT '支付渠道 (支付宝/微信/银行/现金)',
    remark          VARCHAR(200) DEFAULT NULL COMMENT '备注',
    create_time     DATETIME     NOT NULL COMMENT '发生时间',
    PRIMARY KEY (record_id),
    KEY idx_billing_msisdn_time (msisdn, create_time),
    KEY idx_billing_type_time (bill_type, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='话费账单表';


-- ============================================================
-- 15. 集团客户表 (政企/校园/商户集团 → 子号异常识别)
--     风控要点:
--       - 集团主号 + N 子号结构 → 子号异常高频
--       - (group_id) 聚合 → 子号数量 / 子号风险率
-- ============================================================
CREATE TABLE telecom_group_customer (
    group_id        VARCHAR(20)  NOT NULL COMMENT '集团ID (G+8位)',
    group_name      VARCHAR(80)  NOT NULL COMMENT '集团名称',
    group_type      ENUM('政企','校园','商户','其他') NOT NULL DEFAULT '政企' COMMENT '集团类型',
    customer_id     VARCHAR(20)  NOT NULL COMMENT '关联主客户ID',
    contact_person  VARCHAR(50)  DEFAULT NULL COMMENT '联系人',
    contact_phone   VARCHAR(20)  DEFAULT NULL COMMENT '联系电话',
    open_date       DATE         NOT NULL COMMENT '开户日期',
    group_status    ENUM('正常','冻结','销户') NOT NULL DEFAULT '正常' COMMENT '集团状态',
    PRIMARY KEY (group_id),
    KEY idx_group_customer (customer_id),
    KEY idx_group_status (group_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='集团客户表';


-- ============================================================
-- 建表完成校验
-- ============================================================
SELECT TABLE_NAME, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'telecom'
ORDER BY TABLE_NAME;

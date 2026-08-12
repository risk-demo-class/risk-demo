-- ============================================
-- 二手交易平台物流侧风控系统 - 业务表 DDL 初始化脚本
-- 三段式物流模型 (A 卖家→验货中心, B 验货中心→买家, C 退货逆向)
-- 字段设计兼顾风控特征计算效率 (调包检测/验货质检/画像聚合) 和索引覆盖
-- ============================================

-- 目标数据库由 init_db.py 的 --db 参数连接指定, 此处不写 USE (硬切库名换环境必挂)
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================
-- 第一层: 基础维度表 (无外键)
-- ============================

-- 1. 发件人(卖家)信息表
CREATE TABLE IF NOT EXISTS `shipper_info` (
  `shipper_id` varchar(50) NOT NULL COMMENT '卖家ID',
  `shipper_name` varchar(50) NOT NULL COMMENT '卖家姓名',
  `shipper_phone` varchar(20) NOT NULL COMMENT '卖家手机号',
  `shipper_id_card` varchar(50) DEFAULT NULL COMMENT '身份证号(加密)',
  `shipper_province` varchar(20) NOT NULL COMMENT '发件省',
  `shipper_city` varchar(20) NOT NULL COMMENT '发件市',
  `shipper_district` varchar(20) NOT NULL COMMENT '发件区',
  `shipper_street` varchar(100) NOT NULL COMMENT '发件详细地址',
  `register_time` timestamp NOT NULL COMMENT '注册时间',
  `trade_total` int DEFAULT '0' COMMENT '历史交易量',
  `dispute_count` int DEFAULT '0' COMMENT '累计纠纷数',
  `cancel_count` int DEFAULT '0' COMMENT '累计取消单数',
  `wb_total` int DEFAULT '0' COMMENT '历史运单总数',
  `complaint_total` int DEFAULT '0' COMMENT '累计投诉次数',
  PRIMARY KEY (`shipper_id`),
  KEY `idx_sp_phone` (`shipper_phone`),
  KEY `idx_sp_register` (`register_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='发件人(卖家)信息表';

-- 2. 收件人(买家)信息表
CREATE TABLE IF NOT EXISTS `consignee_info` (
  `consignee_id` varchar(50) NOT NULL COMMENT '买家ID',
  `consignee_name` varchar(50) NOT NULL COMMENT '买家姓名',
  `consignee_phone` varchar(20) NOT NULL COMMENT '买家手机号',
  `consignee_province` varchar(20) NOT NULL COMMENT '收件省',
  `consignee_city` varchar(20) NOT NULL COMMENT '收件市',
  `consignee_district` varchar(20) NOT NULL COMMENT '收件区',
  `consignee_street` varchar(100) NOT NULL COMMENT '收件详细地址',
  `sign_count` int DEFAULT '0' COMMENT '历史签收次数',
  `return_count` int DEFAULT '0' COMMENT '历史退货次数',
  `return_rate` decimal(5,4) DEFAULT '0.0000' COMMENT '退货率',
  PRIMARY KEY (`consignee_id`),
  KEY `idx_cg_phone` (`consignee_phone`),
  KEY `idx_cg_addr` (`consignee_province`,`consignee_city`,`consignee_district`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='收件人(买家)信息表';

-- 3. 承运商/快递员信息表
CREATE TABLE IF NOT EXISTS `carrier_info` (
  `carrier_id` varchar(50) NOT NULL COMMENT '快递员ID',
  `carrier_name` varchar(50) NOT NULL COMMENT '快递员姓名',
  `carrier_phone` varchar(20) NOT NULL COMMENT '联系电话',
  `vehicle_plate` varchar(20) DEFAULT NULL COMMENT '车牌号',
  `vehicle_type` enum('厢式货车','平板货车','冷链车','危化品车','快递三轮车') DEFAULT NULL COMMENT '车型',
  `vehicle_capacity` decimal(10,2) DEFAULT NULL COMMENT '核定载重(kg)',
  `qualification` varchar(200) DEFAULT NULL COMMENT '资质证件',
  `deposit_amount` decimal(12,2) DEFAULT '0.00' COMMENT '保证金(元)',
  `is_verified` int DEFAULT '0' COMMENT '是否实名认证(0=未认证,1=已认证)',
  `register_time` timestamp NOT NULL COMMENT '注册/入驻时间',
  `deliver_total` int DEFAULT '0' COMMENT '历史配送量',
  `photo_rate` decimal(5,4) DEFAULT '0.0000' COMMENT '签收拍照率',
  `complaint_total` int DEFAULT '0' COMMENT '累计投诉次数',
  PRIMARY KEY (`carrier_id`),
  KEY `idx_cr_phone` (`carrier_phone`),
  KEY `idx_cr_plate` (`vehicle_plate`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='承运商/快递员信息表';

-- 4. 二手品类维度表
CREATE TABLE IF NOT EXISTS `dimension_cargo_category` (
  `cargo_category` varchar(20) NOT NULL COMMENT '二手品类',
  `is_high_value` int DEFAULT '0' COMMENT '是否高溢价品类(调包高发)',
  PRIMARY KEY (`cargo_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='二手品类维度表';

-- 5. 运单状态维度表
CREATE TABLE IF NOT EXISTS `dimension_waybill_status` (
  `waybill_status` varchar(20) NOT NULL COMMENT '运单状态',
  PRIMARY KEY (`waybill_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单状态维度表';

-- 6. 投诉原因表 (维度表)
CREATE TABLE IF NOT EXISTS `complaint_reason` (
  `complaint_reason` varchar(100) NOT NULL COMMENT '投诉原因',
  PRIMARY KEY (`complaint_reason`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投诉原因表';

-- ============================
-- 第二层: 核心业务表
-- ============================

-- 7. 运单主表
CREATE TABLE IF NOT EXISTS `waybill_info` (
  `waybill_id` varchar(50) NOT NULL COMMENT '运单号',
  `create_time` timestamp NOT NULL COMMENT '创建时间(卖家下单寄件)',
  `pickup_time` timestamp NULL DEFAULT NULL COMMENT '揽收入仓时间',
  `delivered_time` timestamp NULL DEFAULT NULL COMMENT '买家签收时间',
  `complete_time` timestamp NULL DEFAULT NULL COMMENT '完成时间',
  `segment` enum('A','B','C') DEFAULT 'A' COMMENT '当前所属链路(A=入仓/B=出仓/C=退货逆向)',
  `shipper_id` varchar(50) NOT NULL COMMENT '卖家ID',
  `consignee_id` varchar(50) NOT NULL COMMENT '买家ID',
  `carrier_id` varchar(50) DEFAULT NULL COMMENT '快递员ID',
  `waybill_status` varchar(20) NOT NULL COMMENT '运单状态',
  `inspection_record_id` varchar(50) DEFAULT NULL COMMENT '关联验货报告ID',
  `seal_id` varchar(50) DEFAULT NULL COMMENT '验货后封条/防拆贴ID',
  `cargo_category` varchar(20) NOT NULL COMMENT '二手品类',
  `cargo_weight` decimal(10,2) NOT NULL COMMENT '包裹重量(kg)',
  `cargo_volume` decimal(10,4) NOT NULL COMMENT '包裹体积(m³)',
  `cargo_quantity` int NOT NULL COMMENT '货物件数',
  `declared_value` decimal(12,2) DEFAULT '0.00' COMMENT '声明价值(元)',
  `freight_amount` decimal(12,2) NOT NULL COMMENT '运费(元)',
  `cod_amount` decimal(12,2) DEFAULT '0.00' COMMENT '代收货款金额(元)',
  `insurance_amount` decimal(12,2) DEFAULT '0.00' COMMENT '保价金额(元)',
  `insurance_premium` decimal(10,2) DEFAULT '0.00' COMMENT '保价费(元)',
  `is_night_order` int DEFAULT '0' COMMENT '是否夜间下单(0-6点)',
  `is_urgent` int DEFAULT '0' COMMENT '是否加急',
  `cargo_type` enum('普通','电池','化学品','液体','粉末','刀具','其他') DEFAULT '普通' COMMENT '货物类型(用于危险品检测)',
  `is_cross_border` int DEFAULT '0' COMMENT '是否跨境(港澳台/国际)',
  PRIMARY KEY (`waybill_id`),
  KEY `idx_wb_shipper` (`shipper_id`,`create_time`),
  KEY `idx_wb_carrier` (`carrier_id`,`create_time`),
  KEY `idx_wb_status` (`waybill_status`),
  KEY `idx_wb_category` (`cargo_category`),
  KEY `idx_wb_night` (`is_night_order`),
  KEY `idx_wb_cross` (`is_cross_border`),
  KEY `idx_wb_segment` (`segment`),
  CONSTRAINT `waybill_info_ibfk_1` FOREIGN KEY (`shipper_id`) REFERENCES `shipper_info` (`shipper_id`),
  CONSTRAINT `waybill_info_ibfk_2` FOREIGN KEY (`consignee_id`) REFERENCES `consignee_info` (`consignee_id`),
  CONSTRAINT `waybill_info_ibfk_3` FOREIGN KEY (`carrier_id`) REFERENCES `carrier_info` (`carrier_id`),
  CONSTRAINT `waybill_info_ibfk_4` FOREIGN KEY (`waybill_status`) REFERENCES `dimension_waybill_status` (`waybill_status`),
  CONSTRAINT `waybill_info_ibfk_5` FOREIGN KEY (`cargo_category`) REFERENCES `dimension_cargo_category` (`cargo_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单主表';

-- 8. 运单明细表
CREATE TABLE IF NOT EXISTS `waybill_detail` (
  `detail_id` varchar(50) NOT NULL COMMENT '明细ID',
  `waybill_id` varchar(50) NOT NULL COMMENT '运单号',
  `item_imei` varchar(50) DEFAULT NULL COMMENT '商品序列号/IMEI(关联 item_identity)',
  `cargo_name` varchar(100) NOT NULL COMMENT '物品名称',
  `item_brand` varchar(50) NOT NULL COMMENT '品牌',
  `item_model` varchar(50) NOT NULL COMMENT '型号',
  `item_grade` enum('优','良','差') DEFAULT '良' COMMENT '寄出时成色',
  `cargo_category` varchar(20) NOT NULL COMMENT '二手品类',
  `cargo_weight` decimal(10,2) NOT NULL COMMENT '重量(kg)',
  `cargo_volume` decimal(10,4) NOT NULL COMMENT '体积(m³)',
  `cargo_quantity` int NOT NULL COMMENT '件数',
  `declared_value` decimal(12,2) DEFAULT '0.00' COMMENT '声明价值(元)',
  PRIMARY KEY (`detail_id`),
  KEY `idx_wbd_waybill` (`waybill_id`),
  KEY `idx_wbd_imei` (`item_imei`),
  KEY `idx_wbd_category` (`cargo_category`),
  CONSTRAINT `waybill_detail_ibfk_1` FOREIGN KEY (`waybill_id`) REFERENCES `waybill_info` (`waybill_id`),
  CONSTRAINT `waybill_detail_ibfk_2` FOREIGN KEY (`cargo_category`) REFERENCES `dimension_cargo_category` (`cargo_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运单明细表';

-- 9. 商品身份表 (调包检测核心)
CREATE TABLE IF NOT EXISTS `item_identity` (
  `item_id` varchar(50) NOT NULL COMMENT '商品身份ID',
  `item_imei` varchar(50) NOT NULL COMMENT 'IMEI/序列号',
  `item_brand` varchar(50) NOT NULL COMMENT '品牌',
  `item_model` varchar(50) NOT NULL COMMENT '型号',
  `cargo_category` varchar(20) NOT NULL COMMENT '二手品类',
  `declared_grade` enum('优','良','差') NOT NULL COMMENT '寄出时卖家声明成色',
  `inspected_grade` enum('优','良','差') DEFAULT NULL COMMENT '验货后成色(与声明对比)',
  `return_grade` enum('优','良','差') DEFAULT NULL COMMENT '退货时成色(与出仓对比)',
  `waybill_id` varchar(50) NOT NULL COMMENT '关联运单号',
  `status` enum('在途','已售','退货中','已退回','已锁定') DEFAULT '在途' COMMENT '商品当前状态',
  `create_time` timestamp NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`item_id`),
  KEY `idx_ii_imei` (`item_imei`),
  KEY `idx_ii_waybill` (`waybill_id`),
  CONSTRAINT `item_identity_ibfk_1` FOREIGN KEY (`waybill_id`) REFERENCES `waybill_info` (`waybill_id`),
  CONSTRAINT `item_identity_ibfk_2` FOREIGN KEY (`cargo_category`) REFERENCES `dimension_cargo_category` (`cargo_category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='商品身份表';

-- 10. 验货记录表
CREATE TABLE IF NOT EXISTS `inspection_record` (
  `record_id` varchar(50) NOT NULL COMMENT '验货记录ID',
  `waybill_id` varchar(50) NOT NULL COMMENT '运单号',
  `item_imei` varchar(50) NOT NULL COMMENT '商品序列号/IMEI',
  `inspector_id` varchar(50) NOT NULL COMMENT '验货员ID',
  `inspect_type` enum('入仓验货','出仓复验','退货验货') NOT NULL COMMENT '验货环节',
  `grade_result` enum('优','良','差') NOT NULL COMMENT '验货成色结果',
  `functional_result` enum('正常','异常') DEFAULT '正常' COMMENT '功能检测结果',
  `accessories_result` enum('齐全','缺失') DEFAULT '齐全' COMMENT '配件检测结果',
  `photo_url` varchar(500) DEFAULT NULL COMMENT '验货照片URL',
  `video_url` varchar(500) DEFAULT NULL COMMENT '验货视频URL',
  `seal_id` varchar(50) DEFAULT NULL COMMENT '封条ID',
  `duration_min` int DEFAULT NULL COMMENT '验货耗时(分钟)',
  `inspect_time` timestamp NOT NULL COMMENT '验货时间',
  PRIMARY KEY (`record_id`),
  KEY `idx_ir_waybill` (`waybill_id`),
  KEY `idx_ir_inspector` (`inspector_id`,`inspect_time`),
  KEY `idx_ir_imei` (`item_imei`),
  CONSTRAINT `inspection_record_ibfk_1` FOREIGN KEY (`waybill_id`) REFERENCES `waybill_info` (`waybill_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='验货记录表';

-- 11. 轨迹事件表
CREATE TABLE IF NOT EXISTS `tracking_event` (
  `event_id` bigint NOT NULL AUTO_INCREMENT COMMENT '事件ID',
  `waybill_id` varchar(50) NOT NULL COMMENT '运单号',
  `event_type` enum('卖家下单寄件','揽收入仓','验货完成','出仓发货',
    '运输中','派送中','买家签收','买家拒收','买家退回寄件','退货入仓验货')
    NOT NULL COMMENT '事件类型(三段式10类)',
  `event_time` timestamp NOT NULL COMMENT '事件时间',
  `location_province` varchar(20) DEFAULT NULL COMMENT '所在省',
  `location_city` varchar(20) DEFAULT NULL COMMENT '所在市',
  `location_district` varchar(20) DEFAULT NULL COMMENT '所在区',
  `location_lat` decimal(10,6) DEFAULT NULL COMMENT '纬度',
  `location_lng` decimal(10,6) DEFAULT NULL COMMENT '经度',
  `node_weight` decimal(10,2) DEFAULT NULL COMMENT '节点称重(kg, 调包检测)',
  `operator_id` varchar(50) DEFAULT NULL COMMENT '操作人ID(快递员/验货员)',
  `remark` varchar(200) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`event_id`),
  KEY `idx_te_waybill` (`waybill_id`,`event_type`),
  KEY `idx_te_time` (`waybill_id`,`event_time`),
  CONSTRAINT `tracking_event_ibfk_1` FOREIGN KEY (`waybill_id`) REFERENCES `waybill_info` (`waybill_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='轨迹事件表';

-- 12. 投诉纠纷表
CREATE TABLE IF NOT EXISTS `complaint_claim` (
  `claim_id` varchar(50) NOT NULL COMMENT '投诉/理赔ID',
  `waybill_id` varchar(50) NOT NULL COMMENT '运单号',
  `claimant` enum('买家','卖家') NOT NULL COMMENT '投诉方',
  `claim_type` enum('调包投诉','成色不符','退货争议','未收到',
    '破损投诉','遗失投诉','费用争议','其他') NOT NULL COMMENT '投诉/理赔类型',
  `claim_amount` decimal(12,2) DEFAULT '0.00' COMMENT '争议金额(元)',
  `claim_reason` varchar(500) NOT NULL COMMENT '投诉/理赔原因',
  `claim_status` enum('待处理','处理中','已赔付','已驳回','已关闭')
    NOT NULL COMMENT '处理状态',
  `create_time` timestamp NOT NULL COMMENT '创建时间',
  `complete_time` timestamp NULL DEFAULT NULL COMMENT '完成时间',
  PRIMARY KEY (`claim_id`),
  KEY `idx_cc_waybill` (`waybill_id`),
  KEY `idx_cc_type` (`claim_type`),
  KEY `idx_cc_status` (`claim_status`),
  KEY `idx_cc_claimant` (`claimant`),
  CONSTRAINT `complaint_claim_ibfk_1` FOREIGN KEY (`waybill_id`) REFERENCES `waybill_info` (`waybill_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投诉纠纷表';

SET FOREIGN_KEY_CHECKS = 1;
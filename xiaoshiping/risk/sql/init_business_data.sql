SET NAMES utf8mb4;
USE manufacturing_risk;
SET FOREIGN_KEY_CHECKS = 0;

INSERT INTO plant VALUES ('P001','华东精密制造一厂','冲压车间','冲压一线','A-01','ACTIVE'),('P002','华东精密制造一厂','机加工车间','CNC二线','B-02','ACTIVE'),('P003','华南零部件工厂','注塑车间','注塑三线','C-03','ACTIVE'),('P004','华南零部件工厂','总装车间','装配一线','D-01','ACTIVE');
INSERT INTO customer VALUES ('C001','华星汽车系统有限公司','A','汽车制造',5000000,'APPROVED'),('C002','东岳新能源汽车有限公司','A','新能源汽车',4200000,'APPROVED'),('C003','恒通传动设备有限公司','B','工业机械',1800000,'APPROVED'),('C004','远达工程机械有限公司','B','工程机械',1500000,'APPROVED'),('C005','启辰制动科技有限公司','A','汽车零部件',2600000,'APPROVED'),('C006','北辰电驱有限公司','B','电驱系统',1300000,'APPROVED'),('C007','中原农机集团','B','农业机械',900000,'APPROVED'),('C008','海岳工业自动化有限公司','C','自动化设备',600000,'APPROVED'),('C009','万和商用车有限公司','A','商用车',3500000,'APPROVED'),('C010','精工售后服务中心','C','售后服务',300000,'APPROVED'),('C011','新锐动力有限公司','C','动力系统',400000,'PENDING'),('C012','华南试制中心','C','试制研发',200000,'APPROVED');
INSERT INTO supplier VALUES ('S001','东海钢材供应有限公司','A','VALID','2027-06-30','LOW'),('S002','华中铝材有限公司','A','VALID','2027-03-31','LOW'),('S003','精益塑胶材料有限公司','B','VALID','2026-12-31','MEDIUM'),('S004','安泰标准件有限公司','B','VALID','2027-01-31','LOW'),('S005','恒达热处理有限公司','A','VALID','2026-08-05','HIGH'),('S006','远景电子元件有限公司','A','EXPIRED','2026-07-31','HIGH'),('S007','瑞丰表面处理有限公司','B','VALID','2027-02-28','MEDIUM'),('S008','新源外协加工厂','C','SUSPENDED','2026-11-30','HIGH');
INSERT INTO employee VALUES ('E001','张伟','采购经理','采购部',NULL,NULL,'ACTIVE'),('E002','李娜','采购专员','采购部',NULL,NULL,'ACTIVE'),('E003','王强','生产主管','冲压车间',NULL,NULL,'ACTIVE'),('E004','赵敏','生产主管','机加工车间',NULL,NULL,'ACTIVE'),('E005','陈杰','操作员','冲压一线',NULL,NULL,'ACTIVE'),('E006','刘洋','操作员','CNC二线',NULL,NULL,'ACTIVE'),('E007','周丽','质量检验员','质量部','IQC/FQC','2027-12-31','ACTIVE'),('E008','孙磊','质量检验员','质量部','IPQC','2026-12-31','ACTIVE'),('E009','吴刚','设备工程师','设备部','电工作业','2027-05-31','ACTIVE'),('E010','郑凯','维修技师','设备部','LOTO','2026-07-31','ACTIVE'),('E011','何芳','仓库管理员','仓储部',NULL,NULL,'ACTIVE'),('E012','马超','发运专员','物流部',NULL,NULL,'ACTIVE'),('E013','许静','操作员','注塑三线',NULL,NULL,'ACTIVE'),('E014','高峰','检验员','质量部','OQC','2027-06-30','ACTIVE'),('E015','蒋雪','工艺工程师','工程部',NULL,NULL,'ACTIVE'),('E016','胡斌','承包商','设备部','高处作业','2026-09-30','ACTIVE'),('E017','郭婷','采购专员','采购部',NULL,NULL,'ACTIVE'),('E018','罗成','操作员','装配一线',NULL,NULL,'ACTIVE'),('E019','丁磊','仓库管理员','仓储部',NULL,NULL,'ACTIVE'),('E020','沈悦','质量经理','质量部',NULL,NULL,'ACTIVE');
INSERT INTO material VALUES ('M001','高强度冷轧钢板','RAW','1.5mm x 1250mm','SPCC','KG',365,1,'R1'),('M002','铝合金板材','RAW','2.0mm x 1200mm','6061-T6','KG',365,1,'R1'),('M003','工程塑料粒子','RAW','PA66-GF30','PA66-GF30','KG',180,1,'R2'),('M004','六角法兰螺栓','RAW','M8 x 30','10.9级','PCS',730,0,'R1'),('M005','冲压支架半成品','WIP','BRK-100','BRK-100','PCS',NULL,1,'R3'),('M006','电机安装支架','FG','ASM-200','ASM-200','PCS',NULL,1,'R5'),('M007','齿轮箱壳体','FG','GEAR-300','ADC12','PCS',NULL,1,'R2'),('M008','塑料连接器壳体','FG','CON-400','PA66-GF30','PCS',NULL,1,'R2'),('M009','轴承座','FG','BRG-500','QT500','PCS',NULL,1,'R1'),('M010','铝制端盖','WIP','CAP-600','6061-T6','PCS',NULL,1,'R2'),('M011','密封圈','RAW','OR-45','FKM','PCS',365,1,'R1'),('M012','铜排','RAW','8mm x 30mm','T2','KG',365,1,'R1'),('M013','不锈钢垫片','RAW','M8','304','PCS',730,0,'R1'),('M014','润滑脂','RAW','NLGI-2','工业级','KG',365,0,'R1'),('M015','制动器连接板','FG','BRK-700','Q235B','PCS',NULL,1,'R1'),('M016','传感器安装座','FG','SNS-800','ADC12','PCS',NULL,1,'R1'),('M017','碳钢圆棒','RAW','直径30mm','45#','KG',730,1,'R1'),('M018','热处理轴套','WIP','BUSH-900','20CrMnTi','PCS',NULL,1,'R2'),('M019','线束护套','FG','HNS-1000','TPU','PCS',NULL,1,'R1'),('M020','包装托盘','PACK','1200 x 800','木质','PCS',730,0,'R1');
INSERT INTO equipment VALUES ('EQ001','P001','800T冲压机','PRESS','CRITICAL','RUNNING','2027-01-31','2026-08-15'),('EQ002','P001','400T冲压机','PRESS','HIGH','RUNNING','2027-01-31','2026-08-20'),('EQ003','P002','CNC加工中心01','CNC','CRITICAL','RUNNING','2026-09-30','2026-08-10'),('EQ004','P002','CNC加工中心02','CNC','HIGH','ALARM','2026-09-30','2026-08-25'),('EQ005','P003','注塑机01','INJECTION','CRITICAL','RUNNING','2027-02-28','2026-08-18'),('EQ006','P003','注塑机02','INJECTION','HIGH','STOPPED','2027-02-28','2026-08-12'),('EQ007','P004','自动装配线01','ASSEMBLY','CRITICAL','RUNNING',NULL,'2026-08-30'),('EQ008','P004','扭矩检测台','TEST','CRITICAL','RUNNING','2026-07-31','2026-08-30'),('EQ009','P001','三坐标测量机','CMM','CRITICAL','RUNNING','2026-08-05','2026-09-30'),('EQ010','P002','清洗机','CLEANING','MEDIUM','RUNNING',NULL,'2026-08-22'),('EQ011','P003','视觉检测台','VISION','HIGH','RUNNING','2027-03-31','2026-08-28'),('EQ012','P004','泄漏测试台','TEST','HIGH','RUNNING','2027-01-31','2026-08-27');
INSERT INTO bom VALUES ('B001','M006','M005',1,0.02,'R1'),('B002','M006','M004',4,0.01,'R1'),('B003','M007','M002',2.5,0.03,'R1'),('B004','M007','M017',1.2,0.02,'R1'),('B005','M008','M003',0.18,0.015,'R2'),('B006','M009','M017',2,0.02,'R1'),('B007','M015','M001',1.1,0.02,'R1'),('B008','M019','M003',0.08,0.01,'R1');

DELIMITER $$
CREATE PROCEDURE seed_demo_data()
BEGIN
  DECLARE i INT DEFAULT 1;
  DECLARE material_no INT;
  DECLARE customer_no INT;
  DECLARE supplier_no INT;
  DECLARE work_status VARCHAR(20);
  DECLARE quality_state VARCHAR(20);
  WHILE i <= 120 DO
    SET material_no = 6 + MOD(i - 1, 4);
    SET customer_no = 1 + MOD(i - 1, 12);
    SET supplier_no = 1 + MOD(i - 1, 8);
    SET work_status = IF(MOD(i,17)=0,'HOLD',IF(MOD(i,5)=0,'IN_PROGRESS','COMPLETED'));
    SET quality_state = IF(MOD(i,19)=0,'HOLD',IF(MOD(i,13)=0,'FAILED','PASSED'));
    INSERT INTO sales_order VALUES (CONCAT('SO',LPAD(i,4,'0')),CONCAT('C',LPAD(customer_no,3,'0')),CONCAT('M',LPAD(material_no,3,'0')),500+MOD(i*37,700),DATE_ADD('2026-08-12',INTERVAL 5+MOD(i,20) DAY),IF(MOD(i,7)=0,'HIGH','NORMAL'),50+MOD(i*7,100),'R1','RELEASED',DATE_ADD('2026-08-01 08:00:00',INTERVAL i HOUR));
    INSERT INTO purchase_order VALUES (CONCAT('PO',LPAD(i,4,'0')),CONCAT('S',LPAD(supplier_no,3,'0')),CONCAT('M',LPAD(1+MOD(i-1,4),3,'0')),1000+MOD(i*53,2000),5+MOD(i*3,45),DATE_ADD('2026-08-01',INTERVAL MOD(i,10) DAY),IF(MOD(i,2)=0,'E001','E002'),'RELEASED',DATE_ADD('2026-07-25 08:00:00',INTERVAL i HOUR));
    INSERT INTO receipt VALUES (CONCAT('RC',LPAD(i,4,'0')),CONCAT('PO',LPAD(i,4,'0')),CONCAT('LOT-',LPAD(i,4,'0')),990+MOD(i*53,2000),'WH-RAW',DATE_ADD('2026-08-01 09:00:00',INTERVAL i HOUR),IF(MOD(i,2)=0,'E011','E019'));
    INSERT INTO iqc_inspection VALUES (CONCAT('IQ',LPAD(i,4,'0')),CONCAT('RC',LPAD(i,4,'0')),quality_state,50,IF(quality_state='PASSED',MOD(i,2),8),IF(MOD(i,2)=0,'E007','E008'),DATE_ADD('2026-08-01 12:00:00',INTERVAL i HOUR));
    INSERT INTO inventory VALUES (CONCAT('INV',LPAD(i,4,'0')),CONCAT('M',LPAD(1+MOD(i-1,4),3,'0')),CONCAT('LOT-',LPAD(i,4,'0')),'WH-RAW',990+MOD(i*53,2000),quality_state,DATE_ADD('2026-08-01',INTERVAL MOD(i,12) DAY),DATE_ADD('2027-01-01',INTERVAL i DAY));
    INSERT INTO work_order VALUES (CONCAT('WO',LPAD(i,4,'0')),CONCAT('SO',LPAD(i,4,'0')),CONCAT('P',LPAD(1+MOD(i-1,4),3,'0')),CONCAT('M',LPAD(material_no,3,'0')),500+MOD(i*37,700),IF(work_status='COMPLETED',495+MOD(i*37,700),400+MOD(i*37,700)),'R1','R1',DATE_ADD('2026-08-02 07:00:00',INTERVAL i HOUR),DATE_ADD('2026-08-03 19:00:00',INTERVAL i HOUR),work_status);
    INSERT INTO material_issue VALUES (CONCAT('MI',LPAD(i,4,'0')),CONCAT('WO',LPAD(i,4,'0')),CONCAT('M',LPAD(1+MOD(i-1,4),3,'0')),CONCAT('LOT-',LPAD(i,4,'0')),100+MOD(i*17,900),IF(MOD(i,2)=0,'E005','E006'),DATE_ADD('2026-08-02 08:00:00',INTERVAL i HOUR));
    INSERT INTO operation_report VALUES (CONCAT('OR',LPAD(i,4,'0')),CONCAT('WO',LPAD(i,4,'0')),10,490+MOD(i*37,700),MOD(i,12),8+MOD(i,16),IF(MOD(i,2)=0,'E005','E006'),DATE_ADD('2026-08-02 18:00:00',INTERVAL i HOUR));
    INSERT INTO ipqc_inspection VALUES (CONCAT('IP',LPAD(i,4,'0')),CONCAT('WO',LPAD(i,4,'0')),10,IF(MOD(i,16)=0,10.35,10.00+MOD(i,15)/100),9.80,10.20,IF(MOD(i,16)=0,'FAILED','PASSED'),IF(MOD(i,2)=0,'E008','E014'),CONCAT('EQ',LPAD(1+MOD(i-1,12),3,'0')),DATE_ADD('2026-08-02 14:00:00',INTERVAL i HOUR));
    INSERT INTO finished_goods VALUES (CONCAT('FG',LPAD(i,4,'0')),CONCAT('WO',LPAD(i,4,'0')),CONCAT('FGLOT-',LPAD(i,4,'0')),CONCAT('SN',LPAD(i*1000,6,'0'),'-SN',LPAD(i*1000+499,6,'0')),495+MOD(i*37,700),IF(MOD(i,19)=0,'HOLD','PASSED'),'WH-FG',DATE_ADD('2026-08-03 20:00:00',INTERVAL i HOUR));
    INSERT INTO shipment VALUES (CONCAT('SH',LPAD(i,4,'0')),CONCAT('C',LPAD(customer_no,3,'0')),CONCAT('SO',LPAD(i,4,'0')),CONCAT('M',LPAD(material_no,3,'0')),CONCAT('FGLOT-',LPAD(i,4,'0')),480+MOD(i*37,700),IF(MOD(i,23)=0,'HOLD','PASSED'),IF(MOD(i,23)=0,NULL,'E012'),DATE_ADD('2026-08-04 09:00:00',INTERVAL i HOUR));
    INSERT INTO business_event VALUES (CONCAT('BE',LPAD(i,4,'0')),ELT(1+MOD(i-1,8),'material_received','iqc_completed','material_issued','production_reported','inspection_completed','finished_goods_putaway','shipment_released','maintenance_due'),ELT(1+MOD(i-1,5),'receipt','work_order','material','shipment','equipment'),CONCAT('WO',LPAD(i,4,'0')),ELT(1+MOD(i-1,5),'ERP','MES','WMS','QMS','EAM'),IF(MOD(i,2)=0,'E005','E007'),DATE_ADD('2026-08-01 08:00:00',INTERVAL i HOUR),CONCAT('TRACE-',LPAD(i,4,'0')),JSON_OBJECT('sequence',i,'demo',true));


    SET i = i + 1;
  END WHILE;
END$$
DELIMITER ;
CALL seed_demo_data();
DROP PROCEDURE seed_demo_data;

INSERT INTO customer_complaint (complaint_id, customer_id, shipment_id, defect_code, severity, claim_amount, returned_qty, status, created_at)
SELECT CONCAT('CC', LPAD(n, 4, '0')), CONCAT('C', LPAD(1 + MOD(n - 1, 12), 3, '0')), CONCAT('SH', LPAD(n, 4, '0')), IF(MOD(n, 30) = 0, 'CRACK', 'DIMENSION_OUT'), IF(MOD(n, 30) = 0, 'HIGH', 'MEDIUM'), 1000 + n * 100, 5 + MOD(n, 20), 'OPEN', DATE_ADD('2026-08-07 10:00:00', INTERVAL n HOUR)
FROM (SELECT 15 AS n UNION ALL SELECT 30 UNION ALL SELECT 45 UNION ALL SELECT 60 UNION ALL SELECT 75 UNION ALL SELECT 90 UNION ALL SELECT 105 UNION ALL SELECT 120) AS complaint_seed;

INSERT INTO maintenance_order (maintenance_order_id, equipment_id, failure_code, downtime_minutes, technician_id, loto_required, acceptance_status, started_at, completed_at)
SELECT CONCAT('MO', LPAD(n, 4, '0')), CONCAT('EQ', LPAD(1 + MOD(n - 1, 12), 3, '0')), IF(MOD(n, 30) = 0, 'CALIBRATION_EXPIRED', 'PM_DUE'), 30 + MOD(n * 9, 300), IF(MOD(n, 2) = 0, 'E009', 'E010'), MOD(n, 2), IF(MOD(n, 30) = 0, 'PENDING', 'ACCEPTED'), DATE_ADD('2026-08-01 18:00:00', INTERVAL n HOUR), IF(MOD(n, 30) = 0, NULL, DATE_ADD('2026-08-01 20:00:00', INTERVAL n HOUR))
FROM (SELECT 15 AS n UNION ALL SELECT 30 UNION ALL SELECT 45 UNION ALL SELECT 60 UNION ALL SELECT 75 UNION ALL SELECT 90 UNION ALL SELECT 105 UNION ALL SELECT 120) AS maintenance_seed;
SET FOREIGN_KEY_CHECKS = 1;

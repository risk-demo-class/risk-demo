USE education_risk;

INSERT INTO user_info VALUES
('edu_001','李明','学生','S2026001',1,'device_normal','2025-09-01 09:00:00'),
('edu_002','王小雨','学生','S2026002',1,'device_risk_shared','2026-08-09 02:00:00'),
('edu_003','赵老师','老师','T2026001',1,'device_teacher','2024-01-01 09:00:00'),
('edu_004','陈同学','学生','S2026004',1,'device_risk_shared','2026-08-10 02:00:00'),
('edu_005','周同学','学生','S2026005',1,'device_risk_shared','2026-08-11 02:00:00'),
('edu_006','孙同学','学生','S2026006',1,'device_risk_shared','2026-08-11 03:00:00'),
('edu_007','吴同学','学生','S2026007',1,'device_risk_shared','2026-08-11 04:00:00');

INSERT INTO course VALUES
('course_python','Python就业实战','编程',5999.00,'edu_003',80),
('course_ai','AI大模型应用','人工智能',12999.00,'edu_003',120),
('course_math','高等数学强化','基础课',999.00,'edu_003',40);

INSERT INTO enrollment VALUES
('enr_normal_001','edu_001','course_math',999.00,'2026-06-01 10:00:00','已报名','考研'),
('enr_normal_002','edu_001','course_python',5999.00,'2026-07-01 10:00:00','已报名','就业'),
('enr_risk_001','edu_002','course_ai',39999.00,'2026-08-12 02:10:00','已报名','快速拿证'),
('enr_risk_002','edu_002','course_python',5999.00,'2026-08-12 02:15:00','已报名','就业'),
('enr_risk_003','edu_002','course_math',999.00,'2026-08-12 02:20:00','已报名','考试');

INSERT INTO learning_progress VALUES
('prg_001','edu_001','course_math',1200,0.50,'2026-08-11 19:00:00'),
('prg_002','edu_001','course_python',2100,0.44,'2026-08-11 20:00:00'),
('prg_003','edu_002','course_ai',3,0.00,'2026-08-12 02:30:00');

INSERT INTO refund_request VALUES
('ref_risk_001','enr_risk_001','edu_002','不想学了',3,39999.00,'2026-08-12 02:35:00','待审核'),
('ref_risk_002','enr_risk_002','edu_002','课程不适合',2,5999.00,'2026-08-12 02:36:00','待审核'),
('ref_risk_003','enr_risk_003','edu_002','重复购买',1,999.00,'2026-08-12 02:37:00','待审核');

INSERT INTO live_reward VALUES
('reward_normal_001','edu_001','edu_003',100.00,'2026-08-10 20:00:00','live_001'),
('reward_risk_001','edu_002','edu_003',8888.00,'2026-08-12 02:40:00','live_001');

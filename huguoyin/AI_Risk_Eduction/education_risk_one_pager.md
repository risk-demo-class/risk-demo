# 教育行业风控系统一页纸业务说明

## 1. 业务边界

教育风控的核心对象不是“商品交易”，而是“课程服务履约 + 学员权益保护 + 合规经营”。系统建议覆盖在线/线下培训平台的报名、合同、支付、预收费资金、学习履约、退款、投诉、证书/学历核验、直播互动等链路。风控目标分三类：识别欺诈套利、发现机构/课程合规风险、保护未成年人和家长权益。

## 2. 典型欺诈与违规场景

| 场景 | 风险描述 | 典型信号 | 建议动作 |
|---|---|---|---|
| 虚假身份/代报名 | 冒用学生、家长或教师身份报名、授课、认证 | 同证件多账号、学生年龄/年级与课程不符、教师资质缺失 | 拦截或实名补验 |
| 批量刷课/代学 | 工作室代看视频、脚本刷学时、账号共享 | 同设备/同 IP 多学员、异常完课速度、观看行为无交互 | 标记、限流、人工复核 |
| 退款套利 | 先领取资料、听完核心课后集中退款，或多账号循环报名退款 | 低学习时长高退款、短周期多退款、同支付工具关联多账号 | 人工复核、限制退款自动化 |
| 预收费风险 | 超周期/超课时/超金额售课，私账收款，诱导培训贷 | 预收费跨度 > 3 个月或 > 60 课时，非监管账户入账，loan_flag=true | 拦截支付、合规告警 |
| 违规招生营销 | 虚假优惠、虚构名师、保过承诺、私域导流 | 高频改价、异常优惠券、客服导流外部收款 | 下架课程、人工审核 |
| 隐形变异培训 | 以非学科、托管、咨询等名义开展违规学科培训 | 课程分类与内容关键词不一致、节假日集中排课 | 合规审核 |
| 证书/学历造假 | 上传伪造证书、学历、成绩单或代办认证 | OCR/核验源不一致、同材料多账号复用 | 拒绝认证、加入黑名单 |
| 未成年人高额消费 | 未成年人直播打赏、冲动购买大额课程 | age < 18 且大额支付/打赏、监护同意缺失 | 二次确认、监护人验证 |

## 3. 关键业务字段

| 领域 | 核心字段 |
|---|---|
| 用户/学员 | user_id, role, student_id, name_hash, age_band, grade, guardian_id, real_name_status, guardian_consent_status, register_at, device_fingerprint, ip_region |
| 机构/教师/课程 | institution_id, license_status, whitelist_status, teacher_id, teacher_qualification_status, course_id, course_name, subject_type, training_type, delivery_mode, total_hours, price, published_status |
| 报名/合同/支付 | enrollment_id, contract_id, order_id, course_id, pay_amount, pay_channel, payer_id, payment_account_type, supervision_account_flag, loan_flag, prepaid_months, prepaid_hours, invoice_status |
| 学习履约 | lesson_id, schedule_time, checkin_time, watch_minutes, interaction_count, completion_rate, device_count, ip_count, homework_submit_at, exam_score |
| 退款/投诉/认证 | refund_id, refund_reason, study_minutes_before_refund, consumed_hours, refund_amount, complaint_id, complaint_type, cert_id, cert_verify_source, verify_result |
| 风控证据 | event_type, source_id, event_data, risk_score, risk_level, rule_hits, action, operator_id, audit_trace_id |

## 4. 推荐事件类型

ACCOUNT_REGISTER, REALNAME_VERIFY, GUARDIAN_CONSENT_UPDATE, COURSE_CREATE, COURSE_UPDATE, TEACHER_QUALIFICATION_VERIFY, ENROLLMENT_SUBMIT, CONTRACT_SIGN, PAYMENT_INIT, PAYMENT_SUCCESS, PREPAID_PACKAGE_PURCHASE, CLASS_SCHEDULE_CREATE, CLASS_CHECKIN, ONLINE_LESSON_WATCH, HOMEWORK_SUBMIT, EXAM_SUBMIT, CERTIFICATE_VERIFY, REFUND_APPLY, REFUND_REVIEW, COMPLAINT_SUBMIT, LIVE_REWARD, DEVICE_BIND, LOGIN, INSTITUTION_ACCOUNT_CHANGE。

## 5. 国内监管适配要点

- 预收费必须重点监控：面向中小学生的校外培训预收费应进入培训收费专用账户，不得通过培训贷缴费，不得一次性或变相收取时间跨度超过 3 个月或 60 课时的费用；非学科类校外培训还应关注单次收费不超过 5000 元的监管口径。
- 平台应支持机构黑白名单、在线选课、支付、退费、评价、投诉等监管服务链路，便于与全国校外教育培训监管与服务综合平台的治理逻辑对齐。
- 涉及未成年人时，学员年龄、监护人关系、监护同意、消费管理、投诉举报必须进入风控字段；不满 14 周岁未成年人个人信息属于敏感个人信息，应取得监护人同意并制定专门处理规则。
- 在线教育产品不得向未成年人推送与教学无关的信息；直播、音视频等互动场景要设置时间管理、权限管理、消费管理能力。
- 规则输出要保留证据链：命中的字段、规则、风险分、处置动作、人工复核记录、申诉/纠错记录均应留痕，避免“一刀切”影响正常学员权益。

主要参考：教育部等六部门《关于加强校外培训机构预收费监管工作的通知》、教育部《校外培训行政处罚暂行办法》、教育部等十三部门《关于规范面向中小学生的非学科类校外培训的意见》、教育部《全国校外教育培训监管与服务综合平台应用管理办法》、《中华人民共和国个人信息保护法》、《中华人民共和国未成年人保护法》。

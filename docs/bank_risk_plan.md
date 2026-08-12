# 电商风控 → 银行信贷风控 改造方案

> **目标**：把现有"电商风控系统"（规则引擎 + XGBoost 双轨融合 + 黑名单 + 案件审核 + 告警 + AI Agent）整体改造成**银行信贷风控系统**，用于面试展示。
>
> **核心思路**：风控引擎（决策流水线 / 规则引擎 / ML 融合 / 案件状态机 / 告警调度 / 黑名单 / 审计）是**领域无关**的，全部保留；只替换**领域层**：业务表、特征、规则、事件类型、前端文案、数据生成脚本。

---

## 一、改造哲学（面试叙事）

> "电商风控关注的是**交易欺诈**（订单、退款、收货地址），银行风控关注的是**信用风险 + 欺诈风险 + 合规风险**（信贷违约、多头借贷、洗钱、黑名单制裁）。我把同一个风控中台架构从电商领域迁移到银行信贷领域，核心是**领域建模的替换**，引擎能力（规则+ML 双轨融合、一票否决、人工审核案件流）完全复用。"

---

## 二、领域映射总览

### 2.1 事件类型映射

| 电商事件 | 银行事件 | 业务含义 |
|---|---|---|
| 下单 | **贷款申请** | 客户提交贷款申请，风控在线审批 |
| 支付 | **放款** | 审批通过后放款环节复核 |
| 售后申请 | **还款/逾期** | 还款异常、逾期记录 |
| 物流投诉 | **客户投诉** | 客户投诉（服务/纠纷） |

### 2.2 17 张业务表映射

| # | 电商表 | 银行表 | 说明 |
|---|---|---|---|
| 1 | user_info | **customer_info** | 客户表 |
| 2 | region | region | 地区表（保留） |
| 3 | product_category | **loan_product_category** | 贷款产品类别（信用贷/抵押贷/经营贷/消费贷/车贷/房贷） |
| 4 | order_status | **loan_status** | 贷款状态（申请中/审批中/已放款/还款中/已结清/逾期/已拒绝） |
| 5 | logistics_company | **bank_branch** | 银行网点 |
| 6 | postsale_status | **repayment_status** | 还款状态（正常/逾期/已结清） |
| 7 | receive_info | **contact_info** | 联系信息（手机/地址/紧急联系人） |
| 8 | sku_info | **loan_product** | 贷款产品（名称/利率/期限/额度上限） |
| 9 | postsale_reason | **overdue_reason** | 逾期原因 |
| 10 | order_info | **loan_application** | 贷款申请（核心表） |
| 11 | logistics | **repayment_record** | 还款记录 |
| 12 | order_detail | **loan_installment** | 分期明细（期数/应还/实还） |
| 13 | order_logistics | **loan_repayment_rel** | 申请↔还款关联 |
| 14 | logistics_complaint | **complaint_content** | 投诉内容对照 |
| 15 | logistics_complaints_record | **complaint_record** | 投诉记录 |
| 16 | postsale | **overdue_record** | 逾期记录 |
| 17 | postsale_logistics | **overdue_repayment_rel** | 逾期↔还款关联 |

### 2.3 25 维特征设计（客户 14 / 申请 8 / 设备网络 3）

**客户维度（14）**——对应原 user_*

| 特征名 | 含义 | 对应电商特征 | 银行风控意义 |
|---|---|---|---|
| cust_total_loans | 历史贷款申请总数 | user_total_orders | 信贷活跃度 |
| cust_loans_30d | 近 30 天申请次数 | user_orders_30d | **多头借贷信号** |
| cust_loans_7d | 近 7 天申请次数 | user_orders_7d | **多头借贷强信号** |
| cust_total_credit | 历史累计授信金额 | user_total_amount | 授信敞口 |
| cust_avg_loan_amount | 平均贷款金额 | user_avg_order_amount | 借贷规模 |
| cust_max_loan_amount | 最大单笔贷款 | user_max_order_amount | 极端敞口 |
| cust_overdue_count | 历史逾期次数 | user_refund_count | **信用违约史** |
| cust_overdue_rate | 逾期率 | user_refund_rate | **信用违约率** |
| cust_overdue_amount | 逾期总金额 | user_refund_amount | 违约规模 |
| cust_repay_count | 正常还款次数 | user_postsale_count | 履约记录 |
| cust_repay_rate | 还款履约率 | user_postsale_rate | **履约率** |
| cust_reject_count | 历史被拒次数 | user_cancel_count | **信用污点** |
| cust_complaint_count | 投诉次数 | user_complaint_count | 纠纷信号 |
| cust_contact_count | 联系方式数量 | user_address_count | 信息稳定性 |

**申请维度（8）**——对应原 order_*

| 特征名 | 含义 | 对应电商特征 | 银行风控意义 |
|---|---|---|---|
| loan_amount | 申请金额 | order_total_amount | 授信额度风险 |
| loan_term_month | 申请期限(月) | order_item_count | 期限结构 |
| loan_installment_count | 分期期数 | order_sku_count | 分期结构 |
| loan_debt_ratio | 负债率 | order_discount_amount | **偿付能力** |
| loan_income_debt_ratio | 收入负债比 | order_discount_rate | **偿付能力核心** |
| apply_interval_sec | 填写到提交间隔(秒) | order_pay_interval_sec | **机器申请检测** |
| apply_is_night | 是否夜间申请 | order_is_night | 异常行为 |
| apply_product_count | 申请产品数 | order_category_count | 申请目标分散度 |

**设备/网络维度（3）**——对应原 addr_*

| 特征名 | 含义 | 对应电商特征 | 银行风控意义 |
|---|---|---|---|
| dev_total_count | 设备总数 | addr_total_count | 设备稳定性 |
| dev_ip_province_count | IP 跨省数 | addr_province_count | **异地欺诈信号** |
| dev_is_new | 是否新设备 | addr_is_new | **新设备欺诈信号** |

### 2.4 30 条规则设计（6 大银行场景）

| 场景 | 条数 | 代表规则 |
|---|---|---|
| 欺诈风险 | 6 | 多头借贷（7天≥3次）、团伙申请（同设备多客户）、极速申请（≤5秒）、夜间申请、异地异常、资料信息矛盾 |
| 信用风险 | 6 | 负债率≥50%、逾期率≥30%、收入负债比≤1.5、历史逾期≥5次、频繁被拒≥3次、新客户大额申请 |
| 反洗钱 | 4 | 频繁大额放款、快进快出、拆分交易、大额无真实用途 |
| 账户风险 | 5 | 异常登录、新设备登录、批量注册、账号信息频繁修改、密码多次尝试 |
| 贷后风险 | 5 | 逾期、连续逾期、套现特征、提前还款异常、还款来源异常 |
| 合规风险 | 4 | 命中黑名单、制裁名单、敏感行业、高风险地区 |

---

## 三、文件改造清单

### 3.1 领域层（替换）

| 文件 | 改造内容 |
|---|---|
| `sql/init_business_tables.sql` | 17 张银行表 DDL |
| `sql/init_business_data.sql` | 银行业务数据（客户/产品/申请/还款/逾期） |
| `sql/init_risk_data.sql` | 30 条银行规则 |
| `app/models_business.py` | 17 张银行表 ORM |
| `app/engine/feature.py` | 25 维银行特征 |
| `app/engine/ml_model.py` | FEATURE_COLUMNS 同步更新 |
| `app/models_risk.py` | risk_user_profile 字段改银行语义 |
| `app/schemas.py` | event_type / 规则分类 / 画像字段 |
| `app/service/event.py` | 业务实体校验（客户/申请/还款） |
| `app/engine/decision.py` | _build_context / _update_user_profile |
| `scripts/gen_*.py` × 6 | 银行数据生成 |
| `scripts/train_xgb_model.py` | 训练脚本（特征名） |
| `templates/*.html` + `static/app.js` | 前端文案 |
| `app/agent/tools.py` / `chat.py` | Agent 工具（若引用电商实体） |
| `tests/` | 领域相关测试重写 |

### 3.2 引擎层（保留，不动）

- `app/engine/rule.py`（规则解析/匹配）
- `app/engine/decision.py` 的评分/融合/一票否决逻辑
- `app/service/case.py`（案件状态机）
- `app/service/alert.py` / `app/scheduler.py`（告警调度）
- `app/service/action_log.py`（审计）
- 黑名单、仪表盘、分页框架

---

## 四、实施阶段

| 阶段 | 内容 | 验证 |
|---|---|---|
| P1 | 写 SQL：17 张表 + 数据 + 30 条规则 | 初始化成功 |
| P2 | 改 ORM + 特征工程 + FEATURE_COLUMNS | feature demo 输出 25 维 |
| P3 | 改 schema / event 校验 / decision 上下文 | 风控检查跑通 |
| P4 | 改数据生成脚本 + 训练脚本 | 生成数据 + 训练 ML |
| P5 | 改前端文案 + Agent 工具 | 页面演示正常 |
| P6 | 重写领域测试，跑全量 pytest | 测试全绿 |
| P7 | 更新 README / 方案总结 | 面试材料完整 |

---

## 五、面试亮点（改造后可讲）

1. **领域迁移能力**：从电商到银行，领域建模替换，引擎复用
2. **银行风控专业术语**：多头借贷、负债率、收入负债比、反洗钱(KYC/AML)、一票否决、人工复核
3. **双轨融合**：规则（可解释、可运营）+ XGBoost（自动学习），A卡/B卡概念可延伸
4. **完整闭环**：申请 → 实时风控 → 人工审核 → 催收/逾期 → 黑名单沉淀 → 模型重训
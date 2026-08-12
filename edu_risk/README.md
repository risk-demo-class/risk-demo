# EduRisk — 教育行业 AI 风控系统

> 参照《电商风控系统 AI_Risk 完整架构与模块设计》教学宝典,将业务场景从**电商**(下单/支付/售后/物流)迁移为**教育**(报名/缴费/退费/考试/作业)的完整项目代码。

**一句话**:用"规则 + AI"双保险守护教育机构资金与教学安全的安检系统。

---

## 🎯 业务场景映射

| 电商风控 | 教育风控 (本项目) |
|---------|------------------|
| 下单 | **报名** (Enrollment) |
| 支付 | **缴费** (PaymentRecord) |
| 售后 | **退费** (RefundRecord) |
| 物流投诉 | **投诉** (ComplaintRecord) |
| 商品 | **课程** (CourseInfo) |
| 用户 | **学员** (UserInfo) |
| 收货地址 | **校区/账号** (School/AccountInfo) |
| 订单特征 | **报名特征** (enroll_*) |
| 黑名单用户 | **黑名单学员** |

**5 类风控事件**: 报名 / 缴费 / 退费 / 考试 / 作业
**6 类风险**: 报名风险 / 缴费风险 / 退费风险 / 考试风险 / 账号风险 / 内容行为风险

---

## 🏗️ 5 层架构

```
L1 Routers(接待)  : risk / rule / case / user / dashboard / agent / blacklist / event / course / setting — 10 router, 30+ 端点
L2 Service(业务)  : event.py 7 步流水线 / case.py 状态机 / validator.py 6 校验 / action_log.py 审计
L3 Engine(引擎)   : rule.py JSON 求值(14 op) / feature.py 25 维特征 / ml_model.py XGBoost / decision.py 双轨融合
L4 Models(数据)   : 24 张表(17 业务 + 7 风控) + 异步连接池
L5 Agent(AI)      : chat.py 懒加载 Agent / tools.py 8 个 @tool
```

## 📊 核心数字

| 数字 | 含义 |
|------|------|
| 5 层架构 | routers / service / engine / models / agent |
| 10 个 router | 30+ API 端点 |
| 24 张表 | 17 业务 + 7 风控 |
| 30 条预置规则 | 6 大类风险 |
| 25 维特征 | 14 学员 + 8 报名 + 3 账号 |
| 8 个 AI 工具 | LangChain |
| 4 种决策 | 通过 / 标记 / 人工审核 / 拒绝 |
| 5 状态案件 | 待审核 / 审核中 / 已通过 / 已拒绝 / 已关闭 |
| 14 种 op | 规则引擎运算符 |
| 1 票否决 | 极高规则 → 强制拒绝 |

---

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置数据库 (复制 .env.example 为 .env,填 DB_PASSWORD)
cp .env.example .env

# 3. 建表 + 预置 30 条教育规则
python scripts/init_db.py

# 4. 造业务数据 (200 学员)
python scripts/gen_edu_data.py 200

# 5. 训练 XGBoost (可选,不训练则走纯规则降级)
python scripts/gen_edu_data.py 500 --target-pos-ratio 0.30
python scripts/train_xgb_model.py

# 6. 启动服务
python _run.py
# Swagger: http://localhost:8000/docs
```

## 🧪 动手试试

```bash
# 跑一次风控检查 (报名事件)
curl -X POST http://localhost:8000/api/risk/check \
  -H "Content-Type: application/json" \
  -d '{"event_type":"报名","source_id":"ENR_TEST_001","user_id":"1001"}'

# 查案件工作台
curl http://localhost:8000/api/cases?active_only=true

# 查询学员画像
curl http://localhost:8000/api/users/U00001/profile

# 测试规则引擎 (R008 一票否决: 新账号 + 大额缴费)
curl -X POST http://localhost:8000/api/rules/test \
  -H "Content-Type: application/json" \
  -d '{"rule_condition":{"and":[{"field":"acct_is_new","op":"==","value":1},{"field":"enroll_total_amount","op":">=","value":30000}]},"features":{"acct_is_new":1,"enroll_total_amount":50000}}'
```

---

## 🧠 25 维特征

- **学员维度 14**: `user_total_enrollments` / `user_enrollments_30d` / `user_enrollments_7d` / `user_total_payment` / `user_avg_payment` / `user_max_payment` / `user_refund_count` / `user_refund_amount` / `user_refund_rate` / `user_complaint_count` / `user_cancel_count` / `user_cheat_count` / `user_exam_count` / `user_device_count`
- **报名维度 8**: `enroll_total_amount` / `enroll_course_count` / `enroll_category_count` / `enroll_discount_amount` / `enroll_discount_rate` / `enroll_pay_interval` / `enroll_is_night` / `enroll_coupon_count`
- **账号维度 3**: `acct_total_count` / `acct_school_count` / `acct_is_new`

## ⚖️ 双轨融合 + 一票否决

```
rule_score = min(max(命中规则 risk_score) + 3 × (额外命中数), 100)
ml_score   = XGBoost(特征) × 100
final      = 0.5 × rule_score + 0.5 × ml_score
一票否决   = 任意规则 risk_level=="极高" → final = max(final, 90)
```

| final_score | risk_level | decision |
|-------------|-----------|----------|
| 0-29 | 低 | 通过 |
| 30-59 | 中 | 标记 |
| 60-79 | 高 | 人工审核 (生成 risk_case) |
| 80-100 | 极高 | 拒绝 (生成 risk_case) |

## 🔒 横向越权防护

教育场景攻击: 拿自己的 `user_id` + 别人的 `enrollment_id` 调风控。
3 步校验: 学员存在(404) → source 与 event_type 匹配(400) → 报名单归属该学员(403)。

## 🤖 AI Agent 8 个工具

`risk_check` / `query_cases` / `query_user_profile` / `manage_blacklist` / `query_dashboard_stats` / `analyze_risk_trend` / `analyze_rule_effectiveness` / `query_business_data`

> 未配置 `LLM_API_KEY` 时自动降级,服务不受影响。

---

## 📁 项目结构

```
edu_risk/
├── _run.py                    # 启动入口
├── requirements.txt
├── .env.example
├── app/
│   ├── api.py                 # 10 router re-export 中心
│   ├── config.py              # Pydantic Settings
│   ├── database.py            # 异步引擎 + 连接池
│   ├── models.py              # 24 张表
│   ├── routers/               # L1 接待层 (10 个)
│   ├── service/               # L2 业务层
│   ├── engine/                # L3 引擎层
│   └── agent/                 # L5 AI 层
├── scripts/
│   ├── main.py                # FastAPI app
│   ├── init_db.py             # 建表 + 30 条教育规则
│   ├── gen_edu_data.py        # 造数据
│   ├── gen_labels.py          # label 生成 (规则反推)
│   └── train_xgb_model.py     # 训练
├── logs/                      # 服务日志
└── tests/                     # 测试
```

## 📚 训练 4 必做

| # | 做法 | 说明 |
|---|------|------|
| 1 | 80/20 stratify 拆分 | 验证集正负比 = 训练集 |
| 2 | 早停 (early_stopping_rounds=10, metric=auc) | 防过拟合 |
| 3 | scale_pos_weight ≤ 10.0 | 防不平衡过拟合 |
| 4 | 最小样本 1250 (25 维 × 50) | 教学经验值 |

**5 件套抗假收敛**: 早停指标换 auc + warmup 50 轮 + L1/L2 正则 + 假收敛自动检测(3 信号) + baseline 对比表。

## ⚠️ 已知未知

- 生产部署方案 (gunicorn/nginx/Dockerfile) 未包含
- Agent 会话为内存级,重启丢失,生产换 Redis
- 训练 label 为规则反推,交付前须升级人工标注
- SHAP 可解释性 / PSI 漂移监控 未实现(未来增强)

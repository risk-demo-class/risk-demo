# Vibe Coding 复盘：电信行业风控系统

> 2026-08-12 | 从电商风控到电信风控的完整迁移实践

## 一、项目概述

### 目标

基于已有的 `ai_risk`（电商风控系统）模板，快速构建一套完整的**电信行业风控系统** (`tele-risk`)，覆盖：

- 6 类电信欺诈场景识别
- 30 维风控特征工程
- 15 条业务规则引擎
- XGBoost 机器学习模型
- 全栈前后端应用

### 成果

| 维度 | 指标 |
|------|------|
| **业务表** | 24 张（15 业务 + 9 风控） |
| **欺诈场景覆盖** | 6/6 类（100%） |
| **风控规则** | 15 条（R001-R015） |
| **特征维度** | 30 维（7 族） |
| **模型性能** | val_auc=1.0, val_f1=1.0 |
| **训练数据** | 299 张号卡（60 风险 + 239 正常） |
| **评估数** | 545 次（批量跑全） |
| **前端页面** | 7 页（仪表盘/风控检查/规则/案件/评估历史/黑名单/Agent） |
| **代码文件** | 40+ Python 文件 |

---

## 二、开发流程

### 阶段 1：业务调研

**目标**：理解电信行业特有的欺诈场景与业务字段

**产出**：
- 6 类典型欺诈场景说明
- 关键业务字段映射（MSISDN/CDR/IMEI/账单等）
- 监管合规要点（反诈法条款映射）

**关键决策**：
- 以 `msisdn`（号卡）为核心枢纽，而非电商的 `user_id`
- CDR 表采用 `calling_no`/`called_no` 双字段（区分主被叫）
- 账单表区分 `充值/消费/转出/退款/调账` 5 种类型

### 阶段 2：数据库设计

**目标**：设计 24 张业务表，索引面向风控特征计算优化

**产出**：
- `init_telecom_tables.sql`：15 张业务表
- `init_risk_tables.sql`：9 张风控表 + 15 条规则
- SQLAlchemy ORM 模型

**关键决策**：
- 新增 `telecom_billing_record`（话费账单表）和 `telecom_group_customer`（集团客户表）
- `telecom_device` 表新增 `mac_address` 字段
- 所有时间字段统一使用 `DATETIME` 类型，便于时间窗口查询
- CDR 表 `calling_no` 改为 `VARCHAR(20)` 支持国际号码

### 阶段 3：特征工程

**目标**：从 25 维扩展到 30 维特征，覆盖 7 个特征族

**产出**：
- `feature.py`：8 个 `compute_*_features` 函数
- `ml_model.py`：30 维 `FEATURE_COLUMNS` 列表

**特征族对比**：

| 特征族 | 维度 | ai_risk 对应 | 电信特有 |
|--------|------|-------------|---------|
| 号卡 | 5 | user_profile | card_age/is_iot/intl_enabled |
| 客户 | 5 | user_profile | cust_card_count/id_multi_card |
| 通信行为 | 9 | order_feature | cdr_out/in/night/short_call |
| 设备 | 3 | address_feature | dev_cards_on_imei/mac_binding |
| 渠道 | 2 | channel_feature | channel_open_count |
| 物联网 | 2 | — | iot_data_burst/unbound |
| 账单 | 2 | — | bill_recharge/outflow_ratio |
| 集团 | 2 | — | grp_sub_count/abnormal |

### 阶段 4：规则引擎

**目标**：设计 15 条业务规则，覆盖 6 类欺诈场景

**规则覆盖**：

| 场景 | 规则ID | 规则名称 | 决策 |
|------|--------|---------|------|
| GOIP 虚拟拨号 | R001 | 短时高频主叫 | 关停号码 |
| GOIP 虚拟拨号 | R002 | 固定点位高频 | 关停号码 |
| 猫池养卡 | R003 | 一机多卡 IMEI 共用 | 关停号码 |
| 一证多卡 | R004 | 同一证件超 5 卡 | 人工审核 |
| 国际诈骗来电 | R005 | 24h 国际来电高频 | 关停号码 |
| 物联网滥用 | R006 | 流量突增+机卡分离 | 人工审核 |
| 渠道异常 | R007 | 代理商 1h 批量开卡 | 关停号码 |
| 设备换卡 | R011 | MAC/IMEI 频繁换卡 | 标记 |
| 话费套现 | R013 | 1h 充值≥3+转出≥50% | 关停号码 |
| 集团子号异常 | R014 | 集团≥8 子号+高频外呼 | 人工审核 |
| 凌晨密集呼叫 | R015 | 凌晨 1h 主叫≥15 | 人工审核 |

### 阶段 5：XGBoost 训练

**训练范式（对齐 ai_risk）**：

```
数据增强 → train_test_split(80/20 stratify) → 仅增强训练集 → 早停 → 评估
```

**训练结果**：

| 指标 | 值 |
|------|-----|
| 样本量 | 299 张（60 风险 / 239 正常） |
| 特征维度 | 30 维 |
| val_auc | 1.0000 |
| val_f1 | 1.0000 |
| val_acc | 1.0000 |
| best_iteration | 50（早停） |

**Top 7 特征重要性**：

```
 1. cust_risk_tag_high_flag     72.3  51.4%
 2. dev_cards_on_imei           37.0  26.3%
 3. cust_open_channel_count     22.4  15.9%
 4. card_age_days                3.4   2.4%
 5. cdr_avg_duration_sec         2.8   2.0%
 6. cust_card_count              2.7   1.9%
 7. channel_is_agent_flag        0.1   0.1%
```

Top 3 特征解释 **93.6%** 的决策。

### 阶段 6：前端开发

**目标**：对齐 ai_risk 前端结构，补齐 7 个页面

**页面清单**：

1. **仪表盘**：统计卡片（规则数/评估数/风险数/案件数）+ 系统说明 + 快速验证
2. **风控检查**：事件类型选择 + 号卡输入 + 业务单号 + 实时检查结果
3. **规则管理**：15 条规则列表，支持按等级/场景筛选
4. **案件管理**：风险案件列表，支持审核状态变更
5. **评估历史**：所有风控评估记录
6. **黑名单**：号卡/客户/设备/渠道黑名单
7. **AI Agent**：LLM 辅助风控分析

### 阶段 7：一条龙脚本

**目标**：实现 `python scripts/one_command.py` 一键完成全流程

**5 步流水线**：

```
建库建表 → 造业务数据 → 训练 XGBoost → 批量风控检查 → 启动 Web 服务
```

**输出示例**：

```
============================================================
电信风控系统 - 一条龙命令 (5 步全流程)
============================================================

[1/5] 建库建表 (init_db.py --yes)
[OK] 执行完成 (44 条 DDL)
[OK] telecom 库现有 24 张表

[2/5] 造业务数据 (gen_telecom_data.py)
  号卡总数: 299 张 (风险 60 + 正常 239)
  CDR: 1936 条, SMS: 452 条, 流量: 2093 条, 账单: 1185 条

[3/5] 训练 XGBoost (train_xgb_model.py)
  val_auc=1.0000, val_f1=1.0000

[4/5] 批量风控检查 (batch_risk_check.py, 299 张号卡)
  通过: 239 | 标记: 20 | 人工审核: 4 | 关停号码: 36

[5/5] 启动 Web 服务 (run_app.py, 端口 8001)
服务已启动, 访问 http://localhost:8001
```

---

## 三、踩坑记录

### 1. 数据增强顺序错误导致 val_auc=1.0 过拟合

**问题**：原流程 `增强→split`，验证集包含训练样本副本。

**修复**：改为 `split→仅增强训练集`，验证集保持原始数据。

### 2. 造数脚本 MSISDN 索引解析错误

**问题**：`int(msisdn[-2:])` 在 300 张号卡时取后两位，导致索引错误。

**修复**：改为 `idx = int(msisdn[3:])`（截取 "138" 后 8 位）。

### 3. CDR 表 calling_no 字段长度不足

**问题**：`VARCHAR(11)` 无法存储国际号码（如 `+8613800000001`）。

**修复**：DDL 修改为 `VARCHAR(20)`，重建表。

### 4. 批量风控检查 source_id 校验失败

**问题**：`batch_risk_check.py` 使用非数字 source_id（如 `batch_通话_0001`），但 validator 要求 source_id 在业务表中存在且类型匹配。

**修复**：新增 `_find_source_id()` 函数，从业务表查询有效 ID；新增 `_preferred_event_types()` 按画像选择事件类型。

### 5. feature.py 缺少 compute_billing_features / compute_group_features

**问题**：扩展到 30 维特征后，账单和集团特征的计算函数缺失。

**修复**：新增 `compute_billing_features`（2 维）和 `compute_group_features`（2 维）。

### 6. 前端页面缺失

**问题**：初始版本缺少"案件管理"、"评估历史"、"黑名单"页面。

**修复**：补齐 3 个页面，前端从 4 页扩展到 7 页。

### 7. 规则覆盖不全

**问题**：初始 12 条规则未覆盖话费套现、集团子号异常、凌晨密集呼叫。

**修复**：新增 R013-R015 规则，规则数从 12 条扩展到 15 条。

---

## 四、复用策略

### ai_risk → tele-risk 复用映射

| ai_risk 模块 | tele-risk 适配 | 复用率 |
|-------------|---------------|--------|
| 风控核心 9 张表 | 直接复用 schema | 100% |
| 风控引擎 4 核心 | 改特征计算函数 | 70% |
| 决策流水线 | 直接复用 7 步流程 | 95% |
| 业务表 | 15 张全新设计 | 0% |
| 特征计算 | 8 个 compute_* 全新 | 10% |
| 业务校验 | 全新 validator + 字典派发 | 20% |
| 前端框架 | 复用布局，改业务字段 | 60% |

### 核心契约（不变）

```python
# 请求契约
RiskCheckRequest(event_type, source_id, msisdn, event_data)

# 处理流程
process_event → ensure_card_exists → ensure_source_matches_event_type
              → 黑名单检查 → compute_features → rule_engine + ml_model
              → 决策融合 → 记录评估 → 返回响应
```

---

## 五、文件清单

### 新增/修改文件（30+）

```
tele-risk/
├── sql/
│   ├── init_telecom_tables.sql      # 15 张业务表 (新增 billing + group)
│   └── init_risk_tables.sql         # 2 张风控表 + 15 条规则 (新增 R013-R015)
├── app/
│   ├── models.py                    # 15 个业务 ORM 模型
│   ├── models_risk.py               # 9 个风控 ORM 模型
│   ├── engine/
│   │   ├── feature.py               # 30 维特征计算 (8 个函数)
│   │   ├── rule.py                  # JSON 条件匹配引擎
│   │   ├── ml_model.py              # XGBoost 30 维特征定义
│   │   └── decision.py              # 7 步决策流水线
│   ├── service/
│   │   ├── event.py                 # process_event 4 步入口
│   │   └── validator.py             # 业务校验器 (3 个 ensure_* + 字典派发)
│   └── api/
│       └── routes.py                # 12 个 REST API 端点
├── scripts/
│   ├── init_db.py                   # 建库建表
│   ├── gen_telecom_data.py          # 造数 (299 张号卡)
│   ├── train_xgb_model.py           # XGBoost 训练
│   ├── batch_risk_check.py          # 批量风控检查 (299 张)
│   ├── smoke_test.py                # 50 条 API 冒烟测试
│   └── one_command.py               # ⭐ 一条龙命令
├── run_app.py                       # Web 服务入口
└── README.md                        # 项目说明
```

---

## 六、后续优化方向

| 方向 | 说明 | 优先级 |
|------|------|--------|
| **数据量扩展** | 当前 299 张，建议积累到 1000+ 张提升模型泛化 | 中 |
| **实时流式处理** | 接入 Kafka/NATS 处理实时 CDR 流 | 低 |
| **规则热更新** | 规则库管理页面支持在线编辑和灰度发布 | 中 |
| **模型版本管理** | MLflow 集成，支持 A/B 测试 | 低 |
| **对抗样本测试** | 验证模型对抗 GOIP 变体的鲁棒性 | 中 |
| **前端国际化** | 支持中英文切换 | 低 |

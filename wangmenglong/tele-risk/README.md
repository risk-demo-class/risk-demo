# 电信风控系统 (tele-risk)

基于 **FastAPI + SQLAlchemy + XGBoost** 的电信行业反欺诈风控系统，覆盖 6 类典型欺诈场景，30 维特征工程，15 条业务规则，XGBoost 与规则引擎双轨融合决策。

---

## 一、业务说明

### 1.1 适用场景

本系统为**电信行业风控教学项目**，模拟运营商反欺诈实时决策流程。核心枢纽是**号卡 (MSISDN)**，围绕号卡关联客户、设备、通信行为、账单、集团等业务数据进行综合风险评估。

### 1.2 6 类欺诈场景

| 场景 | 规则 | 监管依据 | 风险等级 |
|------|------|---------|---------|
| **GOIP 虚拟拨号** | R001 (短时高频) / R002 (固定点位) | 反诈法第 13 条 | 极高 → 关停 |
| **猫池养卡** | R003 (一机多卡) / R011 (频繁换机) | 反诈法第 13 条 | 极高 → 关停 |
| **一证多卡** | R004 (开卡超限) | 反诈法第 10 条 | 高 → 人工审核 |
| **国际诈骗来电** | R005 (国际高频被叫) | 反诈法第 16 条 | 极高 → 关停 |
| **物联网卡滥用** | R006 (流量突增) | 反诈法第 12 条 | 高 → 人工审核 |
| **话费套现** | R013 (高频充值+转出) | 反诈法第 14 条 | 极高 → 关停 |
| **集团子号异常** | R014 (批量办卡+高频外呼) | — | 高 → 人工审核 |
| **凌晨密集呼叫** | R015 (凌晨 1h 主叫≥15) | — | 高 → 人工审核 |
| **渠道批量开卡** | R007 (1h 新开户≥8) | 反诈法第 9 条 | 高 → 人工审核 |
| **短通话异常** | R012 (短通话占比≥80%) | — | 高 → 人工审核 |
| **其他** | R008 (新卡高频) / R009 (机卡异地) / R010 (活体未过) | — | 中高 → 标记/审核 |

### 1.3 系统架构

```
事件入口 (process_event)
  │
  ├── Step 1: 业务校验 (ensure_card_exists + ensure_source_matches_event_type)
  ├── Step 2: 黑名单前置拦截 (号卡/客户/设备/渠道)
  ├── Step 3: 决策引擎 (run_risk_check 7 步)
  │     ├── 3.1 解析请求 → 创建 RiskEvent
  │     ├── 3.2 计算 30 维特征 (7 族 feature.py)
  │     ├── 3.3 加载规则 → JSON 条件匹配 (rule.py)
  │     ├── 3.4 XGBoost 推理 (ml_model.py)
  │     ├── 3.5 融合决策 (规则+模型加权)
  │     └── 3.6 落库 (assessment/event/feature/action_log)
  └── Step 4: 审计日志写入
```

### 1.4 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn (端口 8001) |
| ORM | SQLAlchemy 2.0 (async) |
| 数据库 | MySQL 8.0 |
| 机器学习 | XGBoost (二分类) |
| 前端 | Jinja2 模板 + Tailwind CSS |
| 依赖管理 | uv |

---

## 二、跑通演示（一条龙）

### ⭐ 最快方式：一条命令全流程（~5 分钟）

```bash
python scripts/one_command.py
```

自动完成 5 步：建库建表 → 造业务数据 → 训练 XGBoost → 批量风控检查 → 启动 Web 服务。

**可选参数：**

```bash
python scripts/one_command.py --skip-init      # 跳过建库+造数（DB 已就绪）
python scripts/one_command.py --skip-train     # 跳过训练（模型已就绪）
python scripts/one_command.py --skip-batch    # 跳过批量检查
python scripts/one_command.py --skip-server   # 不启服务
python scripts/one_command.py --only-start    # 只启服务（跳过全部准备步骤）
```

### 分步跑（~5 分钟）

```bash
# 1. 建库建表 (24 张表 + 15 条规则)
python scripts/init_db.py --yes

# 2. 造数 (299 张号卡: 60 风险 + 239 正常)
python scripts/gen_telecom_data.py

# 3. 训练 XGBoost 模型
python scripts/train_xgb_model.py
# 输出: val_auc=1.0000, val_f1=1.0000

# 4. 批量风控检查 (299 次评估)
python scripts/batch_risk_check.py

# 5. 启动服务
python run_app.py
# 访问: http://localhost:8001

# 6. 50 条冒烟测试
python scripts/smoke_test.py
```

### 快捷验证：5 张风险号卡

在前端页面 **风控检查** 输入以下号卡，可触发对应规则：

| 号卡 | 触发规则 | 预期 |
|------|---------|------|
| `13800000001` | R001 + R002 | 极高 → 关停 |
| `13800000002` | R001 + R002 | 极高 → 关停 |
| `13800000009` | R003 | 极高 → 关停 |
| `13800000019` | R004 | 高 → 人工审核 |
| `13800000029` | R005 | 极高 → 关停 |
| `13800000036` | R006 | 高 → 人工审核 |
| `13800000295` | R013 | 极高 → 关停 |
| `13800000290` | R014 | 高 → 人工审核 |

### API 直接调用

```python
import requests

# 风控检查
resp = requests.post("http://localhost:8001/api/risk/check", json={
    "event_type": "通话",
    "source_id": "1",
    "msisdn": "13800000001",
    "event_data": {"calling_no": "13800000001", "cell_id": "CELL_001"}
})
# resp.json() → {decision: "关停号码", final_score: 100, triggered_rules: ["R002"]}
```

---

## 三、XGBoost 评估

### 3.1 模型配置

| 参数 | 值 |
|------|-----|
| 特征维度 | 30 维 (7 族) |
| 样本量 | 299 张号卡 |
| 正样本 | 60 (20.1%) |
| 负样本 | 239 (79.9%) |
| `scale_pos_weight` | 3.98 |
| `max_depth` | 4 |
| `learning_rate` | 0.1 |
| `num_boost_round` | 200 |
| `early_stopping_rounds` | 10 |
| `best_iteration` | 50 |
| 测试集比例 | 20% (stratify) |
| 数据增强 | SMOTE 仅增强训练集 |

### 3.2 训练结果

```
全量:  AUC=1.0000  F1=1.0000  Acc=1.0000  P=1.0000  R=1.0000
验证集: val_auc=1.0000  val_f1=1.0000  val_acc=1.0000  (阈值=0.15)
```

### 3.3 特征重要性 (Top 7)

```
特征名                      重要性   占比
─────────────────────────────────────────────────
cust_risk_tag_high_flag     72.3    51.4%  ← 客户风险标签 (信号最强)
dev_cards_on_imei           37.0    26.3%  ← 一机多卡 (猫池识别核心)
cust_open_channel_count     22.4    15.9%  ← 渠道异常
card_age_days                3.4     2.4%  ← 新卡
cdr_avg_duration_sec         2.8     2.0%  ← 通话时长
cust_card_count              2.7     1.9%  ← 一证多卡
channel_is_agent_flag        0.1     0.1%  ← 代理商

Top 3 特征解释 93.6% 决策
```

### 3.4 30 维特征清单

| 族 | 特征 | 含义 |
|----|------|------|
| **card_** (5) | card_age_days | 开卡天数 |
| | card_is_iot | 是否物联网卡 |
| | card_intl_enabled | 是否开通国际 |
| | card_roam_type_code | 漫游类型编码 |
| | card_status_normal | 状态是否正常 |
| **cust_** (5) | cust_card_count | 客户名下卡数 |
| | cust_id_multi_card_flag | 一证多卡标记 |
| | cust_face_verify_passed | 活体核验是否通过 |
| | cust_risk_tag_high_flag | 是否高风险标签 |
| | cust_open_channel_count | 开卡渠道数 |
| **cdr_** (9) | cdr_out_count_1h | 近 1h 主叫数 |
| | cdr_out_count_24h | 近 24h 主叫数 |
| | cdr_in_count_24h | 近 24h 被叫数 |
| | cdr_distinct_cell_1h | 1h 内不同基站数 |
| | cdr_short_call_ratio | 短通话占比 |
| | cdr_intl_incoming_24h | 24h 国际来电数 |
| | cdr_night_call_ratio | 夜间通话占比 |
| | cdr_avg_duration_sec | 平均通话时长 |
| | cdr_night_call_count | 凌晨 1h 主叫数 |
| **dev_** (3) | dev_cards_on_imei | 同一 IMEI 绑定卡数 |
| | dev_card_imei_mismatch_flag | 机卡是否分离 |
| | dev_binding_changes_30d | 30d 换绑次数 |
| **channel_** (2) | channel_open_count_1h | 1h 渠道新开户数 |
| | channel_is_agent_flag | 是否代理商渠道 |
| **iot_** (2) | iot_data_burst_ratio | 流量突增倍数 |
| | iot_card_device_unbound_flag | 机卡是否分离 |
| **bill_** (2) | bill_recharge_count_1h | 近 1h 充值次数 |
| | bill_outflow_ratio | 转出金额占比 |
| **grp_** (2) | grp_sub_count | 集团子号数 |
| | grp_sub_abnormal_flag | 集团子号异常标记 |

### 3.5 训练范式（对齐 ai_risk）

```
原始 299 张 (60 风险 + 239 正常)
  │
  ├── train_test_split (80/20, stratify)
  │     ├── 训练集 239 张 → SMOTE 增强 → 320 张
  │     └── 验证集 60 张 → 保持原始 (不增强)
  │
  └── XGBoost 训练 (early stopping on val_auc)
        └── best_iteration=50, val_auc=1.0
```

**关键约束：先 split 再增强，验证集不参与数据增强，避免泄漏。**

---

## 四、业务规则讲解

### 4.1 规则引擎设计

规则条件使用 JSON 表达式，支持 `field` / `op` / `value` 三元组，以及 `and` / `or` 嵌套组合：

```json
// 简单条件
{"field": "cdr_out_count_1h", "op": ">=", "value": 20}

// 组合条件
{"and": [
  {"field": "cdr_distinct_cell_1h", "op": "==", "value": 1},
  {"field": "cdr_out_count_1h", "op": ">=", "value": 10}
]}
```

### 4.2 决策融合

```
最终分数 = max(规则命中分, XGBoost 预测分 × 100)

决策映射:
  score >= 85 → 关停号码
  score >= 60 → 人工审核
  score >= 30 → 标记
  score < 30  → 通过
```

### 4.3 15 条规则详解

#### 通话欺诈类 (R001/R002/R008/R012/R015)

| ID | 名称 | 条件 | 等级 | 动作 |
|----|------|------|------|------|
| **R001** | GOIP 短时高频主叫 | `cdr_out_count_1h >= 20` | 高(70) | 人工审核 |
| **R002** | GOIP 固定点位通信 | `cdr_distinct_cell_1h == 1 AND cdr_out_count_1h >= 10` | 极高(95) | 关停号码 |
| **R008** | 新卡高频主叫 | `card_age_days <= 7 AND cdr_out_count_24h >= 50` | 高(65) | 人工审核 |
| **R012** | 短通话占比异常 | `cdr_short_call_ratio >= 0.8 AND cdr_out_count_24h >= 30` | 高(60) | 人工审核 |
| **R015** | 凌晨密集呼叫 | `cdr_night_call_count >= 15` | 高(60) | 人工审核 |

**业务解读**：GOIP 网关的典型特征是 **短时高频 + 固定基站**（因为设备固定放置）。R002 是一票否决规则——1 小时内只在一个基站下呼叫 10+ 次，几乎可以确定是 GOIP。

#### 设备欺诈类 (R003/R009/R011)

| ID | 名称 | 条件 | 等级 | 动作 |
|----|------|------|------|------|
| **R003** | 猫池一机多卡 | `dev_cards_on_imei >= 5` | 极高(95) | 关停号码 |
| **R009** | 机卡异地高频 | `dev_card_imei_mismatch_flag == 1 AND cdr_out_count_1h >= 10` | 高(60) | 人工审核 |
| **R011** | 频繁换机 | `dev_binding_changes_30d >= 3` | 中(40) | 标记 |

**业务解读**：猫池是一种模拟手机的设备，一台 IMEI 可以同时绑定多张卡。R003 是猫池识别的核心规则。

#### 账户风险类 (R004/R010/R014)

| ID | 名称 | 条件 | 等级 | 动作 |
|----|------|------|------|------|
| **R004** | 一证多卡超限 | `cust_card_count >= 5` | 高(70) | 人工审核 |
| **R010** | 活体核验未通过 | `cust_face_verify_passed == 0` | 中(45) | 标记 |
| **R014** | 集团子号异常 | `grp_sub_count >= 8 AND cdr_out_count_24h >= 30` | 高(65) | 人工审核 |

**业务解读**：R004 对应《反诈法》第 10 条"开卡数量核验"，同一身份证名下超过 5 张卡即触发。R014 识别集团批量办卡用于诈骗的场景。

#### 其他类别

| ID | 名称 | 类别 | 条件 | 等级 | 动作 |
|----|------|------|------|------|------|
| **R005** | 国际诈骗来电高频 | 国际来电 | `cdr_intl_incoming_24h >= 10` | 极高(90) | 关停 |
| **R006** | 物联网流量突增 | 物联网 | `iot_data_burst_ratio >= 10` | 高(65) | 审核 |
| **R007** | 渠道批量开卡 | 渠道 | `channel_open_count_1h >= 8` | 高(70) | 审核 |
| **R013** | 话费套现高频转出 | 资金风险 | `bill_recharge_count_1h >= 3 AND bill_outflow_ratio >= 0.5` | 极高(90) | 关停 |

### 4.4 黑名单类型

系统支持 4 种黑名单类型，撞黑后直接拦截（不跑 7 步决策）：

| 类型 | 说明 | 撞黑后处置 |
|------|------|-----------|
| **号卡** | 风险 MSISDN | 关停号码 |
| **客户** | 风险身份证 | 名下所有卡标记 |
| **设备** | 风险 IMEI/MAC | 绑定的卡标记 |
| **渠道** | 风险代理商 | 该渠道开卡标记 |

### 4.5 核心契约

系统对外暴露统一的 4 字段请求契约：

```python
RiskCheckRequest(
    event_type: str,   # 开户/通话/国际来电/短信发送/物联网激活
    source_id: str,    # 业务实体 ID
    msisdn: str,       # 号卡 (核心枢纽)
    event_data: dict,  # 事件附加数据
) → RiskCheckResponse(
    decision: str,     # 通过/标记/人工审核/关停号码
    final_score: int,  # 0-100
    risk_level: str,   # 低/中/高/极高
    triggered_rules: list,
    ...
)
```

这层契约不可修改，保证前端、Agent、第三方调用方的兼容。

---

## 五、项目结构

```
tele-risk/
├── app/
│   ├── engine/          # 风控引擎 4 核心
│   │   ├── decision.py  # 7 步决策流水线
│   │   ├── feature.py   # 30 维特征计算 (7 族)
│   │   ├── rule.py      # JSON 规则匹配
│   │   └── ml_model.py  # XGBoost 模型
│   ├── service/         # 业务服务
│   │   ├── event.py     # 事件处理管道
│   │   ├── validator.py # 业务校验器
│   │   └── blacklist.py # 黑名单服务
│   ├── models.py        # 业务表 ORM (15 张)
│   ├── models_risk.py   # 风控表 ORM (9 张)
│   ├── schemas.py       # Pydantic 契约
│   ├── config.py        # 配置
│   ├── database.py      # 数据库连接
│   ├── routers/         # API 路由
│   └── main.py          # FastAPI 入口
├── sql/
│   ├── init_telecom_tables.sql  # 业务表 DDL
│   └── init_risk_tables.sql     # 风控表 DDL + 15 条规则
├── scripts/
│   ├── init_db.py             # 建库建表
│   ├── gen_telecom_data.py    # 造数 (299 张号卡)
│   ├── train_xgb_model.py     # XGBoost 训练
│   ├── batch_risk_check.py    # 批量风控检查
│   └── smoke_test.py          # 快速验证
├── templates/             # 前端页面 (7 页)
│   ├── index.html         # 仪表盘
│   ├── risk_check.html    # 风控检查
│   ├── rules.html         # 规则管理
│   ├── cases.html         # 案件管理
│   ├── assessments.html   # 评估历史
│   ├── blacklist.html     # 黑名单
│   └── agent.html         # Agent 对话
└── run_app.py             # 一键启动 (带自检)
```

---

## 六、监管合规

所有规则和特征均标注对应监管条款：

| 规则/特征 | 监管依据 |
|----------|---------|
| R004 一证多卡 / cust_card_count | 《反诈法》第 10 条 |
| R005 国际诈骗来电 / cdr_intl_incoming | 《反诈法》第 16 条 |
| R006 物联网滥用 / iot_data_burst | 《反诈法》第 12 条 |
| R007 渠道异常 / channel_open_count | 《反诈法》第 9 条 |
| R013 话费套现 / bill_outflow_ratio | 《反诈法》第 14 条 |
| R001/R002/R003 GOIP+猫池 | 《反诈法》第 13 条 |
| telecom_risk_action_log | 操作审计, 合规追责 |
| telecom_risk_alert | 系统自我监控, 风险预警 |
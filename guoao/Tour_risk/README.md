# 物流风控系统 Tour_Risk — 项目说明

> 基线：尚硅谷 `AI_Risk` 电商风控系统（风控核心完全复用）
> 行业：物流（寄递实名 / 危险品 / 跨境 / 代收货款）
> 架构：FastAPI + MySQL 8.0 + XGBoost + LangChain Agent

## 一句话简介

把电商版风控的"事件 → 25 维特征 → 规则 + XGBoost 双轨融合 → 四档决策 → 建案人工审核"整条流水线，
平移到物流行业：业务表换成 运单/物品/收件地址，特征换成 寄件频率/危险品瞒报/COD 拒收/跨境虚报，
规则换成物流欺诈场景，其余风控骨架一律不动。

## 行业业务设计

### 事件类型（4 种）

| 事件类型 | source_id | 说明 |
|---|---|---|
| 寄件 | 运单号 | 普通包裹寄递 |
| 跨境申报 | 运单号 | 跨境包裹申报 |
| 代收货款 | 运单号 | 货到付款 (COD) |
| 实名认证 | 用户ID | 寄件人实名核验 |

### 业务表（5 张，与电商版显著不同）

| 表 | 核心字段 | 风控意义 |
|---|---|---|
| `user_info` | real_name_status / id_number_hash / account_age_days | 实名是第一道门，新账号大单风险 |
| `address` | province/city/is_temp/use_count | 多地址、新地址、临时地址识别 |
| `shipment` | shipment_type / weight_kg / declared_value / cod_amount / is_dangerous_declared / is_rejected | 运单主表，危险品瞒报与 COD 拒收的来源 |
| `shipment_item` | item_category (普通/电池/液体/化学品) | 危险品识别 |
| `blacklist_extra` | type (身份证号/寄件网点) | 行业扩展黑名单 |

### 25 维特征

- 用户 14：寄件总数、近 7/30 天寄件数、COD 单数、COD 拒收率、危险品次数、瞒报次数、实名状态、账号年龄、地址数、跨省寄件数、平均申报价值、平均重量、取消数
- 运单 8：重量、物品行数、含危险品、瞒报标记、申报价值、COD 金额、是否跨境、是否夜间
- 地址 3：地址总数、省份数、是否新地址

### 预置规则（9 条）

| 规则 | 触发条件 | 决策 |
|---|---|---|
| R001 危险品瞒报 | 含危险品但未申报 | 极高/拒绝（一票否决） |
| R002 高频寄件 | 近 7 天 ≥ 10 单 | 高/人工审核 |
| R003 凌晨批量寄件 | 近 30 天 ≥ 20 单 + 夜间 | 极高/拒绝 |
| R005 大额代收 | COD ≥ 5000 | 高/人工审核 |
| R008 代收拒收率高 | 拒收率 ≥ 50% | 高/人工审核 |
| R010 未实名寄件 | 实名状态 = 0 | 中/标记 |
| R012 跨境价值虚报 | 跨境 + 申报 ≤ 100 + 重量 ≥ 5kg | 中/标记 |
| R018 新地址大额 COD | 新地址 + COD ≥ 3000 | 中/标记 |
| R025 新用户大单 | 注册 < 7 天 + 申报价值 ≥ 10000 | 中/标记 |

## 快速开始

### 1. 环境准备

```bash
conda create -n tour_risk python=3.11 -y
conda activate tour_risk
pip install -r requirements.txt
```

（或直接用项目自带 `.venv`：`pip install -r requirements.txt`）

### 2. 初始化数据库（独立库 tour_risk）

```bash
python scripts/init_db.py --db tour_risk --reset --yes
```

会建 5 张业务表 + 9 张风控表 + 9 条规则。

### 3. 生成业务数据

```bash
python scripts/gen_business_data.py
```

生成 30 用户（含 RISK001-005 五个高风险画像）+ ~120 运单 + ~250 物品明细 + 扩展黑名单。

### 4. 生成评估数据 + 训练模型

```bash
# 训练数据 (近 30 天 × 60 条, 拉高正例比例)
python scripts/gen_risk_data_with_dates.py --days 30 --per-day 60 --balance-pos

# 训练 XGBoost
python scripts/train_xgb_model.py

# 回填 ml_score
python scripts/backfill_ml_score.py

# 演示数据 (近 7 天 × 50 条)
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 50
```

### 5. 启动

```bash
python run_app.py
```

浏览器打开 http://localhost:8000 （仪表盘 / 风险检查 / 案件 / 评估历史 / 规则 / 黑名单 / AI 助手）。

### 一条龙

```bash
python scripts/one_command.py
```

## 复用边界（相对电商基线）

| 模块 | 处理 |
|---|---|
| 风控 9 张表 + 决策流水线 | 完全复用 |
| 引擎 rule / decision / ml_model | 复用（只改枚举与特征列） |
| 业务表 / 特征 / 规则 / 校验 / 造数 | 全部重写为物流版 |
| 前端 / 文档 / Docker | 框架复用，业务字段已改 |

## 目录速记

- 代码：`app/`（engine=规则/特征/决策/ML，service=事件/校验/案件/告警/审计，agent=AI 助手）
- SQL：`sql/`（业务表 + 风控表 + 规则 + 数据）
- 脚本：`scripts/`（初始化 / 造数 / 训练 / 启动）
- 测试：`tests/`（基线测试为主，物流版部分用例待更新）
- 部署：`docker/`

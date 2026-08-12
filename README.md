# 制造业风控系统 (AI_Risk · 行业改写版)

> 基于尚硅谷 `AI_Risk` 电商风控基线, 按任务书**场景 D: 制造业风控**完成的行业改写。
> 业务边界: **经销商订货 / 采购订单 / 设备保修 / 售后维修**。
> 核心能力: 风控核心 9 张表 + 决策流水线完全复用, 业务层 (表/特征/规则/黑名单/事件) 全部按制造业重写。

---

## 一、项目简介

面向装备制造企业 (数控机床 / 注塑机 / 工业机器人等), 对经销商渠道进行风控:

| 场景 | 典型欺诈 | 对应规则 |
|---|---|---|
| 经销商订货 | 大额囤货骗返利、新经销商大单、凌晨突击下单、低价串货 | R005 / R012 / R010 / R020 |
| 采购订单 | 大额采购异常 | R003 |
| 设备保修 | 出保后高频保修、高保修率经销商 | R002 / R015 |
| 售后维修 | 同一设备 SN 套保、维修费用虚报 | R008 / R018 |
| 渠道合规 | 跨区串货举报、经销商资质过期 | R001 / R025 / R026 |

系统保留基线的双轨决策: **规则引擎 + XGBoost**, 一票否决规则 (极高风险) 强制拒绝。

## 二、复用边界 (对照任务书)

| 模块 | 处理方式 |
|---|---|
| 风控核心 9 张表 (risk_rule / risk_event / risk_feature / risk_assessment / risk_case / risk_blacklist / risk_user_profile / risk_action_log / risk_alert) | **完全复用** (仅 event_type / rule_category 值域按行业调整) |
| 决策流水线 (`process_event` 4 步 + `run_risk_check` 7 步) | **完全复用**, 流程不变 |
| `RiskCheckRequest(event_type, source_id, user_id, event_data)` → `RiskCheckResponse` | **核心契约不改** |
| 行业业务表 `app/models_business.py` | **7 张全新建造** |
| 特征计算 `compute_user/order/address_features` | **25 维按制造业重写** |
| 业务校验 `validator.py::ensure_source_matches_event_type` | **派发表重写** (订货单/保修工单/串货举报) |
| 业务黑名单类型 | **用户**(核心表) + **经销商/设备SN/维修工**(业务表 `blacklist_extra`) |
| 业务事件类型 | **经销商订货 / 采购订单 / 保修申请 / 售后维修 / 串货举报** (5 种) |
| 业务数据生成 | `gen_business_data.py` / `gen_risky_users.py` / `gen_risk_data.py` / `gen_train_dataset.py` 全部按行业重写 |
| 业务规则 | 13 条 (R001-R026, 覆盖任务书 D.2 全部 8 条必选) |
| 前端 / 文档 / Docker | 框架复用, 业务字段已改 |

## 三、快速开始

环境: Python 3.12 + MySQL 8.0 (本地 `root/123321`, 库名 `ecs`, 见 `.env`)。

```bash
# 1. 初始化数据库 (7 张业务表 + 9 张风控表 + 13 条规则 + 基础数据)
.venv\Scripts\python.exe scripts\init_db.py --reset --yes

# 2. 造业务数据 (基础 230 行 + 5 个 RISK 高风险经销商)
.venv\Scripts\python.exe scripts\gen_business_data.py

# 3. 一键验收 (6 类高风险场景 + 2 类黑名单拦截 + 1 个正常对照)
.venv\Scripts\python.exe scripts\verify_mfg.py

# 4. 训练 XGBoost (可选: 先扩 RISK 用户 + 强标注训练集)
.venv\Scripts\python.exe scripts\gen_risky_users.py --count 30
.venv\Scripts\python.exe scripts\gen_train_dataset.py --reset
.venv\Scripts\python.exe -u scripts\train_xgb_model.py
.venv\Scripts\python.exe scripts\backfill_ml_score.py

# 5. 造跨天演示数据 (仪表盘趋势)
.venv\Scripts\python.exe scripts\gen_risk_data_with_dates.py --days 14 --per-day 20

# 6. 启动 Web 控制台
.venv\Scripts\python.exe run_app.py
# 浏览器打开 http://localhost:8000
```

一条龙: `python scripts/one_command.py` (重置 → RISK → 训练数据 → 训练 → 回填 → 启动)。

## 四、业务设计

### 4.1 业务表 (7 张, `sql/init_business_tables.sql`)

| 表 | 说明 | 跟电商版差异 |
|---|---|---|
| `user_info` | 用户 (经销商/终端用户/内部员工) | 加 role / dealer_level / region |
| `product` | 设备目录 | 电商 SKU → 设备, 加 MSRP + 保修月数 |
| `dealer_info` | 经销商档案 | 全新表 (授权品牌/合同期) |
| `order_info` | 订货/采购订单 | C 端订单 → B 端经销商订单, 加 ship_to_region |
| `warranty_record` | 保修/维修工单 | 全新表, 按设备 SN 管理 |
| `cross_region_report` | 跨区串货举报 | 全新表 |
| `blacklist_extra` | 行业黑名单扩展 | type: 经销商 / 设备SN / 维修工 |

### 4.2 业务事件类型 (5 种)

`经销商订货` / `采购订单` / `保修申请` / `售后维修` / `串货举报`

### 4.3 业务规则 (13 条, `sql/init_risk_data.sql`)

R001 跨区串货举报 (极高·拒绝) / R002 保修期外高频保修 (高·人工审核) /
R003 大额采购订单 (高·人工审核) / R005 大额经销商囤货 (高·人工审核) /
R007 30天高频订货 (极高·拒绝) / R008 套保嫌疑 (极高·拒绝) /
R010 凌晨突击订货 (中·标记) / R012 新经销商大单 (中·标记) /
R015 高保修率经销商 (极高·拒绝) / R018 维修费用异常 (中·标记) /
R020 异常低价订货 (中·标记) / R025 经销商资质过期 (中·标记) /
R026 跨区发货大单 (高·人工审核)

### 4.4 25 维特征 (`app/engine/feature.py`)

用户 (12): 订货单数/近 7/30 天订货/总额/均值/最大单/保修次数/维修次数/保修率/合同过期/取消数/被举报数

订单 (10): 总额/数量/单价/MSRP 折扣比/夜间单/跨区匹配/SN 近 90 天维修次数/被举报次数/维修费占比/是否出保

区域 (3): 历史发货区域数/跨区订单数/是否新区域

### 4.5 黑名单

- 核心表 `risk_blacklist`: 用户级 (永久/临时, 带过期时间 + 审计)。
- 行业表 `blacklist_extra`: 经销商 / 设备SN / 维修工, `process_event` 前置拦截:
  订货/采购查经销商, 保修/维修查设备SN+维修工, 串货举报查被举报经销商。

## 五、演示数据与验收

`scripts/verify_mfg.py` 一键演示 10 个场景:

| 场景 | 事件 | 期望 |
|---|---|---|
| 高频订货 (RISK002) | 经销商订货 | 拒绝 (R007) |
| 跨区串货 (D004) | 串货举报 | 拒绝 (R001) |
| 套保+维修费 (RISK003) | 售后维修 | 拒绝 (R008+R018) |
| 出保高频保修 (D010) | 保修申请 | 标记 (R002) |
| 资质过期 (D001) | 经销商订货 | 标记 (R025) |
| 黑经销商 (D008) | 经销商订货 | 拒绝 (黑名单) |
| 黑设备SN (SN-D010-0002) | 售后维修 | 拒绝 (黑名单) |
| 新经销商大单 (RISK005) | 经销商订货 | 标记 (R012) |
| 大额采购 (D002) | 采购订单 | 标记 (R003) |
| 正常订货 (D002) | 经销商订货 | 通过 (对照) |

## 六、文档

- [1-业务说明.md](1-业务说明.md): 制造业业务理解 (欺诈场景/关键字段/事件类型/术语表)
- [agent_design.md](agent_design.md): Vibe Coding 协作设计与复盘
- 基线说明: `docker/README.md` (Docker 部署), `AI_Risk_行业风控实战任务书.md` (任务书)

## 七、常见问题

- **`init_db.py` 重置会删库**: 默认 `--reset` 清空 `ecs` 全部数据, 教学/演示环境才用。
- **XGBoost 没训也能跑**: 模型缺失/特征名不匹配时自动走纯规则, 不影响业务。
- **正例比例低**: 训练前先 `gen_risky_users.py --count 30` + `gen_train_dataset.py --reset`。
- **控制台中文乱码**: 脚本已强制 UTF-8 stdout; Windows 终端建议 `chcp 65001`。

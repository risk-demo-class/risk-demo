# 旅游风控系统 Travel_Risk — 项目启动文档

> 5 层架构 · 18 张业务表 + 9 张风控表 · 28 维旅游特征 · 30 条风控规则 · XGBoost 双轨融合 ·
> 一票否决 + sigmoid 校准 + 严格训练数据集 + 一条龙命令 + 统一日志 + 一键启动自检 + Docker 部署

以电商风控项目为模板重构的**旅游行业风控系统**：把电商的"商品/订单/物流/售后"域替换为旅游的
"产品/旅游订单/出行人/退改/理赔/投诉/点评/设备"域，风险场景覆盖下单欺诈、支付风险、账户风险、
退改滥用、出行人风险、供应商风险、综合风险 7 大类。

---

## 1. 环境准备

### 1.1 Python 依赖

```bash
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

核心依赖：`fastapi 0.115` / `uvicorn 0.34` / `sqlalchemy 2.0` / `pymysql 1.1` / `aiomysql 0.2` /
`pydantic 2.10` / `pandas 2.2` / `numpy 2.2` / `scikit-learn 1.5` / `xgboost 2.0` / `pytest 8.3` /
`faker 33` / `ulid-py 1.1`

### 1.2 MySQL 准备

```bash
# Docker (推荐)
docker run -d --name travel-risk-mysql \
  -e MYSQL_ROOT_PASSWORD=123321 \
  -e MYSQL_DATABASE=travel_risk \
  -p 3306:3306 \
  mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_0900_ai_ci
```

或使用本机 MySQL，确保 utf8mb4 且账号有 CREATE DATABASE 权限。

### 1.3 .env 配置

```ini
# 项目根目录 .env (复制 docker/.env.example)
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123321
DB_NAME=travel_risk
TEST_DB_NAME=travel_risk_test

# LLM (可选, 不配 AI Agent 自动降级为规则问答)
LLM_API_KEY=
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# XGBoost 开关 (默认 True, 没模型时自动降级纯规则)
XGB_ENABLED=True
```

---

## 2. 数据库初始化

```bash
python scripts/init_db.py          # 幂等建库建表
python scripts/init_db.py --drop   # 先删后建 (危险, 清空所有数据)
```

按顺序执行：创建数据库 `travel_risk` → 18 张业务表 → 业务测试数据 → 9 张风控表 → 30 条预置规则。

---

## 3. 数据生成（4 种场景）

### 3.1 大量随机业务数据（旅游场景）

```bash
python scripts/gen_10w_data.py                       # 默认 5000 用户
python scripts/gen_10w_data.py --users 500 --max-orders 5
```

产出：用户 / 设备 / 出行人 / 旅游订单 / 明细 / 出行人关联 / 支付 / 退改 / 理赔 / 投诉 / 点评。

风险画像自动注入：
- 80% 正常用户（低退改率、1-2 设备、正常时段下单）
- 15% 中风险（退改率 30-50%、多设备 2-3）
- 5% 高风险（大额 5w+、深夜下单、退改率 50%+、理赔+投诉）

### 3.2 高风险演示用户

```bash
python scripts/gen_risky_users.py --count 30
```

生成 RISK001-RISK030，覆盖：高退改率 / 大额订单 / 深夜下单 / 多设备 / 批量囤票 / 理赔骗保 /
恶意投诉 / 刷评 等画像，用于规则演示和训练数据正例。

### 3.3 风控评估数据（从业务数据触发真实流水线）

```bash
python scripts/gen_risk_data.py 100                  # 100 条评估
python scripts/gen_risk_data.py 200 --balance-pos    # 优先 RISK 用户 (训练用)
python scripts/gen_risk_data_with_dates.py --days 30 --per-day 20 --clean  # 带日期 (趋势图)
```

### 3.4 严格标注训练数据集

```bash
python scripts/gen_train_dataset.py --reset
# 30 RISK × 25 高风险事件 + 30 普通 × 25 正常事件 = 1500 条
# 标签由 30 规则真实跑出, 特征 28 维真实从 DB 查, ml_score 强制 NULL (纯净)
```

---

## 4. 规则制定

30 条规则覆盖 7 大旅游风险场景：

| 分类 | 数量 | 典型规则 |
|---|---:|---|
| 下单欺诈 | 5 | R001 单笔≥2w 审核 / R002 ≥5w 拒绝 (一票否决) |
| 支付风险 | 4 | R006 7 天 10 单 / R007 30 天 30 单 (一票否决) |
| 账户风险 | 4 | R010 退改率≥30% / R011 ≥50% (一票否决) |
| 退改滥用 | 5 | R014 退改≥3 次 / R016 理赔≥2 次 / R017 理赔率≥30% (一票否决) |
| 出行人风险 | 4 | R019 单笔出行人≥8 / R020 出行人手机号≥4 |
| 供应商风险 | 4 | R023 出境游大额 / R025 临期预订 |
| 综合风险 | 4 | R027 三重信号叠加 (一票否决) / R030 新出行人出境游 |

规则条件 JSON 支持 `> >= < <= == != in not_in between` 和 `and / or` 嵌套：

```json
{"and": [
  {"field": "user_refund_rate", "op": ">=", "value": 0.3},
  {"field": "user_claim_count", "op": ">=", "value": 1},
  {"field": "user_device_count", "op": ">=", "value": 2}
]}
```

---

## 5. 28 维特征工程

| 域 | 数量 | 特征 |
|---|---:|---|
| 用户 | 16 | 历史订单数 / 7 天 30 天下单 / 总消费 / 均单 / 最大单 / 退改次数 / 退改率 / 退改金额 / 理赔次数 / 理赔率 / 投诉数 / 累计出行人 / 设备数 / 点评数 / 取消数 |
| 订单 | 9 | 订单金额 / 产品行数 / 出行人数 / 折扣率 / 支付间隔 / 夜间下单 / 预订提前天数 / 行程天数 / 是否出境游 |
| 出行人 | 3 | 出行人总数 / 不同出行人手机号数 / 新出行人数 |

---

## 6. 模型训练（XGBoost 双轨融合）

```bash
python scripts/gen_train_dataset.py --reset   # 1. 严格标注训练数据
python scripts/train_xgb_model.py             # 2. 训练 + 质量验收 + 保存 app/engine/xgb_model.json
python scripts/backfill_ml_score.py           # 3. 回填历史评估 ml_score
```

决策融合：`final_score = 0.5 × 规则分 + 0.5 × ML分(sigmoid 校准)`，任何"极高"规则命中即一票否决，
ML 无法推翻。教学场景可用合成数据快速体验：

```bash
python scripts/train_demo_model.py --n 2000   # 无需 DB, 6 高风险模式 + 正常模式
```

---

## 7. 一条龙命令（从 0 到可演示）

```bash
python scripts/one_command.py                # 6 步全跑: init → RISK用户 → 训练数据 → 训练 → 回填 → 造数
python scripts/one_command.py --skip-init    # 跳过 1+2
python scripts/one_command.py --only-start   # 只跑最后一步
```

---

## 8. 启动服务

```bash
python run_app.py            # 6 步启动前自检 (依赖/MySQL/初始化/端口/模型)
```

浏览器打开 http://localhost:8000：

| 页面 | 功能 |
|---|---|
| 数据总览 | 业务规模 + 风控决策分布 |
| 风控检查 | 6 种事件实时决策 (含 ML 评分 + 特征快照) |
| 规则管理 | 规则 CRUD / 启停 / 条件 JSON 编辑 |
| 案件管理 | 待办审核 / 状态机 / 拒绝联动黑名单 |
| 评估历史 | 全量评估 + 命中规则回溯 |
| 黑名单 | 用户 / 手机号 / 设备 三类管理 |
| AI 助手 | 规则问诊 (未配 LLM 自动降级规则问答) |

API 文档：http://localhost:8000/docs

### 8.1 灵活入参 (用户ID / 业务ID / 设备ID 任一即可)

```json
// 只给用户ID → 账户级通用检查
{"user_id": "U003"}
// 只给设备ID → 自动反查最近绑定用户
{"device_id": "DEV001"}
// 只给业务ID → 自动识别事件类型并反查用户 (订单/支付/退改/理赔/投诉)
{"source_id": "RISKB00200"}
```

三个维度至少提供一个，缺失维度由后端自动补全；什么都不传返回 400。

---

## 9. 跑测试

```bash
pytest -q
```

覆盖：规则引擎求值、决策评分/一票否决/阈值映射、28 维特征对齐、XGBoost 训练与推理、
黑名单优先级短路、案件状态机、分页、审计日志、告警去重、Agent 路由、训练数据纯净性、启动自检。

---

## 10. 生产部署 (Docker)

```bash
cd docker
docker compose up -d --build
docker compose exec app python scripts/init_db.py --yes
docker compose exec app python scripts/one_command.py --skip-init
```

详见 `docker/README.md`。

---

## 11. 架构一览

```
Web 层      FastAPI + Jinja2 页面 + REST API (/api/*) + AI Agent
服务层      process_event 流水线 (校验 → 补全 → 黑名单拦截 → 决策)
引擎层      28 维特征工程 → 规则引擎(30条) → 决策引擎(评分/一票否决/双轨融合) → XGBoost
存储层      MySQL: 18 张业务表 + 9 张风控表 (事件/特征快照/评估/案件/黑名单/画像/审计/告警)
脚本层      init_db / 4 种造数 / 训练 / 回填 / 一条龙 / 冒烟验证
```

## 12. 常见问题

- **MySQL 连不上**：确认服务在跑、密码正确；改 `.env` 的 DB_*。
- **模型没加载**：跑 `train_xgb_model.py`；没有模型时自动降级纯规则。
- **重复跑造数报唯一键**：`init_db.py --drop` 后重跑，或用 `gen_risky_users.py`（内置幂等清理）。
- **评估历史看不到事件类型**：检查 risk_event 与 risk_assessment 是否同库同步。

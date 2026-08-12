# 旅游出行风控系统

基于尚硅谷 `AI_Risk` 电商风控架构扩展的旅游 OTA 风控系统。

## 核心能力

- 规则引擎：JSON 条件表达式快速拦截，极高风险一票否决。
- XGBoost：离线训练 0-100 分风险评分，双轨融合。
- 旅游特有风险：机票退改、酒店预授权、团票批量、跨境订单、签证黑产。
- 行为时序特征：7 天下单次数、连续退改、同设备多账号订酒店。
- DeepSeek 本地 LLM：识别订单备注黄牛暗号 / 违规拼团，失败兜底。
- 特征配置化：`config/features.yaml` 增减特征。
- 可训练 CSV：`data/travel_risk_train.csv`。
- 评估脚本：准确率、召回率、混淆矩阵。
- Docker / Postman 交付。

## 目录结构

```text
AI_lvyou/
├── app/
│   ├── agent/        AI Agent 轻量工具
│   ├── engine/       特征 / 规则 / XGBoost / 决策
│   ├── llm/          DeepSeek 本地备注分析
│   ├── routers/      FastAPI 路由
│   ├── service/      校验 / 案件 / 事件流水线
│   ├── config.py     全局配置
│   └── database.py   异步数据库层
├── config/features.yaml
├── data/             训练 CSV
├── db/init.sql       建表脚本
├── docker/           docker-compose
├── postman/          Postman 集合
├── scripts/          初始化 / 造数 / 训练 / 评估
└── tests/            单元测试
```

## 快速启动

```bash
cd AI_lvyou
python -m venv .venv
.venv/Scripts/activate
pip install -e .
cp .env.example .env
python scripts/init_db.py --yes
python scripts/gen_business_data.py --users 100 --orders 300
python scripts/gen_risky_users.py
python scripts/gen_risk_data.py --count 30 --balance-pos
python scripts/gen_train_csv.py --n 2000 --pos-ratio 0.3
python scripts/train_xgb_model.py
python scripts/evaluate_model.py
python run_app.py
```

访问：

- Web UI: http://localhost:8000
- Swagger: http://localhost:8000/docs

## Docker 启动

```bash
cd AI_lvyou/docker
docker compose up -d --build
```

容器启动时会自动初始化数据库、生成业务数据、生成风控评估并启动服务。

## 常用命令

```bash
# 造数
python scripts/gen_business_data.py --users 200 --orders 600

# 训练
python scripts/gen_train_csv.py --n 3000 --pos-ratio 0.3
python scripts/train_xgb_model.py

# 评估
python scripts/evaluate_model.py --threshold 0.3

# 测试
python -m pytest tests -q
```

## DeepSeek 本地 LLM

本地启动 OpenAI 兼容服务后，在 `.env` 配置：

```ini
LLM_ENABLED=true
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=deepseek-r1:7b
LLM_API_KEY=
```

服务不可用或超时时，系统自动按 0 分兜底，不影响风控主链路。

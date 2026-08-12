# TravelRisk — OTA 旅游行业智能风控系统

TravelRisk 是从 AI_Risk 电商基线项目演化出的旅游行业风控系统，覆盖机票、酒店、签证和订单支付四种实时事件。

## 能力

- 9 张旅游业务表 + 9 张核心风控表
- 25 维账户、行程、证件/设备特征
- 8 条旅游规则（拒签、黄牛、大额跨境、新用户大单等）
- 规则分 + XGBoost 概率双轨融合
- 用户、手机号、护照、设备、IP 黑名单
- 风险评估、案件审核、用户画像、操作审计和告警
- 旅游业务查询 API 和 8 个 AI Agent 工具
- Jinja2 管理页面、Docker 部署、Pytest 契约测试

## 核心流程

```text
RiskCheckRequest
  → 用户/业务实体/归属校验
  → 订单和关联载体补全
  → 核心及旅游扩展黑名单
  → 25 维特征
  → 当前事件规则 + 通用规则
  → 规则/XGBoost 融合与一票否决
  → event/feature/assessment/case/profile 原子落库
```

## 事件与演示 ID

| 事件 | source_id | 内置演示 |
|---|---|---|
| 机票预订 | flight_booking.booking_id | `FB_NORMAL_001` / `FB_SCALPER_001` |
| 酒店预订 | hotel_booking.booking_id | `HB_NEW_001` |
| 签证申请 | visa_application.visa_id | `VA_CURRENT_001` |
| 订单支付 | payment_record.payment_id | `PAY_NORMAL_001` |

对应用户：`TU_NORMAL_001`、`TU_SCALPER_001`、`TU_NEW_001`、`TU_VISA_001`。

## 本地启动

要求 Python 3.11 和 MySQL 8。

```bash
cd TravelRisk
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python scripts/init_db.py --reset --yes
python scripts/gen_business_data.py --count 120
python scripts/gen_risk_data.py --count 100
python run_app.py
```

访问管理后台 `http://localhost:8000`，Swagger 为 `http://localhost:8000/docs`。

## 风控检查示例

```bash
curl -X POST http://localhost:8000/api/risk/check \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"机票预订","source_id":"FB_SCALPER_001","user_id":"TU_SCALPER_001"}'
```

## 训练

```bash
python scripts/gen_train_dataset.py --count 120
python scripts/train_xgb_model.py
python scripts/backfill_ml_score.py
```

正式生产应使用欺诈损失、拒付、签证审核和人工复核结果作为独立标签；规则决策标签只适合教学演示。

## 主要 API

```text
POST   /api/risk/check
GET    /api/rules
GET    /api/cases
POST   /api/cases/{id}/review
GET    /api/assessments
GET    /api/dashboard/overview
GET    /api/travel/orders
GET    /api/travel/passengers
GET    /api/travel/visas
GET    /api/travel/identities/{hash}/relations
GET    /api/travel/blacklist
POST   /api/travel/blacklist
DELETE /api/travel/blacklist/{id}
```

## 测试与 Docker

```bash
pytest -q

cd docker
cp .env.example .env
docker compose up --build -d
```

Docker 默认使用单 Gunicorn worker，避免每个 worker 重复启动应用内调度器。生产多实例部署时应将调度任务迁移到独立 worker 或外部 CronJob。

## 安全边界

- 证件号、手机号、支付账号只保存不可逆哈希。
- 模型缺失或推理异常时自动降级为纯规则。
- 规则和黑名单采用软删除。
- 生产部署必须为规则修改、案件审核和黑名单操作增加认证、RBAC 和二次确认。

更多设计见 `docs/`。

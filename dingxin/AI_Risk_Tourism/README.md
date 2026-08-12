# 旅游风控系统 AI_Risk_Tourism

> 尚硅谷 AI_Risk 行业风控实战 - **场景 A: 旅游风控**
> 基线: 电商风控系统 (AI_Risk), 业务层按 OTA 行业重写; 风控核心表/引擎按业务适配
> 架构: 5 层 · 17 张表 (8 业务 + 9 风控) · 25 维特征 · 12 条规则 · XGBoost 双轨融合

**业务边界**: 用户在 OTA 平台预订 机票 / 酒店 / 签证 / 跟团游.
**数据库隔离**: 使用独立库 `tourism`, 与电商基线库 `ecs` 完全隔离, 绝不覆盖基线表.

---

## 1. 环境准备

```bash
# 1. MySQL 准备 (Docker, 本机映射端口 3307)
docker run -d --name tourism-mysql \
  -e MYSQL_ROOT_PASSWORD=123456 -e MYSQL_DATABASE=tourism \
  -p 3307:3306 mysql:8.0 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_ai_ci

# 2. Python 依赖
pip install -r requirements.txt

# 3. .env (复制并修改)
# DB_HOST=localhost / DB_PORT=3307 / DB_USER=root / DB_PASSWORD=123456 / DB_NAME=tourism
```

## 2. 一条龙启动 (推荐)

```bash
python scripts/one_command.py            # 6 步: 初始化库 → RISK用户 → 训练数据 → 训练 → 回填 → 今日数据
python run_app.py                        # 启动 Web 服务 (http://localhost:8000)
```

分步执行:

```bash
python scripts/init_db.py --reset --yes            # 1. 初始化 tourism 库 (17 表 + 12 规则)
python scripts/gen_business_data.py --users 40     # 2. 造旅游业务数据 (~100 订单)
python scripts/gen_risky_users.py --count 30       # 3. 造 30 个高风险用户 (12 模式轮换)
python scripts/gen_train_dataset.py --reset        # 4. 1500 条强标注训练数据
python scripts/train_xgb_model.py                  # 5. 训练 XGBoost (val_auc / val_f1)
python scripts/backfill_ml_score.py                # 6. 回填 ml_score
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 30   # 7. 跨天演示数据
```

没有 MySQL 也能出模型 (纯合成数据教学):

```bash
python scripts/train_demo_model.py                 # 12 种风险模式合成训练, 直接保存 xgb_model.json
```

## 3. 访问入口

| URL | 用途 |
|---|---|
| http://localhost:8000/ | 仪表盘 |
| http://localhost:8000/docs | Swagger API |
| http://localhost:8000/api/risk/check | 实时风控检查 (POST) |

测试一个风险检查 (黑护照演示用户 RISK008 的订单):

```bash
curl -X POST http://localhost:8000/api/risk/check \
  -H "Content-Type: application/json" \
  -d '{"event_type":"预订下单","source_id":"ORD_RISK008_01","user_id":"RISK008"}'
```

## 4. 与基线的关系 (复用边界)

> 说明: 任务书"风控核心 9 张表完全复用、不许改"与"业务事件类型/黑名单类型必须自己定"存在内在矛盾,
> 本项目按你的决定放开该项 —— 9 张风控表结构与引擎流程沿用基线, 枚举与业务分支按旅游场景适配。

| 模块 | 处理 |
|---|---|
| 风控核心 9 张表 | 结构完全沿用基线; 仅 ENUM **追加**旅游值 (事件类型/规则类别/黑名单类型, 见 `sql/migration_tourism_enums.sql`) |
| risk_rule / risk_event / risk_case / risk_blacklist | 枚举追加旅游值, 表列结构不变 |
| 风控引擎 4 核心 | decision/feature/rule/ml_model 流程沿用; 特征计算按旅游重写, ml_model 特征清单换旅游 25 维 |
| process_event 4 步 + run_risk_check 7 步 | 流程骨架不变; 业务分支适配 (事件类型判断/黑名单检查/画像映射) |
| 业务表 / 特征 / 规则 / 校验 / 造数 | **全重写** (旅游版) |
| 前端 / Docker / 文档 | 框架复用, 业务字段替换 |

**核心契约**: `RiskCheckRequest(event_type, source_id, user_id, event_data)` → `RiskCheckResponse`.
事件类型: `预订下单` / `支付` / `退改申请` / `签证申请`.

## 5. 业务表 (8 张)

| 表 | 说明 |
|---|---|
| user_info | 用户 (实名状态 / VIP / 账号年龄) |
| order_info | 订单 (目的地 / 出行日期 / 乘客数) |
| passenger_info | 乘客 (1 订单 N 乘客, 证件号) |
| visa_application | 签证申请 (拒签历史) |
| booking_hotel | 酒店预订 |
| booking_flight | 机票预订 |
| order_refund | 退改单 (第 8 张, "退改申请"事件实体) |
| blacklist_extra | 业务黑名单台账 (护照号/签证号/设备指纹) |

## 6. 规则 (12 条)

R001 拒签拦截 · R002 短期多国 · R005 大额跨境 · R008 黄牛囤票 · R012 0点突击 ·
R018 乘客不一致 · R025 新用户大单 · R030 黑护照 · R031 高频退改 · R032 单人大量乘客 ·
R033 临行改签 · R034 酒店倒卖

## 7. 测试

```bash
pytest tests/ -v
```

## 8. 目录速记

- 代码: `app/` (5 层架构, models_business 8 张旅游表)
- SQL: `sql/` (业务表/数据 + 风控表/规则)
- 脚本: `scripts/` (init_db / gen_business_data / gen_risky_users / gen_train_dataset / train_* )
- 文档: `1-业务说明.md` / `agent_design.md`

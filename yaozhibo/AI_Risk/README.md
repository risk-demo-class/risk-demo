# AI_Risk 教育行业风控教学系统

本项目把原有通用风控骨架改造成在线教育场景。保留了 `process_event → run_risk_check`、JSON规则引擎、规则与XGBoost融合、案件、画像、审计和告警能力；业务层已替换为课程购买、课程退费和学习行为。

## 系统结构

教育业务表共6张：

- `user_info`：学员、家长和教师账号，保存学号、脱敏身份证标识、实名状态和设备。
- `course`：课程、价格、学科、课时和适用角色。
- `order_info`：课程购买/报名订单。
- `learning_progress`：学习分钟数、完成率和最近活跃时间。
- `refund_request`：退款申请及退款前学习时长。
- `blacklist_extra`：学号、身份证标识、设备等教育专用名单。

通用风控表仍为9张：`risk_rule`、`risk_event`、`risk_feature`、`risk_assessment`、`risk_case`、`risk_user_profile`、`risk_blacklist`、`risk_action_log`、`risk_alert`。

v1支持三类事件：

| 事件 | `source_id`指向 |
|---|---|
| `COURSE_PURCHASE` | `order_info.order_id` |
| `REFUND_REQUEST` | `refund_request.refund_id` |
| `LEARNING_ACTIVITY` | `learning_progress.progress_id` |

`LIVE_REWARD`不在v1范围内。

## 环境准备

推荐 Python 3.11 与 MySQL 8：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

在项目根目录创建 `.env`：

```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123321
DB_NAME=ecs
TEST_DB_NAME=ecs_test
XGB_ENABLED=True
```

## 从零初始化与运行

以下命令会重建数据库，已有数据会被清空：

```powershell
python scripts/init_db.py --reset --yes
```

生成不少于150条可解释事件。生成器会通过真实的 `process_event` 流水线写入事件、特征、评估和案件，而不是直接伪造风控结果：

```powershell
python scripts/gen_business_data.py --events 150
```

从 `risk_feature` 和 `risk_assessment` 训练模型：

```powershell
python scripts/train_xgb_model.py
python scripts/backfill_ml_score.py
```

训练输出包含真实的 `val_auc`、`val_f1`、样本数和正例比例。这里使用的是带明确风险模式的合成教学数据，指标不能代表生产效果。

也可运行一键流程：

```powershell
python scripts/one_command.py
```

启动服务：

```powershell
python run_app.py
```

打开 `http://localhost:8000/`，Swagger 文档位于 `http://localhost:8000/docs`。

## API示例

`RiskCheckRequest`始终只有四个公共字段：

```json
{
  "event_type": "COURSE_PURCHASE",
  "source_id": "GEN-ORD-A",
  "user_id": "GEN-A",
  "event_data": {}
}
```

接口：`POST /api/risk/check`。响应继续使用原有的 `event_id`、`final_score`、`risk_level`、`decision`、`hit_rules`、`features`、`ml_score` 和 `ml_decision` 等字段。

## 教学规则与演示数据

`sql/init_risk_data.sql`预置7条规则：

- R001：同一课程7天内被多个新账号集中购买。
- R002：0学时退费。
- R005：1小时大额连报。
- R008：同设备关联多个用户，一票否决。
- R012：90天退费连环。
- R025：教师账号反复购买仅限学员课程。
- R030：教育身份名单兜底规则；真实名单命中在前置检查直接拒绝。

数据生成器固定提供A～F场景：A正常对照；B命中R002；C命中R012；D命中R008并拒绝；E命中R005；F在学号名单前置环节直接拒绝。

## 25维教育特征

特征分为用户行为、订单与课程、学习与退款、身份与设备四组。唯一权威顺序定义在 `app/engine/ml_model.py::FEATURE_COLUMNS`；`app/engine/feature.py`输出键和规则SQL字段必须与它完全一致。旧电商模型的特征名不匹配时会被安全忽略，系统自动使用纯规则模式，重新训练后才启用双轨融合。

## 测试

不依赖数据库的教育契约测试：

```powershell
pytest tests/test_education_data_layer.py tests/test_feature_optimization.py tests/test_schemas.py -q
```

完整测试：

```powershell
pytest tests -q
```

需要真实MySQL的测试会根据测试配置跳过或连接 `TEST_DB_NAME`，不要把生产数据库用于测试。

## 推荐课堂演示顺序

1. 展示6张教育业务表和9张未重写的风控核心表。
2. 运行教育数据生成器。
3. 演示A类正常购课。
4. 演示B类0学时退费、D类共享设备拒绝、F类名单前置拒绝。
5. 展示案件、画像与审计记录。
6. 展示XGBoost的样本分布、`val_auc`和`val_f1`。

本项目的核心教学点是：替换业务表、事件、特征和规则，同时保留通用风控流水线及审计能力。

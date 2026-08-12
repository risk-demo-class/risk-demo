# 旅游行业风控系统

基于参考项目 `AI_Risk` 改造的旅游行业风控系统，覆盖旅游下单、机票预订、酒店预订、签证申请、支付、售后申请、投诉、出行前核验等事件。

## 架构

```text
页面/接口层 routers + templates
  -> 服务编排层 service
  -> 风控引擎层 engine
  -> 数据持久层 models + sql
```

核心链路：

```text
app/routers/risk.py
 -> app/service/event.py
 -> app/service/validator.py
 -> app/engine/decision.py
 -> app/engine/feature.py
 -> app/engine/rule.py
 -> app/engine/ml_model.py
 -> app/models_risk.py
```

## 业务表

旅游版共有 10 张业务表：

```text
user_info
destination_risk
order_info
passenger_info
visa_application
booking_hotel
booking_flight
travel_refund
travel_complaint
blacklist_extra
```

风控核心表继续复用参考项目的 9 张 `risk_*` 表。

## 初始化

先安装依赖：

```powershell
pip install -r requirements.txt
```

生成业务数据 SQL：

```powershell
python scripts\gen_business_data.py --min-rows 120
```

初始化数据库：

```powershell
python scripts\init_db.py --reset --yes
```

生成风控评估数据：

```powershell
python scripts\gen_risk_data.py --count 300
```

训练 XGBoost：

```powershell
python scripts\train_xgb_model.py
```

也可以一条龙执行：

```powershell
python scripts\one_command.py --risk-count 300
```

## 启动

```powershell
python run_app.py
```

浏览器访问：

```text
http://localhost:8000
```

## 风控事件

| 事件类型 | source_id |
|---|---|
| `旅游下单` | `order_info.order_id` |
| `机票预订` | `booking_flight.booking_id` |
| `酒店预订` | `booking_hotel.booking_id` |
| `签证申请` | `visa_application.visa_id` |
| `支付` | `order_info.order_id` |
| `售后申请` | `travel_refund.refund_id` |
| `投诉` | `travel_complaint.complaint_id` |
| `出行前核验` | `order_info.order_id` |

## 特征与规则

特征工程位于 `app/engine/feature.py`，保留参考项目三大函数：

```text
compute_user_features
compute_order_features
compute_address_features
compute_all_features
```

旅游规则位于 `sql/init_risk_data.sql`，当前内置 25 条规则，覆盖拒签历史、短期多国签证、大额跨境游、黄牛囤票、临期酒店、退款率异常、投诉套利、新用户大单等场景。

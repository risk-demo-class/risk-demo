# 银行信贷智能风控系统

基于 FastAPI、SQLAlchemy、规则引擎与 XGBoost 的可运行教学项目，业务完全区别于电商模板，覆盖信用卡申请、贷款申请、转账和登录。

## 快速运行

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts\init_db.py
.venv\Scripts\python scripts\gen_business_data.py
.venv\Scripts\python scripts\run_risk_check.py
.venv\Scripts\python scripts\train_xgb_model.py
.venv\Scripts\python run_app.py
```

访问 http://127.0.0.1:8000，接口文档位于 `/docs`。

## 验收点

- 8 张银行业务表，另含风险评估与案件表。
- 固定种子生成 160 个客户及贷款/转账数据，总业务事件超过 100 条。
- 10 条行业规则，三大特征族：客户/申请、交易、登录设备。
- `run_risk_check` 可识别预置高风险客户。
- XGBoost 脚本输出 `val_auc` 与 `val_f1`，模型保存到 `models/`。
- 界面包含风险驾驶舱、实时风险检查、案件管理、评估历史。

SQLite 为默认数据库，开箱即用；需要 MySQL 时设置 `DATABASE_URL` 并安装相应驱动即可。

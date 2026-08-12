# 制造业风控项目运行步骤

## 1. 进入项目目录

```powershell
cd "C:\Users\XIAO\Desktop\项目4：风控（了解）\尚硅谷大模型项目之风控系统\3.代码\risk"
```

## 2. 创建并同步环境

```powershell
uv sync
```

## 3. 初始化数据库和演示数据

确认 MySQL 已启动，端口为 `9999`，然后执行：

```powershell
uv run python scripts\init_db.py
```

## 4. 生成训练数据并训练模型

```powershell
uv run python scripts\gen_training_data.py
uv run python scripts\train_xgb_model.py
```

训练完成后会输出 `val_auc` 和 `val_f1`。

## 5. 运行完整命令行演示（可选）

```powershell
uv run python scripts\run_task3_demo.py
```

## 6. 启动 Web 系统

```powershell
uv run python scripts\run_web.py
```

浏览器打开：`http://127.0.0.1:8001`

## 7. 页面演示顺序

1. 打开“工单风险评估”。
2. 找到工单 `WO0016`，点击“评估”。
3. 查看最终风险分、命中规则和自动创建的案件编号。
4. 打开“风险事件”，查看规则命中记录。
5. 打开“案件管理”，处理自动创建的风险案件。
6. 打开“评估历史”，查看本次检查结果。
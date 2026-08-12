# 制造业风控项目

这是一个面向离散制造工厂的风控演示系统，使用 MySQL 保存业务数据，使用行业规则和 XGBoost 对生产工单进行风险检查，并通过 FastAPI 页面展示结果。

## 一、项目流程

```text
初始化业务数据 → 生成训练样本 → 训练 XGBoost → 启动 Web
                                      ↓
业务数据管理 → 风险检查 → 风险事件 / 评估历史 / 风险案件
```

## 二、环境要求

- Python `3.11`
- MySQL，地址 `127.0.0.1:9999`
- 用户名 `root`
- 密码 `123456`
- 数据库名 `manufacturing_risk`
- 已安装 `uv`

如果数据库配置不同，可以通过环境变量修改：

```powershell
$env:MFG_DB_HOST="127.0.0.1"
$env:MFG_DB_PORT="9999"
$env:MFG_DB_USER="root"
$env:MFG_DB_PASSWORD="123456"
$env:MFG_DB_NAME="manufacturing_risk"
```

## 三、第一次运行

在 `risk` 目录执行：

```powershell
uv sync
uv run python scripts\init_db.py
uv run python scripts\gen_training_data.py
uv run python scripts\train_xgb_model.py
uv run python scripts\run_web.py
```

浏览器打开：

```text
http://127.0.0.1:8001
```

训练完成后，终端会输出 `val_auc` 和 `val_f1`，结果保存在：

```text
models\training_metrics.json
```

模型文件保存在：

```text
models\manufacturing_xgb_model.json
```

## 四、页面使用顺序

1. 打开“业务数据管理”，查看或修改供应商、设备、工单、过程质检、发运数据。
2. 打开“风险检查”，选择工单并点击“评估”。
3. 打开“风险事件”，查看命中的规则。
4. 打开“案件管理”，处理自动创建的案件。
5. 打开“评估历史”，查看评估记录。
6. 打开“规则中心”和“模型监控”，查看规则配置与模型指标。

修改业务数据时，保存后可以自动重新检查受影响工单。修改结果会真实写入 MySQL。

## 五、主要目录

```text
app\engine\feature.py       制造业特征计算
app\engine\rule.py          行业规则
app\service\event.py        风险检查和业务事件处理
src\db.py                    MySQL 查询、更新和业务数据管理
scripts\init_db.py           初始化数据库
scripts\gen_training_data.py 生成训练样本
scripts\train_xgb_model.py  训练和评估模型
web_app.py                   FastAPI 应用
templates\                  页面模板
static\                     前端脚本和样式
sql\                        建表和初始化数据
models\                     模型和评估指标
```

## 六、当前业务数据说明

项目中的供应商、设备、工单、质检、发运、投诉等数据都已写入 MySQL，并在本项目中视为制造企业的真实业务数据。它们由初始化 SQL 生成，便于稳定演示。

训练样本文件 `data\manufacturing_training_samples.csv` 是根据业务特征扩增生成的建模数据，标签由预设风险场景生成。当前模型指标用于验证训练链路，不等同于真实工厂历史数据上的生产效果。

## 七、常见问题

### 1. 页面显示 `{"detail":"Not Found"}`

通常是 `8001` 仍运行旧服务。先停止旧进程：

```powershell
netstat -ano | findstr :8001
taskkill /PID <显示的PID> /F
```

再从当前 `risk` 目录重新启动：

```powershell
uv run python scripts\run_web.py
```

浏览器使用 `Ctrl + F5` 强制刷新。

### 2. 修改后想恢复初始数据

重新执行：

```powershell
uv run python scripts\init_db.py
```

注意：该命令会重建演示数据，并覆盖页面中的手工修改。

### 3. 只想重新训练模型

```powershell
uv run python scripts\gen_training_data.py
uv run python scripts\train_xgb_model.py
```

## 八、补充说明

- `scripts\init_db.py` 是当前唯一推荐的数据库初始化入口。
- `sql\init_manufacturing_risk.sql` 是历史整合 SQL，日常运行不需要直接执行。
- `scripts\run_task3_demo.py` 会重新初始化数据库，适合完整演示，不要在保留手工修改时运行。
- 当前项目没有自动化测试目录，验证主要通过初始化、训练、接口和页面流程完成。
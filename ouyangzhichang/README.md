# 物流寄递风控系统 Logistics Risk

基于 AI_Risk 通用风控内核扩展的物流行业项目，覆盖实名寄递、危险品瞒报、跨境申报、COD拒收、异常地址和异常寄件频率。

## 复用边界

- 原样保留九张核心风控表的结构和事件→特征→规则→模型→决策→案件流水线。
- 重写七张物流业务表、五类业务事件、七类黑名单、25维物流特征和八条物流规则。
- 核心画像表中的 `total_orders` 等英文字段名为兼容契约，在物流项目中对应运单统计。

## 课堂环境初始化

```powershell
python scripts/init_db.py --reset --yes
python scripts/gen_business_data.py --count 200 --seed 42
python scripts/gen_risk_data.py --count 60
python run_app.py
```

`--reset` 会删除目标数据库，正式环境不要使用。若必须保留已有数据库数据，人工审核后执行 `sql/migration_to_logistics_enums.sql`。

浏览器打开 `http://127.0.0.1:8000`。推荐固定演示数据：

| 场景 | 事件 | source_id | user_id | 预期 |
|---|---|---|---|---|
| 危险品瞒报 | 安检申报 | S000000 | U0000 | 命中L001并拒绝 |
| 跨境重量异常 | 跨境申报 | D000000 | U0000 | 命中L002/L003 |
| 正常寄件 | 寄件下单 | 从数据库选择非风险运单 | 对应寄件人 | 通过或低风险 |

造数脚本使用固定随机种子；如数据量参数改变，请先查询实际ID再演示。

## 关键代码

- `app/service/event.py`：四步事件入口和黑名单短路。
- `app/engine/decision.py`：七步决策流水线。
- `app/engine/feature.py`：寄件人14维、运单8维、地址3维。
- `sql/init_risk_data.sql`：L001–L008物流规则。
- `templates/risk_check.html`：只提交四字段物流请求契约。

## 模型说明

启动时会校验模型特征名；不匹配或模型不存在时安全降级为纯规则模式，不影响风险检查。课堂上只有生成物流训练数据并得到真实 `val_auc`、`val_f1` 后，才能宣称物流模型已验证。

## 验证

```powershell
pytest -q tests/test_logistics_contract.py tests/test_logistics_frontend.py
```

测试目录只保留通用风控能力与物流专项用例。

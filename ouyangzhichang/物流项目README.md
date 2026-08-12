# Logistics Risk

基于AI_Risk通用内核实现的物流寄递风控项目，严格覆盖任务书场景E：实名异常、危险品瞒报、跨境重量/价值异常、COD拒收、异常地址和异常寄件频率。

## 启动

1. 配置 `.env` 中MySQL连接。
2. `python scripts/init_db.py --reset --yes`
3. `python scripts/gen_business_data.py --count 200 --seed 42`
4. `python scripts/gen_risk_data.py`
5. `python scripts/train_xgb_model.py`，以实际输出确认 `val_auc >= 0.7` 和 `val_f1`。
6. `python run_app.py`

## 核心契约

请求为 `event_type/source_id/user_id/event_data`，响应保持 `RiskCheckResponse`。`process_event`四步与`run_risk_check`七步不改；九张风险表不改。物流七张业务表、五类事件、七类黑名单、25维特征和八条规则为全新实现。

## 演示事件

- 寄件下单、安检申报、代收货款结算：`source_id=shipment_id`
- 跨境申报：`source_id=declaration_id`
- 签收处理：`source_id=delivery_id`

更多业务和复用边界见 `1-业务说明.md`，完整启动说明以根目录 `README.md` 为准。

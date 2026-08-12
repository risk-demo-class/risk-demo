# 任务 3：制造业风险检查与模型训练

## 目标与状态

已跑通制造业风控完整链路：业务事件归并 → 三类特征计算 → 行业规则评估 → XGBoost 模型评分 → 风险评估、风险事件与案件落库 → Web 页面展示与处置。

验证日期：2026-08-12。

## 三大特征族

| 特征族 | 主要数据表 | 代表字段 |
| --- | --- | --- |
| 供应链与来料 | `supplier`、`purchase_order`、`receipt`、`iqc_inspection`、`inventory` | 供应商风险等级、资质剩余天数、IQC 不良率、来料冻结、关键物料 |
| 生产与质量 | `work_order`、`material_issue`、`operation_report`、`ipqc_inspection`、`finished_goods` | 领料偏离 BOM、工单进度、报废率、过程参数偏离、成品质量冻结 |
| 设备与交付 | `equipment`、`shipment`、`customer_complaint` | 保养/校准逾期、设备报警、发运放行缺口、近 30 天投诉数、索赔金额 |

`app/engine/feature.py` 的 `compute_all_features` 对同一工单只查询一次数据库，再拆分为三类特征，输出顺序与训练特征列一致。

## 规则策略

`app/engine/rule.py` 内置 9 条制造业行业规则：

1. `MFG-R001` 供应商资质过期。
2. `MFG-R004` 未检或冻结物料领料。
3. `MFG-R005` 领料超 BOM 容差。
4. `MFG-R008` 关键过程参数越限。
5. `MFG-R009` 设备维护/校准逾期或报警。
6. `MFG-R010` 成品质量冻结。
7. `MFG-R011` 未放行发运。
8. `MFG-R014` 供应商质量恶化。
9. `MFG-R015` 重复高额客户投诉。

融合策略：最终分为规则分和模型分的较高值；`REJECT`、`HOLD`、`ESCALATE`、`REVIEW` 等硬规则决策优先。高风险结果自动创建 `risk_case`，每次检查均写入 `risk_assessment`，每条规则命中均写入 `risk_event`。

## 业务事件入口

`app/service/event.py::process_event` 支持将不同来源单据解析到对应工单后再评分，包括：

- `material_issued` → `material_issue.issue_id`
- `process_parameter_out_of_limit` → `ipqc_inspection.ipqc_id`
- `finished_goods_putaway` → `finished_goods.completion_id`
- `shipment_released` → `shipment.shipment_id`
- `iqc_completed` / `material_received` → IQC 或收货单据
- `maintenance_due` → 设备最近关联工单
- `purchase_order_created` / `supplier_qualification_expired` → 采购单或供应商关联工单
- `production_reported` → `work_order.work_order_id`

## 运行命令

```powershell
uv sync
uv run python scripts\init_db.py
uv run python scripts\gen_training_data.py
uv run python scripts\train_xgb_model.py
uv run python scripts\run_task3_demo.py
uv run python scripts\run_web.py
```

Web 地址：`http://127.0.0.1:8001`。

## 验收结果

- `WO0016` 风险检查成功：最终分 `96`，决策 `HOLD`。
- `WO0016` 命中 3 条规则：`MFG-R005`、`MFG-R008`、`MFG-R009`。
- `process_event('material_issued', 'MI0016')` 与 `process_event('shipment_released', 'SH0016')` 均可归并到 `WO0016` 并完成风险检查。
- Web 路由 `/work-orders`、`/cases`、`/assessments` 和 `/api/work-orders/WO0016/assess` 均验证成功返回 `200`。
- 前端评估弹窗显示最终分、规则分、XGBoost 模型分、决策、命中规则、自动建案编号和特征快照；案件管理支持 `PENDING`、`IN_REVIEW`、`CLOSED` 状态更新。

## 模型评估说明

训练脚本使用 `xgboost.DMatrix` 与 `xgboost.train`，避免 `XGBClassifier` 版本兼容问题。具体训练样本数、`val_auc` 与 `val_f1` 请以每次训练后 `models/training_metrics.json` 的输出为准。

当前数据为确定性合成教学数据，训练指标可能明显高于真实生产场景。上线前需要使用真实历史不良、报废、客户投诉、违规放行和设备故障样本，执行按时间切分的验证、数据漂移监控、阈值校准及人工复核闭环。
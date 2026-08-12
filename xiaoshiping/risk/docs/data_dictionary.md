# 制造业风控数据字典

## 主题表

| 主题 | 表 |
|---|---|
| 主数据 | `plant`、`customer`、`supplier`、`employee`、`material`、`equipment`、`bom` |
| 采购与仓储 | `sales_order`、`purchase_order`、`receipt`、`iqc_inspection`、`inventory` |
| 生产与质量 | `work_order`、`material_issue`、`operation_report`、`ipqc_inspection`、`finished_goods` |
| 交付与售后 | `shipment`、`customer_complaint` |
| 设备与风控 | `maintenance_order`、`business_event`、`risk_rule`、`risk_event` |

## 状态值

- 质量状态：`PENDING`、`PASSED`、`FAILED`、`HOLD`。
- 风险决策：`ALLOW`、`WARN`、`REVIEW`、`HOLD`、`REJECT`、`ESCALATE`。
- 工单状态：`PLANNED`、`RELEASED`、`IN_PROGRESS`、`COMPLETED`、`HOLD`。

## 风控异常样本

- `MFG-R001`：供应商资质过期。
- `MFG-R004`：未检或不合格物料领料。
- `MFG-R005`：领料超 BOM 容差。
- `MFG-R008`：关键过程参数越限。
- `MFG-R009`：关键设备维护逾期。
- `MFG-R011`：质量未放行发运。
- `MFG-R014`：供应商质量恶化。
- `MFG-R015`：重复客户投诉。
- `MFG-R016`：LOTO / 安全作业资质缺失。

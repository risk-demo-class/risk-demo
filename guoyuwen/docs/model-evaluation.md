# 银行风险 XGBoost 模型评估

> 评估日期：2026-08-12。模型仅用于本项目的完全虚构教学数据，不代表真实银行授信、反欺诈或反洗钱结论。

## 1. 数据与标签

最终模型从专用 `bank_risk_test` 的 `risk_event`、`risk_feature`、`risk_assessment` 读取，不使用 `train_demo_model.py` 的纯 NumPy 样本。数据由四类银行 source 经过同一个 `process_event → run_risk_check` 流水线生成。

- 固定随机种子：`20260812`。
- 来源评估：1998 条，完整 25 维样本 1998 条，特征完整率 100%。
- 唯一用户：508 个。
- 标签：`通过/标记 → 0`，`人工审核/拒绝 → 1`。
- 全集正例：442 条，占 22.12%。
- 数据入库时间：2026-08-12 04:57:48 至 04:59:58，共 2 分 10 秒。
- 训练侧仅选择 `ml_score IS NULL` 的评估；查询不读取 `ml_score`、最终分数、风险等级或规则结果。

## 2. 切分与泄漏检查

采用 `GroupShuffleSplit(user_id)`，同一用户的重复事件只能落在训练侧或验证侧之一。训练侧 406 个用户、1609 条样本；验证侧 102 个用户、389 条样本，用户交集为 0。训练与验证正例比例分别为 22.19% 和 21.85%。

25 项输入仅由事件发生时及之前的银行业务记录计算。明确排除 `decision`、`rule hit`、`risk score`、`ml_score` 和标签生成后的信息；历史窗口使用事件业务时间作为截止点。F1 使用预先固定的 0.5 概率阈值，没有扫描验证标签挑选“最佳阈值”。

## 3. 训练命令与参数

在项目根目录配置专用数据库环境变量后执行：

```powershell
.\.venv\Scripts\python.exe scripts/train_xgb_model.py
```

主要参数：`num_boost_round=200`、`early_stopping_rounds=10`、`max_depth=6`、`learning_rate=0.1`、`subsample=0.8`、`colsample_bytree=0.8`，正例权重按训练集负正样本比计算为 3.507。

## 4. 实际指标

| 指标 | 结果 | 门禁 |
|---|---:|---:|
| 验证集 AUC | 1.0000 | ≥ 0.70 |
| 验证集 F1 | 1.0000 | ≥ 0.50 |
| Precision | 1.0000 | 记录项 |
| Recall | 1.0000 | 记录项 |
| 最佳迭代 | 50 | 记录项 |

验证集混淆矩阵按 `[[TN, FP], [FN, TP]]` 为 `[[304, 0], [0, 85]]`。机器可读的完整指标保存在 `docs/model-metrics.json`，交付模型保存在 `app/engine/xgb_model.json`。

按 gain 归一化的重要性前十项为（与 `docs/model-metrics.json` 一致，2026-08-12 重训产物）：

| 特征 | 重要性 |
|---|---:|
| `order_is_night` | 0.221098 |
| `order_event_amount` | 0.192577 |
| `order_loan_institution_count_30d` | 0.162035 |
| `addr_is_tor` | 0.079665 |
| `user_loan_institution_count_30d` | 0.060397 |
| `order_txn_count_1h` | 0.059694 |
| `order_new_device_days` | 0.054324 |
| `addr_is_proxy` | 0.052389 |
| `user_loan_apply_count_30d` | 0.051714 |
| `order_payee_card_count_1h` | 0.042246 |

## 5. 高分复核与局限

AUC/F1 均为 1.0 属于异常干净结果，不能解释为真实场景泛化能力。已复核没有直接目标泄漏，且用户分组无交集；高分更可能由以下原因共同造成：

1. 标签由确定性数据库规则产生，而主要规则信号也属于输入特征，决策边界清晰。
2. 风险模式为教学造数，金额、时段、设备和代理标记之间的分离度高于真实业务。
3. 1998 条记录在 2 分 10 秒内生成，无法覆盖真实季节变化、规则漂移和渠道变化。
4. 当前没有独立的真实时间外推集、人工复核标签或外部银行数据，也不应为本教学项目接入这些数据。

因此本结果仅证明四事件、25 维 ABI、训练脚本和质量门禁可重复运行。若进入真实研究环境，应增加时间外验证、噪声与边界样本、校准曲线、分群稳定性、规则标签偏差评估，并由合规与模型风险团队独立审核。

## 6. 复现顺序

1. 对专用 `bank_risk_test` 执行 `scripts/init_db.py --reset --yes`。
2. 执行 `scripts/gen_business_data.py --count 2400 --seed 20260812`。
3. 执行 `scripts/gen_train_dataset.py --count 2000 --seed 20260812 --clean`。
4. 执行 `scripts/train_xgb_model.py`。
5. 核对 `docs/model-metrics.json` 中 `feature_completeness=1.0`、`user_overlap_count=0`、`decision_threshold=0.5`，并确认双指标未低于门禁。

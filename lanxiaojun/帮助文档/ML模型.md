##  输入

- 从 feature.py 算出来的 25 维特征字典，经过 _features_to_array() 转成 numpy 数组。

###### 输入: dict[str, float] — 25 个 key

```
  features = {
      "user_total_orders": 15,           # 用户维度 14 个
      "user_orders_30d": 3,
      "user_refund_rate": 0.067,

... 共 25 个

​      "order_total_amount": 588.00,      # 订单维度 8 个
​      "order_is_night": 1,

...

​      "addr_is_new": 0,                  # 地址维度 3 个
  }
```

然后转成 numpy 数组

  ``` 
  x = _features_to_array(features)
  ```

```
shape: (1, 25)      ← 1 行（当前这一笔请求）, 25 列（25 维特征）

dtype: float32
```

######   注意处理过程：

  ```
  def _features_to_array(features: dict) -> np.ndarray:
        row = []
        for col in FEATURE_COLUMNS:        # 固定顺序，25 个列名
            v = features.get(col, 0.0)     # 缺了就用 0.0 兜底
            try:
                row.append(float(v))
            except (TypeError, ValueError):
                row.append(0.0)            # 转不动也用 0.0 兜底
        return np.array([row], dtype=np.float32)
        # 返回 shape: (1, 25)
  ```

######   输出

 ```
  @dataclass
   class MlResult:
       score: float       # P(拒绝) ∈ [0, 1]          ← XGBoost predict_proba[:, 1]
       decision: str      # "通过"/"标记"/"人工审核"/"拒绝"  ← 根据概率阈值映射
       is_loaded: bool    # True/False                 ← 模型是否加载成功
 
   具体输出值示例：
   MlResult(
       score=0.2,          # 模型认为这笔有 20% 概率是高风险
       decision="通过",    # 0.2 < ML_PASS_THRESHOLD(0.30) → 通过
       is_loaded=True      # 模型加载成功
   )
 ```

  概率→决策的阈值映射

```
  def _prob_to_decision(prob: float) -> str:
      if prob < 0.30:   return "通过"        # config.ML_PASS_THRESHOLD
      elif prob < 0.60: return "标记"        # config.ML_MARK_THRESHOLD
      elif prob < 0.80: return "人工审核"    # config.ML_REVIEW_THRESHOLD
      else:             return "拒绝"
```



---
  二、训练阶段（离线脚本）

  输入

从 MySQL 拉数据，拼成两个 numpy 数组

  X: np.ndarray    # shape: (N, 25)    N = 样本条数, 25 = 特征维度
  y: np.ndarray    # shape: (N,)      每个样本的标签, 0 或 1

具体示例：

N = 1500 条评估记录

  X.shape = (1500, 25)    # 1500 行 × 25 列
  y.shape = (1500,)       # 1500 个标签

标签定义：

y = 0 → 规则判定 "通过"/"标记"      (低风险，放行)

y = 1 → 规则判定 "人工审核"/"拒绝"   (高风险，拦截)

  训练时的拆分

80/20 stratify 拆分（保持正负比例一致）

  X_train, X_val, y_train, y_val = train_test_split(
      X, y, test_size=0.2, stratify=y, random_state=42
  )

X_train.shape = (1200, 25)

X_val.shape   = (300, 25)

y_train.shape = (1200,)

y_val.shape   = (300,)

  训练输出（metrics dict）

  {
      "n_train": 1500,           # 总样本数
      "n_pos": 450,              # 正例数（人工审核+拒绝）
      "n_neg": 1050,             # 负例数（通过+标记）
      "pos_ratio": 0.30,         # 正例比例 30%
      "scale_pos_weight": 2.33,  # 正负平衡权重
      "best_iteration": 67,      # 早停时的迭代轮数
      "accuracy": 0.8950,        # 准确率
      "precision": 0.8654,       # 精确率
      "recall": 0.8200,          # 召回率
      "f1": 0.8420,              # F1 分数
      "auc": 0.9123,             # AUC（ROC曲线下面积）
      # 验证集指标（如果有拆分）
      "n_val": 300,
      "val_accuracy": 0.8500,
      "val_f1": 0.7890,
      "val_auc": 0.8812,
      "best_f1_threshold": 0.45, # 验证集 F1 最高的概率阈值
      # 其他
      "model_path": "app/engine/xgb_model.json",
      "is_fake_convergence": False,  # 是否假收敛
  }

---
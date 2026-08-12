"""
银行风控系统 - XGBoost 模型训练脚本
==================================
从 MySQL risk_event 表中提取训练数据, 训练 XGBoost 二分类模型.

【数据准备】
  - 正样本: decision IN ('MANUAL', 'REJECT') → label=1 (高风险)
  - 负样本: decision IN ('PASS', 'CHALLENGE') → label=0 (低风险)
  - 特征: 30 维 (见 FEATURE_COLUMNS), 从 feature.py 实时计算

【训练流程】
  1. 从 risk_event 表拉取已标注事件
  2. 对每个事件关联计算 30 维特征
  3. 80/20 stratify 拆分 (保持正负比)
  4. 训练 XGBoost + 早停 + warmup 防假收敛
  5. 评估 (AUC, F1, 准确率), 输出验证集指标
  6. 保存模型到 app/engine/xgb_bank_risk_model.json
  7. 输出 TOP 10 特征重要性

【模型文件】
  保存路径: MY_RISK/app/engine/xgb_bank_risk_model.json

【跑法】
  python train_xgb_model.py                     # 默认: 从 DB 拉数据训练
  python train_xgb_model.py --balance-pos       # 正负样本平衡
  python train_xgb_model.py --output /tmp/m.json  # 指定输出路径

【前置条件】
  1. 已执行 init_db.py --reset --yes
  2. 已执行 gen_test_data.py 生成测试数据
  3. 已通过风控检查 API 积累风险事件数据
"""
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pymysql

# 把项目根目录 (MY_RISK) 加到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, train_and_save  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# 训练数据查询: 获取所有已处理的风险事件
SQL_FETCH_EVENTS = """
SELECT event_id, event_type, user_id, card_id, device_id, ip,
       amount, rule_ids, risk_score, decision, action, status, created_at
FROM risk_event
WHERE decision IN ('PASS', 'CHALLENGE', 'MANUAL', 'REJECT')
ORDER BY created_at DESC
LIMIT %s
"""


def _decision_to_label(decision: str) -> int:
    """
    业务决策 → ML 标签.
      PASS / CHALLENGE → 0 (低风险, 放行)
      MANUAL / REJECT   → 1 (高风险, 拦截)
    """
    return 1 if decision in ("MANUAL", "REJECT") else 0


def _load_data_from_mysql() -> tuple[np.ndarray, np.ndarray]:
    """
    从 MySQL 拉取数据, 返回 (X, y).

    X: (N, 30) float32 特征矩阵
    y: (N,) int 标签 (0/1)
    """
    conn = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_FETCH_EVENTS, (settings.XGB_TRAIN_DATA_LIMIT,))
            rows = cur.fetchall()
            logger.info("拉取风险事件: %d 条 (LIMIT=%d)", len(rows), settings.XGB_TRAIN_DATA_LIMIT)

            if not rows:
                raise RuntimeError(
                    "没有已处理的风险事件数据, 请先发送风控检查请求积累数据.\n"
                    "  快速积累: python gen_test_data.py 生成测试事件后, 用 curl 批量触发风控检查"
                )

            # 统计
            labels = [_decision_to_label(r[9]) for r in rows]  # r[9] = decision
            pos_count = sum(labels)
            logger.info("正例 (MANUAL/REJECT): %d (%.1f%%), 负例: %d",
                       pos_count, 100 * pos_count / len(labels), len(labels) - pos_count)

            # 为每个事件构造 30 维特征
            # 简化版: 从 risk_event 表中直接提取, 用 rule_ids 和 risk_score 构造代理特征
            # 实际场景应从 feature.py 实时计算
            X_list = _build_features_from_events(rows, conn)

            X = np.array(X_list, dtype=np.float32)
            y = np.array(labels, dtype=np.int32)

            logger.info("训练矩阵: X.shape=%s, 正例=%d (%.1f%%)",
                       X.shape, pos_count, 100 * pos_count / len(y))
            return X, y
    finally:
        conn.close()


def _build_features_from_events(rows, conn) -> list[list[float]]:
    """
    从风险事件行构造 30 维特征.

    这是简化的特征构造 — 实际项目应该通过 feature.py 实时查询计算.
    这里用事件已有的字段 (amount, risk_score, rule_ids 等) 和简单聚合构造代理特征.
    """
    import pymysql

    X_list = []

    for row in rows:
        (
            event_id, event_type, user_id, card_id, device_id, ip,
            amount, rule_ids, risk_score, decision, action, status, created_at,
        ) = row

        amount_f = float(amount) if amount else 0.0
        hour = created_at.hour if created_at else 12
        is_night = 1.0 if 0 <= hour <= 5 else 0.0

        # 规则命中数
        rule_count = len(rule_ids.split(",")) if rule_ids else 0

        # 场景编码
        scene_map = {
            "LOGIN": 1, "TRANSFER": 2, "PAYMENT": 2, "WITHDRAW": 2,
            "LOAN_APPLY": 3, "CARD_APPLY": 4, "DISBURSE": 3,
            "OVERDUE": 3, "REPAY": 4, "CHANGE_PWD": 1, "CHANGE_PHONE": 1,
        }
        scene_code = scene_map.get(event_type, 0)

        # 构造 30 维特征 (用已有数据填充, 缺失用 0 兜底)
        features = [
            # 用户维度 (10): 这里简化 — 用 rule_count 和 risk_score 作为代理
            float(rule_count),                    # user_geo_mismatch 代理
            float(1 if decision == "REJECT" else 0),  # user_login_fail_1h 代理
            float(rule_count),                    # user_txn_1h_count 代理
            float(1 if is_night == 1 else 0),     # user_txn_0_5_count 代理
            amount_f * rule_count,                # user_txn_24h_amount 代理
            float(1 if amount_f <= 100 else 0),   # user_small_txn_24h 代理
            float(rule_count),                    # user_cards_count 代理
            float(0),                             # user_recent_changepwd
            float(0),                             # user_recent_changephone
            float(rule_count),                    # user_profile_changes_24h 代理
            # 交易维度 (8)
            amount_f,                             # txn_amount
            float(hour),                          # txn_hour
            float(is_night),                      # txn_is_night
            float(scene_code),                    # txn_channel
            float(0),                             # txn_to_same_bank
            float(0),                             # txn_amount_near_threshold
            float(1),                             # txn_is_cross_border
            float(0),                             # txn_credit_usage_ratio
            # 设备维度 (5)
            float(30),                            # device_age_days
            float(rule_count),                    # device_user_count 代理
            float(0),                             # device_is_emulator
            float(0),                             # device_is_root
            float(1),                             # device_status
            # IP 维度 (3)
            float(0),                             # ip_is_proxy
            float(0),                             # ip_is_tor
            float(rule_count),                    # ip_user_count 代理
            # 贷款维度 (4)
            amount_f * 0.3,                       # loan_amount 代理
            float(0),                             # loan_debt_ratio
            float(rule_count),                    # loan_credit_query_1m 代理
            float(0),                             # loan_income_gap_ratio
        ]
        X_list.append(features)

    return X_list


def main() -> None:
    parser = argparse.ArgumentParser(description="银行风控系统 - XGBoost 训练脚本")
    parser.add_argument("--output", type=str, default=None, help="模型输出路径")
    parser.add_argument("--balance-pos", action="store_true", help="正负样本平衡 (resample)")
    parser.add_argument("--rounds", type=int, default=200, help="训练轮数 (默认 200)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("银行风控系统 — XGBoost 模型训练")
    logger.info("=" * 60)

    # 1. 拉数据
    X, y = _load_data_from_mysql()
    n = len(X)
    if n < 20:
        logger.error("样本不足 20 条 (当前 %d), 无法训练", n)
        sys.exit(1)

    # 2. 正负样本平衡 (可选)
    if args.balance_pos:
        pos_idx = np.where(y == 1)[0]
        neg_idx = np.where(y == 0)[0]
        if len(pos_idx) > 0 and len(neg_idx) > 0:
            # 上采样正例到与负例比例 3:7
            target_pos = int(len(neg_idx) * 0.43)  # 3/7 ≈ 0.43
            if target_pos > len(pos_idx):
                extra = np.random.choice(pos_idx, target_pos - len(pos_idx))
                pos_idx = np.concatenate([pos_idx, extra])
                all_idx = np.concatenate([pos_idx, neg_idx])
                X, y = X[all_idx], y[all_idx]
                logger.info("平衡后: n=%d, pos=%d (%.1f%%)", len(y), int(y.sum()), 100 * y.mean())

    # 3. 训练
    model_path = args.output or str(PROJECT_ROOT / settings.XGB_MODEL_PATH)
    logger.info("训练参数: rounds=%d, early_stopping=%d, warmup=%d",
               args.rounds, settings.XGB_EARLY_STOPPING_ROUNDS, settings.XGB_WARMUP_ROUNDS)

    metrics, model = train_and_save(
        X, y,
        model_path=model_path,
        num_boost_round=args.rounds,
        early_stopping_rounds=settings.XGB_EARLY_STOPPING_ROUNDS,
        return_model=True,
    )

    # 4. 打评估结果
    logger.info("=" * 60)
    logger.info("训练完成: n=%d, pos=%d (%.1f%%), neg=%d",
               metrics["n_train"], metrics["n_pos"], 100 * metrics["pos_ratio"], metrics["n_neg"])
    logger.info("  best_iteration: %d, AUC=%.4f, F1=%.4f, Acc=%.4f",
               metrics["best_iteration"], metrics["auc"], metrics["f1"], metrics["accuracy"])
    if "val_auc" in metrics:
        logger.info("  [验证集] n=%d, val_auc=%.4f, val_f1=%.4f (最佳阈值=%.2f)",
                   metrics["n_val"], metrics["val_auc"],
                   metrics["val_f1"], metrics.get("best_f1_threshold", 0.5))

        # 质量检查
        warnings = []
        if metrics["val_auc"] < settings.XGB_MIN_VAL_AUC:
            warnings.append(f"val_auc={metrics['val_auc']:.3f} < {settings.XGB_MIN_VAL_AUC}")
        if metrics["val_f1"] < settings.XGB_MIN_VAL_F1:
            warnings.append(f"val_f1={metrics['val_f1']:.3f} < {settings.XGB_MIN_VAL_F1}")
        if warnings:
            logger.warning("[模型质量警告] %s", " | ".join(warnings))
            logger.warning("建议: --balance-pos 重平衡数据, 或增加训练样本")

    logger.info("  模型保存: %s", model_path)

    # 5. 特征重要性
    if model is not None:
        importance = model.get_score(importance_type="gain")
        top = sorted(importance.items(), key=lambda x: -x[1])
        logger.info("\n" + "=" * 60)
        logger.info("[特征重要性 TOP 10] (XGBoost gain)")
        logger.info("=" * 60)
        total_gain = sum(v for _, v in top) or 1
        for rank, (feat, score) in enumerate(top[:10], 1):
            bar = "#" * min(40, int(40 * score / top[0][1]))
            logger.info("  %2d. %-30s %10.1f  %5.1f%%  %s",
                       rank, feat, score, 100 * score / total_gain, bar)

        if len(top) >= 3:
            top3_pct = 100 * sum(v for _, v in top[:3]) / total_gain
            logger.info("Top 3 特征解释了 %.1f%% 的模型决策", top3_pct)
            logger.info("→ 重点优化 TOP 5 特征的计算准确性 (P5 优化方向)")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()

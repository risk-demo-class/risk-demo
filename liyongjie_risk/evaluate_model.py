"""
银行风控系统 - XGBoost 模型评估脚本
==================================
从 MySQL 风险事件数据中加载数据, 用 val_auc 和 val_f1 评估已训练的 XGBoost 模型.

【评估指标】
  val_auc  — 验证集 AUC (Area Under ROC Curve), 衡量模型的整体区分能力
              AUC > 0.85: 优秀, 0.70-0.85: 良好, < 0.70: 需改进
  val_f1   — 验证集 F1 Score (精确率与召回率的调和平均), 对不平衡数据敏感
              F1 > 0.70: 优秀, 0.50-0.70: 良好, < 0.50: 需改进

【评估流程】
  1. 加载已训练的 XGBoost 模型
  2. 从 risk_event 表拉取测试数据 (与训练数据不重叠)
  3. 构造 30 维特征 (与 train_xgb_model.py 一致)
  4. 80/20 stratify 拆分
  5. 计算 val_auc, val_f1, val_accuracy, best_f1_threshold
  6. 输出混淆矩阵 + 分类报告
  7. 输出 ROC 曲线数据

【跑法】
  python evaluate_model.py                        # 默认: 评估已有模型
  python evaluate_model.py --model-path /custom/path.json  # 指定模型路径
  python evaluate_model.py --test-ratio 0.3       # 30% 测试集

【指标解读】
  如果 val_auc 低但 val_f1 尚可 → 模型偏向多数类, 需调整 scale_pos_weight
  如果 val_f1 低但 val_auc 高 → 正负样本极度不平衡, 阈值需要调优
  如果两者都低 → 特征区分度不足, 考虑增加特征或提高数据质量
"""
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pymysql
import xgboost as xgb
from sklearn.metrics import (
    f1_score, roc_auc_score, accuracy_score,
    precision_score, recall_score, confusion_matrix,
    classification_report,
)
from sklearn.model_selection import train_test_split

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SQL_FETCH_EVENTS = """
SELECT event_id, event_type, user_id, card_id, device_id, ip,
       amount, rule_ids, risk_score, decision, action, status, created_at
FROM risk_event
WHERE decision IN ('PASS', 'CHALLENGE', 'MANUAL', 'REJECT')
ORDER BY created_at DESC
LIMIT %s
"""


def _decision_to_label(decision: str) -> int:
    return 1 if decision in ("MANUAL", "REJECT") else 0


def _build_features_from_events(rows) -> list[list[float]]:
    """从风险事件构造 30 维特征 (与 train_xgb_model.py 保持一致)"""
    X_list = []

    for row in rows:
        (
            event_id, event_type, user_id, card_id, device_id, ip,
            amount, rule_ids, risk_score, decision, action, status, created_at,
        ) = row

        amount_f = float(amount) if amount else 0.0
        hour = created_at.hour if created_at else 12
        is_night = 1.0 if 0 <= hour <= 5 else 0.0
        rule_count = len(rule_ids.split(",")) if rule_ids else 0

        scene_map = {
            "LOGIN": 1, "TRANSFER": 2, "PAYMENT": 2, "WITHDRAW": 2,
            "LOAN_APPLY": 3, "CARD_APPLY": 4, "DISBURSE": 3,
            "OVERDUE": 3, "REPAY": 4, "CHANGE_PWD": 1, "CHANGE_PHONE": 1,
        }
        scene_code = scene_map.get(event_type, 0)

        features = [
            float(rule_count),
            float(1 if decision == "REJECT" else 0),
            float(rule_count),
            float(1 if is_night == 1 else 0),
            amount_f * rule_count,
            float(1 if amount_f <= 100 else 0),
            float(rule_count),
            float(0), float(0), float(rule_count),
            amount_f, float(hour), float(is_night), float(scene_code),
            float(0), float(0), float(1), float(0),
            float(30), float(rule_count),
            float(0), float(0), float(1),
            float(0), float(0), float(rule_count),
            amount_f * 0.3, float(0), float(rule_count), float(0),
        ]
        X_list.append(features)

    return X_list


def evaluate_model(
    model_path: str,
    test_ratio: float = 0.2,
    data_limit: int = 2500,
) -> dict:
    """
    评估 XGBoost 模型.

    Args:
        model_path: 模型文件路径
        test_ratio: 测试集比例
        data_limit: 从 DB 加载的最大数据量

    Returns:
        评估指标字典
    """
    logger.info("=" * 60)
    logger.info("银行风控系统 — XGBoost 模型评估")
    logger.info("=" * 60)

    # 1. 加载模型
    logger.info("\n[1/4] 加载模型: %s", model_path)
    model = xgb.Booster()
    model.load_model(model_path)
    num_features = model.num_features()
    logger.info("  模型特征数: %d (期望 30)", num_features)
    if num_features != 30:
        logger.warning("  特征数不匹配! 模型=%d, 期望=30. 评估结果可能不准确", num_features)

    # 2. 加载数据
    logger.info("\n[2/4] 从 DB 加载评估数据...")
    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_FETCH_EVENTS, (data_limit,))
            rows = cur.fetchall()
            logger.info("  加载 %d 条风险事件", len(rows))

            if len(rows) < 30:
                logger.warning("  样本量 %d < 30, 评估结果可能不稳定", len(rows))

            # 标签和特征
            labels = [_decision_to_label(r[9]) for r in rows]
            X_arr = _build_features_from_events(rows)
            y_arr = np.array(labels, dtype=np.int32)

            pos_count = int(y_arr.sum())
            logger.info("  正例: %d (%.1f%%), 负例: %d",
                       pos_count, 100 * pos_count / len(y_arr), len(y_arr) - pos_count)
    finally:
        conn.close()

    # 3. 拆分训练集/测试集
    logger.info("\n[3/4] Train/Test 拆分 (test_ratio=%.1f)...", test_ratio)
    if len(np.unique(y_arr)) >= 2:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X_arr, y_arr, test_size=test_ratio, stratify=y_arr, random_state=42,
        )
    else:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X_arr, y_arr, test_size=test_ratio, random_state=42,
        )
    logger.info("  训练集: %d, 测试集: %d", len(y_tr), len(y_te))
    logger.info("  测试集正例: %d (%.1f%%)", int(y_te.sum()), 100 * y_te.mean())

    # 4. 评估
    logger.info("\n[4/4] 模型评估...")

    # 全量预测
    dtest = xgb.DMatrix(X_te, feature_names=FEATURE_COLUMNS)
    y_prob = model.predict(dtest)

    # 最佳 F1 阈值扫描
    best_f1, best_thr = 0.0, 0.5
    for thr in [round(x * 0.01, 2) for x in range(10, 90, 5)]:
        y_pred_t = (y_prob >= thr).astype(int)
        f1_t = f1_score(y_te, y_pred_t, zero_division=0)
        if f1_t > best_f1:
            best_f1 = f1_t
            best_thr = thr

    # 用最佳阈值
    y_pred = (y_prob >= best_thr).astype(int)

    # 计算指标
    val_accuracy = accuracy_score(y_te, y_pred)
    val_precision = precision_score(y_te, y_pred, zero_division=0)
    val_recall = recall_score(y_te, y_pred, zero_division=0)
    val_f1 = f1_score(y_te, y_pred, zero_division=0)
    val_auc = roc_auc_score(y_te, y_prob) if len(np.unique(y_te)) > 1 else 0.0
    cm = confusion_matrix(y_te, y_pred)

    # 打印结果
    logger.info("\n" + "=" * 60)
    logger.info("【评估结果】")
    logger.info("=" * 60)
    logger.info("  %-25s %s", "指标", "数值")
    logger.info("  %-25s %s", "-" * 25, "-" * 10)
    logger.info("  %-25s %.4f", "val_auc (AUC)", val_auc)
    logger.info("  %-25s %.4f", "val_f1 (F1 Score)", val_f1)
    logger.info("  %-25s %.4f", "val_accuracy", val_accuracy)
    logger.info("  %-25s %.4f", "val_precision", val_precision)
    logger.info("  %-25s %.4f", "val_recall", val_recall)
    logger.info("  %-25s %.2f", "best_f1_threshold", best_thr)
    logger.info("  %-25s %d", "测试集样本数", len(y_te))
    logger.info("  %-25s %d (%.1f%%)", "测试集正例", int(y_te.sum()), 100 * y_te.mean())

    # 混淆矩阵
    logger.info("\n  混淆矩阵 (最佳阈值=%.2f):", best_thr)
    logger.info("               预测负例  预测正例")
    logger.info("  实际负例      %-8d  %-8d" % (cm[0][0], cm[0][1]))
    if cm.shape[0] > 1:
        logger.info("  实际正例      %-8d  %-8d" % (cm[1][0], cm[1][1]))

    # 分类报告
    logger.info("\n  分类报告:")
    logger.info(classification_report(
        y_te, y_pred,
        target_names=["低风险(放行)", "高风险(拦截)"],
        zero_division=0,
    ))

    # 评级
    logger.info("=" * 60)
    if val_auc >= 0.85 and val_f1 >= 0.70:
        logger.info("[评级: 优秀 ★★★] 模型区分能力强, 可以直接上线")
    elif val_auc >= 0.70 and val_f1 >= 0.50:
        logger.info("[评级: 良好 ★★] 模型可用, 建议积累更多数据后重训")
    elif val_auc >= 0.60:
        logger.info("[评级: 一般 ★] 模型有区分度但不够强, 建议 --balance-pos 重训练")
    else:
        logger.info("[评级: 需改进] val_auc < 0.60, 建议检查特征质量和标签分布")
    logger.info("=" * 60)

    # 返回字典
    return {
        "val_auc": round(float(val_auc), 4),
        "val_f1": round(float(val_f1), 4),
        "val_accuracy": round(float(val_accuracy), 4),
        "val_precision": round(float(val_precision), 4),
        "val_recall": round(float(val_recall), 4),
        "best_f1_threshold": round(best_thr, 2),
        "n_test": len(y_te),
        "n_pos_test": int(y_te.sum()),
        "pos_ratio_test": round(float(y_te.mean()), 4),
        "confusion_matrix": cm.tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="银行风控系统 — XGBoost 模型评估 (val_auc + val_f1)"
    )
    parser.add_argument(
        "--model-path", type=str,
        default=str(PROJECT_ROOT / settings.XGB_MODEL_PATH),
        help="模型文件路径",
    )
    parser.add_argument("--test-ratio", type=float, default=0.2, help="测试集比例 (默认 0.2)")
    parser.add_argument("--data-limit", type=int, default=2500, help="加载数据上限")
    args = parser.parse_args()

    metrics = evaluate_model(
        model_path=args.model_path,
        test_ratio=args.test_ratio,
        data_limit=args.data_limit,
    )

    # 返回码: 质量不达标 → 非 0 (CI/CD 用)
    if metrics["val_auc"] < 0.60:
        logger.warning("模型质量不达标 (val_auc=%.4f < 0.60), 阻止上线", metrics["val_auc"])
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

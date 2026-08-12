"""基于物流运单标签和风险特征快照训练 XGBoost。"""
import logging
import sys
from pathlib import Path

import numpy as np
import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, train_and_save  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SQL_FETCH_SAMPLES = """
SELECT re.event_id, s.risk_label
FROM risk_event re
JOIN shipment s ON s.shipment_id = re.event_source_id
ORDER BY re.create_time DESC
LIMIT %s
"""

SQL_FETCH_FEATURES_WIDE = """
SELECT event_id, feature_name, feature_value
FROM risk_feature
WHERE event_id IN ({event_ids})
"""


def _decision_to_label(decision: str) -> int:
    """兼容旧调用；物流训练实际使用 shipment.risk_label。"""
    return 1 if decision in ("人工审核", "拒绝") else 0


def _load_data_from_mysql() -> tuple[np.ndarray, np.ndarray]:
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
            cur.execute(SQL_FETCH_SAMPLES, (settings.XGB_TRAIN_DATA_LIMIT,))
            samples = cur.fetchall()
            if not samples:
                raise RuntimeError("没有物流特征快照，请先运行 scripts/gen_train_dataset.py --reset")
            event_to_label = {event_id: int(label) for event_id, label in samples}
            ids = list(event_to_label)
            event_to_features: dict[str, dict[str, float]] = {}
            for start in range(0, len(ids), 500):
                batch = ids[start:start + 500]
                placeholders = ",".join(["%s"] * len(batch))
                cur.execute(SQL_FETCH_FEATURES_WIDE.format(event_ids=placeholders), batch)
                for event_id, name, value in cur.fetchall():
                    event_to_features.setdefault(event_id, {})[name] = float(value or 0)
            X_rows, y_rows = [], []
            missing = 0
            for event_id, label in event_to_label.items():
                values = event_to_features.get(event_id, {})
                if not set(FEATURE_COLUMNS).issubset(values):
                    missing += 1
                    continue
                X_rows.append([values[name] for name in FEATURE_COLUMNS])
                y_rows.append(label)
            X = np.asarray(X_rows, dtype=np.float32)
            y = np.asarray(y_rows, dtype=np.int32)
            logger.info(
                "物流训练矩阵: X=%s, 正例=%d/%d (%.1f%%), 缺特征跳过=%d",
                X.shape, int(y.sum()), len(y), 100 * float(y.mean()) if len(y) else 0, missing,
            )
            if len(np.unique(y)) < 2:
                raise RuntimeError("训练标签只有一个类别，请检查 shipment.risk_label")
            return X, y
    finally:
        conn.close()


def main() -> None:
    X, y = _load_data_from_mysql()
    if len(X) < 50:
        raise RuntimeError(f"有效训练样本不足 50 条: {len(X)}")
    metrics, model = train_and_save(
        X, y,
        num_boost_round=200,
        early_stopping_rounds=settings.XGB_EARLY_STOPPING_ROUNDS,
        return_model=True,
    )
    logger.info(
        "训练完成: val_auc=%.4f val_f1=%.4f val_accuracy=%.4f model=%s",
        metrics.get("val_auc", metrics["auc"]),
        metrics.get("val_f1", metrics["f1"]),
        metrics.get("val_accuracy", metrics["accuracy"]),
        metrics["model_path"],
    )
    if metrics.get("val_auc", metrics["auc"]) < settings.XGB_MIN_VAL_AUC:
        raise RuntimeError("val_auc 未达到 0.70")
    if metrics.get("val_f1", metrics["f1"]) < settings.XGB_MIN_VAL_F1:
        raise RuntimeError("val_f1 未达到 0.50")
    if model is not None:
        importance = sorted(model.get_score(importance_type="gain").items(), key=lambda x: -x[1])
        logger.info("特征重要性 TOP5: %s", importance[:5])


if __name__ == "__main__":
    main()

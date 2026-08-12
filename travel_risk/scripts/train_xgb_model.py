"""
旅游风控系统 - XGBoost 训练脚本 (一次性)
================
数据源: MySQL risk_assessment + risk_feature (28 维宽表)
步骤:
  1. 拉历史评估 (ml_score IS NULL 保证数据纯净)
  2. 每个 event_id JOIN 出 28 个特征 (pivot risk_feature)
  3. 标签二分类: 0=通过/标记, 1=人工审核/拒绝
  4. 80/20 stratify 拆分 + 早停 + AUC/F1 评估
  5. 质量验收 (假收敛检测) + 保存 app/engine/xgb_model.json + 特征重要性

跑法: python scripts/train_xgb_model.py
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pymysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS, train_and_save

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _decision_to_label(decision: str) -> int:
    """通过/标记 → 0, 人工审核/拒绝 → 1."""
    return 1 if decision in ("人工审核", "拒绝") else 0


def _load_data_from_mysql() -> tuple[np.ndarray, np.ndarray]:
    """拉评估 + 28 维特征宽表, 返回 (X, y)."""
    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
        password=settings.DB_PASSWORD, database=settings.DB_NAME, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT assessment_id, event_id, decision
                FROM risk_assessment
                WHERE decision IN ('通过', '标记', '人工审核', '拒绝')
                  AND ml_score IS NULL
                ORDER BY create_time DESC
                LIMIT %s
            """, (settings.XGB_TRAIN_DATA_LIMIT,))
            rows = cur.fetchall()
            logger.info("拉取评估: %d 条 (LIMIT=%d)", len(rows), settings.XGB_TRAIN_DATA_LIMIT)
            if not rows:
                raise RuntimeError(
                    "没有可训练数据. 先跑: python scripts/gen_train_dataset.py --reset"
                )

            cur.execute("SELECT COUNT(*) FROM risk_assessment")
            db_total = cur.fetchone()[0]
            cur.execute("SELECT MIN(create_time), MAX(create_time) FROM risk_assessment")
            db_min, db_max = cur.fetchone()
            span_days = None
            if db_min and db_max:
                try:
                    if isinstance(db_min, datetime):
                        span_days = (db_max - db_min).days
                    else:
                        span_days = (
                            datetime.strptime(str(db_max)[:19], "%Y-%m-%d %H:%M:%S")
                            - datetime.strptime(str(db_min)[:19], "%Y-%m-%d %H:%M:%S")
                        ).days
                except Exception:
                    span_days = None
            if len(rows) < settings.XGB_TRAIN_DATA_LIMIT * 0.8:
                logger.warning(
                    "DB 实际只加载 %d 条 (< LIMIT %d 的 80%%), DB 总 %d 条. "
                    "建议先 gen_train_dataset.py --reset 重新造数",
                    len(rows), settings.XGB_TRAIN_DATA_LIMIT, db_total,
                )
            if span_days is not None and span_days < 1 and db_total > 100:
                logger.warning(
                    "评估数据时间跨度 < 1 天, 建议用 gen_risk_data_with_dates.py 造带日期的数据"
                )

            event_to_label = {eid: _decision_to_label(dec) for _aid, eid, dec in rows}
            event_ids = list(event_to_label.keys())

            # 分块拉特征, 避免 IN 列表过长
            feature_map: dict[str, dict[str, float]] = {}
            chunk_size = 500
            for i in range(0, len(event_ids), chunk_size):
                chunk = event_ids[i:i + chunk_size]
                placeholders = ",".join(["%s"] * len(chunk))
                cur.execute(
                    f"SELECT event_id, feature_name, feature_value FROM risk_feature "
                    f"WHERE event_id IN ({placeholders})",
                    chunk,
                )
                for eid, fname, fval in cur.fetchall():
                    try:
                        feature_map.setdefault(eid, {})[fname] = float(fval)
                    except (TypeError, ValueError):
                        feature_map.setdefault(eid, {})[fname] = 0.0

            # 组装 X (N×28), 缺失特征用 0
            X = []
            y = []
            missing_features = 0
            for eid in event_ids:
                feats = feature_map.get(eid, {})
                missing_features += len(FEATURE_COLUMNS) - len(feats)
                row = [feats.get(col, 0.0) for col in FEATURE_COLUMNS]
                X.append(row)
                y.append(event_to_label[eid])
            if missing_features:
                logger.warning("共缺 %d 个特征值 (自动补 0)", missing_features)

            X = np.array(X, dtype=np.float32)
            y = np.array(y, dtype=np.int32)
            n_pos = int((y == 1).sum())
            logger.info("特征矩阵: %s, 正例 %d 条 (%.1f%%)",
                        X.shape, n_pos, 100 * n_pos / len(y) if len(y) else 0)
            return X, y
    finally:
        conn.close()


def main():
    X, y = _load_data_from_mysql()
    model_path = os.path.join(PROJECT_ROOT, settings.XGB_MODEL_PATH)
    metrics, booster = train_and_save(
        X, y, model_path=model_path, num_boost_round=300, return_model=True,
    )

    print("\n" + "=" * 60)
    print("训练质量报告:")
    for k, v in metrics.items():
        print(f"  {k:<18} = {v}")

    # 质量验收
    if metrics["train_auc"] < settings.XGB_MIN_VAL_AUC:
        logger.warning("⚠️  train_auc %.4f < %.2f, 模型可能无效", metrics["train_auc"], settings.XGB_MIN_VAL_AUC)
    if metrics["best_iter"] < settings.XGB_MIN_BEST_ITER:
        logger.warning("⚠️  best_iter %d < %d, 可能假收敛", metrics["best_iter"], settings.XGB_MIN_BEST_ITER)
    if metrics["pos_ratio"] < settings.XGB_MIN_POS_RATIO or metrics["pos_ratio"] > settings.XGB_MAX_POS_RATIO:
        logger.warning("⚠️  正例比例 %.1f%% 不在 [%.0f%%, %.0f%%] 区间", 
                       100 * metrics["pos_ratio"], 100 * settings.XGB_MIN_POS_RATIO, 100 * settings.XGB_MAX_POS_RATIO)

    # 特征重要性 Top 15
    importance = booster.get_score(importance_type="gain")
    top = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)[:15]
    print("\n特征重要性 Top 15 (按 gain):")
    for fname, gain in top:
        print(f"  {fname:<30} {gain:.2f}")
    print("=" * 60)
    print(f"模型已保存: {model_path}")
    print("下一步: python scripts/backfill_ml_score.py  回填线上评估")


if __name__ == "__main__":
    main()

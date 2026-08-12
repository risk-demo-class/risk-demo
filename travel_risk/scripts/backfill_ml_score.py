"""
旅游风控系统 - 回填历史评估的 ml_score / ml_decision
================
用训练好的 XGBoost 模型, 对 risk_assessment 中 ml_score IS NULL 的
历史评估逐条推理并回填 (特征从 risk_feature 宽表读取).

用法:
  python scripts/backfill_ml_score.py
  python scripts/backfill_ml_score.py --limit 5000
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS, load_model, predict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main(limit: int = 5000):
    if not load_model():
        logger.error("模型加载失败, 先跑: python scripts/train_xgb_model.py")
        return

    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
        password=settings.DB_PASSWORD, database=settings.DB_NAME, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT assessment_id, event_id FROM risk_assessment
                WHERE ml_score IS NULL AND decision IN ('通过','标记','人工审核','拒绝')
                ORDER BY create_time DESC LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            logger.info("待回填评估: %d 条", len(rows))
            if not rows:
                print("没有需要回填的评估")
                return

            event_ids = [eid for _aid, eid in rows]
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

            updated = 0
            for assessment_id, event_id in rows:
                feats = {col: feature_map.get(event_id, {}).get(col, 0.0) for col in FEATURE_COLUMNS}
                result = predict(feats)
                cur.execute(
                    "UPDATE risk_assessment SET ml_score=%s, ml_decision=%s WHERE assessment_id=%s",
                    (result.score, result.decision, assessment_id),
                )
                updated += 1
            conn.commit()
            logger.info("回填完成: %d 条", updated)

            # 回填后决策分布
            cur.execute("SELECT ml_decision, COUNT(*) FROM risk_assessment GROUP BY ml_decision")
            dist = {d: int(c) for d, c in cur.fetchall()}
            print(f"ML 决策分布: {dist}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回填历史评估的 ml_score")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    main(args.limit)

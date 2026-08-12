"""使用已训练模型，根据 risk_feature 快照回填 ML 概率。"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymysql

from app.config import settings
from app.engine.ml_model import load_model, predict


def backfill(limit: int = 2500, dry_run: bool = False) -> dict:
    if not load_model():
        raise RuntimeError("模型加载失败，请先执行 scripts/train_xgb_model.py")
    conn = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT,
                           user=settings.DB_USER, password=settings.DB_PASSWORD,
                           database=settings.DB_NAME, charset="utf8mb4")
    updated = 0
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT assessment_id,event_id FROM risk_assessment
                           WHERE ml_score IS NULL ORDER BY create_time DESC LIMIT %s""", (limit,))
            rows = cur.fetchall()
            for assessment_id, event_id in rows:
                cur.execute("SELECT feature_name,feature_value FROM risk_feature WHERE event_id=%s", (event_id,))
                features = {name: float(value or 0) for name, value in cur.fetchall()}
                result = predict(features)
                if not result.is_loaded:
                    continue
                if not dry_run:
                    cur.execute("UPDATE risk_assessment SET ml_score=%s,ml_decision=%s WHERE assessment_id=%s",
                                (result.score, result.decision, assessment_id))
                updated += 1
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return {"updated": updated, "dry_run": dry_run}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(backfill(args.limit, args.dry_run))

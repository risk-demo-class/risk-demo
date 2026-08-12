"""Read-only final database/model audit for Step 6."""

from __future__ import annotations

import argparse
import json
import os
import sys

import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS
from scripts.ml_pipeline_common import DEFAULT_MODEL_PATH, connect_mysql


def audit(db_name: str, model_path: str) -> dict:
    result: dict = {}
    filters = {
        "dealer": "dealer_id LIKE 'MLD%'",
        "device": "device_id LIKE 'MLDEV%'",
        "purchase_order": "po_id LIKE 'MLPO%'",
        "warranty_claim": "claim_id LIKE 'MLCLM%'",
        "cross_region_report": "report_id LIKE 'MLCRR%'",
        "blacklist_extra": "value LIKE 'ML-%'",
    }
    conn = connect_mysql(db_name)
    try:
        with conn.cursor() as cur:
            for table, where in filters.items():
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}")
                result[table] = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM risk_event WHERE event_source_id LIKE 'ML%'")
            result["risk_events"] = int(cur.fetchone()[0])
            cur.execute("""
                SELECT COUNT(*) FROM risk_feature AS f
                JOIN risk_event AS e ON e.event_id=f.event_id
                WHERE e.event_source_id LIKE 'ML%'
            """)
            result["risk_features"] = int(cur.fetchone()[0])
            cur.execute("""
                SELECT MIN(feature_count), MAX(feature_count) FROM (
                    SELECT COUNT(*) AS feature_count
                    FROM risk_feature AS f
                    JOIN risk_event AS e ON e.event_id=f.event_id
                    WHERE e.event_source_id LIKE 'ML%'
                    GROUP BY f.event_id
                ) AS counts
            """)
            result["features_per_event_min_max"] = list(cur.fetchone())
            cur.execute("""
                SELECT COUNT(*), SUM(a.ml_score IS NOT NULL),
                       MIN(a.ml_score), MAX(a.ml_score)
                FROM risk_assessment AS a
                JOIN risk_event AS e ON e.event_id=a.event_id
                WHERE e.event_source_id LIKE 'ML%'
            """)
            row = cur.fetchone()
            result["assessments"] = int(row[0])
            result["assessments_with_ml_score"] = int(row[1])
            result["ml_score_min"] = float(row[2])
            result["ml_score_max"] = float(row[3])
            cur.execute("""
                SELECT
                  (SELECT COUNT(*) FROM purchase_order p LEFT JOIN dealer d
                   ON d.dealer_id=p.dealer_id WHERE d.dealer_id IS NULL)
                + (SELECT COUNT(*) FROM warranty_claim w LEFT JOIN dealer d
                   ON d.dealer_id=w.dealer_id LEFT JOIN device v
                   ON v.device_id=w.device_id
                   WHERE d.dealer_id IS NULL OR v.device_id IS NULL)
                + (SELECT COUNT(*) FROM cross_region_report r LEFT JOIN device v
                   ON v.device_id=r.device_id WHERE v.device_id IS NULL)
            """)
            result["orphan_fk_count"] = int(cur.fetchone()[0])
    finally:
        conn.close()

    booster = xgb.Booster()
    booster.load_model(model_path)
    result["feature_columns_count"] = len(FEATURE_COLUMNS)
    result["model_num_features"] = booster.num_features()
    result["model_feature_names_match"] = booster.feature_names == FEATURE_COLUMNS
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 6 只读数据库/模型验收")
    parser.add_argument("--db", default=settings.DB_NAME)
    parser.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    args = parser.parse_args()
    print(json.dumps(audit(args.db, args.model_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

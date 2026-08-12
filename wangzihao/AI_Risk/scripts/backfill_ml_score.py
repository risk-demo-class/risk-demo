"""Backfill ml_score from immutable 25-feature risk_feature snapshots."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS, is_model_loaded, load_model, predict
from scripts.ml_pipeline_common import connect_mysql


@dataclass
class BackfillReport:
    assessments_selected: int = 0
    complete_snapshots: int = 0
    missing_snapshots: int = 0
    skipped: int = 0
    updated: int = 0
    positive_average_score: float = 0.0
    negative_average_score: float = 0.0
    separation: float = 0.0
    dry_run: bool = True


def _load_candidates(cur, source_prefix: str, limit: int | None):
    sql = """
        SELECT a.assessment_id, a.event_id, a.decision
        FROM risk_assessment AS a
        JOIN risk_event AS e ON e.event_id = a.event_id
        WHERE a.ml_score IS NULL AND e.event_source_id LIKE %s
        ORDER BY a.create_time, a.assessment_id
    """
    params: list[object] = [f"{source_prefix}%"]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    cur.execute(sql, params)
    return list(cur.fetchall())


def backfill_ml_score(
    *,
    db_name: str,
    source_prefix: str = "ML",
    limit: int | None = None,
    dry_run: bool = True,
    model_path: str | None = None,
) -> BackfillReport:
    if not is_model_loaded() and not load_model(model_path):
        raise RuntimeError("XGBoost model failed to load; train the manufacturing model first")

    conn = connect_mysql(db_name)
    report = BackfillReport(dry_run=dry_run)
    updates: list[tuple[float, str, str]] = []
    positive_scores: list[float] = []
    negative_scores: list[float] = []
    try:
        with conn.cursor() as cur:
            candidates = _load_candidates(cur, source_prefix, limit)
            report.assessments_selected = len(candidates)
            if candidates:
                event_ids = [row[1] for row in candidates]
                snapshots: dict[str, dict[str, float]] = {}
                for offset in range(0, len(event_ids), 500):
                    batch = event_ids[offset:offset + 500]
                    placeholders = ",".join(["%s"] * len(batch))
                    cur.execute(
                        "SELECT event_id, feature_name, feature_value FROM risk_feature "
                        f"WHERE event_id IN ({placeholders})",
                        batch,
                    )
                    for event_id, feature_name, feature_value in cur.fetchall():
                        snapshots.setdefault(event_id, {})[feature_name] = float(feature_value)

            expected = set(FEATURE_COLUMNS)
            for assessment_id, event_id, decision in candidates:
                features = snapshots.get(event_id, {})
                if len(features) != 25 or set(features) != expected:
                    report.missing_snapshots += 1
                    report.skipped += 1
                    continue
                ordered_features = {name: features[name] for name in FEATURE_COLUMNS}
                result = predict(ordered_features)
                updates.append((result.score, result.decision, assessment_id))
                report.complete_snapshots += 1
                if decision in ("人工审核", "拒绝"):
                    positive_scores.append(result.score)
                else:
                    negative_scores.append(result.score)

            if not dry_run and updates:
                cur.executemany(
                    "UPDATE risk_assessment SET ml_score=%s, ml_decision=%s "
                    "WHERE assessment_id=%s AND ml_score IS NULL",
                    updates,
                )
                conn.commit()
                report.updated = cur.rowcount
    finally:
        conn.close()

    report.positive_average_score = round(
        sum(positive_scores) / len(positive_scores), 6
    ) if positive_scores else 0.0
    report.negative_average_score = round(
        sum(negative_scores) / len(negative_scores), 6
    ) if negative_scores else 0.0
    report.separation = round(
        report.positive_average_score - report.negative_average_score, 6
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="基于 risk_feature 历史快照回填 ml_score")
    parser.add_argument("--db", default=settings.DB_NAME)
    parser.add_argument("--source-prefix", default="ML")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model-path")
    parser.add_argument("--dry-run", action="store_true",
                        help="只读统计，不更新 risk_assessment")
    args = parser.parse_args()
    backfill_ml_score(
        db_name=args.db,
        source_prefix=args.source_prefix,
        limit=args.limit,
        dry_run=args.dry_run,
        model_path=args.model_path,
    )


if __name__ == "__main__":
    main()

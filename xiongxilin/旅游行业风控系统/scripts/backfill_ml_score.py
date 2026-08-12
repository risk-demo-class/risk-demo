"""
训练模型后回填历史评估的 XGBoost 分数。

用途:
  先生成评估数据、后训练模型时，早期 risk_assessment.ml_score 会是 0.0。
  本脚本用当前 app/engine/xgb_model.json 对历史 risk_feature 重新推理，并更新:
    - risk_assessment.ml_score
    - risk_assessment.ml_decision

跑法:
  python scripts/backfill_ml_score.py
  python scripts/backfill_ml_score.py --limit 500
  python scripts/backfill_ml_score.py --only-zero
"""
import argparse
import logging
import sys
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, is_model_loaded, load_model, predict  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _connect():
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=False,
    )


def _load_assessments(cur, limit: int, only_zero: bool) -> list[tuple[str, str]]:
    where = "WHERE ml_score IS NULL OR ml_score = 0" if only_zero else ""
    sql = f"""
        SELECT assessment_id, event_id
        FROM risk_assessment
        {where}
        ORDER BY create_time DESC
        LIMIT %s
    """
    cur.execute(sql, (limit,))
    return list(cur.fetchall())


def _load_features(cur, event_ids: list[str]) -> dict[str, dict[str, float]]:
    if not event_ids:
        return {}

    event_to_features: dict[str, dict[str, float]] = {}
    batch_size = 500
    for i in range(0, len(event_ids), batch_size):
        batch = event_ids[i:i + batch_size]
        placeholders = ",".join(["%s"] * len(batch))
        cur.execute(
            f"""
            SELECT event_id, feature_name, feature_value
            FROM risk_feature
            WHERE event_id IN ({placeholders})
            """,
            batch,
        )
        for event_id, feature_name, feature_value in cur.fetchall():
            event_to_features.setdefault(event_id, {})
            try:
                event_to_features[event_id][feature_name] = float(feature_value)
            except (TypeError, ValueError):
                event_to_features[event_id][feature_name] = 0.0
    return event_to_features


def _backfill(limit: int, only_zero: bool, dry_run: bool) -> tuple[int, int]:
    if not is_model_loaded():
        load_model()
    if not is_model_loaded():
        raise RuntimeError(f"XGBoost 模型未加载，请先训练: python scripts/train_xgb_model.py")

    conn = _connect()
    try:
        with conn.cursor() as cur:
            rows = _load_assessments(cur, limit=limit, only_zero=only_zero)
            event_ids = [event_id for _, event_id in rows]
            feature_map = _load_features(cur, event_ids)

            updated = 0
            skipped = 0
            for assessment_id, event_id in rows:
                features = feature_map.get(event_id) or {}
                if len(features) < len(FEATURE_COLUMNS):
                    skipped += 1
                    continue
                result = predict(features)
                if not result.is_loaded:
                    skipped += 1
                    continue
                if not dry_run:
                    cur.execute(
                        """
                        UPDATE risk_assessment
                        SET ml_score=%s, ml_decision=%s
                        WHERE assessment_id=%s
                        """,
                        (result.score, result.decision, assessment_id),
                    )
                updated += 1

            if dry_run:
                conn.rollback()
            else:
                conn.commit()
            return updated, skipped
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="回填历史评估的 XGBoost ML 分数")
    parser.add_argument("--limit", type=int, default=5000, help="最多回填多少条评估")
    parser.add_argument("--only-zero", action="store_true", help="只回填 ml_score 为空或 0 的评估")
    parser.add_argument("--dry-run", action="store_true", help="只统计不落库")
    args = parser.parse_args()

    updated, skipped = _backfill(args.limit, args.only_zero, args.dry_run)
    action = "可回填" if args.dry_run else "已回填"
    logger.info("%s %d 条，跳过 %d 条特征不全/模型不可用记录", action, updated, skipped)


if __name__ == "__main__":
    main()

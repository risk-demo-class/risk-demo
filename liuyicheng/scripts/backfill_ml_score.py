"""训练完成后，用新模型回填历史评估的 ml_score 和 ml_decision。

训练样本生成阶段必须保持 ml_score=NULL，以避免旧模型输出泄漏进标签；
新模型训练完成后再运行本脚本，前端历史评估和案件即可显示模型评分。
"""
import argparse
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, load_model, predict  # noqa: E402


def backfill(samples: int, dry_run: bool) -> int:
    if not load_model():
        raise RuntimeError("模型加载失败，请先运行 train_xgb_model.py")

    conn = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with conn.cursor() as cursor:
            sql = (
                "SELECT assessment_id, event_id, decision FROM risk_assessment "
                "WHERE ml_score IS NULL ORDER BY create_time DESC"
            )
            params: tuple[int, ...] = ()
            if samples > 0:
                sql += " LIMIT %s"
                params = (samples,)
            cursor.execute(sql, params)
            assessments = cursor.fetchall()
            if not assessments:
                print("没有 ml_score=NULL 的评估，无需回填")
                return 0

            feature_map: dict[str, dict[str, float]] = {}
            event_ids = [row[1] for row in assessments]
            batch_size = 500
            for start in range(0, len(event_ids), batch_size):
                batch = event_ids[start:start + batch_size]
                placeholders = ",".join(["%s"] * len(batch))
                cursor.execute(
                    "SELECT event_id, feature_name, feature_value FROM risk_feature "
                    f"WHERE event_id IN ({placeholders})",
                    batch,
                )
                for event_id, feature_name, feature_value in cursor.fetchall():
                    try:
                        value = float(feature_value)
                    except (TypeError, ValueError):
                        value = 0.0
                    feature_map.setdefault(event_id, {})[feature_name] = value

            updates = []
            skipped = 0
            pos_scores = []
            neg_scores = []
            for assessment_id, event_id, decision in assessments:
                features = feature_map.get(event_id, {})
                if len(features) < len(FEATURE_COLUMNS):
                    skipped += 1
                    continue
                result = predict(features)
                if not result.is_loaded:
                    skipped += 1
                    continue
                updates.append((result.score, result.decision, assessment_id))
                target = pos_scores if decision in ("人工审核", "拒绝") else neg_scores
                target.append(result.score)

            if not dry_run and updates:
                cursor.executemany(
                    "UPDATE risk_assessment SET ml_score=%s, ml_decision=%s "
                    "WHERE assessment_id=%s AND ml_score IS NULL",
                    updates,
                )
                conn.commit()
            else:
                conn.rollback()

            mode = "DRY-RUN" if dry_run else "已写库"
            print(f"模型评分回填完成: {len(updates)} 条，跳过 {skipped} 条，模式={mode}")
            if pos_scores:
                print(f"  高风险标签平均 ml_score: {sum(pos_scores) / len(pos_scores):.4f}")
            if neg_scores:
                print(f"  低风险标签平均 ml_score: {sum(neg_scores) / len(neg_scores):.4f}")
            return len(updates)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="用训练后的XGBoost回填历史评估模型评分")
    parser.add_argument(
        "--samples", "--limit", dest="samples", type=int, default=0,
        help="最多回填多少条；0表示回填全部NULL记录",
    )
    parser.add_argument("--dry-run", action="store_true", help="只计算，不写数据库")
    args = parser.parse_args()
    if args.samples < 0:
        parser.error("--samples 必须 >= 0")
    backfill(args.samples, args.dry_run)


if __name__ == "__main__":
    main()

"""Export manufacturing risk_feature snapshots as a fixed 25-column dataset.

Labels are weak/synthetic supervision derived from the current JSON-rule decision:
label=1 means 人工审核/拒绝; label=0 means 通过/标记. This script is read-only and
never clears historical ml_score values.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS
from scripts.ml_pipeline_common import (
    DEFAULT_DATASET_PATH,
    load_snapshot_dataset,
    save_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出制造业 25 维训练数据（只读）")
    parser.add_argument("--db", default=settings.DB_NAME)
    parser.add_argument("--output", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--source-prefix", default="ML")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    dataset = load_snapshot_dataset(
        args.db, source_prefix=args.source_prefix, limit=args.limit,
    )
    path = save_dataset(dataset, args.output)
    positive = int(dataset.y.sum())
    negative = int(len(dataset.y) - positive)
    print(f"FEATURE_COLUMNS={len(FEATURE_COLUMNS)}; X.shape={dataset.X.shape}")
    print(f"label=0: {negative}; label=1: {positive}; positive_ratio={positive/len(dataset.y):.4f}")
    print(f"dealers(groups): {len(set(dataset.groups))}; unique_sources: {len(set(dataset.source_ids))}")
    print(f"missing/incomplete snapshots skipped: {len(dataset.missing_event_ids)}")
    print(f"dataset saved: {path}")
    print("下一步: python scripts/train_xgb_model.py --dataset", path)


if __name__ == "__main__":
    main()

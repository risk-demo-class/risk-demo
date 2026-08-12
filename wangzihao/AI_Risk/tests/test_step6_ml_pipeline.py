"""Step 6 manufacturing ML contract and leakage regression tests."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

from app.engine.ml_model import FEATURE_COLUMNS
from scripts.ml_pipeline_common import SnapshotDataset, decision_to_label
from scripts.train_xgb_model import group_split


ROOT = Path(__file__).resolve().parent.parent


def _dataset() -> SnapshotDataset:
    rows = []
    labels = []
    groups = []
    sources = []
    for dealer_index in range(20):
        label = dealer_index % 2
        for source_index in range(3):
            row = np.arange(25, dtype=np.float32)
            row = row + dealer_index * 100 + source_index
            rows.append(row)
            labels.append(label)
            groups.append(f"D{dealer_index:03d}")
            sources.append(f"S{dealer_index:03d}_{source_index}")
    n = len(rows)
    return SnapshotDataset(
        X=np.asarray(rows, dtype=np.float32),
        y=np.asarray(labels, dtype=np.int8),
        groups=np.asarray(groups),
        source_ids=np.asarray(sources),
        event_ids=np.asarray([f"E{i}" for i in range(n)]),
        assessment_ids=np.asarray([f"A{i}" for i in range(n)]),
        event_types=np.asarray(["下单"] * n),
        missing_event_ids=(),
    )


def test_feature_columns_remain_exactly_25():
    assert len(FEATURE_COLUMNS) == 25
    assert len(set(FEATURE_COLUMNS)) == 25


def test_weak_label_contract():
    assert decision_to_label("通过") == 0
    assert decision_to_label("标记") == 0
    assert decision_to_label("人工审核") == 1
    assert decision_to_label("拒绝") == 1


def test_group_split_has_no_dealer_or_source_leakage():
    dataset = _dataset()
    train_idx, val_idx, audit = group_split(dataset, test_size=0.25)
    assert set(dataset.groups[train_idx]).isdisjoint(dataset.groups[val_idx])
    assert set(dataset.source_ids[train_idx]).isdisjoint(dataset.source_ids[val_idx])
    assert audit["dealer_overlap"] == 0
    assert audit["source_overlap"] == 0


def test_training_and_backfill_use_snapshots_not_legacy_event_columns():
    files = {
        name: (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for name in (
            "gen_risky_users.py",
            "gen_risk_data.py",
            "gen_train_dataset.py",
            "train_xgb_model.py",
            "backfill_ml_score.py",
        )
    }
    combined = "\n".join(files.values())
    for old_table in (
        "user_info", "order_info", "order_detail", "postsale",
        "receive_info", "logistics_complaint",
    ):
        assert old_table not in combined
    backfill = files["backfill_ml_score.py"]
    assert "FROM risk_feature" in backfill
    assert "compute_all_features" not in backfill
    assert "settings.DB_URL" not in backfill
    assert "ml_score IS NULL" in backfill


def test_frozen_production_modules_are_not_imported_for_mutation():
    train_tree = ast.parse((ROOT / "scripts" / "train_xgb_model.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(train_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "app.engine.decision" not in imported
    assert "app.engine.feature" not in imported

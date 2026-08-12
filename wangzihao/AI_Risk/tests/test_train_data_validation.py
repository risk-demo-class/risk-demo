"""Dataset validation and dealer-group split tests."""

import numpy as np
import pytest

from app.engine.ml_model import FEATURE_COLUMNS
from scripts.ml_pipeline_common import SnapshotDataset, load_dataset, save_dataset
from scripts.train_xgb_model import group_split


def _sample_dataset() -> SnapshotDataset:
    X, y, groups, sources = [], [], [], []
    for dealer in range(24):
        for source in range(2):
            X.append(np.arange(25, dtype=np.float32) + dealer * 100 + source)
            y.append(dealer % 2)
            groups.append(f"D{dealer}")
            sources.append(f"S{dealer}_{source}")
    n = len(X)
    return SnapshotDataset(
        X=np.asarray(X), y=np.asarray(y), groups=np.asarray(groups),
        source_ids=np.asarray(sources), event_ids=np.asarray([f"E{i}" for i in range(n)]),
        assessment_ids=np.asarray([f"A{i}" for i in range(n)]),
        event_types=np.asarray(["下单"] * n), missing_event_ids=(),
    )


def test_saved_dataset_round_trips_exact_feature_order(tmp_path):
    path = save_dataset(_sample_dataset(), tmp_path / "dataset.npz")
    loaded = load_dataset(path)
    assert loaded.X.shape == (48, 25)
    assert np.isfinite(loaded.X).all()


def test_dataset_rejects_feature_column_reordering(tmp_path):
    dataset = _sample_dataset()
    path = tmp_path / "bad.npz"
    np.savez_compressed(
        path, X=dataset.X, y=dataset.y, groups=dataset.groups,
        source_ids=dataset.source_ids, event_ids=dataset.event_ids,
        assessment_ids=dataset.assessment_ids, event_types=dataset.event_types,
        feature_columns=np.asarray(list(reversed(FEATURE_COLUMNS))),
    )
    with pytest.raises(RuntimeError, match="FEATURE_COLUMNS"):
        load_dataset(path)


def test_group_split_is_dealer_and_source_disjoint():
    dataset = _sample_dataset()
    train, validation, audit = group_split(dataset)
    assert set(dataset.groups[train]).isdisjoint(dataset.groups[validation])
    assert set(dataset.source_ids[train]).isdisjoint(dataset.source_ids[validation])
    assert audit["exact_feature_vector_overlap"] == 0

"""银行模型数据验证与按用户分组切分测试。"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pytest

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS
from scripts.train_xgb_model import (
    SEED,
    TrainingDataset,
    _group_split,
    _validate_training_dataset,
)


def make_dataset(*, n_users=100, events_per_user=3, positive_every=4, complete=True, span_days=30):
    users = []
    labels = []
    rows = []
    event_ids = []
    for user_index in range(n_users):
        for event_index in range(events_per_user):
            users.append(f"U{user_index:04d}")
            label = int(user_index % positive_every == 0)
            labels.append(label)
            rows.append(np.full(len(FEATURE_COLUMNS), label + event_index / 10, dtype=np.float32))
            event_ids.append(f"E{user_index:04d}_{event_index}")
    now = datetime(2026, 8, 12)
    complete_rows = len(rows)
    source_rows = complete_rows + (5 if not complete else 0)
    return TrainingDataset(
        X=np.asarray(rows, dtype=np.float32),
        y=np.asarray(labels, dtype=np.int32),
        users=np.asarray(users),
        event_ids=event_ids,
        min_time=now - timedelta(days=span_days),
        max_time=now,
        source_rows=source_rows,
        complete_rows=complete_rows,
    )


class TestGroupSplit:
    def test_same_user_never_crosses_train_and_validation(self):
        data = make_dataset()
        train_idx, val_idx = _group_split(data)
        assert set(data.users[train_idx]).isdisjoint(set(data.users[val_idx]))
        assert set(data.y[train_idx]) == {0, 1}
        assert set(data.y[val_idx]) == {0, 1}

    def test_split_is_reproducible_with_fixed_seed(self):
        data = make_dataset()
        first = _group_split(data)
        second = _group_split(data)
        assert SEED == 20260812
        assert np.array_equal(first[0], second[0])
        assert np.array_equal(first[1], second[1])


class TestDatasetValidation:
    def test_warns_for_incomplete_features(self, caplog):
        data = make_dataset(complete=False)
        with caplog.at_level(logging.WARNING):
            _validate_training_dataset(data)
        assert any("特征不完整" in record.message for record in caplog.records)

    def test_warns_for_low_positive_ratio(self, caplog):
        data = make_dataset(positive_every=20)
        with caplog.at_level(logging.WARNING):
            _validate_training_dataset(data)
        assert any("正例比例" in record.message for record in caplog.records)

    def test_warns_for_short_time_span(self, caplog):
        data = make_dataset(span_days=0)
        with caplog.at_level(logging.WARNING):
            _validate_training_dataset(data)
        assert any("create_time 跨度" in record.message for record in caplog.records)

    def test_healthy_distribution_has_no_distribution_warning(self, caplog, monkeypatch):
        data = make_dataset(positive_every=4)
        monkeypatch.setattr(settings, "XGB_TRAIN_DATA_LIMIT", data.source_rows)
        with caplog.at_level(logging.WARNING):
            _validate_training_dataset(data)
        messages = [record.message for record in caplog.records]
        assert not any("特征不完整" in message for message in messages)
        assert not any("正例比例" in message for message in messages)
        assert not any("create_time 跨度" in message for message in messages)


class TestTrainScriptConfigWiring:
    def test_uses_parameterized_config_limit(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "scripts" / "train_xgb_model.py").read_text(encoding="utf-8")
        assert "LIMIT %s" in source
        assert "settings.XGB_TRAIN_DATA_LIMIT" in source
        assert "LIMIT 5000" not in source

    def test_config_quality_gates_are_not_lowered(self):
        assert settings.XGB_MIN_VAL_AUC >= 0.70
        assert settings.XGB_MIN_VAL_F1 >= 0.50

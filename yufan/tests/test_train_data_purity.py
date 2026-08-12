"""阶段 10：教育训练集生成测试。"""

import csv
from pathlib import Path

from app.engine.ml_model import FEATURE_COLUMNS
from scripts.gen_train_dataset import generate_dataset
from scripts.train_xgb_model import load_csv


def test_generated_dataset_has_25_features_and_binary_label(tmp_path: Path):
    target = tmp_path / "education.csv"
    total, positives = generate_dataset(target, samples=200, positive_ratio=0.4, seed=7)
    X, y = load_csv(target)
    assert total == 200
    assert 20 <= positives <= 180
    assert X.shape == (200, 25)
    assert y.shape == (200,)
    assert set(y.tolist()) == {0, 1}


def test_generation_is_reproducible(tmp_path: Path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    generate_dataset(first, samples=150, seed=20260811)
    generate_dataset(second, samples=150, seed=20260811)
    assert first.read_bytes() == second.read_bytes()


def test_csv_header_matches_protected_model_feature_order(tmp_path: Path):
    target = tmp_path / "education.csv"
    generate_dataset(target, samples=100)
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == FEATURE_COLUMNS + ["label"]

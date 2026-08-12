"""训练 CSV 测试."""

from pathlib import Path

import pandas as pd

from app.config import settings
from app.engine.feature_registry import FEATURE_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_train_csv_exists():
    path = PROJECT_ROOT / settings.TRAIN_CSV_PATH
    assert path.exists(), "请先运行 scripts/gen_train_csv.py"


def test_train_csv_columns_and_label():
    path = PROJECT_ROOT / settings.TRAIN_CSV_PATH
    df = pd.read_csv(path)
    assert "label" in df.columns
    assert set(FEATURE_COLUMNS).issubset(df.columns)
    assert set(df["label"].unique()).issubset({0, 1})

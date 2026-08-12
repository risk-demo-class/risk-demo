"""阶段 10：训练 CSV 输入校验与模型指标验收。"""

import csv
import json
from pathlib import Path

import pytest

from app.engine.ml_model import FEATURE_COLUMNS
from scripts.train_xgb_model import load_csv


ROOT = Path(__file__).resolve().parents[1]


def test_load_csv_rejects_wrong_column_order(tmp_path: Path):
    path = tmp_path / "wrong.csv"
    path.write_text("label,user_total_orders\n0,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="列顺序"):
        load_csv(path)


def test_load_csv_rejects_single_class(tmp_path: Path):
    path = tmp_path / "single.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FEATURE_COLUMNS + ["label"])
        writer.writerow([0] * 25 + [0])
    with pytest.raises(ValueError, match="正例"):
        load_csv(path)


def test_generated_model_metrics_meet_acceptance_threshold():
    metrics = json.loads(
        (ROOT / "data" / "education_model_metrics.json").read_text(encoding="utf-8")
    )
    assert metrics["industry"] == "教育风控"
    assert metrics["sample_count"] >= 1250
    assert metrics["feature_count"] == 25
    assert metrics["val_auc"] >= 0.7
    assert 0 <= metrics["val_f1"] <= 1

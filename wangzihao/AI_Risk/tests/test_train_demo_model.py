"""Legacy demo entry no longer trains ecommerce-shaped random vectors."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "train_demo_model.py"


def test_demo_entry_delegates_to_manufacturing_trainer():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "from scripts.train_xgb_model import main" in source
    assert "gen_synthetic_dataset" not in source
    assert "train_test_split" not in source


def test_demo_entry_documents_why_random_ecommerce_data_was_removed():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "six manufacturing business tables" in source
    assert "25-feature" in source

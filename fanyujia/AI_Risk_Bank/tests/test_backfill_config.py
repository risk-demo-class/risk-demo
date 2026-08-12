from pathlib import Path


def test_backfill_uses_project_database_url_builder():
    script = (Path(__file__).resolve().parent.parent / "scripts" / "backfill_ml_score.py").read_text(
        encoding="utf-8"
    )

    assert "settings.get_database_url_async()" in script
    assert "settings.DB_URL" not in script


def test_backfill_reads_persisted_bank_features():
    script = (Path(__file__).resolve().parent.parent / "scripts" / "backfill_ml_score.py").read_text(
        encoding="utf-8"
    )

    assert "FROM risk_feature" in script
    assert "feature_name, feature_value" in script
    assert "order_id, receive_id" not in script

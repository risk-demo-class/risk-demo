import csv
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.gen_paypal_business_data import CsvDatasetWriter, GeneratorConfig, PayPalLikeGenerator


def _count(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def test_custom_conversation_and_merchant_volumes(tmp_path: Path) -> None:
    output = tmp_path / "custom"
    config = GeneratorConfig(
        users=20,
        merchants=7,
        transactions=40,
        interactions=12,
        segments=36,
        messages=180,
        seed=99,
        email_ratio=0.4,
        attachment_ratio=0.5,
    )
    PayPalLikeGenerator(config).generate(CsvDatasetWriter(output))
    assert _count(output / "merchant_info.csv") == 7
    assert _count(output / "interaction.csv") == 12
    assert _count(output / "conversation_segment.csv") == 36
    assert _count(output / "message.csv") == 180


def test_monitoring_pages_and_query_validation() -> None:
    with TestClient(app) as client:
        transactions = client.get("/transactions")
        interactions = client.get("/interactions")
        assert transactions.status_code == 200
        assert "amount_min" in transactions.text
        assert interactions.status_code == 200
        assert "segment_count_min" in interactions.text
        assert client.get("/api/transactions?sort_by=unsafe_column").status_code == 422
        assert client.get("/api/transactions/DOES-NOT-EXIST").status_code == 404
        assert client.get("/api/interactions/DOES-NOT-EXIST").status_code == 404

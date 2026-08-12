import csv
import json
from pathlib import Path

import pytest

from scripts.gen_paypal_business_data import (
    TABLE_COLUMNS,
    CsvDatasetWriter,
    GeneratorConfig,
    PayPalLikeGenerator,
    build_rule_seeds,
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_generator_writes_exactly_40_business_tables(tmp_path: Path) -> None:
    output = tmp_path / "dataset"
    config = GeneratorConfig(users=20, transactions=60, seed=7, risk_ratio=0.2)
    PayPalLikeGenerator(config).generate(CsvDatasetWriter(output))

    table_files = {path.stem for path in output.glob("*.csv") if not path.name.startswith("_")}
    assert len(TABLE_COLUMNS) == 40
    assert table_files == set(TABLE_COLUMNS)
    manifest = json.loads((output / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["table_count"] == 40
    assert manifest["rule_count"] == 74


def test_conversation_granularity_and_foreign_keys(tmp_path: Path) -> None:
    output = tmp_path / "dataset"
    PayPalLikeGenerator(GeneratorConfig(users=20, transactions=40, seed=11)).generate(CsvDatasetWriter(output))

    interactions = {row["interaction_id"] for row in _read(output / "interaction.csv")}
    segments = _read(output / "conversation_segment.csv")
    messages = _read(output / "message.csv")
    segment_ids = {row["segment_id"] for row in segments}

    assert all(row["interaction_id"] in interactions for row in segments)
    assert all(row["segment_id"] in segment_ids for row in messages)
    assert len(messages) == len(segments) * 2


def test_transaction_ledger_is_balanced(tmp_path: Path) -> None:
    output = tmp_path / "dataset"
    PayPalLikeGenerator(GeneratorConfig(users=20, transactions=50, seed=19)).generate(CsvDatasetWriter(output))
    ledger = _read(output / "ledger_entry.csv")

    totals: dict[str, float] = {}
    for row in ledger:
        sign = 1 if row["direction"] == "CREDIT" else -1
        totals[row["transaction_id"]] = totals.get(row["transaction_id"], 0.0) + sign * float(row["amount"])
    assert all(abs(total) < 0.001 for total in totals.values())


def test_seed_rules_cover_production_categories() -> None:
    rules = build_rule_seeds()
    assert len(rules) == 74
    assert len({rule["rule_id"] for rule in rules}) == 74
    assert {rule["category"] for rule in rules} == {
        "KYC_KYB", "AML", "PAYMENT_FRAUD", "ACCOUNT_TAKEOVER",
        "SANCTIONS_PEP", "REFUND_CHARGEBACK", "COMMUNICATION",
    }


def test_existing_output_requires_explicit_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "dataset"
    output.mkdir()
    with pytest.raises(FileExistsError):
        CsvDatasetWriter(output)

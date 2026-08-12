"""Regression tests for the offline risk evaluation metric definitions."""

from scripts.evaluate_risk_system import calculate_metrics, generate_holdout


def _rows(truth: list[int], scores: list[int]) -> list[dict]:
    return [
        {"truth_label": label, "final_score": score}
        for label, score in zip(truth, scores, strict=True)
    ]


def test_perfect_classifier_metrics() -> None:
    metrics = calculate_metrics(_rows([0, 0, 1, 1], [0, 29, 30, 100]), "final_score", 30)
    assert metrics["accuracy"] == 1
    assert metrics["precision"] == 1
    assert metrics["recall"] == 1
    assert metrics["false_positive_rate"] == 0
    assert metrics["false_negative_rate"] == 0


def test_confusion_matrix_and_rate_denominators() -> None:
    metrics = calculate_metrics(_rows([1, 0, 0, 1], [80, 10, 80, 10]), "final_score", 30)
    assert (metrics["tp"], metrics["tn"], metrics["fp"], metrics["fn"]) == (1, 1, 1, 1)
    assert metrics["accuracy"] == 0.5
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["false_positive_rate"] == 0.5
    assert metrics["false_negative_rate"] == 0.5


def test_no_positive_predictions_are_zero_division_safe() -> None:
    metrics = calculate_metrics(_rows([0, 0, 1, 1], [0, 0, 0, 0]), "final_score", 30)
    assert metrics["precision"] == 0
    assert metrics["recall"] == 0
    assert metrics["false_positive_rate"] == 0
    assert metrics["false_negative_rate"] == 1


def test_higher_threshold_reduces_or_preserves_action_rate() -> None:
    rows = _rows([0, 1, 0, 1, 0], [10, 35, 55, 85, 95])
    threshold_30 = calculate_metrics(rows, "final_score", 30)
    threshold_80 = calculate_metrics(rows, "final_score", 80)
    assert threshold_80["action_rate"] <= threshold_30["action_rate"]


def test_holdout_is_deterministic_and_stratified() -> None:
    first = generate_holdout(per_scenario=100, seed=20260821)
    second = generate_holdout(per_scenario=100, seed=20260821)
    assert first == second
    assert len(first) == 400
    assert {scenario: sum(row["scenario"] == scenario for row in first) for scenario in {
        "CARD", "LOAN", "TRANSFER", "LOGIN"
    }} == {"CARD": 100, "LOAN": 100, "TRANSFER": 100, "LOGIN": 100}

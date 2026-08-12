from __future__ import annotations

import unittest
from datetime import date, datetime

from app.scoring import calculate_account_age_days, calculate_risk_score, sigmoid


class RiskScoreTests(unittest.TestCase):
    def test_no_hits_is_zero_and_passes(self) -> None:
        result = calculate_risk_score([])
        self.assertEqual(result.final_score, 0)
        self.assertEqual(result.decision, "PASS")

    def test_single_hit_keeps_rule_score(self) -> None:
        result = calculate_risk_score([70])
        self.assertEqual(result.raw_score, 70)
        self.assertEqual(result.final_score, 70)
        self.assertEqual(result.decision, "REVIEW")

    def test_multiple_hits_add_only_hit_count_minus_one(self) -> None:
        result = calculate_risk_score([50, 70, 60])
        self.assertEqual(result.highest_rule_score, 70)
        self.assertEqual(result.hit_count, 3)
        self.assertEqual(result.final_score, 72)
        self.assertEqual(result.decision, "REVIEW")

    def test_score_is_capped_at_one_hundred(self) -> None:
        result = calculate_risk_score([95, 90, 80, 70, 60, 50, 50, 50])
        self.assertEqual(result.raw_score, 102)
        self.assertEqual(result.final_score, 100)
        self.assertEqual(result.decision, "REJECT")

    def test_model_margin_uses_sigmoid_and_percentage_score(self) -> None:
        result = calculate_risk_score([], model_margin=0.0)
        self.assertAlmostEqual(result.model_probability, 0.5)
        self.assertEqual(result.model_score, 50)
        self.assertEqual(result.blended_score, 20)
        self.assertEqual(result.final_score, 20)
        self.assertEqual(result.decision, "PASS")

    def test_model_can_raise_but_never_lower_rule_score(self) -> None:
        high_model = calculate_risk_score([70], model_margin=3.0)
        self.assertEqual(high_model.model_score, 95)
        self.assertEqual(high_model.blended_score, 80)
        self.assertEqual(high_model.final_score, 80)
        self.assertEqual(high_model.decision, "REJECT")

        low_model = calculate_risk_score([70], model_margin=-3.0)
        self.assertEqual(low_model.model_score, 5)
        self.assertEqual(low_model.final_score, 70)

    def test_sigmoid_is_stable_for_large_margins(self) -> None:
        self.assertAlmostEqual(sigmoid(1000), 1.0)
        self.assertAlmostEqual(sigmoid(-1000), 0.0)

    def test_confirmed_decision_boundaries(self) -> None:
        expected = {
            29: "PASS",
            30: "REVIEW",
            74: "REVIEW",
            75: "REJECT",
        }
        for score, decision in expected.items():
            with self.subTest(score=score):
                self.assertEqual(calculate_risk_score([score]).decision, decision)

    def test_account_age_is_calculated_from_registration_date(self) -> None:
        registered_at = datetime(2026, 8, 1, 23, 30)
        self.assertEqual(
            calculate_account_age_days(registered_at, as_of=date(2026, 8, 11)),
            10,
        )

    def test_future_registration_never_returns_negative_age(self) -> None:
        self.assertEqual(
            calculate_account_age_days(date(2026, 8, 12), as_of=date(2026, 8, 11)),
            0,
        )


if __name__ == "__main__":
    unittest.main()

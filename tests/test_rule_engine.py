import unittest

from app.engine.rule import evaluate_condition


class RuleEngineTests(unittest.TestCase):
    def test_rule_matches_a_feature_threshold(self):
        self.assertTrue(
            evaluate_condition(
                {"field": "device_linked_new_users_7d", "op": ">=", "value": 5},
                {"device_linked_new_users_7d": 5},
            )
        )

    def test_rule_does_not_match_when_the_feature_is_below_threshold(self):
        self.assertFalse(
            evaluate_condition(
                {"field": "device_linked_new_users_7d", "op": ">=", "value": 5},
                {"device_linked_new_users_7d": 4},
            )
        )

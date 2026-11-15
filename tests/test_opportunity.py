import unittest
from datetime import datetime, timedelta, timezone

from layer1.opportunity import (
    FACTOR_NAMES, OpportunityEvaluationEngine, OpportunityPolicy,
)


def now(delta=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()


class OpportunityEvaluationEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = OpportunityEvaluationEngine()
        self.fixed_now = now()
        self.policy = OpportunityPolicy(
            policy_version="test-policy-v1",
            weights={
                "evidence_strength": 0.25, "timeliness": 0.20,
                "materiality": 0.15, "audience_usefulness": 0.15,
                "novelty": 0.15, "risk_control": 0.10,
            },
            proceed_threshold=75, defer_threshold=50,
        )
        self.factors = {name: 90 for name in FACTOR_NAMES}

    def evaluate(self, **overrides):
        args = {
            "eligibility_status": "ELIGIBLE", "eligibility_verified_at": self.fixed_now,
            "research_completeness": "READY", "event_state": "CONFIRMED",
            "now": self.fixed_now,
            "contradiction_count": 0, "unresolved_critical_count": 0,
            "unsupported_causal_framing": False, "duplicate_angle": False,
            "materially_new": False, "factors": self.factors, "policy": self.policy,
        }
        args.update(overrides)
        return self.engine.evaluate(**args)

    def test_deterministic_high_quality_research_proceeds(self):
        first = self.evaluate()
        second = self.evaluate()
        self.assertEqual(first.state, "PROCEED")
        self.assertEqual(first.score, 90)
        self.assertEqual(first.decision_id, second.decision_id)

    def test_unlisted_asset_is_rejected_even_with_maximum_score(self):
        result = self.evaluate(eligibility_status="NOT_ELIGIBLE")
        self.assertEqual(result.state, "REJECT")
        self.assertIn("BINANCE_SPOT_ELIGIBILITY_NOT_VERIFIED", result.reasons)

    def test_stale_snapshot_defers_even_with_high_score(self):
        result = self.evaluate(eligibility_verified_at=now(-400))
        self.assertEqual(result.state, "DEFER")
        self.assertIn("BINANCE_SPOT_ELIGIBILITY_STALE", result.reasons)

    def test_contradiction_rejects_and_unresolved_critical_claim_requests_more(self):
        self.assertEqual(self.evaluate(contradiction_count=1).state, "REJECT")
        self.assertEqual(self.evaluate(unresolved_critical_count=1).state, "RESEARCH_MORE")

    def test_duplicate_angle_requires_material_update(self):
        self.assertEqual(self.evaluate(duplicate_angle=True).state, "REJECT")
        self.assertEqual(self.evaluate(duplicate_angle=True, materially_new=True).state, "PROCEED")

    def test_unconfigured_policy_defers_instead_of_guessing_weights(self):
        result = self.evaluate(policy=None)
        self.assertEqual(result.state, "DEFER")
        self.assertIn("APPROVED_OPPORTUNITY_SCORING_POLICY_NOT_CONFIGURED", result.reasons)

    def test_invalid_weights_or_factors_are_rejected(self):
        bad = OpportunityPolicy(
            policy_version="bad", weights={name: 1 for name in FACTOR_NAMES},
            proceed_threshold=70, defer_threshold=50,
        )
        with self.assertRaisesRegex(ValueError, "sum to 1.0"):
            bad.validate()
        result = self.evaluate(factors={"evidence_strength": 101})
        self.assertEqual(result.state, "DEFER")
        self.assertIn("OPPORTUNITY_FACTORS_INCOMPLETE", result.reasons)

    def test_nonready_research_or_withdrawn_event_never_proceeds(self):
        self.assertEqual(self.evaluate(research_completeness="RESEARCH_MORE").state, "RESEARCH_MORE")
        self.assertEqual(self.evaluate(event_state="WITHDRAWN").state, "REJECT")
        self.assertEqual(self.evaluate(event_state="DISPUTED").state, "REJECT")
        self.assertEqual(self.evaluate(event_state="STALE").state, "DEFER")

    def test_decision_identity_binds_exact_factor_inputs_not_only_weighted_score(self):
        first_factors = dict(self.factors)
        second_factors = dict(self.factors)
        first_factors["evidence_strength"] = 94
        first_factors["timeliness"] = 85
        second_factors["evidence_strength"] = 86
        second_factors["timeliness"] = 95
        first = self.evaluate(factors=first_factors)
        second = self.evaluate(factors=second_factors)
        self.assertEqual(first.score, second.score)
        self.assertNotEqual(first.decision_id, second.decision_id)

    def test_decision_identity_binds_policy_thresholds_and_weights(self):
        from dataclasses import replace
        first = self.evaluate()
        alternate = replace(
            self.policy,
            weights={name: 1 / len(FACTOR_NAMES) for name in FACTOR_NAMES},
            proceed_threshold=76,
        )
        second = self.evaluate(policy=alternate)
        self.assertEqual(first.state, second.state)
        self.assertEqual(first.score, second.score)
        self.assertNotEqual(first.decision_id, second.decision_id)

    def test_eligibility_age_bound_must_be_a_positive_integer_even_without_policy(self):
        for invalid in (True, 0, -1, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "eligibility age bound"):
                    self.evaluate(policy=None, eligibility_max_age_seconds=invalid)

    def test_policy_rejects_boolean_non_numeric_and_non_finite_thresholds(self):
        for proceed, defer in ((True, 50), (75, False), (float("nan"), 50),
                               (75, float("inf")), ("75", 50)):
            with self.subTest(proceed=proceed, defer=defer):
                invalid = OpportunityPolicy(
                    policy_version="invalid-threshold",
                    weights=self.policy.weights,
                    proceed_threshold=proceed,
                    defer_threshold=defer,
                )
                with self.assertRaisesRegex(ValueError, "thresholds"):
                    invalid.validate()

    def test_decision_store_rejects_malformed_decision_payload(self):
        import sqlite3
        from dataclasses import replace
        from layer1.opportunity import OpportunityDecisionStore
        connection = sqlite3.connect(":memory:")
        try:
            store = OpportunityDecisionStore(connection)
            decision = self.evaluate()
            with self.assertRaisesRegex(ValueError, "decision payload"):
                store.save("research:package:1", replace(decision, state="UNKNOWN"))
            with self.assertRaisesRegex(ValueError, "decision payload"):
                store.save("research:package:1", replace(decision, score=float("nan")))
        finally:
            connection.close()

    def test_decision_store_rejects_id_collision_with_different_decision_payload(self):
        import sqlite3
        from dataclasses import replace
        from layer1.opportunity import OpportunityDecisionStore
        connection = sqlite3.connect(":memory:")
        try:
            store = OpportunityDecisionStore(connection)
            decision = self.evaluate()
            store.save("research:package:1", decision)
            stored = connection.execute(
                "SELECT input_snapshot_json FROM opportunity_decisions WHERE decision_id=?",
                (decision.decision_id,),
            ).fetchone()
            import json
            snapshot = json.loads(stored[0])
            self.assertEqual(snapshot["inputs"]["factors"]["evidence_strength"], 90.0)
            self.assertEqual(snapshot["policy"]["policy_version"], "test-policy-v1")
            tampered = replace(decision, score=decision.score - 1)
            with self.assertRaisesRegex(ValueError, "decision ID"):
                store.save("research:package:1", tampered)
            with self.assertRaisesRegex(ValueError, "different research package"):
                store.save("research:package:2", decision)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

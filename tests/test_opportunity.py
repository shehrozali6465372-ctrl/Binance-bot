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
            "eligibility_status": "ELIGIBLE", "eligibility_verified_at": now(),
            "research_completeness": "READY", "event_state": "CONFIRMED",
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


if __name__ == "__main__":
    unittest.main()

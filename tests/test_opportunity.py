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

    def test_identical_opportunity_inputs_for_different_assets_have_distinct_decision_ids(self):
        first = self.evaluate(asset_id="coingecko:asset-one")
        second = self.evaluate(asset_id="coingecko:asset-two")

        self.assertEqual(first.state, "PROCEED")
        self.assertEqual(second.state, "PROCEED")
        self.assertNotEqual(first.decision_id, second.decision_id)

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


class OpportunityFactorProvenanceSchemaTests(unittest.TestCase):
    """Versioned provenance schema must be strict while legacy snapshots replay."""

    def setUp(self):
        import copy
        self.copy = copy
        self.cutoff = "2026-11-21T12:00:00Z"
        self.asset_id = "coingecko:bitcoin"
        self.snapshot = {
            "policy": {"policy_version": "proposal-only-test-v1"},
            "inputs": {
                "schema_version": 2,
                "asset_id": self.asset_id,
                "decision_cutoff_at": self.cutoff,
                "factor_assessments": [self._factor(name) for name in FACTOR_NAMES],
            },
        }

    def _factor(self, name):
        return {
            "factor_name": name,
            "assessment_status": "READY",
            "value": 72.5,
            "rubric_version": "unapproved-fixture-rubric-v1",
            "feature_pipeline_version": "fixture-pipeline-v1",
            "source_contract_version": "fixture-source-contract-v1",
            "subfeatures": [{
                "feature_key": name + ".fixture_signal",
                "asset_id": self.asset_id,
                "availability": "AVAILABLE",
                "raw_value": 123.0,
                "normalized_value": 0.725,
                "unit": "fixture_unit",
                "source_refs": ["evidence:" + name + ":1"],
                "source_payload_hashes": ["a" * 64],
                "provider_timestamp": "2026-11-21T11:59:00Z",
                "event_at": None,
                "event_time_semantics": None,
                "published_at": "2026-11-21T11:58:00Z",
                "updated_at": "2026-11-21T11:59:00Z",
                "observed_at": "2026-11-21T11:59:30Z",
                "window_start_at": "2026-11-21T11:00:00Z",
                "window_end_at": "2026-11-21T11:59:00Z",
                "transformation_id": "fixture-normalizer",
                "transformation_version": "1",
                "baseline_id": "fixture-baseline",
                "baseline_version": "1",
                "source_dependency_group": "fixture-source-family",
                "quality_flags": [],
                "missing_reason": None,
            }],
            "reason_codes": [],
            "evaluated_at": "2026-11-21T12:00:00Z",
            "decision_cutoff_at": self.cutoff,
        }

    def validate(self, snapshot=None, expected_asset_id=None):
        from layer1.opportunity import validate_opportunity_input_snapshot
        return validate_opportunity_input_snapshot(
            self.snapshot if snapshot is None else snapshot,
            expected_asset_id=expected_asset_id,
        )

    def test_accepts_complete_versioned_provenance_envelope(self):
        self.assertEqual(self.validate(expected_asset_id=self.asset_id), 2)

    def test_preserves_legacy_snapshot_compatibility(self):
        legacy = {"policy": {"version": "legacy-v1"}, "inputs": {"factor": 0.9}}
        self.assertEqual(self.validate(legacy), 1)
        self.assertEqual(self.validate({"policy": None, "inputs": ["legacy", 1]}), 1)

    def test_rejects_versioned_snapshot_for_different_research_asset(self):
        with self.assertRaisesRegex(ValueError, "snapshot asset identity"):
            self.validate(expected_asset_id="coingecko:ethereum")

    def test_rejects_missing_factor_assessment(self):
        malformed = self.copy.deepcopy(self.snapshot)
        malformed["inputs"]["factor_assessments"].pop()
        with self.assertRaisesRegex(ValueError, "all six factors"):
            self.validate(malformed)

    def test_rejects_numeric_value_for_non_ready_factor(self):
        malformed = self.copy.deepcopy(self.snapshot)
        factor = malformed["inputs"]["factor_assessments"][0]
        factor["assessment_status"] = "STALE"
        factor["reason_codes"] = ["SOURCE_TOO_OLD"]
        with self.assertRaisesRegex(ValueError, "non-READY"):
            self.validate(malformed)

    def test_rejects_ready_factor_without_source_references(self):
        malformed = self.copy.deepcopy(self.snapshot)
        malformed["inputs"]["factor_assessments"][0]["subfeatures"][0]["source_refs"] = []
        with self.assertRaisesRegex(ValueError, "source reference"):
            self.validate(malformed)

    def test_rejects_evidence_observed_after_decision_cutoff(self):
        malformed = self.copy.deepcopy(self.snapshot)
        malformed["inputs"]["factor_assessments"][0]["subfeatures"][0]["observed_at"] = "2026-11-21T12:00:01Z"
        with self.assertRaisesRegex(ValueError, "after decision cutoff"):
            self.validate(malformed)

    def test_rejects_subfeature_for_different_asset(self):
        malformed = self.copy.deepcopy(self.snapshot)
        malformed["inputs"]["factor_assessments"][0]["subfeatures"][0]["asset_id"] = "coingecko:ethereum"
        with self.assertRaisesRegex(ValueError, "asset identity"):
            self.validate(malformed)

    def test_rejects_malformed_source_payload_hash(self):
        malformed = self.copy.deepcopy(self.snapshot)
        malformed["inputs"]["factor_assessments"][0]["subfeatures"][0]["source_payload_hashes"] = ["not-a-hash"]
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.validate(malformed)

    def test_rejects_future_event_time_without_scheduled_event_semantics(self):
        malformed = self.copy.deepcopy(self.snapshot)
        subfeature = malformed["inputs"]["factor_assessments"][0]["subfeatures"][0]
        subfeature["event_at"] = "2026-11-22T12:00:00Z"
        with self.assertRaisesRegex(ValueError, "future event_at"):
            self.validate(malformed)

    def test_accepts_future_event_time_only_when_explicitly_scheduled(self):
        valid = self.copy.deepcopy(self.snapshot)
        subfeature = valid["inputs"]["factor_assessments"][0]["subfeatures"][0]
        subfeature["event_at"] = "2026-11-22T12:00:00Z"
        subfeature["event_time_semantics"] = "SCHEDULED_FUTURE_EVENT"
        self.assertEqual(self.validate(valid), 2)

    def test_rejects_ready_factor_that_depends_on_unavailable_subfeature(self):
        malformed = self.copy.deepcopy(self.snapshot)
        subfeature = malformed["inputs"]["factor_assessments"][0]["subfeatures"][0]
        subfeature["availability"] = "STALE"
        subfeature["raw_value"] = None
        subfeature["normalized_value"] = None
        subfeature["source_refs"] = []
        subfeature["missing_reason"] = "STALE_SOURCE"
        with self.assertRaisesRegex(ValueError, "READY factor assessment cannot depend"):
            self.validate(malformed)

    def test_rejects_normalized_feature_without_baseline_provenance(self):
        malformed = self.copy.deepcopy(self.snapshot)
        subfeature = malformed["inputs"]["factor_assessments"][0]["subfeatures"][0]
        subfeature["baseline_id"] = None
        subfeature["baseline_version"] = None
        with self.assertRaisesRegex(ValueError, "requires baseline provenance"):
            self.validate(malformed)

    def test_rejects_duplicate_subfeature_keys_within_factor(self):
        malformed = self.copy.deepcopy(self.snapshot)
        subfeature = self.copy.deepcopy(malformed["inputs"]["factor_assessments"][0]["subfeatures"][0])
        malformed["inputs"]["factor_assessments"][0]["subfeatures"].append(subfeature)
        with self.assertRaisesRegex(ValueError, "subfeature keys must be unique"):
            self.validate(malformed)

    def test_rejects_non_utc_timestamp_offsets(self):
        malformed = self.copy.deepcopy(self.snapshot)
        malformed["inputs"]["factor_assessments"][0]["subfeatures"][0]["observed_at"] = "2026-11-21T16:59:30+05:00"
        with self.assertRaisesRegex(ValueError, "UTC ISO-8601"):
            self.validate(malformed)

    def test_rejects_not_applicable_until_rubric_approval_exists(self):
        malformed = self.copy.deepcopy(self.snapshot)
        malformed["inputs"]["factor_assessments"][0]["assessment_status"] = "NOT_APPLICABLE"
        malformed["inputs"]["factor_assessments"][0]["value"] = None
        malformed["inputs"]["factor_assessments"][0]["reason_codes"] = ["NOT_APPROVED"]
        with self.assertRaisesRegex(ValueError, "status is not approved"):
            self.validate(malformed)

    def test_decision_digest_rejects_malformed_versioned_snapshot(self):
        import json
        from layer1.opportunity import _decision_digest
        malformed = self.copy.deepcopy(self.snapshot)
        malformed["inputs"]["factor_assessments"] = []
        encoded = json.dumps(malformed, sort_keys=True, separators=(",", ":"))
        with self.assertRaisesRegex(ValueError, "all six factors"):
            _decision_digest(
                state="DEFER", score=None, reasons=("INVALID",),
                policy_version="UNCONFIGURED", input_snapshot_json=encoded,
            )

    def test_decision_digest_binds_and_validates_versioned_provenance(self):
        import json
        from layer1.opportunity import _decision_digest
        encoded = json.dumps(self.snapshot, sort_keys=True, separators=(",", ":"))
        first = _decision_digest(
            state="DEFER", score=None, reasons=("PROVENANCE_FIXTURE_ONLY",),
            policy_version="UNCONFIGURED", input_snapshot_json=encoded,
        )
        changed = self.copy.deepcopy(self.snapshot)
        changed["inputs"]["factor_assessments"][0]["subfeatures"][0]["source_refs"] = ["evidence:changed"]
        changed_encoded = json.dumps(changed, sort_keys=True, separators=(",", ":"))
        second = _decision_digest(
            state="DEFER", score=None, reasons=("PROVENANCE_FIXTURE_ONLY",),
            policy_version="UNCONFIGURED", input_snapshot_json=changed_encoded,
        )
        self.assertNotEqual(first, second)


    def test_sqlite_decision_store_accepts_versioned_provenance_and_replays_immutably(self):
        import json
        import sqlite3
        from layer1.opportunity import OpportunityDecision, OpportunityDecisionStore, _decision_digest
        encoded = json.dumps(self.snapshot, sort_keys=True, separators=(",", ":"))
        reasons = ("PROVENANCE_FIXTURE_ONLY",)
        decision_id = _decision_digest(
            state="DEFER", score=None, reasons=reasons,
            policy_version="UNCONFIGURED", input_snapshot_json=encoded,
        )
        decision = OpportunityDecision("DEFER", None, reasons, "UNCONFIGURED", decision_id, encoded)
        connection = sqlite3.connect(":memory:")
        try:
            store = OpportunityDecisionStore(connection)
            self.assertEqual(store.save("research:package:v2", decision), decision_id)
            self.assertEqual(store.save("research:package:v2", decision), decision_id)
        finally:
            connection.close()

    def test_postgres_input_validator_accepts_valid_versioned_provenance(self):
        import json
        from layer1.opportunity import OpportunityDecision, _decision_digest
        from layer1.publication_postgres import validate_opportunity_decision_input
        encoded = json.dumps(self.snapshot, sort_keys=True, separators=(",", ":"))
        reasons = ("PROVENANCE_FIXTURE_ONLY",)
        decision_id = _decision_digest(
            state="DEFER", score=None, reasons=reasons,
            policy_version="UNCONFIGURED", input_snapshot_json=encoded,
        )
        decision = OpportunityDecision("DEFER", None, reasons, "UNCONFIGURED", decision_id, encoded)
        validate_opportunity_decision_input("research:package:v2", decision)

    def test_read_digest_verifier_accepts_legacy_and_v2_records(self):
        import json
        from layer1.opportunity import _decision_digest, verify_opportunity_decision_digest
        legacy = {"policy": {"version": "legacy-v1"}, "inputs": {"factor": 0.9}}
        legacy_json = json.dumps(legacy, sort_keys=True, separators=(",", ":"))
        legacy_reasons = ("LEGACY_REPLAY",)
        legacy_id = _decision_digest(
            state="DEFER", score=None, reasons=legacy_reasons,
            policy_version="legacy-v1", input_snapshot_json=legacy_json,
        )
        self.assertTrue(verify_opportunity_decision_digest(
            decision_id=legacy_id, state="DEFER", score=None,
            reasons=list(legacy_reasons), policy_version="legacy-v1",
            input_snapshot=legacy,
        ))
        v2_json = json.dumps(self.snapshot, sort_keys=True, separators=(",", ":"))
        v2_reasons = ("PROVENANCE_FIXTURE_ONLY",)
        v2_id = _decision_digest(
            state="DEFER", score=None, reasons=v2_reasons,
            policy_version="UNCONFIGURED", input_snapshot_json=v2_json,
        )
        self.assertTrue(verify_opportunity_decision_digest(
            decision_id=v2_id, state="DEFER", score=None,
            reasons=list(v2_reasons), policy_version="UNCONFIGURED",
            input_snapshot=self.snapshot,
        ))

    def test_read_digest_verifier_rejects_stored_snapshot_tampering(self):
        from layer1.opportunity import verify_opportunity_decision_digest
        with self.assertRaisesRegex(ValueError, "digest"):
            verify_opportunity_decision_digest(
                decision_id="0" * 64, state="DEFER", score=None,
                reasons=["TAMPERED"], policy_version="legacy-v1",
                input_snapshot={"policy": {"version": "legacy-v1"}, "inputs": {"factor": 0.9}},
            )

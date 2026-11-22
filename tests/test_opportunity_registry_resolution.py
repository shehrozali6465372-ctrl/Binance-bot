from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import asdict

from layer1.evidence_verification import Claim, EvidenceRecord, EvidenceVerificationEngine


class RegistryBoundFactorSourceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.record = EvidenceRecord(
            source_id="market-snapshot:btc:001", source_family="binance_spot",
            source_kind="MARKET", publisher="Binance Spot API", subject="coingecko:bitcoin",
            claim_key="market.price", value=65000.0,
            published_at="2026-11-21T11:58:00Z", updated_at="2026-11-21T11:59:00Z",
            observed_at="2026-11-21T11:59:30Z", asset_id="coingecko:bitcoin",
            unit="usd", timeframe="spot", source_url="https://api.binance.com/api/v3/ticker/price",
            content_hash="b" * 64, lineage_id="binance-snapshot:001",
            is_primary=True, source_status="ACCEPTED",
        )
        self.claim = Claim(
            text=f"Source assertion: coingecko:bitcoin market.price = 65000.0",
            subject="coingecko:bitcoin", claim_key="market.price", value=65000.0,
            observed_at="2026-11-21T11:59:45Z", evidence_ids=(self.record.evidence_id,),
            asset_id="coingecko:bitcoin", unit="usd", timeframe="spot",
            claim_type="SOURCE_ASSERTION", impact="MEDIUM",
        )
        self.registry_object = EvidenceVerificationEngine().verify((self.claim,), (self.record,))
        self.payload = self.registry_object.to_dict()
        self.registry_id = self._digest(self.payload)
        self.registry = {"verification_id": self.registry_id, "payload": self.payload}
        self.subfeature = {
            "source_refs": [self.record.evidence_id],
            "claim_refs": [self.claim.claim_id],
            "source_payload_hashes": [self.record.content_hash],
            "source_provenance": [asdict(self.record) | {"evidence_id": self.record.evidence_id}],
        }

    @staticmethod
    def _digest(payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def resolve(self, subfeature=None, registry=None, expected_registry_id=None):
        from layer1.opportunity import resolve_factor_source_provenance
        selected_registry = self.registry if registry is None else registry
        return resolve_factor_source_provenance(
            self.subfeature if subfeature is None else subfeature,
            selected_registry,
            expected_registry_verification_id=(
                selected_registry["verification_id"] if expected_registry_id is None
                else expected_registry_id
            ),
            expected_asset_id="coingecko:bitcoin",
            decision_cutoff_at="2026-11-21T12:00:00Z",
        )

    def test_resolves_exact_record_from_digest_verified_registry(self):
        self.assertEqual(self.resolve(), (self.record,))

    def test_rejects_unknown_evidence_reference(self):
        malformed = copy.deepcopy(self.subfeature)
        malformed["source_refs"] = ["f" * 64]
        malformed["source_provenance"][0]["evidence_id"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.resolve(malformed)

    def test_rejects_copied_trust_metadata_tampering_even_when_evidence_id_is_unchanged(self):
        malformed = copy.deepcopy(self.subfeature)
        malformed["source_provenance"][0]["publisher"] = "untrusted replacement"
        with self.assertRaisesRegex(ValueError, "provenance does not match"):
            self.resolve(malformed)

    def test_rejects_registry_snapshot_digest_mismatch(self):
        tampered = copy.deepcopy(self.registry)
        tampered["payload"]["evidence_records"][0]["publisher"] = "tampered"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.resolve(registry=tampered)

    def test_rejects_different_registry_snapshot_id(self):
        with self.assertRaisesRegex(ValueError, "ID does not match"):
            self.resolve(expected_registry_id="e" * 64)

    def test_does_not_fabricate_payload_hash_for_adapters_without_one(self):
        record = EvidenceRecord(
            source_id="onchain-observation:001", source_family="provider-x",
            source_kind="ONCHAIN", publisher="provider-x", subject="coingecko:bitcoin",
            claim_key="onchain.transaction_hash", value="0x" + "1" * 64,
            published_at="2026-11-21T11:58:00Z", observed_at="2026-11-21T11:59:30Z",
            asset_id="coingecko:bitcoin", timeframe="ethereum-mainnet",
            content_hash="", lineage_id="observation:001",
            is_primary=True, source_status="ACCEPTED",
        )
        payload = {
            "claims": [],
            "evidence_records": [asdict(record) | {"evidence_id": record.evidence_id}],
            "results": [], "unresolved_issues": [],
        }
        registry_id = self._digest(payload)
        subfeature = {
            "source_refs": [record.evidence_id], "source_payload_hashes": [],
            "source_provenance": [asdict(record) | {"evidence_id": record.evidence_id}],
        }
        from layer1.opportunity import resolve_factor_source_provenance
        resolved = resolve_factor_source_provenance(
            subfeature, {"verification_id": registry_id, "payload": payload},
            expected_registry_verification_id=registry_id,
            expected_asset_id="coingecko:bitcoin",
            decision_cutoff_at="2026-11-21T12:00:00Z",
        )
        self.assertEqual(resolved, (record,))

    def test_rejects_cross_asset_evidence(self):
        registry = copy.deepcopy(self.registry)
        registry["payload"]["evidence_records"][0]["asset_id"] = "coingecko:ethereum"
        raw = registry["payload"]["evidence_records"][0]
        registry["payload"]["evidence_records"][0]["evidence_id"] = EvidenceRecord(**{
            key: value for key, value in raw.items() if key != "evidence_id"
        }).evidence_id
        registry["verification_id"] = self._digest(registry["payload"])
        malformed = copy.deepcopy(self.subfeature)
        malformed["source_refs"] = [registry["payload"]["evidence_records"][0]["evidence_id"]]
        malformed["source_provenance"][0]["evidence_id"] = registry["payload"]["evidence_records"][0]["evidence_id"]
        malformed["source_provenance"][0]["asset_id"] = "coingecko:ethereum"
        with self.assertRaisesRegex(ValueError, "asset identity"):
            self.resolve(malformed, registry)

    def test_rejects_source_observed_after_decision_cutoff(self):
        registry = copy.deepcopy(self.registry)
        registry["payload"]["evidence_records"][0]["observed_at"] = "2026-11-21T12:00:01Z"
        raw = registry["payload"]["evidence_records"][0]
        registry["payload"]["evidence_records"][0]["evidence_id"] = EvidenceRecord(**{
            key: value for key, value in raw.items() if key != "evidence_id"
        }).evidence_id
        registry["verification_id"] = self._digest(registry["payload"])
        malformed = copy.deepcopy(self.subfeature)
        malformed["source_refs"] = [registry["payload"]["evidence_records"][0]["evidence_id"]]
        malformed["source_provenance"][0]["evidence_id"] = registry["payload"]["evidence_records"][0]["evidence_id"]
        malformed["source_provenance"][0]["observed_at"] = "2026-11-21T12:00:01Z"
        with self.assertRaisesRegex(ValueError, "after decision cutoff"):
            self.resolve(malformed, registry)

    def test_rejects_payload_hash_not_bound_to_source_record(self):
        malformed = copy.deepcopy(self.subfeature)
        malformed["source_payload_hashes"] = ["c" * 64]
        with self.assertRaisesRegex(ValueError, "payload hashes do not match"):
            self.resolve(malformed)

    def _v3_snapshot(self):
        feature = {
            "feature_key": "evidence_strength.source_quality",
            "asset_id": "coingecko:bitcoin", "availability": "AVAILABLE",
            "raw_value": 1.0, "normalized_value": None, "unit": "count",
            "source_refs": [self.record.evidence_id],
            "claim_refs": [self.claim.claim_id],
            "source_payload_hashes": [self.record.content_hash],
            "source_provenance": [asdict(self.record) | {"evidence_id": self.record.evidence_id}],
            "provider_timestamp": None, "event_at": None, "event_time_semantics": None,
            "published_at": self.record.published_at, "updated_at": self.record.updated_at,
            "observed_at": self.record.observed_at, "window_start_at": None, "window_end_at": None,
            "transformation_id": None, "transformation_version": None,
            "baseline_id": None, "baseline_version": None,
            "source_dependency_group": "binance_spot", "quality_flags": [], "missing_reason": None,
        }
        factors = []
        for name in (
            "evidence_strength", "timeliness", "materiality",
            "audience_usefulness", "novelty", "risk_control",
        ):
            factors.append({
                "factor_name": name, "assessment_status": "READY", "value": 50.0,
                "rubric_version": "fixture-rubric-v1",
                "feature_pipeline_version": "fixture-pipeline-v1",
                "source_contract_version": "fixture-source-v1",
                "subfeatures": [copy.deepcopy(feature)], "reason_codes": [],
                "evaluated_at": "2026-11-21T12:00:00Z",
                "decision_cutoff_at": "2026-11-21T12:00:00Z",
            })
        return {"policy": None, "inputs": {
            "schema_version": 3, "asset_id": "coingecko:bitcoin",
            "decision_cutoff_at": "2026-11-21T12:00:00Z",
            "registry_verification_id": self.registry_id,
            "factor_assessments": factors,
        }}

    def test_registry_bound_v3_snapshot_resolves_all_source_refs(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        self.assertEqual(
            validate_registry_bound_opportunity_input_snapshot(
                self._v3_snapshot(), self.registry,
            ),
            3,
        )

    def test_registry_bound_v3_ready_evidence_strength_requires_claim_refs(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        snapshot = self._v3_snapshot()
        evidence_factor = next(
            item for item in snapshot["inputs"]["factor_assessments"]
            if item["factor_name"] == "evidence_strength"
        )
        evidence_factor["subfeatures"][0].pop("claim_refs")
        with self.assertRaisesRegex(ValueError, "claim references are required"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, self.registry)

    def test_registry_bound_v3_ready_materiality_requires_claim_refs(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        snapshot = self._v3_snapshot()
        materiality_factor = next(
            item for item in snapshot["inputs"]["factor_assessments"]
            if item["factor_name"] == "materiality"
        )
        materiality_factor["subfeatures"][0].pop("claim_refs")
        with self.assertRaisesRegex(ValueError, "claim references are required"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, self.registry)

    def test_registry_bound_v3_snapshot_rejects_missing_registry_reference(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        snapshot = self._v3_snapshot()
        snapshot["inputs"]["registry_verification_id"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "snapshot ID does not match"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, self.registry)

    def _v3_decision(self):
        from layer1.opportunity import OpportunityDecision, _decision_digest
        encoded = json.dumps(self._v3_snapshot(), sort_keys=True, separators=(",", ":"))
        reasons = ("V3_FIXTURE_ONLY",)
        decision_id = _decision_digest(
            state="DEFER", score=None, reasons=reasons,
            policy_version="UNCONFIGURED", input_snapshot_json=encoded,
        )
        return OpportunityDecision(
            "DEFER", None, reasons, "UNCONFIGURED", decision_id, encoded,
        )

    def test_sqlite_v3_decision_save_and_load_resolve_exact_registry(self):
        import sqlite3
        from layer1.evidence_verification import ClaimRegistryStore
        from layer1.opportunity import OpportunityDecisionStore
        connection = sqlite3.connect(":memory:")
        try:
            ClaimRegistryStore(connection)
            connection.execute(
                "INSERT INTO layer1_claim_verification_runs "
                "(verification_id,created_at,claim_count,verified_count,corroborated_count,unresolved_count,payload_json) "
                "VALUES (?,?,?,?,?,?,?)",
                (self.registry_id, "2026-11-21T12:00:00Z", 0, 0, 0, 0,
                 json.dumps(self.payload, sort_keys=True, separators=(",", ":"))),
            )
            store = OpportunityDecisionStore(connection)
            decision = self._v3_decision()
            store.save("research:package:v3", decision)
            loaded = store.load(decision.decision_id)
            self.assertEqual(loaded["input_snapshot"], self._v3_snapshot())
            self.assertEqual(loaded["research_package_id"], "research:package:v3")
            connection.execute(
                "UPDATE layer1_claim_verification_runs SET payload_json=? WHERE verification_id=?",
                (json.dumps(self.payload | {"unresolved_issues": ["tampered"]}), self.registry_id),
            )
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                store.load(decision.decision_id)
        finally:
            connection.close()

    def test_sqlite_v3_decision_rejects_missing_exact_registry_id(self):
        import sqlite3
        from layer1.evidence_verification import ClaimRegistryStore
        from layer1.opportunity import OpportunityDecisionStore
        connection = sqlite3.connect(":memory:")
        try:
            ClaimRegistryStore(connection)
            store = OpportunityDecisionStore(connection)
            decision = self._v3_decision()
            with self.assertRaisesRegex(ValueError, "missing claim registry"):
                store.save("research:package:v3", decision)
        finally:
            connection.close()

    def test_postgres_decision_validator_accepts_v3_structure_before_store_resolution(self):
        from layer1.publication_postgres import validate_opportunity_decision_input
        validate_opportunity_decision_input("research:package:v3", self._v3_decision())

    @unittest.skipUnless(__import__("os").environ.get("TEST_POSTGRES_DSN"), "TEST_POSTGRES_DSN is not configured")
    def test_postgres_v3_decision_save_load_reverifies_exact_registry(self):
        import hashlib
        import os
        import uuid
        from layer1.publication_postgres import PostgresPublicationStore
        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        suffix = uuid.uuid4().hex
        research_key = "test-opportunity-v3-registry:" + suffix
        payload = {"asset_id": "coingecko:bitcoin", "test": suffix}
        package_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        registry_payload = self.payload | {"unresolved_issues": [{"test": suffix}]}
        registry_json = json.dumps(
            registry_payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        registry_id = hashlib.sha256(registry_json.encode("utf-8")).hexdigest()
        snapshot = self._v3_snapshot()
        snapshot["inputs"]["registry_verification_id"] = registry_id
        encoded_snapshot = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        from layer1.opportunity import OpportunityDecision, _decision_digest
        reasons = ("V3_POSTGRES_INTEGRATION_FIXTURE",)
        decision_id = _decision_digest(
            state="DEFER", score=None, reasons=reasons,
            policy_version="UNCONFIGURED", input_snapshot_json=encoded_snapshot,
        )
        decision = OpportunityDecision(
            "DEFER", None, reasons, "UNCONFIGURED", decision_id, encoded_snapshot,
        )
        try:
            package = store.save_research_package(
                research_key=research_key, package_hash=package_hash,
                cutoff_at="2026-11-21T12:00:00Z", payload=payload,
            )
            store.conn.execute(
                "INSERT INTO layer1_claim_verification_runs "
                "(verification_id,created_at,claim_count,verified_count,corroborated_count,unresolved_count,payload_json) "
                "VALUES (%s,now(),0,0,0,0,%s::jsonb)",
                (registry_id, registry_json),
            )
            store.save_opportunity_decision(package["package_id"], decision)
            loaded = store.load_opportunity_decision(decision.decision_id)
            self.assertEqual(loaded["input_snapshot"], snapshot)
            store.conn.execute(
                "UPDATE layer1_claim_verification_runs "
                "SET payload_json=jsonb_set(payload_json,'{unresolved_issues}','[{\"tampered\":true}]'::jsonb) "
                "WHERE verification_id=%s",
                (registry_id,),
            )
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                store.load_opportunity_decision(decision.decision_id)
        finally:
            store.conn.execute(
                "DELETE FROM opportunity_decisions WHERE research_package_id IN "
                "(SELECT package_id FROM layer1_research_package_versions WHERE research_key=%s)",
                (research_key,),
            )
            store.conn.execute(
                "DELETE FROM layer1_claim_verification_runs WHERE verification_id=%s",
                (registry_id,),
            )
            store.conn.execute(
                "DELETE FROM layer1_research_package_versions WHERE research_key=%s",
                (research_key,),
            )
            store.close()


if __name__ == "__main__":
    unittest.main()

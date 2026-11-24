from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import asdict

from layer1.evidence_verification import Claim, EvidenceRecord, EvidenceVerificationEngine
from tests.evidence_fixtures import trusted_evidence_record


def evidence_dict(record):
    return {
        key: value for key, value in asdict(record).items()
        if key != "_provenance_proof"
    }


class RegistryBoundFactorSourceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.record = trusted_evidence_record(
            source_id="market-snapshot:btc:001", source_family="binance_spot",
            source_kind="MARKET", publisher="Binance Spot API", subject="coingecko:bitcoin",
            claim_key="market.price", value=65000.0,
            published_at="2026-11-21T11:58:00Z", updated_at="2026-11-21T11:59:00Z",
            observed_at="2026-11-21T11:59:30Z", asset_id="coingecko:bitcoin",
            unit="usd", timeframe="spot", source_url="https://api.binance.com/api/v3/ticker/price",
            content_hash="b" * 64, content_hash_kind="CANONICAL_PARSED_PROVIDER_JSON_SHA256",
            lineage_id="binance-snapshot:001",
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
            "source_provenance": [evidence_dict(self.record) | {"evidence_id": self.record.evidence_id}],
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

    def test_resolves_historical_registry_v1_without_hash_kind_field(self):
        legacy_payload = copy.deepcopy(self.payload)
        legacy_payload.pop("schema_version", None)
        for raw in legacy_payload["evidence_records"]:
            raw.pop("content_hash_kind", None)
        legacy_id = self._digest(legacy_payload)
        legacy_registry = {"verification_id": legacy_id, "payload": legacy_payload}
        legacy_subfeature = copy.deepcopy(self.subfeature)
        legacy_subfeature["source_provenance"][0].pop("content_hash_kind", None)
        from layer1.opportunity import resolve_factor_source_provenance
        resolved = resolve_factor_source_provenance(
            legacy_subfeature, legacy_registry,
            expected_registry_verification_id=legacy_id,
            expected_asset_id="coingecko:bitcoin",
            decision_cutoff_at="2026-11-21T12:00:00Z",
        )
        self.assertEqual(resolved[0].evidence_id, self.record.evidence_id)
        self.assertEqual(resolved[0].content_hash_kind, "UNSPECIFIED")

    def test_legacy_v1_registry_claim_support_fails_closed_without_authority_metadata(self):
        from layer1.opportunity import validate_factor_claim_support
        legacy_payload = copy.deepcopy(self.payload)
        legacy_payload.pop("schema_version", None)
        for raw in legacy_payload["evidence_records"]:
            raw.pop("content_hash_kind", None)
            raw.pop("source_authority_id", None)
            raw.pop("independence_group", None)
            raw.pop("source_receipt_key_id", None)
            raw.pop("source_receipt", None)
            raw.pop("source_receipt_payload", None)
        with self.assertRaisesRegex(ValueError, "source lineage is inconsistent"):
            validate_factor_claim_support(
                factor_name="evidence_strength",
                claim_refs=[self.claim.claim_id],
                source_refs=[self.record.evidence_id],
                registry_payload=legacy_payload,
                expected_asset_id="coingecko:bitcoin",
            )

    def test_registry_source_resolution_rejects_boolean_or_float_schema_versions(self):
        for version in (True, 2.0):
            with self.subTest(version=version):
                payload = copy.deepcopy(self.payload)
                payload["schema_version"] = version
                registry_id = self._digest(payload)
                registry = {"verification_id": registry_id, "payload": payload}
                with self.assertRaisesRegex(ValueError, "schema version is unsupported"):
                    self.resolve(registry=registry)

    def test_factor_claim_support_rejects_boolean_or_float_registry_schema_versions(self):
        from layer1.opportunity import validate_factor_claim_support
        for version in (True, 2.0):
            with self.subTest(version=version):
                payload = copy.deepcopy(self.payload)
                payload["schema_version"] = version
                with self.assertRaisesRegex(ValueError, "schema version is unsupported"):
                    validate_factor_claim_support(
                        factor_name="evidence_strength",
                        claim_refs=[self.claim.claim_id],
                        source_refs=[self.record.evidence_id],
                        registry_payload=payload,
                        expected_asset_id="coingecko:bitcoin",
                    )

    def test_source_resolver_rejects_invalid_hash_contract_version_types_and_values(self):
        from layer1.opportunity import resolve_factor_source_provenance
        for version in (True, 2.0, 5):
            with self.subTest(version=version):
                with self.assertRaisesRegex(ValueError, "hash contract version is unsupported"):
                    resolve_factor_source_provenance(
                        self.subfeature, self.registry,
                        expected_registry_verification_id=self.registry_id,
                        expected_asset_id="coingecko:bitcoin",
                        decision_cutoff_at="2026-11-21T12:00:00Z",
                        hash_contract_version=version,
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
        record = trusted_evidence_record(
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
            "evidence_records": [evidence_dict(record) | {"evidence_id": record.evidence_id}],
            "results": [], "unresolved_issues": [],
        }
        registry_id = self._digest(payload)
        subfeature = {
            "source_refs": [record.evidence_id], "source_payload_hashes": [],
            "source_provenance": [evidence_dict(record) | {"evidence_id": record.evidence_id}],
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
            "source_provenance": [evidence_dict(self.record) | {"evidence_id": self.record.evidence_id}],
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

    def _v4_snapshot(self):
        snapshot = self._v3_snapshot()
        snapshot["inputs"]["schema_version"] = 4
        for factor in snapshot["inputs"]["factor_assessments"]:
            for subfeature in factor["subfeatures"]:
                subfeature.pop("source_payload_hashes")
                subfeature["source_hashes"] = [{
                    "evidence_id": self.record.evidence_id,
                    "sha256": self.record.content_hash,
                    "kind": self.record.content_hash_kind,
                }]
        return snapshot

    def test_registry_bound_v4_uses_registry_bound_typed_hashes(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        self.assertEqual(
            validate_registry_bound_opportunity_input_snapshot(self._v4_snapshot(), self.registry),
            4,
        )

    def test_registry_bound_v4_rejects_hash_kind_tampering(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        snapshot = self._v4_snapshot()
        snapshot["inputs"]["factor_assessments"][0]["subfeatures"][0]["source_hashes"][0]["kind"] = "RAW_TRANSPORT_BYTES_SHA256"
        with self.assertRaisesRegex(ValueError, "hash metadata"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, self.registry)

    def test_registry_bound_v4_rejects_unclassified_registry_hash(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        from layer1.evidence_verification import EvidenceRecord
        registry = copy.deepcopy(self.registry)
        raw = registry["payload"]["evidence_records"][0]
        raw["content_hash_kind"] = "UNSPECIFIED"
        registry["verification_id"] = self._digest(registry["payload"])
        snapshot = self._v4_snapshot()
        for factor in snapshot["inputs"]["factor_assessments"]:
            for subfeature in factor["subfeatures"]:
                subfeature["source_provenance"][0]["content_hash_kind"] = "UNSPECIFIED"
        snapshot["inputs"]["registry_verification_id"] = registry["verification_id"]
        with self.assertRaisesRegex(ValueError, "hash metadata"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, registry)

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

    def test_registry_bound_v3_rejects_orphan_claim_verification_result(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        registry = copy.deepcopy(self.registry)
        orphan = copy.deepcopy(registry["payload"]["results"][0])
        orphan["claim_id"] = "f" * 64
        registry["payload"]["results"].append(orphan)
        registry["verification_id"] = self._digest(registry["payload"])
        snapshot = self._v3_snapshot()
        snapshot["inputs"]["registry_verification_id"] = registry["verification_id"]
        with self.assertRaisesRegex(ValueError, "result references do not match"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, registry)

    def test_registry_bound_v3_rejects_duplicate_claim_result_evidence_ids(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        registry = copy.deepcopy(self.registry)
        result = registry["payload"]["results"][0]
        result["supporting_evidence_ids"] = list(result["supporting_evidence_ids"]) * 2
        registry["verification_id"] = self._digest(registry["payload"])
        snapshot = self._v3_snapshot()
        snapshot["inputs"]["registry_verification_id"] = registry["verification_id"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, registry)

    def test_registry_bound_v3_rejects_tampered_claim_result_lineage(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        registry = copy.deepcopy(self.registry)
        result = registry["payload"]["results"][0]
        result["source_lineage"] = {key: "forged-lineage" for key in result["supporting_evidence_ids"]}
        registry["verification_id"] = self._digest(registry["payload"])
        snapshot = self._v3_snapshot()
        snapshot["inputs"]["registry_verification_id"] = registry["verification_id"]
        with self.assertRaisesRegex(ValueError, "lineage"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, registry)

    def test_registry_bound_v3_rejects_claim_result_evidence_set_mismatch(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        registry = copy.deepcopy(self.registry)
        result = registry["payload"]["results"][0]
        result["evidence_ids"] = []
        registry["verification_id"] = self._digest(registry["payload"])
        snapshot = self._v3_snapshot()
        snapshot["inputs"]["registry_verification_id"] = registry["verification_id"]
        with self.assertRaisesRegex(ValueError, "evidence linkage"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, registry)

    def test_registry_bound_v3_rejects_cross_asset_record_forged_as_claim_support(self):
        from layer1.opportunity import validate_registry_bound_opportunity_input_snapshot
        from layer1.evidence_verification import EvidenceRecord
        registry = copy.deepcopy(self.registry)
        raw = registry["payload"]["evidence_records"][0]
        unrelated_values = {key: value for key, value in raw.items() if key != "evidence_id"}
        unrelated_values.update({
            "source_id": "unrelated-ethereum-feed", "source_family": "independent-ethereum-feed",
            "subject": "coingecko:ethereum", "asset_id": "coingecko:ethereum",
            "content_hash": "c" * 64, "lineage_id": "unrelated-ethereum-lineage",
        })
        unrelated = EvidenceRecord(**unrelated_values)
        registry["payload"]["evidence_records"].append(
            asdict(unrelated) | {"evidence_id": unrelated.evidence_id}
        )
        old_claim = registry["payload"]["claims"][0]
        from layer1.evidence_verification import Claim
        claim_values = {key: value for key, value in old_claim.items() if key != "claim_id"}
        claim_values["evidence_ids"] = tuple(claim_values["evidence_ids"]) + (unrelated.evidence_id,)
        forged_claim = Claim(**claim_values)
        registry["payload"]["claims"][0] = asdict(forged_claim) | {"claim_id": forged_claim.claim_id}
        result = registry["payload"]["results"][0]
        result["claim_id"] = forged_claim.claim_id
        result["supporting_evidence_ids"] = list(result["supporting_evidence_ids"]) + [unrelated.evidence_id]
        result["evidence_ids"] = list(result["evidence_ids"]) + [unrelated.evidence_id]
        result["source_lineage"][unrelated.evidence_id] = "unrelated-ethereum-lineage"
        result["independent_source_count"] = 2
        result["state"] = "CORROBORATED"
        registry["verification_id"] = self._digest(registry["payload"])
        snapshot = self._v3_snapshot()
        for factor in snapshot["inputs"]["factor_assessments"]:
            for subfeature in factor["subfeatures"]:
                if "claim_refs" in subfeature:
                    subfeature["claim_refs"] = [forged_claim.claim_id if value == old_claim["claim_id"] else value for value in subfeature["claim_refs"]]
        snapshot["inputs"]["registry_verification_id"] = registry["verification_id"]
        with self.assertRaisesRegex(ValueError, "source lineage is inconsistent"):
            validate_registry_bound_opportunity_input_snapshot(snapshot, registry)

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

    def _v4_decision(self):
        from layer1.opportunity import OpportunityDecision, _decision_digest
        encoded = json.dumps(self._v4_snapshot(), sort_keys=True, separators=(",", ":"))
        reasons = ("V4_FIXTURE_ONLY",)
        decision_id = _decision_digest(
            state="DEFER", score=None, reasons=reasons,
            policy_version="UNCONFIGURED", input_snapshot_json=encoded,
        )
        return OpportunityDecision("DEFER", None, reasons, "UNCONFIGURED", decision_id, encoded)

    def test_sqlite_v4_decision_save_and_load_resolve_typed_registry_hashes(self):
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
            decision = self._v4_decision()
            store.save("research:package:v4", decision)
            loaded = store.load(decision.decision_id)
            self.assertEqual(loaded["input_snapshot"], self._v4_snapshot())
            self.assertEqual(loaded["research_package_id"], "research:package:v4")
        finally:
            connection.close()

    def test_postgres_decision_validator_accepts_v4_structure(self):
        from layer1.publication_postgres import validate_opportunity_decision_input
        validate_opportunity_decision_input("research:package:v4", self._v4_decision())

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
    def test_postgres_v4_decision_save_load_reverifies_typed_hash_metadata(self):
        import hashlib
        import os
        import uuid
        from layer1.publication_postgres import PostgresPublicationStore
        store = PostgresPublicationStore(os.environ["TEST_POSTGRES_DSN"])
        suffix = uuid.uuid4().hex
        research_key = "test-opportunity-v4-registry:" + suffix
        package_payload = {"asset_id": "coingecko:bitcoin", "test": suffix}
        package_hash = hashlib.sha256(
            json.dumps(package_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        registry_payload = self.payload | {"unresolved_issues": [{"test": suffix}]}
        registry_json = json.dumps(
            registry_payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        registry_id = hashlib.sha256(registry_json.encode("utf-8")).hexdigest()
        snapshot = self._v4_snapshot()
        snapshot["inputs"]["registry_verification_id"] = registry_id
        encoded_snapshot = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        from layer1.opportunity import OpportunityDecision, _decision_digest
        reasons = ("V4_POSTGRES_INTEGRATION_FIXTURE",)
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
                cutoff_at="2026-11-21T12:00:00Z", payload=package_payload,
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
            self.assertEqual(loaded["input_snapshot"]["inputs"]["schema_version"], 4)
            store.conn.execute(
                "UPDATE layer1_claim_verification_runs "
                "SET payload_json=jsonb_set(payload_json,'{evidence_records,0,content_hash_kind}','\"UNSPECIFIED\"'::jsonb) "
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

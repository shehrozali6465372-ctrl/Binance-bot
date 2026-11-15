import os
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from layer1.publication_runtime import (
    PostgresClaimRegistryStore,
    PostgresDraftStore,
    PostgresEditorialBriefStore,
    PostgresOpportunityDecisionStore,
    PostgresResearchPackageStore,
    PostgresPublicationAuthorizationEngine,
    PostgresRunLease,
)


@dataclass(frozen=True)
class Package:
    research_key: str = "research-key"
    package_id: str = "pending"
    version: int = 0
    package_hash: str = "a" * 64
    cutoff_at: str = "2026-11-15T00:00:00+00:00"


@dataclass(frozen=True)
class Brief:
    event_id: str = "event-1"
    angle_id: str = "angle-1"
    brief_id: str = "pending"
    version: int = 0
    research_package_id: str = "research-key:1"
    brief_hash: str = "b" * 64
    status: str = "READY"


class FakeConnection:
    def execute(self, query, params):
        class Cursor:
            def fetchone(self):
                return (1,)
        self.last_query = (query, params)
        return Cursor()


class FakeStore:
    def __init__(self):
        self.conn = FakeConnection()
        self.calls = []

    def save_claim_registry(self, value):
        self.calls.append(("claim", value)); return "claim-id"

    def load_latest_claim_registry(self):
        return {"verification_id": "claim-id"}

    def save_research_package(self, **kwargs):
        self.calls.append(("research", kwargs))
        return {"version": 2, "package_id": "research-key:2"}

    def load_latest_research_package(self, key):
        return {"research_key": key}

    def save_editorial_brief(self, **kwargs):
        self.calls.append(("brief", kwargs))
        return {"version": 3, "brief_id": "event-1:angle-1:3"}

    def load_latest_editorial_brief(self, event_id, angle_id):
        return {"event_id": event_id, "angle_id": angle_id}

    def save_opportunity_decision(self, package_id, decision):
        self.calls.append(("opportunity", package_id, decision)); return decision.decision_id

    def load_opportunity_decision(self, decision_id):
        return {"decision_id": decision_id}

    def save_draft(self, *args, **kwargs): self.calls.append(("draft", args, kwargs)); return "draft"
    def save_text_validation(self, **kwargs): self.calls.append(("text", kwargs)); return "text"
    def save_visual_validation(self, **kwargs): self.calls.append(("visual", kwargs)); return "visual"
    def save_image_artifact(self, *args, **kwargs): self.calls.append(("image", args, kwargs)); return "image"
    def load_image_artifact(self, *args): return {"artifact_id": "image"}
    def load_latest_text_validation(self, *args): return {"status": "PASS"}
    def load_latest_visual_validation(self, *args): return {"status": "PASS"}
    def load_latest_draft(self, *args): return {"draft_id": "draft"}
    def reserve_daily_quota(self, **kwargs): self.calls.append(("quota", kwargs)); return "quota"
    def mark_quota_status(self, *args): self.calls.append(("quota_status", args))
    def save_publication_authorization(self, *args): self.calls.append(("authorization", args))
    def inspect_active_run_lease(self): self.calls.append(("inspect_run",)); return {"run_id": "run-1"}
    def acquire_run_lease(self, context): self.calls.append(("acquire_run", context))
    def finish_run_lease(self, run_id, status, summary): self.calls.append(("finish_run", run_id, status, summary))


class PostgresRuntimeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()

    def test_claim_registry_adapter_delegates_append_only_snapshot(self):
        registry = object()
        adapter = PostgresClaimRegistryStore(self.store)
        self.assertEqual(adapter.save(registry), "claim-id")
        self.assertEqual(adapter.load_latest()["verification_id"], "claim-id")
        self.assertEqual(self.store.calls[0], ("claim", registry))

    def test_research_package_adapter_returns_postgres_version_identity(self):
        saved = PostgresResearchPackageStore(self.store).save(Package())
        self.assertEqual((saved.version, saved.package_id), (2, "research-key:2"))
        self.assertEqual(self.store.calls[0][0], "research")
        self.assertEqual(self.store.calls[0][1]["research_key"], "research-key")

    def test_editorial_adapter_uses_persisted_angle_and_returns_database_identity(self):
        adapter = PostgresEditorialBriefStore(self.store)
        self.assertTrue(adapter.has_angle("event-1", "angle-1"))
        saved = adapter.save(Brief())
        self.assertEqual((saved.version, saved.brief_id), (3, "event-1:angle-1:3"))

    def test_opportunity_adapter_delegates_to_same_postgres_store(self):
        decision = type("Decision", (), {"decision_id": "decision-1"})()
        self.assertEqual(PostgresOpportunityDecisionStore(self.store).save("package-1", decision), "decision-1")

    def test_draft_adapter_routes_every_publication_artifact_to_postgres(self):
        adapter = PostgresDraftStore(self.store)
        self.assertEqual(adapter.save_draft("body"), "draft")
        self.assertEqual(adapter.save_text_validation(draft_hash="a"), "text")
        self.assertEqual(adapter.save_visual_validation(draft_hash="a"), "visual")
        self.assertEqual(adapter.save_image_artifact({"x": 1}, image_path="image.png"), "image")
        self.assertEqual(adapter.latest_text_validation("a"), "PASS")
        self.assertEqual(adapter.visual_validation("a", "b"), "PASS")
        self.assertEqual(adapter.load_latest("draft-key")["draft_id"], "draft")

    def test_authorization_adapter_delegates_quota_and_requires_postgres_store(self):
        adapter = PostgresPublicationAuthorizationEngine(self.store)
        self.assertEqual(adapter.reserve_daily_quota(symbol="BTC", daily_limit=1), "quota")
        adapter.mark_quota_status("quota", "RELEASED")
        with self.assertRaisesRegex(TypeError, "PostgreSQL publication store"):
            PostgresPublicationAuthorizationEngine(object())


class PostgresRunLeaseAdapterTests(unittest.TestCase):
    def test_run_lease_adapter_delegates_acquire_inspect_finish_and_keeps_shared_connection_open(self):
        store = FakeStore()
        lease = PostgresRunLease(store)
        context = type("Context", (), {"run_id": "run-1"})()
        lease.acquire(context)
        self.assertEqual(lease.run_id, "run-1")
        self.assertEqual(lease.inspect_active()["run_id"], "run-1")
        lease.finish("SUCCEEDED", {"count": 1})
        self.assertIsNone(lease.run_id)
        lease.close()
        self.assertEqual([call[0] for call in store.calls], ["acquire_run", "inspect_run", "finish_run"])
        self.assertEqual(store.calls[2], ("finish_run", "run-1", "SUCCEEDED", {"count": 1}))

    def test_run_lease_adapter_rejects_invalid_store_and_status(self):
        with self.assertRaisesRegex(TypeError, "PostgreSQL publication store"):
            PostgresRunLease(object())
        lease = PostgresRunLease(FakeStore())
        lease.run_id = "run-1"
        with self.assertRaisesRegex(ValueError, "unsupported run status"):
            lease.finish("UNKNOWN")


class RuntimeBackendConfigurationTests(unittest.TestCase):
    def test_postgresql_selection_requires_explicit_dsn_and_no_silent_fallback(self):
        from main import Config
        with patch.dict(os.environ, {"PERSISTENCE_BACKEND": "postgresql", "POSTGRES_DSN": ""}, clear=False):
            config = Config.from_env()
        with self.assertRaisesRegex(ValueError, "POSTGRES_DSN is required"):
            config.validate()

    def test_sqlite_remains_the_default_runtime_backend(self):
        from main import Config
        with patch.dict(os.environ, {"PERSISTENCE_BACKEND": "sqlite", "POSTGRES_DSN": ""}, clear=False):
            config = Config.from_env()
        config.validate()
        self.assertEqual(config.persistence_backend, "sqlite")


if __name__ == "__main__":
    unittest.main()

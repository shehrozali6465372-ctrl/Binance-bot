import os
import unittest
import uuid


_LAYER1_TEST_DSN = os.environ.get("TEST_POSTGRES_DSN")


@unittest.skipUnless(_LAYER1_TEST_DSN, "TEST_POSTGRES_DSN is not configured")
class PostgresLayer1StoreIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from psycopg.conninfo import conninfo_to_dict
        info = conninfo_to_dict(_LAYER1_TEST_DSN)
        host = info.get("host", "")
        database = info.get("dbname") or info.get("database")
        allowed_host = os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip()
        if (database != "binance_onchain_test" or not allowed_host or host != allowed_host
                or info.get("sslmode") not in {"require", "verify-ca", "verify-full"}):
            raise RuntimeError(
                "Layer1 PostgreSQL tests require binance_onchain_test on exact TEST_POSTGRES_ALLOWED_HOST with TLS"
            )
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(_LAYER1_TEST_DSN)

    def setUp(self):
        from layer1.publication_postgres import PostgresPublicationStore
        from layer1.layer1_postgres import PostgresLayer1Store
        self.owner = PostgresPublicationStore(_LAYER1_TEST_DSN)
        self.layer1 = PostgresLayer1Store(self.owner.conn)
        self.suffix = uuid.uuid4().hex
        self.asset_id = "coingecko:layer1-test-" + self.suffix
        self.source_id = "source-" + self.suffix
        self.analysis_id = "analysis-" + self.suffix
        self.cluster_id = uuid.uuid4().hex + uuid.uuid4().hex

    def tearDown(self):
        with self.owner.conn.transaction():
            self.owner.conn.execute("DELETE FROM layer1_market_observations WHERE asset_id=%s", (self.asset_id,))
            self.owner.conn.execute("DELETE FROM layer1_market_analyses WHERE analysis_id=%s", (self.analysis_id,))
            self.owner.conn.execute("DELETE FROM layer1_identity_proofs WHERE asset_id=%s", (self.asset_id,))
            self.owner.conn.execute("DELETE FROM layer1_announcement_revisions WHERE source_id=%s", (self.source_id,))
            self.owner.conn.execute("DELETE FROM layer1_announcement_evidence WHERE source_id=%s", (self.source_id,))
            self.owner.conn.execute("DELETE FROM layer1_trend_signals WHERE topic=%s", (self.suffix,))
            self.owner.conn.execute("DELETE FROM layer1_trend_clusters WHERE cluster_id=%s", (self.cluster_id,))
            self.owner.conn.execute("DELETE FROM layer1_candidates WHERE candidate_id=%s", (self.suffix,))
            self.owner.conn.execute("DELETE FROM layer1_candidate_rejections WHERE symbol=%s", (self.suffix.upper(),))
            self.owner.conn.execute("DELETE FROM layer1_candidate_scores WHERE candidate_id=%s", (self.suffix,))
        self.layer1.close()
        self.owner.close()

    def test_full_layer1_persistence_runtime_uses_postgres_without_creating_sqlite_database(self):
        import hashlib
        import json
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import main

        captured = []
        original_save = self.owner.save_claim_registry

        def capture_registry(registry):
            payload = json.dumps(
                registry.to_dict(), sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
            verification_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            exists = self.owner.conn.execute(
                "SELECT 1 FROM layer1_claim_verification_runs WHERE verification_id=%s",
                (verification_id,),
            ).fetchone() is not None
            result = original_save(registry)
            captured.append((result, exists))
            return result

        self.owner.save_claim_registry = capture_registry
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANNOUNCEMENT_DATABASE_URL": ""}):
                database_path = Path(tmp) / "must-not-be-created.sqlite"
                summary = main._persist_layer1_market_intelligence(
                    [], str(database_path), [], postgres_store=self.owner,
                )
                self.assertFalse(database_path.exists())
                self.assertEqual(summary["observations"], 0)
                self.assertEqual(summary["claim_verification_summary"]["status"], "AVAILABLE_EMPTY")
            self.assertEqual(len(captured), 1)
        finally:
            for verification_id, existed in captured:
                if not existed:
                    self.owner.conn.execute(
                        "DELETE FROM layer1_claim_verification_runs WHERE verification_id=%s",
                        (verification_id,),
                    )
            self.owner.save_claim_registry = original_save

    def test_postgres_layer1_store_round_trips_source_records_and_writes_atomically(self):
        from layer1.foundation import (
            AnnouncementEvidence, AssetIdentity, AssetIdentityProof, Candidate,
            EligibilityDecision, MarketAnalysisResult, MarketObservation,
            RelevanceScore, TrendCluster, TrendSignal, utc_now,
        )
        now = utc_now()
        identity = AssetIdentity(self.asset_id, "Layer1 test asset", "L1T", "USDT")
        proof = AssetIdentityProof(
            "VERIFIED", self.asset_id, "L1T", "USDT", "binance", "L1T/USDT",
            "guarded integration proof", "coingecko_coin_tickers", now, now, now,
            "a" * 64, {},
        )
        observation = MarketObservation(
            self.asset_id, "integration-provider", "/integration", now, price=12.5,
        )
        announcement = AnnouncementEvidence(
            self.source_id, "https://www.binance.com/en/support/announcement/" + self.suffix,
            "Binance", "listing", "Integration listing", now, now, (self.asset_id,), "b" * 64,
        )
        trend = TrendSignal(self.suffix, "integration-provider", now, 1, (self.asset_id,), self.suffix, "c" * 64)
        analysis = MarketAnalysisResult(
            self.analysis_id, self.asset_id, "integration-provider", "USD", now, "PARTIAL",
            None, None, None, None, None, None, None, ("price observed",), (), ("24h baseline missing",),
            ("BASELINE_UNAVAILABLE",), ("market:" + self.suffix,),
        )
        cluster = TrendCluster(
            self.cluster_id, "layer1-test", (self.asset_id,), 1, 1, 1, now,
            ("trend:" + self.suffix,),
        )
        eligibility = EligibilityDecision("ELIGIBLE", self.asset_id, "L1T", ("L1TUSDT",), "exact test pair", now)
        candidate = Candidate(
            self.suffix, self.asset_id, (), eligibility, (), (self.suffix,), "READY_FOR_RESEARCH",
        )
        score = RelevanceScore(self.suffix, 71.5, {"evidence": 71.5}, "integration-v1", "guarded test")

        self.layer1.save_identity_proof(proof, 300)
        self.layer1.save_market(observation)
        self.layer1.save_announcement(announcement)
        self.layer1.save_trend(trend)
        self.layer1.save_market_analysis(analysis)
        self.layer1.save_trend_cluster(cluster)
        self.layer1.save_candidate(candidate)
        self.layer1.save_rejection(self.suffix, "TEST_REJECT", "integration", now, {"scope": self.suffix})
        self.layer1.save_score(score)

        self.assertEqual(self.layer1.get_identity_proof(identity).data_hash, "a" * 64)
        self.assertEqual([item.data_hash for item in self.layer1.get_market_history(self.asset_id)], [observation.data_hash])
        self.assertEqual([item.source_id for item in self.layer1.iter_announcement_revisions()], [self.source_id])
        self.assertEqual([item.source_item_id for item in self.layer1.iter_trend_signals()], [self.suffix])
        self.assertEqual([item.data_hash for item in self.layer1.iter_market_observations()], [observation.data_hash])
        self.assertEqual(
            self.owner.conn.execute("SELECT status FROM layer1_market_analyses WHERE analysis_id=%s",
                                    (self.analysis_id,)).fetchone()["status"],
            "PARTIAL",
        )
        self.assertEqual(
            self.owner.conn.execute("SELECT confidence_limit FROM layer1_trend_clusters WHERE cluster_id=%s",
                                    (self.cluster_id,)).fetchone()["confidence_limit"],
            "ATTENTION_ONLY_NOT_EVENT_PROOF",
        )
        self.assertEqual(
            self.owner.conn.execute("SELECT state FROM layer1_candidates WHERE candidate_id=%s",
                                    (self.suffix,)).fetchone()["state"],
            "READY_FOR_RESEARCH",
        )
        self.assertEqual(
            self.owner.conn.execute("SELECT score FROM layer1_candidate_scores WHERE candidate_id=%s",
                                    (self.suffix,)).fetchone()["score"],
            71.5,
        )
        # close() is deliberately a no-op because the connection belongs to the publication store.
        self.layer1.close()
        self.assertIsNotNone(self.owner.conn.execute("SELECT 1").fetchone())


if __name__ == "__main__":
    unittest.main()

"""Isolated PostgreSQL acceptance for the real scheduled run entrypoint.

The test intentionally exercises the current no-candidate fail-closed branch.
It does not invent an opportunity policy or authorize publication.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main

_DSN = os.environ.get("TEST_POSTGRES_DSN")


@unittest.skipUnless(_DSN, "TEST_POSTGRES_DSN is not configured")
class ScheduledPostgresFailClosedAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.postgres_test_support import validate_postgres_test_target
        validate_postgres_test_target(
            _DSN, os.environ.get("TEST_POSTGRES_ALLOWED_HOST", "").strip(),
        )
        from layer1.publication_postgres import apply_publication_postgres_migrations
        apply_publication_postgres_migrations(_DSN)

    def test_real_run_once_persists_no_candidate_outcome_without_publisher_side_effects(self):
        from layer1.publication_postgres import PostgresPublicationStore

        with tempfile.TemporaryDirectory(prefix="scheduled-pg-acceptance-") as directory:
            config = replace(
                main.CONFIG,
                persistence_backend="postgresql",
                postgres_dsn=_DSN,
                database_path=str(Path(directory) / "legacy-must-not-be-used.sqlite"),
                publish_log_path=str(Path(directory) / "publish.log"),
                post_interval=0,
                max_iterations=1,
                dry_run=True,
                publisher_enabled=False,
                image_required=False,
                save_research_packages=False,
            )
            config.validate()
            store = PostgresPublicationStore(_DSN)
            before_runs = store.conn.execute(
                "SELECT COUNT(*) AS count FROM layer1_runs"
            ).fetchone()["count"]
            before_attempts = store.conn.execute(
                "SELECT COUNT(*) AS count FROM publication_attempts"
            ).fetchone()["count"]
            before_reservations = store.conn.execute(
                "SELECT COUNT(*) AS count FROM publication_quota_reservations"
            ).fetchone()["count"]

            class FakePublisherDatabase:
                def get_today_post_count(self):
                    return 0

                def get_posted_hours_dict(self, hours=72):
                    return {}

            class NetworkDisabledPublisher:
                def __init__(self):
                    self.db = FakePublisherDatabase()
                    self.postgres_store = store
                    self.publish_calls = 0

                def publish(self, *args, **kwargs):
                    self.publish_calls += 1
                    raise AssertionError("publisher transport must never be reached in this test")

            class EmptyScanner:
                def _universe(self):
                    return []

            publisher = NetworkDisabledPublisher()
            run_id = None
            try:
                with (
                    patch.object(main, "CONFIG", config),
                    patch.object(main, "_verify_persistence_integrity", return_value=True),
                    patch.object(main, "_retry_pending_push"),
                    patch.object(main, "_load_post_history", return_value={}),
                    patch("urllib.request.urlopen", side_effect=AssertionError("network access forbidden")),
                    patch.object(main, "http_get_json", side_effect=AssertionError("provider HTTP forbidden")),
                ):
                    outcome = main.run_once(
                        config, EmptyScanner(), SimpleNamespace(),
                        SimpleNamespace(), SimpleNamespace(), publisher, set(),
                        hot_search_engine=SimpleNamespace(get_trending=lambda **_: []),
                    )

                self.assertFalse(outcome)
                self.assertEqual(publisher.publish_calls, 0)
                self.assertFalse(Path(config.database_path).exists())
                self.assertFalse(Path(config.publish_log_path).exists())

                after_attempts = store.conn.execute(
                    "SELECT COUNT(*) AS count FROM publication_attempts"
                ).fetchone()["count"]
                after_reservations = store.conn.execute(
                    "SELECT COUNT(*) AS count FROM publication_quota_reservations"
                ).fetchone()["count"]
                self.assertEqual(after_attempts, before_attempts)
                self.assertEqual(after_reservations, before_reservations)

                run = store.conn.execute(
                    "SELECT run_id, status, summary_json FROM layer1_runs "
                    "ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
                run_id = run["run_id"]
                self.assertEqual(run["status"], "NO_CANDIDATE_OR_BLOCKED")
                self.assertEqual(run["summary_json"]["cycle_result"], "NO_CANDIDATE_OR_BLOCKED")
                lease = store.conn.execute(
                    "SELECT COUNT(*) AS count FROM layer1_run_lease WHERE lease_name='agent'"
                ).fetchone()["count"]
                self.assertEqual(lease, 0, "completed run must release the singleton lease")
                self.assertEqual(
                    store.conn.execute(
                        "SELECT COUNT(*) AS count FROM layer1_runs WHERE run_id=%s", (run_id,),
                    ).fetchone()["count"],
                    before_runs + 1,
                )
            finally:
                if run_id:
                    store.conn.execute("DELETE FROM layer1_runs WHERE run_id=%s", (run_id,))
                store.close()


    def test_real_run_once_persists_research_more_without_editorial_or_publish_side_effects(self):
        import hashlib
        import json
        from datetime import datetime, timezone
        from unittest.mock import patch
        import uuid

        from layer1.foundation import AssetIdentityProof
        from layer1.publication_postgres import PostgresPublicationStore

        suffix = uuid.uuid4().hex[:10]
        symbols = ("TST" + suffix[:3].upper(), "TSU" + suffix[3:6].upper())
        asset_ids = tuple("coingecko:scheduled-acceptance-" + suffix + "-" + symbol.lower() for symbol in symbols)
        observed_at = datetime.now(timezone.utc).isoformat()
        pairs = [
            {
                "symbol": symbol + "USDT", "baseAsset": symbol, "quoteAsset": "USDT",
                "status": "TRADING", "isSpotTradingAllowed": True,
                "permissionSets": [["SPOT", "MARGIN"]],
            }
            for symbol in symbols
        ]
        exchange_info = {
            "serverTime": int(datetime.now(timezone.utc).timestamp() * 1000),
            "symbols": pairs,
        }
        coins = []
        for index, (symbol, asset_id) in enumerate(zip(symbols, asset_ids), start=1):
            payload = {
                "id": asset_id.split(":", 1)[1],
                "symbol": symbol.lower(),
                "name": "Scheduled Test Asset " + str(index),
                "current_price": 2.0 + index,
                "price_change_percentage_24h": 5.2 + index,
                "total_volume": 2_000_000.0,
                "market_cap": 1_200_000_000.0 + index,
                "last_updated": observed_at,
                "sparkline_in_7d": {"price": [2.0 + index, 2.1 + index]},
            }
            content_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            ).hexdigest()
            coin = main.Coin(
                symbol, payload["name"], payload["current_price"],
                payload["price_change_percentage_24h"], payload["total_volume"],
                2.5, payload["market_cap"], [2.0 + index, 2.1 + index],
            )
            coin.asset_id = asset_id
            coin.observed_at = observed_at
            coin.provider_published_at = observed_at
            coin.market_data_source = "coingecko_markets"
            coin.market_data_hash = content_hash
            coin.market_data_payload = payload
            coin.market_data_provider_metadata = {}
            coins.append(coin)

        def fake_identity_proof(identity, timeout=None):
            digest = hashlib.sha256(
                (identity.asset_id + "|" + identity.base_asset).encode()
            ).hexdigest()
            return AssetIdentityProof(
                "VERIFIED", identity.asset_id, identity.base_asset, identity.quote_asset,
                "binance", identity.base_asset + "/" + identity.quote_asset,
                "isolated deterministic test fixture", "coingecko_coin_tickers",
                observed_at, observed_at, observed_at, digest, {},
            )

        class DeterministicResearch:
            def build_research_package(self, coin_dict, announcements, posted_hours_ago):
                return (
                    "COIN: " + coin_dict["symbol"] + "\n"
                    + "Price: $" + format(coin_dict["price"], ".2f") + "\n"
                    + "24h Change: " + format(coin_dict["change_24h"], ".2f") + "%\n"
                    + "Volume 24h: $" + format(coin_dict["volume_24h"], ".0f") + "\n"
                    + "Market Cap: $" + format(coin_dict["market_cap"], ".0f") + "\n"
                    + "Binance Spot: YES\n"
                )

            def analyze(self, coin_dict, announcement=None):
                return None

        class DeterministicGenerator:
            def __init__(self):
                self.generate_calls = 0

            def decide(self, packages):
                return [{"rank": 1, "symbol": symbols[0], "reason": "deterministic isolated acceptance fixture"}]

            def generate(self, *args, **kwargs):
                self.generate_calls += 1
                raise AssertionError("content generation must remain blocked without an approved opportunity policy")

        class FakePublisherDatabase:
            def get_today_post_count(self):
                return 0

            def get_posted_hours_dict(self, hours=72):
                return {}

        class NetworkDisabledPublisher:
            def __init__(self, store):
                self.db = FakePublisherDatabase()
                self.postgres_store = store
                self.publish_calls = 0

            def publish(self, *args, **kwargs):
                self.publish_calls += 1
                raise AssertionError("publisher transport is disabled in this acceptance test")

        class DeterministicScanner:
            def _universe(self):
                return coins

        with tempfile.TemporaryDirectory(prefix="scheduled-pg-positive-discovery-") as directory:
            config = replace(
                main.CONFIG,
                persistence_backend="postgresql",
                postgres_dsn=_DSN,
                database_path=str(Path(directory) / "sqlite-must-not-be-created.sqlite"),
                publish_log_path=str(Path(directory) / "publish.log"),
                post_interval=0,
                max_iterations=1,
                min_candidates=2,
                dry_run=True,
                publisher_enabled=False,
                image_required=False,
                save_research_packages=False,
            )
            config.validate()
            store = PostgresPublicationStore(_DSN)
            publisher = NetworkDisabledPublisher(store)
            generator = DeterministicGenerator()
            before = {
                "runs": store.conn.execute("SELECT COUNT(*) AS count FROM layer1_runs").fetchone()["count"],
                "research": store.conn.execute("SELECT COUNT(*) AS count FROM layer1_research_package_versions").fetchone()["count"],
                "decisions": store.conn.execute("SELECT COUNT(*) AS count FROM opportunity_decisions").fetchone()["count"],
                "editorial": store.conn.execute("SELECT COUNT(*) AS count FROM editorial_brief_versions").fetchone()["count"],
                "drafts": store.conn.execute("SELECT COUNT(*) AS count FROM content_draft_versions").fetchone()["count"],
                "authorizations": store.conn.execute("SELECT COUNT(*) AS count FROM publication_authorizations").fetchone()["count"],
                "attempts": store.conn.execute("SELECT COUNT(*) AS count FROM publication_attempts").fetchone()["count"],
                "reservations": store.conn.execute("SELECT COUNT(*) AS count FROM publication_quota_reservations").fetchone()["count"],
            }
            run_id = None
            research_failures = []
            original_debug = main.LOGGER.debug

            def capture_research_failure(message, *args, **kwargs):
                if isinstance(message, str) and "Research package failed" in message:
                    research_failures.append((message, args))
                return original_debug(message, *args, **kwargs)

            try:
                with (
                    patch.object(main, "CONFIG", config),
                    patch.object(main.LOGGER, "debug", side_effect=capture_research_failure),
                    patch.object(main, "_verify_persistence_integrity", return_value=True),
                    patch.object(main, "_retry_pending_push"),
                    patch.object(main, "_load_post_history", return_value={}),
                    patch.object(main, "_check_jsonl_cooldown", return_value=False),
                    patch.object(main, "_get_binance_listed", return_value=set(symbols)),
                    patch.object(main, "_binance_spot_pairs_cache", {symbol: [pair] for symbol, pair in zip(symbols, pairs)}),
                    patch.object(main, "_binance_spot_snapshot_observed_at", observed_at),
                    patch.object(main, "_binance_spot_exchange_info_snapshot", exchange_info),
                    patch.object(main, "_fetch_coingecko_binance_identity_proof", side_effect=fake_identity_proof),
                    patch("urllib.request.urlopen", side_effect=AssertionError("network access forbidden")),
                    patch.object(main, "http_get_json", side_effect=AssertionError("provider HTTP forbidden")),
                ):
                    outcome = main.run_once(
                        config, DeterministicScanner(), SimpleNamespace(),
                        DeterministicResearch(), generator, publisher, set(),
                        hot_search_engine=SimpleNamespace(get_trending=lambda **_: []),
                    )

                self.assertFalse(outcome)
                self.assertEqual(generator.generate_calls, 0)
                self.assertEqual(publisher.publish_calls, 0)
                self.assertFalse(Path(config.database_path).exists())
                self.assertFalse(Path(config.publish_log_path).exists())

                package_rows = store.conn.execute(
                    "SELECT package_id,payload_json FROM layer1_research_package_versions "
                    "WHERE payload_json->>'asset_id'=ANY(%s)",
                    (list(asset_ids),),
                ).fetchall()
                self.assertEqual(len(package_rows), 2, f"research failures: {research_failures!r}")
                self.assertTrue(all(
                    row["payload_json"]["completeness"] == "RESEARCH_MORE"
                    and "MISSING_REQUIRED_SOURCE_KINDS:PRIMARY" in row["payload_json"]["gaps"]
                    for row in package_rows
                ), repr([(row["payload_json"].get("completeness"), row["payload_json"].get("gaps")) for row in package_rows]))

                decisions = store.conn.execute(
                    "SELECT d.state,d.reasons_json,p.payload_json->>'asset_id' AS asset_id "
                    "FROM opportunity_decisions d "
                    "JOIN layer1_research_package_versions p ON p.package_id=d.research_package_id "
                    "WHERE p.payload_json->>'asset_id'=ANY(%s) ORDER BY asset_id",
                    (list(asset_ids),),
                ).fetchall()
                self.assertEqual(len(decisions), 2)
                for decision in decisions:
                    self.assertEqual(decision["state"], "RESEARCH_MORE")
                    self.assertIn("RESEARCH_PACKAGE_NOT_COMPLETE", decision["reasons_json"])

                after = {
                    "research": store.conn.execute("SELECT COUNT(*) AS count FROM layer1_research_package_versions").fetchone()["count"],
                    "decisions": store.conn.execute("SELECT COUNT(*) AS count FROM opportunity_decisions").fetchone()["count"],
                    "editorial": store.conn.execute("SELECT COUNT(*) AS count FROM editorial_brief_versions").fetchone()["count"],
                    "drafts": store.conn.execute("SELECT COUNT(*) AS count FROM content_draft_versions").fetchone()["count"],
                    "authorizations": store.conn.execute("SELECT COUNT(*) AS count FROM publication_authorizations").fetchone()["count"],
                    "attempts": store.conn.execute("SELECT COUNT(*) AS count FROM publication_attempts").fetchone()["count"],
                    "reservations": store.conn.execute("SELECT COUNT(*) AS count FROM publication_quota_reservations").fetchone()["count"],
                }
                self.assertEqual(after["research"], before["research"] + 2)
                self.assertEqual(after["decisions"], before["decisions"] + 2)
                for key in ("editorial", "drafts", "authorizations", "attempts", "reservations"):
                    self.assertEqual(after[key], before[key], key + " must not advance after DEFER")

                run = store.conn.execute(
                    "SELECT run_id,status,summary_json FROM layer1_runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
                run_id = run["run_id"]
                self.assertEqual(run["status"], "NO_CANDIDATE_OR_BLOCKED")
                self.assertEqual(run["summary_json"]["cycle_result"], "NO_CANDIDATE_OR_BLOCKED")
                self.assertEqual(
                    store.conn.execute("SELECT COUNT(*) AS count FROM layer1_run_lease WHERE lease_name='agent'").fetchone()["count"],
                    0,
                )

                import subprocess
                import sys
                child_source = """
import json
import os
from tests.postgres_test_support import validate_postgres_test_target
from layer1.publication_postgres import PostgresPublicationStore

dsn = os.environ["TEST_POSTGRES_DSN"]
validate_postgres_test_target(dsn, os.environ["TEST_POSTGRES_ALLOWED_HOST"])
assets = json.loads(os.environ["SCHEDULED_TEST_ASSET_IDS"])
run_id = os.environ["SCHEDULED_TEST_RUN_ID"]
store = PostgresPublicationStore(dsn)
decisions = store.conn.execute(
    "SELECT d.state,p.payload_json->>'asset_id' AS asset_id "
    "FROM opportunity_decisions d "
    "JOIN layer1_research_package_versions p ON p.package_id=d.research_package_id "
    "WHERE p.payload_json->>'asset_id'=ANY(%s) ORDER BY asset_id",
    (assets,),
).fetchall()
run = store.conn.execute(
    "SELECT status,summary_json FROM layer1_runs WHERE run_id=%s", (run_id,),
).fetchone()
lease_count = store.conn.execute(
    "SELECT COUNT(*) AS count FROM layer1_run_lease WHERE lease_name='agent'",
).fetchone()["count"]
print(json.dumps({
    "decisions": [{"asset_id": row["asset_id"], "state": row["state"]} for row in decisions],
    "run_status": run["status"] if run else None,
    "cycle_result": run["summary_json"]["cycle_result"] if run else None,
    "lease_count": lease_count,
}, sort_keys=True))
store.close()
"""
                child_env = os.environ.copy()
                child_env["SCHEDULED_TEST_ASSET_IDS"] = json.dumps(list(asset_ids))
                child_env["SCHEDULED_TEST_RUN_ID"] = run_id
                child = subprocess.run(
                    [sys.executable, "-c", child_source],
                    check=True, capture_output=True, text=True,
                    env=child_env, timeout=20,
                )
                child_result = json.loads(child.stdout)
                self.assertEqual(len(child_result["decisions"]), 2)
                self.assertTrue(all(item["state"] == "RESEARCH_MORE" for item in child_result["decisions"]))
                self.assertEqual(child_result["run_status"], "NO_CANDIDATE_OR_BLOCKED")
                self.assertEqual(child_result["cycle_result"], "NO_CANDIDATE_OR_BLOCKED")
                self.assertEqual(child_result["lease_count"], 0)
            finally:
                if run_id is None:
                    current_runs = store.conn.execute(
                        "SELECT COUNT(*) AS count FROM layer1_runs"
                    ).fetchone()["count"]
                    if current_runs > before["runs"]:
                        latest_run = store.conn.execute(
                            "SELECT run_id FROM layer1_runs ORDER BY started_at DESC LIMIT 1"
                        ).fetchone()
                        run_id = latest_run["run_id"] if latest_run else None
                if run_id:
                    with store.conn.transaction():
                        store.conn.execute(
                            "DELETE FROM layer1_run_lease WHERE run_id=%s", (run_id,),
                        )
                        package_ids = [
                            row["package_id"] for row in store.conn.execute(
                                "SELECT package_id FROM layer1_research_package_versions "
                                "WHERE payload_json->>'asset_id'=ANY(%s)",
                                (list(asset_ids),),
                            ).fetchall()
                        ]
                        if package_ids:
                            store.conn.execute(
                                "DELETE FROM opportunity_decisions WHERE research_package_id=ANY(%s)",
                                (package_ids,),
                            )
                            store.conn.execute(
                                "DELETE FROM layer1_research_package_versions WHERE package_id=ANY(%s)",
                                (package_ids,),
                            )
                        store.conn.execute(
                            "DELETE FROM layer1_claim_verification_runs WHERE payload_json::text LIKE %s OR payload_json::text LIKE %s",
                            ("%" + asset_ids[0] + "%", "%" + asset_ids[1] + "%"),
                        )
                        store.conn.execute("DELETE FROM layer1_candidate_scores WHERE candidate_id IN (SELECT candidate_id FROM layer1_candidates WHERE asset_id=ANY(%s))", (list(asset_ids),))
                        store.conn.execute("DELETE FROM layer1_candidates WHERE asset_id=ANY(%s)", (list(asset_ids),))
                        store.conn.execute("DELETE FROM layer1_market_analyses WHERE asset_id=ANY(%s)", (list(asset_ids),))
                        store.conn.execute("DELETE FROM layer1_market_observations WHERE asset_id=ANY(%s)", (list(asset_ids),))
                        store.conn.execute("DELETE FROM layer1_identity_proofs WHERE asset_id=ANY(%s)", (list(asset_ids),))
                        store.conn.execute("DELETE FROM layer1_runs WHERE run_id=%s", (run_id,))
                store.close()


if __name__ == "__main__":
    unittest.main()

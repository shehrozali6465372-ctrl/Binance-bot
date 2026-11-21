import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from image_engine import CloudflareImageArtifact, CloudflareWorkersAIImageGenerator, ImageComposer
from layer1.content_generation import DraftStore
from layer1.content_verification import ContentVerificationEngine
from layer1.editorial_strategy import EditorialBriefStore, EditorialStrategyEngine
from layer1.event_lifecycle import EventLifecycleStore
from layer1.evidence_verification import EvidenceRecord, EvidenceVerificationEngine
from layer1.foundation import AnnouncementEvidence, Layer1Store
from layer1.opportunity import (
    FACTOR_NAMES, OpportunityEvaluationEngine, OpportunityPolicy,
    OpportunityDecisionStore,
)
from layer1.publication_authorization import PublicationAuthorizationEngine
from layer1.research_package import DeepResearchEngine, ResearchPackageStore
from layer1.visual_quality import VisualQualityEngine


def iso(delta=0):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()


class EndToEndPipelineTests(unittest.TestCase):
    def test_verified_research_to_image_and_immutable_publication_authorization(self):
        tmp = tempfile.TemporaryDirectory()
        old_cwd = os.getcwd()
        db = Layer1Store(str(Path(tmp.name) / "pipeline.db"))
        try:
            asset_id = "coingecko:abc"
            timestamp = iso(-30)
            announcement = AnnouncementEvidence(
                source_id="stable-announcement-abc",
                source_url="https://www.binance.com/en/support/announcement/stable-announcement-abc",
                publisher="Binance", event_type="listing",
                title="Binance announces ABC Spot listing",
                published_at=timestamp, observed_at=iso(),
                asset_ids=(asset_id,), content_hash="a" * 64,
                updated_at=timestamp,
            )
            market = EvidenceRecord(
                source_id="market-abc-1", source_family="coingecko",
                source_kind="MARKET", publisher="CoinGecko", subject=asset_id,
                claim_key="market.price", value=1.25, unit="USD",
                published_at=timestamp, observed_at=timestamp,
                asset_id=asset_id, is_primary=True, source_status="ACCEPTED",
            )
            verifier = EvidenceVerificationEngine()
            announcement_evidence = verifier.evidence_from_announcement(announcement)
            evidence = announcement_evidence + (market,)
            claims = verifier._source_assertion_claims(evidence)
            claims = tuple(
                replace(item, text="$ABC market price is 1.25 USD")
                if item.claim_key == "market.price" else item
                for item in claims
            )
            registry = verifier.verify(claims, evidence)
            lifecycle_store = EventLifecycleStore(db)
            lifecycle = lifecycle_store.sync_announcements([announcement], registry)
            self.assertEqual(lifecycle[0].state, "CONFIRMED")

            research = DeepResearchEngine().build(
                asset_id=asset_id, symbol="ABC",
                research_question=announcement.title, cutoff_at=iso(),
                registry=registry, event_states=("CONFIRMED",),
                required_source_kinds=("PRIMARY", "MARKET"),
            )
            self.assertEqual(research.completeness, "READY")
            research = ResearchPackageStore(db.conn).save(research)

            policy = OpportunityPolicy(
                policy_version="integration-policy-v1",
                weights={
                    "evidence_strength": 0.25, "timeliness": 0.20,
                    "materiality": 0.15, "audience_usefulness": 0.15,
                    "novelty": 0.15, "risk_control": 0.10,
                },
                proceed_threshold=75, defer_threshold=50,
            )
            decision = OpportunityEvaluationEngine().evaluate(
                eligibility_status="ELIGIBLE", eligibility_verified_at=iso(),
                research_completeness=research.completeness,
                event_state=lifecycle[0].state,
                contradiction_count=0, unresolved_critical_count=0,
                unsupported_causal_framing=False, duplicate_angle=False,
                materially_new=False,
                factors={name: 90 for name in FACTOR_NAMES}, policy=policy,
            )
            self.assertEqual(decision.state, "PROCEED")
            OpportunityDecisionStore(db.conn).save(research.package_id, decision)

            brief_store = EditorialBriefStore(db.conn)
            brief = EditorialStrategyEngine().build(
                research, event_id=lifecycle[0].event_id, store=brief_store,
            )
            brief = brief_store.save(brief)
            self.assertEqual(brief.status, "READY")

            price_claim = next(item for item in registry.claims if item.claim_key == "market.price")
            draft = (
                f"[[CLAIM:{price_claim.claim_id}]]{price_claim.text}.\n"
                "#ABC #Binance #Write2Earn"
            )
            content_result = ContentVerificationEngine().validate(
                draft, registry=registry, symbol="ABC", asset_id=asset_id,
                numeric_validator=lambda _: True,
            )
            self.assertEqual(content_result.status, "PASS")
            draft = content_result.clean_content
            draft_store = DraftStore(db.conn)
            draft_record = draft_store.save_draft(
                draft, asset_id=asset_id, research_package_id=research.package_id,
                editorial_brief_id=brief.brief_id,
                approved_claim_ids=content_result.approved_claim_ids,
            )
            draft_store.save_text_validation(
                draft_hash=draft_record.content_hash, status="PASS", reasons=(),
                validation_version=content_result.validation_version,
            )

            os.chdir(tmp.name)
            with patch("image_engine.CloudflareWorkersAIImageGenerator") as generator_class:
                def fake_generate(prompt, output_path, width, height):
                    Image.new("RGB", (1024, 1024), "midnightblue").save(output_path, format="PNG")
                    raw = Path(output_path).read_bytes()
                    return CloudflareImageArtifact(
                        path=Path(output_path), model=CloudflareWorkersAIImageGenerator.DEFAULT_MODEL,
                        content_hash=hashlib.sha256(raw).hexdigest(), byte_length=len(raw),
                        width=1024, height=1024, format="PNG", request_id="cf-ray-integration",
                        generated_at=iso(),
                    )
                generator_class.return_value.generate.side_effect = fake_generate
                image_path = ImageComposer().generate_post_image(
                    {"symbol": "ABC", "asset_id": asset_id, "price": 1.25, "entry": 0.9},
                    draft_content=draft,
                )
            image_metadata = json.loads(Path(str(image_path) + ".json").read_text(encoding="utf-8"))
            image_artifact_id = draft_store.save_image_artifact(
                image_metadata, image_path=str(image_path),
            )
            self.assertTrue(image_artifact_id)
            visual = VisualQualityEngine().validate(
                image_path, draft_content=draft, symbol="ABC", asset_id=asset_id,
            )
            self.assertEqual(visual.status, "PASS")
            draft_store.save_visual_validation(
                draft_hash=draft_record.content_hash, image_hash=visual.image_hash,
                status="PASS", reasons=(), validation_version=visual.validation_version,
            )

            db.conn.execute(
                "CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, coin_symbol TEXT, content TEXT NOT NULL)"
            )
            db.conn.execute("""
                CREATE TABLE IF NOT EXISTS publication_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT NOT NULL UNIQUE,
                    coin_symbol TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """)
            db.conn.commit()
            authorization_engine = PublicationAuthorizationEngine(db.conn)
            reservation = authorization_engine.reserve_daily_quota(symbol="ABC", daily_limit=6)
            authorization = authorization_engine.authorize(
                symbol="ABC", asset_id=asset_id, content=draft,
                image_hashes=[visual.image_hash],
                eligibility_snapshot_at=iso(), eligibility_max_age_seconds=300,
                event_state=lifecycle[0].state, evidence_status="VERIFIED",
                text_validation_status="PASS", visual_validation_status="PASS",
                quota_reservation_id=reservation, repetition_hard_hours=12,
            )
            self.assertTrue(authorization.verify_integrity())
            self.assertEqual(authorization.validate_for_submission(
                symbol="ABC", asset_id=asset_id, content=draft,
                image_hashes=[visual.image_hash],
            ), ())
        finally:
            os.chdir(old_cwd)
            db.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

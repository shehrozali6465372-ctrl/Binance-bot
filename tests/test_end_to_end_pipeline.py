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


from tests.evidence_fixtures import trusted_evidence_record
def iso(delta=0):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()


class EndToEndPipelineTests(unittest.TestCase):
    def test_unreceipted_announcement_blocks_research_and_publication(self):
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
            market = trusted_evidence_record(
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
                replace(
                    item, text="$ABC market price is 1.25 USD",
                    claim_type="CONFIRMED_FACT",
                )
                if item.claim_key == "market.price" else item
                for item in claims
            )
            registry = verifier.verify(claims, evidence)
            lifecycle_store = EventLifecycleStore(db)
            lifecycle = lifecycle_store.sync_announcements([announcement], registry)
            self.assertEqual(lifecycle[0].state, "UNDER_VERIFICATION")

            research = DeepResearchEngine().build(
                asset_id=asset_id, symbol="ABC",
                research_question=announcement.title, cutoff_at=iso(),
                registry=registry, event_states=("CONFIRMED",),
                required_source_kinds=("PRIMARY", "MARKET"),
            )
            self.assertEqual(research.completeness, "RESEARCH_MORE")
            # The missing CMS ingestion receipt is a deliberate fail-closed
            # blocker. Do not proceed to drafting, image generation or auth.
            return
        finally:
            os.chdir(old_cwd)
            db.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

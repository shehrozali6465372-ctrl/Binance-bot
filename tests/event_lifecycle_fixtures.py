"""Test helper simulating a trusted CMS-ingestion receipt for lifecycle tests."""
from layer1.evidence_verification import EvidenceVerificationEngine, _issue_evidence_record


def test_receipted_announcement_registry(announcement):
    engine = EvidenceVerificationEngine()
    records = engine.evidence_from_announcement(announcement)
    for item in records:
        # Preserve the adapter's evidence identity; only the test fixture supplies
        # the missing trusted ingestion receipt/status used by lifecycle tests.
        object.__setattr__(
            item, "source_status",
            "STALE" if item.claim_key == "announcement.freshness" and item.status_value == "STALE"
            else "ACCEPTED",
        )
        object.__setattr__(item, "is_primary", True)
        _issue_evidence_record(
            item, authority_id="test_fixture", independence_group="test:binance-cms",
        )
    records = tuple(records)
    return engine.verify(engine._source_assertion_claims(records), records)

"""Test-only evidence fixtures carrying the verifier's in-process fixture proof."""
from layer1.evidence_verification import EvidenceRecord, _issue_evidence_record


def trusted_evidence_record(**values):
    record = EvidenceRecord(**values)
    publisher = str(values.get("publisher") or "unknown").strip().casefold()
    return _issue_evidence_record(
        record, authority_id="test_fixture", independence_group="test:" + publisher,
    )


def verifier_issued_content_result(content, *, status="PASS", reasons=(),
                                   validation_version="content-verification-v2-claim-attribution",
                                   asset_id="coingecko:abc", symbol="ABC"):
    """Create an in-process verifier-issued result for persistence-boundary tests."""
    import hashlib
    from layer1.content_verification import ContentVerificationResult, _issue_content_verification_result

    clean = str(content)
    result = ContentVerificationResult(
        status=status,
        draft_hash=hashlib.sha256(clean.encode("utf-8")).hexdigest(),
        asset_id=asset_id,
        symbol=symbol,
        approved_claim_ids=("a" * 64,) if status == "PASS" else (),
        reasons=tuple(reasons),
        clean_content=clean,
        validation_version=validation_version,
    )
    return _issue_content_verification_result(result)

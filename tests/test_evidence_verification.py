import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from layer1.evidence_verification import (
    Claim,
    ClaimRegistryStore,
    EvidenceRecord,
    render_claim_registry,
    EvidenceVerificationEngine,
    split_atomic_claims,
)
from layer1.foundation import AnnouncementEvidence, Layer1Store, MarketObservation, TrendSignal
from layer1.onchain import OnChainObservation, OnChainValidationResult


from tests.evidence_fixtures import trusted_evidence_record
def iso(delta_seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


def record(value=100.0, source_id="source-1", source_family="exchange-a", is_primary=True,
           content_hash="", asset_id="coingecko:abc", subject="coingecko:abc",
           claim_key="market.price", unit="USD", timeframe="spot", event_at=None,
           published_at=None, updated_at=None, observed_at=None, source_status="ACCEPTED",
           status_value=None, lineage_id=None):
    observed_at = observed_at or iso()
    published_at = published_at or iso(-120)
    return trusted_evidence_record(
        source_id=source_id, source_family=source_family, source_kind="PRIMARY" if is_primary else "SECONDARY",
        publisher=source_family, subject=subject, claim_key=claim_key, value=value,
        published_at=published_at, observed_at=observed_at, asset_id=asset_id, unit=unit,
        timeframe=timeframe, event_at=event_at, updated_at=updated_at,
        content_hash=content_hash, lineage_id=lineage_id, is_primary=is_primary,
        source_status=source_status, status_value=status_value,
    )


def claim(evidence, value=100.0, impact="MEDIUM", max_age_seconds=3600,
          claim_type="CONFIRMED_FACT", asset_id="coingecko:abc", subject="coingecko:abc",
          unit="USD", timeframe="spot", event_at=None, expected_status=None, evidence_ids=None):
    return Claim(
        text=f"ABC price is {value} {unit}", subject=subject, asset_id=asset_id,
        claim_key="market.price", value=value, unit=unit, timeframe=timeframe,
        event_at=event_at, expected_status=expected_status,
        observed_at=iso(), claim_type=claim_type, impact=impact,
        evidence_ids=tuple(evidence_ids if evidence_ids is not None else (evidence.evidence_id,)),
        max_age_seconds=max_age_seconds,
    )


class EvidenceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.engine = EvidenceVerificationEngine()

    def test_evidence_record_rejects_malformed_nonempty_content_hash(self):
        malformed = EvidenceRecord(
            source_id="malformed-hash", source_family="exchange-a", source_kind="PRIMARY",
            publisher="exchange-a", subject="coingecko:abc", claim_key="market.price",
            value=100.0, published_at=iso(-120), observed_at=iso(),
            content_hash="sha256:not-a-hex-digest",
        )
        with self.assertRaisesRegex(ValueError, "content_hash must be a lowercase SHA-256"):
            malformed.validate()

    def test_evidence_record_accepts_absent_content_hash_for_normalized_onchain_identity(self):
        normalized = record(content_hash="")
        normalized.validate()

    def test_asset_scoped_registry_excludes_other_assets_before_draft_rendering(self):
        btc = record(
            value=100.0, source_id="btc-market", asset_id="coingecko:btc",
            subject="coingecko:btc",
        )
        abc = record(
            value=25.0, source_id="abc-market", asset_id="coingecko:abc",
            subject="coingecko:abc",
        )
        btc_claim = claim(btc, value=100.0, asset_id="coingecko:btc", subject="coingecko:btc")
        abc_claim = claim(abc, value=25.0)
        registry = self.engine.verify([btc_claim, abc_claim], [btc, abc])
        scoped = self.engine.scope_registry_to_asset(registry, "coingecko:abc")
        self.assertEqual([item.claim_id for item in scoped.claims], [abc_claim.claim_id])
        self.assertEqual([item.evidence_id for item in scoped.evidence_records], [abc.evidence_id])
        self.assertEqual([item.claim_id for item in scoped.results], [abc_claim.claim_id])

    def test_cross_asset_evidence_reference_remains_unresolved_without_leaking_other_asset_data(self):
        btc = record(
            value=100.0, source_id="btc-market", asset_id="coingecko:btc",
            subject="coingecko:btc",
        )
        abc_claim = claim(
            btc, value=100.0, asset_id="coingecko:abc", subject="coingecko:abc",
        )
        registry = self.engine.verify([abc_claim], [btc])
        scoped = self.engine.scope_registry_to_asset(registry, "coingecko:abc")
        self.assertEqual(scoped.evidence_records, ())
        rerun = self.engine.verify(scoped.claims, scoped.evidence_records)
        self.assertEqual(rerun.results[0].state, "UNVERIFIED")
        self.assertIn("MISSING_EVIDENCE_ID", rerun.results[0].issues)

    def test_unsupported_claim_without_evidence_fails_closed(self):
        unsupported = Claim(
            text="ABC price is 100 USD", subject="coingecko:abc", asset_id="coingecko:abc",
            claim_key="market.price", value=100.0, unit="USD", timeframe="spot",
            observed_at=iso(), evidence_ids=(),
        )
        result = self.engine.verify([unsupported], []).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("NO_EVIDENCE_LINKED", result.issues)

    def test_causal_relation_cannot_borrow_market_field_evidence(self):
        market = record(value=100.0, claim_key="market.price", unit="USD")
        candidate = Claim(
            text="ABC price is 100 USD because Binance listed ABC",
            subject=market.subject, asset_id=market.asset_id,
            claim_key="market.price", value=100.0, unit="USD", timeframe="spot",
            observed_at=iso(), evidence_ids=(market.evidence_id,), max_age_seconds=3600,
        )
        result = self.engine.verify([candidate], [market]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("CAUSAL_RELATION_REQUIRES_DIRECT_SOURCE_ASSERTION", result.issues)

    def test_active_causal_relation_cannot_borrow_market_field_evidence(self):
        market = record(value=100.0, claim_key="market.price", unit="USD")
        candidate = Claim(
            text="ABC listing caused the price to rise",
            subject=market.subject, asset_id=market.asset_id,
            claim_key="market.price", value=100.0, unit="USD", timeframe="spot",
            observed_at=iso(), evidence_ids=(market.evidence_id,), max_age_seconds=3600,
        )
        result = self.engine.verify([candidate], [market]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("CAUSAL_RELATION_REQUIRES_DIRECT_SOURCE_ASSERTION", result.issues)

    def test_compound_claim_cannot_borrow_one_atomic_field_evidence(self):
        market = record(value=100.0, claim_key="market.price", unit="USD")
        candidate = Claim(
            text="ABC is 100 USD and volume rose 5%",
            subject=market.subject, asset_id=market.asset_id,
            claim_key="market.price", value=100.0, unit="USD", timeframe="spot",
            observed_at=iso(), evidence_ids=(market.evidence_id,), max_age_seconds=3600,
        )
        result = self.engine.verify([candidate], [market]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE", result.issues)

    def test_comma_participial_second_action_cannot_borrow_one_market_field_evidence(self):
        evidence = record(value=100.0)
        for text in (
            "ABC price rose 8%, falling 4%",
            "ABC price gained 3%, later dropping 2%",
            "ABC price surged 5%, closing 10% higher",
            "ABC price rose 8% as trading volume increased 2%",
            "ABC price rose 8%, which was 4% higher than yesterday",
        ):
            with self.subTest(text=text):
                item = Claim(
                    text=text, subject="coingecko:abc", asset_id="coingecko:abc",
                    claim_key="market.price", value=100.0, unit="USD", timeframe="spot",
                    observed_at=iso(), claim_type="CONFIRMED_FACT", impact="MEDIUM",
                    evidence_ids=(evidence.evidence_id,), max_age_seconds=3600,
                )
                result = self.engine.verify([item], [evidence]).results[0]
                self.assertEqual(result.state, "UNVERIFIED")
                self.assertIn("COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE", result.issues)

    def test_temporal_before_after_second_action_cannot_borrow_one_market_field_evidence(self):
        market = record(value=8.0, claim_key="market.price_change", unit="%")
        for text in (
            "ABC price rose 8% before falling 4%",
            "ABC price gained 3% after rising 2%",
        ):
            with self.subTest(text=text):
                candidate = Claim(
                    text=text, subject=market.subject, asset_id=market.asset_id,
                    claim_key="market.price_change", value=8.0, unit="%", timeframe="spot",
                    observed_at=iso(), evidence_ids=(market.evidence_id,), max_age_seconds=3600,
                )
                result = self.engine.verify([candidate], [market]).results[0]
                self.assertEqual(result.state, "UNVERIFIED")
                self.assertIn("COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE", result.issues)

        single_fact = Claim(
            text="ABC price was 8% before 2026-11-20",
            subject=market.subject, asset_id=market.asset_id,
            claim_key="market.price_change", value=8.0, unit="%", timeframe="spot",
            observed_at=iso(), evidence_ids=(market.evidence_id,), max_age_seconds=3600,
        )
        single_result = self.engine.verify([single_fact], [market]).results[0]
        self.assertEqual(single_result.state, "VERIFIED")
        self.assertNotIn("COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE", single_result.issues)

    def test_shared_subject_then_sequence_cannot_borrow_one_market_field_evidence(self):
        market = record(value=8.0, claim_key="market.price_change", unit="%")
        for text in (
            "ABC price rose 8% then fell 4%",
            "ABC price rose 8% later fell 4%",
            "ABC price rose 8%, subsequently fell 4%",
        ):
            with self.subTest(text=text):
                candidate = Claim(
                    text=text, subject=market.subject, asset_id=market.asset_id,
                    claim_key="market.price_change", value=8.0, unit="%", timeframe="spot",
                    observed_at=iso(), evidence_ids=(market.evidence_id,), max_age_seconds=3600,
                )
                result = self.engine.verify([candidate], [market]).results[0]
                self.assertEqual(result.state, "UNVERIFIED")
                self.assertIn("COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE", result.issues)

    def test_direct_primary_announcement_body_can_remain_attributed_source_assertion(self):
        body = "Binance listed ABC because the project completed its review."
        source = record(
            value=body, source_id="binance-announcement-body", source_family="binance",
            claim_key="announcement.body", unit=None, timeframe=None,
        )
        candidate = self.engine._source_assertion_claims((source,))[0]
        result = self.engine.verify([candidate], [source]).results[0]
        self.assertEqual(result.state, "VERIFIED")

    def test_unrelated_text_cannot_launder_under_an_announcement_body_key(self):
        announcement = AnnouncementEvidence(
            source_id="binance-body-launder",
            source_url="https://www.binance.com/en/support/announcement/body-launder",
            publisher="Binance", event_type="listing", title="ABC listing",
            published_at=iso(-60), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="8" * 64,
            body="Binance will list ABC on 2026-12-01 at 08:00 UTC.",
        )
        evidence = self.engine.evidence_from_announcement(announcement)
        body = next(item for item in evidence if item.claim_key == "announcement.body")
        candidate = self.engine._source_assertion_claims((body,))[0]
        candidate = Claim(**{**candidate.__dict__, "text": "ABC listing confirmed for December 1"})
        result = self.engine.verify([candidate], evidence).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("ANNOUNCEMENT_TEXT_EVIDENCE_MISMATCH", result.issues)

    def test_causal_text_cannot_launder_under_an_announcement_body_key(self):
        body = "Binance listed ABC because the project completed its review."
        source = record(
            value=body, source_id="binance-announcement-body-launder",
            source_family="binance", claim_key="announcement.body",
            unit=None, timeframe=None,
        )
        candidate = Claim(
            text="ABC price rose because Binance listed ABC",
            subject=source.subject, asset_id=source.asset_id,
            claim_key="announcement.body", value=body, observed_at=iso(),
            claim_type="SOURCE_ASSERTION", evidence_ids=(source.evidence_id,),
            max_age_seconds=3600,
        )
        result = self.engine.verify([candidate], [source]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("CAUSAL_RELATION_REQUIRES_DIRECT_SOURCE_ASSERTION", result.issues)

    def test_unlinked_claim_cannot_auto_attach_matching_registry_evidence(self):
        evidence = record()
        unlinked = claim(evidence, evidence_ids=())
        result = self.engine.verify([unlinked], [evidence]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("NO_EVIDENCE_LINKED", result.issues)

    def test_exact_primary_evidence_verifies_structured_claim(self):
        evidence = record()
        candidate = claim(evidence)
        result = self.engine.verify([candidate], [evidence]).results[0]
        self.assertEqual(result.state, "VERIFIED")
        self.assertEqual(result.supporting_evidence_ids, (evidence.evidence_id,))
        self.assertEqual(result.independent_source_count, 1)

    def test_number_mismatch_is_contradicted_and_both_sides_are_preserved(self):
        support = record(value=100.0, source_id="source-a", source_family="exchange-a")
        conflict = record(value=90.0, source_id="source-b", source_family="exchange-b", is_primary=False)
        result = self.engine.verify([claim(support)], [support, conflict]).results[0]
        self.assertEqual(result.state, "CONTRADICTED")
        self.assertIn(support.evidence_id, result.supporting_evidence_ids)
        self.assertIn(conflict.evidence_id, result.contradicting_evidence_ids)
        self.assertEqual(set(result.evidence_ids), {support.evidence_id, conflict.evidence_id})

    def test_asset_unit_timeframe_and_event_date_mismatches_do_not_pass(self):
        event_at = iso(-600)
        evidence = record(event_at=event_at)
        mismatched = claim(
            evidence, asset_id="coingecko:other", unit="BTC", timeframe="24h",
            event_at=iso(-500),
        )
        result = self.engine.verify([mismatched], [evidence]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertTrue(any(issue.startswith("EVIDENCE_FIELD_MISMATCH") for issue in result.issues))

    def test_syndicated_copies_do_not_count_as_independent_corroboration(self):
        first = record(source_id="publisher-a", source_family="publisher-a", is_primary=True,
                       content_hash="f" * 64)
        copy = record(source_id="publisher-b", source_family="publisher-b", is_primary=False,
                      content_hash="f" * 64)
        candidate = claim(first, impact="HIGH")
        result = self.engine.verify([candidate], [first, copy]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertEqual(result.independent_source_count, 1)
        self.assertIn("HIGH_IMPACT_EVIDENCE_THRESHOLD_NOT_MET", result.issues)
        self.assertEqual(len(set(result.source_lineage.values())), 1)

    def test_independent_sources_corroborate_matching_claim(self):
        first = record(source_id="exchange-a", source_family="exchange-a", is_primary=True,
                       content_hash="a" * 64)
        second = record(source_id="exchange-b", source_family="exchange-b", is_primary=False,
                        content_hash="b" * 64)
        candidate = claim(first)
        candidate = Claim(**{**candidate.__dict__, "evidence_ids": (first.evidence_id, second.evidence_id)})
        result = self.engine.verify([candidate], [first, second]).results[0]
        self.assertEqual(result.state, "CORROBORATED")
        self.assertEqual(result.independent_source_count, 2)

    def test_high_impact_requires_primary_and_independent_corroboration(self):
        primary = record(source_id="official", source_family="official", is_primary=True)
        candidate = claim(primary, impact="HIGH")
        single = self.engine.verify([candidate], [primary]).results[0]
        self.assertEqual(single.state, "UNVERIFIED")
        self.assertIn("HIGH_IMPACT_EVIDENCE_THRESHOLD_NOT_MET", single.issues)

        secondary = record(
            source_id="independent", source_family="independent", is_primary=False,
            content_hash="c" * 64, published_at=primary.published_at,
            observed_at=primary.observed_at,
        )
        candidate = Claim(**{**candidate.__dict__, "evidence_ids": (primary.evidence_id, secondary.evidence_id)})
        corroborated = self.engine.verify([candidate], [primary, secondary]).results[0]
        self.assertEqual(corroborated.state, "CORROBORATED")
        self.assertEqual(corroborated.independent_source_count, 2)

    def test_single_secondary_source_verifies_only_an_attributed_source_assertion(self):
        secondary = record(
            value=100.0, source_id="secondary-market", source_family="coingecko_markets",
            is_primary=False,
        )
        source_assertion = claim(secondary)
        source_assertion = Claim(
            **{**source_assertion.__dict__, "claim_type": "SOURCE_ASSERTION"},
        )
        result = self.engine.verify([source_assertion], [secondary]).results[0]
        self.assertEqual(result.state, "VERIFIED")

        factual_claim = Claim(
            **{**source_assertion.__dict__, "claim_type": "CONFIRMED_FACT"},
        )
        factual_result = self.engine.verify([factual_claim], [secondary]).results[0]
        self.assertEqual(factual_result.state, "UNVERIFIED")
        self.assertIn("PRIMARY_OR_INDEPENDENT_EVIDENCE_REQUIRED", factual_result.issues)

    def test_high_impact_claim_requires_explicit_freshness_policy(self):
        evidence = record()
        candidate = claim(evidence, impact="HIGH", max_age_seconds=None)
        result = self.engine.verify([candidate], [evidence]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("HIGH_IMPACT_FRESHNESS_POLICY_REQUIRED", result.issues)

    def test_stale_evidence_fails_even_when_value_matches(self):
        old = record(published_at=iso(-7200), updated_at=iso(-7200), observed_at=iso(-7100))
        candidate = claim(old, max_age_seconds=60)
        result = self.engine.verify([candidate], [old]).results[0]
        self.assertEqual(result.state, "STALE")
        self.assertIn("EVIDENCE_STALE", result.issues)

    def test_source_publication_after_observation_cutoff_is_rejected(self):
        cutoff = iso(-300)
        evidence = record(published_at=iso(-100), observed_at=iso(-90))
        candidate = Claim(
            text="ABC price is 100 USD", subject="coingecko:abc", asset_id="coingecko:abc",
            claim_key="market.price", value=100.0, unit="USD", timeframe="spot",
            observed_at=cutoff, evidence_ids=(evidence.evidence_id,), max_age_seconds=3600,
        )
        result = self.engine.verify([candidate], [evidence]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("EVIDENCE_AFTER_CLAIM_CUTOFF", result.issues)

    def test_estimates_interpretations_and_hypotheses_are_not_verified_as_facts(self):
        evidence = record()
        for claim_type in ("ESTIMATE", "ANALYST_INTERPRETATION", "HYPOTHESIS"):
            candidate = claim(evidence, claim_type=claim_type)
            result = self.engine.verify([candidate], [evidence]).results[0]
            self.assertEqual(result.state, "UNVERIFIED")
            self.assertIn("NON_FACTUAL_CLAIM_TYPE", result.issues)

    def test_research_sentence_drafts_remain_unclassified_and_unverified(self):
        drafts = self.engine.drafts_from_text(
            "ABC volume increased. The catalyst may attract traders.",
            subject="ABC", asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual(len(drafts), 2)
        registry = self.engine.verify(drafts, [])
        self.assertTrue(all(result.state == "UNVERIFIED" for result in registry.results))
        self.assertTrue(all("CLAIM_TYPE_UNCLASSIFIED" in result.issues for result in registry.results))

    def test_rendered_source_assertion_names_the_actual_supporting_publishers(self):
        evidence = record(source_id="binance-market", source_family="binance",
                          is_primary=True)
        registry = self.engine.verify(
            self.engine._source_assertion_claims((evidence,)), (evidence,),
        )
        rendered = render_claim_registry(registry, asset_id="coingecko:abc")
        self.assertIn("source publishers: binance", rendered)
        self.assertIn("A SOURCE_ASSERTION records only what its named publisher asserted", rendered)
        self.assertIn("not independently confirmed truth", rendered)

    def test_rendered_registry_separates_verified_and_unresolved_claims(self):
        evidence = record()
        verified_claim = claim(evidence)
        draft = self.engine.drafts_from_text(
            "Smart money is accumulating.", subject="ABC",
            asset_id="coingecko:abc", observed_at=iso(),
        )[0]
        registry = self.engine.verify([verified_claim, draft], [evidence])
        rendered = render_claim_registry(registry, asset_id="coingecko:abc")
        self.assertIn("[VERIFIED/CONFIRMED_FACT]", rendered)
        self.assertIn("[UNVERIFIED/UNCLASSIFIED]", rendered)
        self.assertIn("model confidence is not evidence", rendered)
        self.assertIn(f"claim ID: {verified_claim.claim_id}", rendered)
        self.assertIn("VERIFIED_COUNT: 1", rendered)
        self.assertIn("UNRESOLVED_COUNT: 1", rendered)

    def test_register_uses_latest_snapshot_and_preserves_latest_stale_state(self):
        old_evidence = record(
            value=99.0, source_id="old-snapshot", event_at=iso(-3600),
            published_at=iso(-4000), observed_at=iso(-3000), source_status="STALE",
        )
        new_evidence = record(
            value=100.0, source_id="new-snapshot", event_at=iso(-60),
            published_at=iso(-120), observed_at=iso(-30), source_status="ACCEPTED",
        )
        old_claim = claim(old_evidence, value=99.0, event_at=old_evidence.event_at)
        new_claim = claim(new_evidence, value=100.0, event_at=new_evidence.event_at)
        registry = self.engine.verify([old_claim, new_claim], [old_evidence, new_evidence])
        rendered = render_claim_registry(registry, asset_id="coingecko:abc")
        self.assertIn("VERIFIED_COUNT: 1", rendered)
        self.assertIn("UNRESOLVED_COUNT: 0", rendered)
        self.assertIn("HISTORICAL_CLAIMS_OMITTED: 1", rendered)
        self.assertNotIn("ABC price is 99.0 USD", rendered)

        latest_stale = record(
            value=101.0, source_id="latest-stale", event_at=iso(-10),
            published_at=iso(-60), observed_at=iso(-5), source_status="STALE",
        )
        latest_stale_claim = claim(latest_stale, value=101.0, event_at=latest_stale.event_at)
        stale_registry = self.engine.verify([new_claim, latest_stale_claim], [new_evidence, latest_stale])
        stale_rendered = render_claim_registry(stale_registry, asset_id="coingecko:abc")
        self.assertIn("VERIFIED_COUNT: 0", stale_rendered)
        self.assertIn("UNRESOLVED_COUNT: 1", stale_rendered)
        self.assertIn("ABC price is 101.0 USD", stale_rendered)

    def test_research_package_maps_exact_market_facts_and_labels_analysis(self):
        observed = iso()
        event = iso(-30)
        price_evidence = trusted_evidence_record(
            source_id="market-price-1", source_family="binance_spot",
            source_kind="MARKET", publisher="binance_spot", subject="coingecko:abc",
            claim_key="market.price", value=100.0000004, published_at=iso(-60),
            updated_at=iso(-60), observed_at=observed, asset_id="coingecko:abc",
            unit="USDT", timeframe="spot", event_at=event,
            content_hash="a" * 64, lineage_id="price-lineage", is_primary=True,
        )
        change_evidence = trusted_evidence_record(
            source_id="market-change-1", source_family="binance_spot",
            source_kind="MARKET", publisher="binance_spot", subject="coingecko:abc",
            claim_key="market.change_24h", value=2.54, published_at=iso(-60),
            updated_at=iso(-60), observed_at=observed, asset_id="coingecko:abc",
            unit="percent", timeframe="24h", event_at=event,
            content_hash="b" * 64, lineage_id="change-lineage", is_primary=True,
        )
        package = (
            "COIN: $ABC (Alpha Coin)\n"
            "── MARKET DATA ──\n"
            "Price: $100.000000 | 24h Change: +2.5%\n"
            "Stage: FRESH — move in progress\n"
        )
        claims = self.engine.claims_from_research_package(
            package, [price_evidence, change_evidence], subject="coingecko:abc",
            asset_id="coingecko:abc", observed_at=observed,
        )
        price_claim = next(item for item in claims if item.claim_key == "market.price")
        self.assertEqual(price_claim.value, 100.0000004)
        self.assertEqual(price_claim.evidence_ids, (price_evidence.evidence_id,))
        self.assertEqual(price_claim.claim_type, "SOURCE_ASSERTION")
        stage_claim = next(item for item in claims if item.text.startswith("Stage:"))
        self.assertEqual(stage_claim.claim_type, "ANALYST_INTERPRETATION")
        self.assertEqual(stage_claim.evidence_ids, ())
        registry = self.engine.verify(claims, [price_evidence, change_evidence])
        rendered = render_claim_registry(registry, asset_id="coingecko:abc")
        self.assertIn("VERIFIED_COUNT: 2", rendered)
        self.assertIn("UNRESOLVED_COUNT: 0", rendered)
        self.assertIn("QUALIFIED_NONFACTUAL_COUNT: 1", rendered)
        self.assertIn("QUALIFIED NON-FACTUAL ANALYSIS", rendered)

    def test_non_market_source_assertion_text_must_match_structured_value(self):
        cases = (
            (record(value=True, claim_key="binance_spot.eligible", unit=None,
                    timeframe="spot", status_value="TRADING"), "Binance Spot: NO"),
            (record(value=2, claim_key="publication.last_posted", unit="hours",
                    timeframe="latest_200_posts", status_value="RECENT_RECORD"),
             "Last posted: 12 hours ago"),
            (record(value="listing", claim_key="announcement.event_type", unit=None,
                    timeframe=None), "Type: delisting"),
            (record(value="FRESH", claim_key="announcement.freshness", unit=None,
                    timeframe=None, status_value="FRESH"), "Age: stale"),
        )
        for evidence, mismatched_text in cases:
            with self.subTest(claim_key=evidence.claim_key):
                candidate = self.engine._source_assertion_claims((evidence,))[0]
                candidate = Claim(**{**candidate.__dict__, "text": mismatched_text})
                result = self.engine.verify([candidate], [evidence]).results[0]
                self.assertEqual(result.state, "UNVERIFIED")
                self.assertTrue(any(
                    issue.startswith("CLAIM_TEXT_STRUCTURED_VALUE_MISMATCH")
                    for issue in result.issues
                ))

    def test_market_claim_uses_exact_candidate_payload_and_does_not_cross_quote_currencies(self):
        observed = iso()
        event = iso(-30)
        coingecko = trusted_evidence_record(
            source_id="coingecko-market", source_family="coingecko_markets",
            source_kind="SECONDARY", publisher="CoinGecko", subject="coingecko:abc",
            claim_key="market.price", value=100.0, published_at=iso(-60),
            updated_at=iso(-60), observed_at=observed, asset_id="coingecko:abc",
            unit="USD", timeframe="spot", event_at=event,
            content_hash="a" * 64, lineage_id="coingecko-lineage", is_primary=False,
        )
        binance = trusted_evidence_record(
            source_id="binance-market", source_family="binance_spot",
            source_kind="MARKET", publisher="Binance", subject="coingecko:abc",
            claim_key="market.price", value=101.0, published_at=iso(-60),
            updated_at=iso(-60), observed_at=observed, asset_id="coingecko:abc",
            unit="USDT", timeframe="spot", event_at=event,
            content_hash="b" * 64, lineage_id="binance-lineage", is_primary=True,
        )
        claims = self.engine.claims_from_research_package(
            "Price: $100.000000", [coingecko, binance],
            subject="coingecko:abc", asset_id="coingecko:abc",
            observed_at=observed, preferred_market_content_hash="a" * 64,
            require_preferred_market_content_hash=True,
        )
        self.assertEqual(claims[0].evidence_ids, (coingecko.evidence_id,))
        result = self.engine.verify(claims, [coingecko, binance]).results[0]
        self.assertEqual(result.state, "VERIFIED")
        self.assertEqual(result.contradicting_evidence_ids, ())

    def test_research_package_does_not_attach_nearby_but_mismatched_market_values(self):
        evidence = record(value=100.0)
        claims = self.engine.claims_from_research_package(
            "Price: $100.010000", [evidence], subject="coingecko:abc",
            asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].claim_type, "SOURCE_ASSERTION")
        self.assertEqual(claims[0].evidence_ids, (evidence.evidence_id,))
        result = self.engine.verify(claims, [evidence]).results[0]
        self.assertEqual(result.state, "CONTRADICTED")
        self.assertIn(evidence.evidence_id, result.contradicting_evidence_ids)

    def test_required_candidate_payload_hash_prevents_cross_provider_autolinking(self):
        evidence = record(value=100.0)
        claims = self.engine.claims_from_research_package(
            "Price: $100.000000", [evidence], subject="coingecko:abc",
            asset_id="coingecko:abc", observed_at=iso(),
            require_preferred_market_content_hash=True,
        )
        self.assertEqual(claims[0].evidence_ids, ())
        result = self.engine.verify(claims, [evidence]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("NO_EVIDENCE_LINKED", result.issues)

    def test_known_spot_assertion_without_official_evidence_remains_unverified(self):
        claims = self.engine.claims_from_research_package(
            "Binance Spot: YES", [], subject="coingecko:abc",
            asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual(claims[0].claim_type, "SOURCE_ASSERTION")
        self.assertEqual(claims[0].evidence_ids, ())
        result = self.engine.verify(claims, []).results[0]
        self.assertEqual(result.state, "UNVERIFIED")

    def test_research_package_splits_compound_unknown_sentences_atomically(self):
        claims = self.engine.claims_from_research_package(
            "Unverified claim A is 12. Unverified claim B is 34.", [],
            subject="coingecko:abc", asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual(len(claims), 2)
        self.assertEqual([item.claim_type for item in claims], ["UNCLASSIFIED", "UNCLASSIFIED"])
        self.assertEqual(claims[0].text, "Unverified claim A is 12")
        self.assertEqual(claims[1].text, "Unverified claim B is 34")

    def test_research_package_splits_shared_subject_predicates_without_inventing_evidence(self):
        claims = self.engine.claims_from_research_package(
            "BTC rose 8% and later fell 4%.", [],
            subject="coingecko:abc", asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual([item.text for item in claims], ["BTC rose 8%", "BTC fell 4%"])
        self.assertTrue(all(item.claim_type == "UNCLASSIFIED" for item in claims))
        self.assertTrue(all(not item.evidence_ids for item in claims))

    def test_research_package_splits_independent_conjunctions_into_unclassified_claims(self):
        claims = self.engine.claims_from_research_package(
            "Binance announced the ABC listing, and ABC rose 12%.", [],
            subject="coingecko:abc", asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual([item.text for item in claims], [
            "Binance announced the ABC listing", "ABC rose 12%",
        ])
        self.assertEqual([item.claim_type for item in claims], ["UNCLASSIFIED", "UNCLASSIFIED"])
        self.assertTrue(all(not item.evidence_ids for item in claims))

    def test_unknown_research_assertion_remains_unclassified(self):
        claims = self.engine.claims_from_research_package(
            "Binance Alpha selected this token", [], subject="coingecko:abc",
            asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual(claims[0].claim_type, "UNCLASSIFIED")
        self.assertEqual(claims[0].evidence_ids, ())

    def test_unmatched_announcement_detail_is_not_laundered_as_analysis(self):
        claims = self.engine.claims_from_research_package(
            "Detail: Binance approved ABC for a new listing", [],
            subject="coingecko:abc", asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].claim_type, "UNCLASSIFIED")
        self.assertEqual(claims[0].claim_key, "announcement.title")
        registry = self.engine.verify(claims, ())
        self.assertEqual(registry.results[0].state, "UNVERIFIED")
        rendered = render_claim_registry(registry, asset_id="coingecko:abc")
        self.assertIn("UNRESOLVED_COUNT: 1", rendered)
        self.assertIn("Binance approved ABC for a new listing", rendered)

    def test_market_movement_details_are_analysis_only_when_explicitly_typed(self):
        claims = self.engine.claims_from_research_package(
            "Type: MARKET MOVEMENT\nDetail: Strong +6.2% momentum",
            [], subject="coingecko:abc", asset_id="coingecko:abc", observed_at=iso(),
        )
        detail = next(item for item in claims if item.text.startswith("Detail:"))
        self.assertEqual(detail.claim_type, "ANALYST_INTERPRETATION")
        self.assertEqual(detail.claim_key, "research.interpretation")

    def test_binance_spot_evidence_requires_active_allowed_spot_pair(self):
        pairs = [
            {
                "symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT",
                "status": "TRADING", "isSpotTradingAllowed": True,
                "permissionSets": [["SPOT"]],
            },
            {
                "symbol": "ABCUSDC", "baseAsset": "ABC", "quoteAsset": "USDC",
                "status": "HALT", "isSpotTradingAllowed": True,
                "permissionSets": [["SPOT"]],
            },
            {
                "symbol": "ABCBTC", "baseAsset": "ABC", "quoteAsset": "BTC",
                "status": "TRADING", "isSpotTradingAllowed": False,
                "permissionSets": [["SPOT"]],
            },
        ]
        evidence = self.engine.evidence_from_binance_spot_pairs(
            "coingecko:abc", pairs, observed_at=iso(), allowed_quote_assets=("USDT", "USDC"), expected_base_asset="ABC",
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].claim_key, "binance_spot.eligible")
        self.assertEqual(evidence[0].value, True)
        self.assertEqual(evidence[0].status_value, "TRADING")
        self.assertEqual(evidence[0].source_family, "binance_spot_exchange_info_unreceipted")
        self.assertEqual(evidence[0].source_status, "UNVERIFIED")
        self.assertFalse(evidence[0].is_primary)
        with self.assertRaisesRegex(ValueError, "no active"):
            self.engine.evidence_from_binance_spot_pairs(
                "coingecko:abc", pairs[1:], observed_at=iso(), allowed_quote_assets=("USDT", "USDC", "BTC"), expected_base_asset="ABC",
            )

    def test_publication_history_evidence_scopes_no_record_to_latest_200(self):
        no_record = self.engine.evidence_from_publication_history(
            "coingecko:abc", "ABC", None, observed_at=iso(),
        )
        recent = self.engine.evidence_from_publication_history(
            "coingecko:abc", "ABC", 3.6, observed_at=iso(),
        )
        self.assertEqual(no_record.value, "NO_RECORD_IN_LATEST_200")
        self.assertEqual(no_record.timeframe, "latest_200_posts")
        self.assertEqual(recent.value, 4)
        self.assertEqual(recent.unit, "hours")
        self.assertEqual(recent.source_family, "local_publication_ledger")

    def test_package_links_spot_and_publication_ledger_assertions(self):
        observed = iso()
        spot = self.engine.evidence_from_binance_spot_pairs(
            "coingecko:abc",
            [{
                "symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT",
                "status": "TRADING", "isSpotTradingAllowed": True,
                "permissionSets": [["SPOT"]],
            }],
            observed_at=observed, expected_base_asset="ABC",
        )
        publication = self.engine.evidence_from_publication_history(
            "coingecko:abc", "ABC", None, observed_at=observed,
        )
        claims = self.engine.claims_from_research_package(
            "Binance Spot: YES\nLast posted: NO RECORD IN LATEST 200 LOCAL POSTS",
            spot + (publication,), subject="coingecko:abc",
            asset_id="coingecko:abc", observed_at=observed,
        )
        registry = self.engine.verify(claims, spot + (publication,))
        self.assertEqual([result.state for result in registry.results], ["UNVERIFIED", "VERIFIED"])
        self.assertEqual(registry.results[0].supporting_evidence_ids, ())
        self.assertTrue(registry.results[1].supporting_evidence_ids)

    def test_atomic_claim_splitter_separates_independent_conjunction_clauses(self):
        self.assertEqual(
            split_atomic_claims("Binance announced the ABC listing, and ABC rose 12%."),
            ("Binance announced the ABC listing", "ABC rose 12%.",),
        )
        self.assertEqual(
            split_atomic_claims("BTC rose 8% but ETH fell 4%."),
            ("BTC rose 8%", "ETH fell 4%.",),
        )

    def test_atomic_claim_splitter_separates_shared_subject_predicates(self):
        self.assertEqual(
            split_atomic_claims("BTC rose 8% and later fell 4%."),
            ("BTC rose 8%", "BTC fell 4%."),
        )
        self.assertEqual(
            split_atomic_claims("Binance listed ABC and launched a new trading pair."),
            ("Binance listed ABC", "Binance launched a new trading pair."),
        )

    def test_atomic_claim_splitter_separates_explicit_comma_then_shared_predicate(self):
        self.assertEqual(
            split_atomic_claims("BTC rose 8%, then fell 4%."),
            ("BTC rose 8%", "BTC fell 4%."),
        )
        self.assertEqual(
            split_atomic_claims("ETH gained 3%, later dropped 2%."),
            ("ETH gained 3%", "ETH dropped 2%."),
        )

    def test_atomic_claim_splitter_separates_possessive_asset_subjects(self):
        self.assertEqual(
            split_atomic_claims("Bitcoin's price rose 8% and Ethereum's price fell 4%."),
            ("Bitcoin's price rose 8%", "Ethereum's price fell 4%."),
        )
        self.assertEqual(
            split_atomic_claims("ETH's price rose 8% while BTC's price fell 4%."),
            ("ETH's price rose 8%", "BTC's price fell 4%."),
        )

    def test_atomic_claim_splitter_handles_negated_did_not_change_possessive_clause(self):
        self.assertEqual(
            split_atomic_claims("Bitcoin's price rose 8% and Ethereum's price did not change."),
            ("Bitcoin's price rose 8%", "Ethereum's price did not change."),
        )

    def test_atomic_claim_splitter_handles_lowercase_possessive_asset_subjects(self):
        self.assertEqual(
            split_atomic_claims("bitcoin's price rose 8% and ethereum's price fell 4%."),
            ("bitcoin's price rose 8%", "ethereum's price fell 4%."),
        )
        self.assertEqual(
            split_atomic_claims("bitcoin's price rose 8% and later fell 4%."),
            ("bitcoin's price rose 8%", "bitcoin's price fell 4%."),
        )

    def test_possessive_asset_clauses_cannot_share_one_market_evidence_link(self):
        evidence = record(
            value=8.0, claim_key="market.price_change", unit="%",
        )
        candidate = Claim(
            text="Bitcoin's price rose 8% and Ethereum's price fell 4%.",
            subject=evidence.subject, asset_id=evidence.asset_id,
            claim_key="market.price_change", value=8.0, unit="%", timeframe="spot",
            observed_at=iso(), claim_type="CONFIRMED_FACT", impact="MEDIUM",
            evidence_ids=(evidence.evidence_id,), max_age_seconds=3600,
        )
        result = self.engine.verify([candidate], [evidence]).results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertIn("COMPOUND_CLAIM_REQUIRES_ATOMIC_EVIDENCE", result.issues)

    def test_atomic_claim_splitter_preserves_conjunctions_that_join_objects(self):
        self.assertEqual(
            split_atomic_claims("Binance listed ABC and BNB."),
            ("Binance listed ABC and BNB.",),
        )

    def test_atomic_claim_splitter_handles_semicolons_without_following_whitespace(self):
        self.assertEqual(
            split_atomic_claims("BTC price is $100;ETH volume is $5m"),
            ("BTC price is $100", "ETH volume is $5m"),
        )

    def test_atomic_claim_splitter_separates_sentences_and_semicolon_clauses(self):
        claims = split_atomic_claims(
            "BTC price is $100. Volume is $5m; Binance published a listing notice.\n- Market cap is $2b."
        )
        self.assertEqual(len(claims), 4)
        self.assertIn("BTC price is $100", claims[0])
        self.assertIn("Binance published a listing notice", claims[2])

    def test_atomic_claim_splitter_preserves_common_abbreviations(self):
        claims = split_atomic_claims(
            "U.S. regulators reviewed the filing. e.g. the listing date remains unconfirmed."
        )
        self.assertEqual(
            claims,
            ("U.S. regulators reviewed the filing.", "e.g. the listing date remains unconfirmed."),
        )

    def test_atomic_claim_splitter_preserves_time_and_organization_abbreviations(self):
        claims = split_atomic_claims(
            "Binance Inc. confirmed the review. SEC Corp. responded."
        )
        self.assertEqual(
            claims,
            ("Binance Inc. confirmed the review.", "SEC Corp. responded."),
        )

    def test_atomic_claim_splitter_preserves_clock_time_abbreviations(self):
        claims = split_atomic_claims(
            "The notice arrived at 9 a.m. The review ended at 4 p.m."
        )
        self.assertEqual(
            claims,
            ("The notice arrived at 9 a.m.", "The review ended at 4 p.m."),
        )

    def test_adapters_preserve_source_identity_and_lineage(self):
        announcement = AnnouncementEvidence(
            source_id="binance-article-1", source_url="https://www.binance.com/en/support/announcement/article-1",
            publisher="Binance", event_type="listing", title="ABC listing", published_at=iso(-60),
            observed_at=iso(), asset_ids=("coingecko:abc",), content_hash="d" * 64,
            body="Binance will list ABC.",
        )
        market = MarketObservation(
            asset_id="coingecko:abc", provider="binance_spot", endpoint="https://data-api.binance.vision/api/v3/ticker/24hr",
            observed_at=iso(), published_at=iso(-10), source_timestamp=iso(-10),
            price=100.0, currency="USDT", data_hash="e" * 64,
            field_availability={"price": "AVAILABLE"}, field_provenance={"price": "binance_spot"},
            freshness_by_field={"price": "FRESH"},
        )
        trend_signal = TrendSignal(
            topic="ABC", source="news-provider", observed_at=iso(), rank=1,
            asset_ids=("coingecko:abc",), source_item_id="story-1", content_hash="f" * 64,
        )
        engine = EvidenceVerificationEngine()
        announcement_records = engine.evidence_from_announcement(announcement)
        market_records = engine.evidence_from_market_observation(market)
        trend_records = engine.evidence_from_trend_signal(trend_signal)
        self.assertFalse(announcement_records[0].is_primary)
        self.assertEqual(announcement_records[0].source_status, "UNVERIFIED")
        self.assertEqual(announcement_records[0].lineage_id, "d" * 64)
        by_claim_key = {item.claim_key: item for item in announcement_records}
        self.assertFalse(by_claim_key["announcement.title"].is_primary)
        self.assertFalse(by_claim_key["announcement.body"].is_primary)
        self.assertFalse(by_claim_key["announcement.event_type"].is_primary)
        self.assertEqual(by_claim_key["announcement.title"].source_status, "UNVERIFIED")
        self.assertFalse(by_claim_key["announcement.freshness"].is_primary)
        self.assertFalse(by_claim_key["announcement.asset_id"].is_primary)
        self.assertTrue(market_records)
        self.assertEqual(market_records[0].source_family, "binance_spot_market")
        self.assertFalse(trend_records[0].is_primary)

    def test_announcement_import_hash_does_not_claim_unverified_canonical_hash_semantics(self):
        announcement = AnnouncementEvidence(
            source_id="announcement-hash-semantics",
            source_url="https://www.binance.com/en/support/announcement/hash-semantics",
            publisher="Binance", event_type="listing", title="ABC listing",
            published_at=iso(-60), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="9" * 64, body="Binance will list ABC.",
        )
        evidence = self.engine.evidence_from_announcement(announcement)
        self.assertTrue(evidence[0].content_hash)
        self.assertEqual(evidence[0].content_hash_kind, "UNSPECIFIED")

    def test_announcement_body_detail_requires_exact_source_text_match(self):
        engine = EvidenceVerificationEngine()
        announcement = AnnouncementEvidence(
            source_id="binance-body-exact", source_url="https://www.binance.com/en/support/announcement/body-exact",
            publisher="Binance", event_type="listing", title="ABC listing",
            published_at=iso(-60), observed_at=iso(), asset_ids=("coingecko:abc",),
            content_hash="9" * 64,
            body="Binance will list ABC on 2026-12-01 at 08:00 UTC.",
        )
        evidence = engine.evidence_from_announcement(announcement)
        exact = engine.claims_from_research_package(
            "Detail: Binance will list ABC on 2026-12-01 at 08:00 UTC.", evidence,
            subject="coingecko:abc", asset_id="coingecko:abc", observed_at=announcement.observed_at,
        )[0]
        self.assertEqual(exact.claim_key, "announcement.body")
        self.assertEqual(exact.evidence_ids, tuple(item.evidence_id for item in evidence if item.claim_key == "announcement.body"))
        self.assertEqual(engine.verify([exact], evidence).results[0].state, "UNVERIFIED")

        paraphrase = engine.claims_from_research_package(
            "Detail: Binance will list ABC next month at 08:00 UTC.", evidence,
            subject="coingecko:abc", asset_id="coingecko:abc", observed_at=announcement.observed_at,
        )[0]
        self.assertEqual(paraphrase.claim_type, "UNCLASSIFIED")
        self.assertEqual(paraphrase.evidence_ids, ())
        self.assertEqual(engine.verify([paraphrase], evidence).results[0].state, "UNVERIFIED")

    def test_announcement_freshness_is_linked_to_the_exact_title_and_stale_updates_fail(self):
        engine = EvidenceVerificationEngine()
        fresh_announcement = AnnouncementEvidence(
            source_id="binance-article-fresh",
            source_url="https://www.binance.com/en/support/announcement/fresh",
            publisher="Binance", event_type="listing", title="ABC listing",
            published_at=iso(-60), observed_at=iso(),
            asset_ids=("coingecko:abc",), content_hash="1" * 64,
        )
        fresh_records = engine.evidence_from_announcement(fresh_announcement)
        fresh_claims = engine.claims_from_research_package(
            "Detail: ABC listing\nAge: Just announced by Binance (FRESH)",
            fresh_records, subject="coingecko:abc", asset_id="coingecko:abc",
            observed_at=fresh_announcement.observed_at,
        )
        fresh_age_claim = next(item for item in fresh_claims if item.claim_key == "announcement.freshness")
        fresh_result = engine.verify([fresh_age_claim], fresh_records).results[0]
        self.assertEqual(fresh_result.state, "UNVERIFIED")
        self.assertEqual(fresh_result.supporting_evidence_ids, ())

        stale_announcement = AnnouncementEvidence(
            source_id="binance-article-stale",
            source_url="https://www.binance.com/en/support/announcement/stale",
            publisher="Binance", event_type="listing", title="ABC listing",
            published_at=iso(-90000), observed_at=iso(),
            asset_ids=("coingecko:abc",), content_hash="2" * 64,
        )
        stale_records = engine.evidence_from_announcement(stale_announcement)
        stale_claims = engine.claims_from_research_package(
            "Detail: ABC listing\nAge: Just announced by Binance (FRESH)",
            stale_records, subject="coingecko:abc", asset_id="coingecko:abc",
            observed_at=stale_announcement.observed_at,
        )
        stale_age_claim = next(item for item in stale_claims if item.claim_key == "announcement.freshness")
        stale_result = engine.verify([stale_age_claim], stale_records).results[0]
        self.assertEqual(stale_result.state, "UNVERIFIED")

    def test_distinct_trend_topics_and_market_snapshots_within_one_minute_are_not_contradictions(self):
        engine = EvidenceVerificationEngine()
        first_topic = TrendSignal(
            topic="BTC", source="coingecko_trending", observed_at=iso(), rank=1,
            asset_ids=("coingecko:abc",), source_item_id="topic-1", content_hash="1" * 64,
            source_endpoint="https://api.coingecko.com/api/v3/search/trending",
        )
        second_topic = TrendSignal(
            topic="btc", source="coingecko_trending", observed_at=iso(), rank=2,
            asset_ids=("coingecko:abc",), source_item_id="topic-2", content_hash="2" * 64,
            source_endpoint="https://api.coingecko.com/api/v3/search/trending",
        )
        topic_evidence = (
            engine.evidence_from_trend_signal(first_topic)
            + engine.evidence_from_trend_signal(second_topic)
        )
        topic_registry = engine.verify(engine._source_assertion_claims(topic_evidence), topic_evidence)
        self.assertEqual(len(topic_registry.results), 1)
        self.assertEqual(topic_registry.results[0].state, "VERIFIED")
        self.assertEqual(topic_registry.results[0].independent_source_count, 1)

        minute = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=1)
        first_time = (minute + timedelta(seconds=10)).isoformat()
        second_time = (minute + timedelta(seconds=40)).isoformat()
        first_market = MarketObservation(
            asset_id="coingecko:abc", provider="binance_spot", endpoint="https://data-api.binance.vision/api/v3/ticker/24hr",
            observed_at=iso(), published_at=first_time, source_timestamp=first_time,
            price=100.0, currency="USDT", data_hash="3" * 64,
            field_availability={"price": "AVAILABLE"}, freshness_by_field={"price": "FRESH"},
        )
        second_market = MarketObservation(
            asset_id="coingecko:abc", provider="binance_spot", endpoint="https://data-api.binance.vision/api/v3/ticker/24hr",
            observed_at=iso(), published_at=second_time, source_timestamp=second_time,
            price=101.0, currency="USDT", data_hash="4" * 64,
            field_availability={"price": "AVAILABLE"}, freshness_by_field={"price": "FRESH"},
        )
        market_evidence = (
            engine.evidence_from_market_observation(first_market)
            + engine.evidence_from_market_observation(second_market)
        )
        market_registry = engine.verify(engine._source_assertion_claims(market_evidence), market_evidence)
        self.assertFalse(any(result.state == "CONTRADICTED" for result in market_registry.results))

    def test_onchain_adapter_requires_matching_module9_acceptance(self):
        observation = OnChainObservation(
            observation_id="obs-abc-1", mapping_id="mapping-abc-1", asset_id="coingecko:abc",
            network_id="ethereum-mainnet", chain_id="1", provider="alchemy",
            endpoint_id="eth-mainnet-read", observation_type="transfer", block_height=100,
            block_hash="0x" + "a" * 64, transaction_hash="0x" + "b" * 64,
            block_time=iso(-30), observed_at=iso(), finality="FINALIZED",
            finality_reference="finalized-block-100",
        )
        accepted = OnChainValidationResult(
            "ACCEPTED", "ONCHAIN_OBSERVATION_VERIFIED", "verified", observation.observation_id,
            observation.asset_id, observation.mapping_id, observation.network_id, observation.provider,
        )
        engine = EvidenceVerificationEngine()
        verified = engine.evidence_from_onchain_observation(observation, accepted)
        self.assertEqual(verified.source_status, "UNVERIFIED")
        self.assertFalse(verified.is_primary)
        mismatched = OnChainValidationResult(
            "ACCEPTED", "ONCHAIN_OBSERVATION_VERIFIED", "mismatched", observation.observation_id,
            observation.asset_id, observation.mapping_id, "polygon-mainnet", observation.provider,
        )
        unverified = engine.evidence_from_onchain_observation(observation, mismatched)
        self.assertEqual(unverified.source_status, "UNVERIFIED")
        self.assertFalse(unverified.is_primary)

        summary = {
            "summary_id": "5" * 64, "asset_id": "coingecko:abc",
            "network_id": "ethereum-mainnet", "mapping_id": "mapping-abc-1",
            "observed_at": iso(), "first_block_time": iso(-120), "last_block_time": iso(-30),
            "threshold_met": True, "decimals": 18, "transfer_count": 4,
            "total_amount": "125.0", "minimum_amount": "100.0",
        }
        summary_evidence = engine.evidence_from_onchain_summary(summary)
        self.assertEqual(summary_evidence.mapping_id, "mapping-abc-1")
        self.assertFalse(summary_evidence.is_primary)
        self.assertEqual(summary_evidence.source_family, "module9_canonical_store")
        with self.assertRaisesRegex(ValueError, "threshold-qualified"):
            engine.evidence_from_onchain_summary({**summary, "threshold_met": False})

    def test_research_package_links_exact_trend_and_onchain_summary_evidence(self):
        trend = TrendSignal(
            topic="ABC", source="coingecko_trending", observed_at=iso(), rank=1,
            asset_ids=("coingecko:abc",), source_item_id="abc-trend-1",
            content_hash="a" * 64,
            source_endpoint="https://api.coingecko.com/api/v3/search/trending",
        )
        trend_evidence = self.engine.evidence_from_trend_signal(trend)
        summary = {
            "summary_id": "b" * 64, "asset_id": "coingecko:abc",
            "network_id": "ethereum-mainnet", "mapping_id": "mapping-abc-1",
            "observed_at": iso(), "first_block_time": iso(-120), "last_block_time": iso(-30),
            "threshold_met": True, "decimals": 18, "transfer_count": 4,
            "total_amount": "125.0", "minimum_amount": "100.0",
        }
        onchain_evidence = self.engine.evidence_from_onchain_summary(summary)
        evidence = trend_evidence + (onchain_evidence,)
        package = self.engine.append_asset_evidence_context(
            "COIN: ABC", evidence,
            subject="coingecko:abc", asset_id="coingecko:abc",
        )
        self.assertIn("Trend topic: abc", package)
        self.assertNotIn("On-chain transfer summary ID:", package)

        claims = self.engine.claims_from_research_package(
            package, evidence, subject="coingecko:abc", asset_id="coingecko:abc",
            observed_at=iso(),
        )
        registry = self.engine.verify(claims, evidence)
        by_key = {item.claim_key: item for item in claims}
        states = {item.claim_id: item.state for item in registry.results}

        self.assertIn("trend.topic:" + hashlib.sha256(b"abc").hexdigest()[:16], by_key)
        self.assertNotIn("onchain.transfer_summary", by_key)
        self.assertTrue(all(item.evidence_ids for item in claims))
        self.assertTrue(all(states[item.claim_id] in {"VERIFIED", "CORROBORATED"} for item in claims))

    def test_asset_evidence_context_does_not_leak_other_asset_records(self):
        trend = TrendSignal(
            topic="ABC", source="coingecko_trending", observed_at=iso(), rank=1,
            asset_ids=("coingecko:abc",), source_item_id="abc-trend-1",
            content_hash="a" * 64,
            source_endpoint="https://api.coingecko.com/api/v3/search/trending",
        )
        evidence = self.engine.evidence_from_trend_signal(trend)
        original = "COIN: XYZ"
        rendered = self.engine.append_asset_evidence_context(
            original, evidence, subject="coingecko:xyz", asset_id="coingecko:xyz",
        )
        self.assertEqual(rendered, original)

    def test_unknown_trend_topic_remains_unverified_without_exact_evidence(self):
        claims = self.engine.claims_from_research_package(
            "Trend topic: not-in-source", (), subject="coingecko:abc",
            asset_id="coingecko:abc", observed_at=iso(),
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].claim_type, "SOURCE_ASSERTION")
        self.assertEqual(claims[0].evidence_ids, ())
        self.assertEqual(self.engine.verify(claims, ()).results[0].state, "UNVERIFIED")

    def test_registry_persists_append_only_and_round_trips_json(self):
        evidence = record()
        registry = self.engine.verify([claim(evidence)], [evidence])
        with tempfile.TemporaryDirectory() as directory:
            store = Layer1Store(os.path.join(directory, "claims.db"))
            try:
                registry_store = ClaimRegistryStore(store.conn)
                verification_id = registry_store.save(registry)
                loaded = registry_store.load_latest()
                self.assertEqual(loaded["verification_id"], verification_id)
                self.assertEqual(loaded["payload"]["results"][0]["state"], "VERIFIED")
                self.assertEqual(registry_store.save(registry), verification_id)
            finally:
                store.close()

    def test_rebuild_from_store_creates_auditable_source_claim_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Layer1Store(os.path.join(directory, "layer1.db"))
            try:
                market = MarketObservation(
                    asset_id="coingecko:abc", provider="binance_spot", endpoint="https://data-api.binance.vision/api/v3/ticker/24hr",
                    observed_at=iso(), published_at=iso(-10), source_timestamp=iso(-10),
                    price=100.0, currency="USDT", data_hash="1" * 64,
                    field_availability={"price": "AVAILABLE"}, field_provenance={"price": "binance_spot"},
                    freshness_by_field={"price": "FRESH"},
                )
                store.save_market(market)
                registry = self.engine.rebuild_from_store(store)
                self.assertTrue(registry.claims)
                self.assertTrue(registry.evidence_records)
                self.assertTrue(all(result.evidence_ids for result in registry.results))
                self.assertTrue(any(result.state == "VERIFIED" for result in registry.results))
            finally:
                store.close()


    def test_market_claim_text_must_match_its_structured_metric_and_value(self):
        evidence = record(value=100.0, claim_key="market.price", unit="USD")
        for text in (
            "ABC price is 999 USD",
            "ABC volume is 100 USD",
            "ABC price is 100 EUR",
        ):
            with self.subTest(text=text):
                candidate = Claim(
                    text=text, subject=evidence.subject, asset_id=evidence.asset_id,
                    claim_key="market.price", value=100.0, unit="USD", timeframe="spot",
                    observed_at=iso(), claim_type="CONFIRMED_FACT", impact="MEDIUM",
                    evidence_ids=(evidence.evidence_id,), max_age_seconds=3600,
                )
                result = self.engine.verify([candidate], [evidence]).results[0]
                self.assertEqual(result.state, "UNVERIFIED")
                self.assertTrue(any(
                    issue.startswith("CLAIM_TEXT_STRUCTURED_VALUE_MISMATCH")
                    for issue in result.issues
                ))


    def test_market_change_direction_must_match_signed_evidence(self):
        cases = (
            (5.0, "ABC 24h change is down 5%", "UNVERIFIED"),
            (-5.0, "ABC 24h change is down 5%", "VERIFIED"),
            (-5.0, "ABC 24h change is up 5%", "UNVERIFIED"),
            (5.0, "ABC 24h change is +5% down", "UNVERIFIED"),
            (5.0, "ABC 24h change is up 5%", "VERIFIED"),
            (0.0, "ABC 24h change is flat at 0%", "VERIFIED"),
            (5.0, "ABC 24h change is unchanged at 5%", "UNVERIFIED"),
            (0.0, "ABC 24h change is up 0%", "UNVERIFIED"),
        )
        for value, text, expected_state in cases:
            with self.subTest(value=value, text=text):
                evidence = record(
                    value=value, claim_key="market.change_24h",
                    unit="percent", timeframe="24h",
                )
                candidate = Claim(
                    text=text, subject=evidence.subject, asset_id=evidence.asset_id,
                    claim_key="market.change_24h", value=value, unit="percent",
                    timeframe="24h", observed_at=iso(),
                    evidence_ids=(evidence.evidence_id,), max_age_seconds=3600,
                )
                result = self.engine.verify([candidate], [evidence]).results[0]
                self.assertEqual(result.state, expected_state)
                if expected_state == "UNVERIFIED":
                    self.assertTrue(any(
                        issue.startswith("CLAIM_TEXT_STRUCTURED_VALUE_MISMATCH")
                        for issue in result.issues
                    ))

    def test_negated_or_modal_market_claim_cannot_verify_as_fact(self):
        cases = (
            ("ABC price is not 100 USD", "market.price", 100.0, "USD", "spot"),
            ("ABC price may be 100 USD", "market.price", 100.0, "USD", "spot"),
            ("ABC 24h change could rise 5%", "market.change_24h", 5.0, "percent", "24h"),
            ("ABC 24h change is not down 5%", "market.change_24h", -5.0, "percent", "24h"),
        )
        for text, claim_key, value, unit, timeframe in cases:
            with self.subTest(text=text):
                evidence = record(
                    value=value, claim_key=claim_key, unit=unit, timeframe=timeframe,
                )
                candidate = Claim(
                    text=text, subject=evidence.subject, asset_id=evidence.asset_id,
                    claim_key=claim_key, value=value, unit=unit, timeframe=timeframe,
                    observed_at=iso(), evidence_ids=(evidence.evidence_id,),
                    max_age_seconds=3600,
                )
                result = self.engine.verify([candidate], [evidence]).results[0]
                self.assertEqual(result.state, "UNVERIFIED")
                self.assertTrue(any(
                    issue.startswith("CLAIM_TEXT_STRUCTURED_VALUE_MISMATCH")
                    for issue in result.issues
                ))


class ClaimRegistrySnapshotIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.engine = EvidenceVerificationEngine()

    def test_registry_v2_binds_hash_semantics_without_changing_evidence_identity(self):
        from dataclasses import replace
        from layer1.evidence_verification import Claim, ClaimRegistry, EvidenceRecord
        record = trusted_evidence_record(
            source_id="cms:source-1", source_family="binance", source_kind="PRIMARY",
            publisher="Binance", subject="coingecko:bitcoin", claim_key="announcement.title",
            value="BTC listing", published_at="2026-11-21T11:58:00Z",
            observed_at="2026-11-21T11:59:00Z", asset_id="coingecko:bitcoin",
            content_hash="a" * 64, lineage_id="cms:source-1",
        )
        original_id = record.evidence_id
        typed = replace(record, content_hash_kind="CANONICAL_NORMALIZED_PAYLOAD_SHA256")
        self.assertEqual(typed.evidence_id, original_id)
        payload = ClaimRegistry((), (typed,), (), ()).to_dict()
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(
            payload["evidence_records"][0]["content_hash_kind"],
            "CANONICAL_NORMALIZED_PAYLOAD_SHA256",
        )

    def test_evidence_record_rejects_unknown_content_hash_kind(self):
        from dataclasses import replace
        from layer1.evidence_verification import EvidenceRecord
        record = trusted_evidence_record(
            source_id="source-1", source_family="provider", source_kind="MARKET",
            publisher="Provider", subject="coingecko:bitcoin", claim_key="market.price",
            value=1.0, published_at="2026-11-21T11:58:00Z",
            observed_at="2026-11-21T11:59:00Z", content_hash="b" * 64,
        )
        with self.assertRaisesRegex(ValueError, "content_hash_kind"):
            replace(record, content_hash_kind="RAW_BYTES_BUT_UNVERIFIED").validate()

    def test_evidence_record_rejects_hash_semantics_without_a_content_hash(self):
        from dataclasses import replace
        from layer1.evidence_verification import EvidenceRecord
        record = trusted_evidence_record(
            source_id="source-no-hash", source_family="provider", source_kind="ONCHAIN",
            publisher="Provider", subject="coingecko:bitcoin", claim_key="onchain.transaction_hash",
            value="0x" + "1" * 64, published_at="2026-11-21T11:58:00Z",
            observed_at="2026-11-21T11:59:00Z",
        )
        typed_without_digest = replace(
            record, content_hash_kind="CANONICAL_PARSED_PROVIDER_JSON_SHA256",
        )
        with self.assertRaisesRegex(ValueError, "requires content_hash"):
            typed_without_digest.validate()

    def test_sqlite_claim_registry_loader_rejects_tampered_snapshot(self):
        import sqlite3
        from layer1.evidence_verification import ClaimRegistry, ClaimRegistryStore
        connection = sqlite3.connect(":memory:")
        try:
            store = ClaimRegistryStore(connection)
            registry = ClaimRegistry(
                claims=(), evidence_records=(), results=(),
                unresolved_issues=({"issue": "immutable-registry"},),
            )
            verification_id = store.save(registry)
            self.assertEqual(store.load_latest()["verification_id"], verification_id)
            tampered = json.dumps({
                "claims": [], "evidence_records": [], "results": [],
                "unresolved_issues": [{"issue": "tampered-registry"}],
            }, sort_keys=True, separators=(",", ":"))
            connection.execute(
                "UPDATE layer1_claim_verification_runs SET payload_json=? WHERE verification_id=?",
                (tampered, verification_id),
            )
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                store.load_latest()
        finally:
            connection.close()

    def test_postgres_claim_registry_loader_verifies_utf8_snapshot_digest(self):
        from layer1.publication_postgres import PostgresPublicationStore
        payload = {
            "claims": [], "evidence_records": [], "results": [],
            "unresolved_issues": [{"issue": "café"}],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        verification_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        row = {"verification_id": verification_id, "payload_json": payload}

        class FakeConnection:
            def execute(self, query):
                return self
            def fetchone(self):
                return row

        store = object.__new__(PostgresPublicationStore)
        store.conn = FakeConnection()
        loaded = store.load_latest_claim_registry()
        self.assertEqual(loaded["verification_id"], verification_id)
        self.assertEqual(loaded["payload"], payload)
        row["payload_json"] = {
            "claims": [], "evidence_records": [], "results": [],
            "unresolved_issues": [{"issue": "tampered"}],
        }
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            store.load_latest_claim_registry()

    def test_postgres_claim_registry_loader_fetches_exact_verification_id(self):
        from layer1.publication_postgres import PostgresPublicationStore
        payload = {
            "claims": [], "evidence_records": [], "results": [],
            "unresolved_issues": [{"issue": "exact-id"}],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        verification_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        row = {"verification_id": verification_id, "payload_json": payload}

        class FakeConnection:
            def __init__(self):
                self.query = None
                self.params = None
            def execute(self, query, params):
                self.query, self.params = query, params
                return self
            def fetchone(self):
                return row

        store = object.__new__(PostgresPublicationStore)
        store.conn = FakeConnection()
        loaded = store.load_claim_registry_by_verification_id(verification_id)
        self.assertEqual(loaded, {"verification_id": verification_id, "payload": payload})
        self.assertEqual(store.conn.params, (verification_id,))
        with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
            store.load_claim_registry_by_verification_id("not-a-digest")


    def test_unissued_caller_record_cannot_manufacture_primary_acceptance(self):
        forged = EvidenceRecord(
            source_id="forged-primary", source_family="invented-primary-family",
            source_kind="SECONDARY", publisher="Unapproved Publisher",
            subject="coingecko:abc", claim_key="market.price", value=100.0,
            published_at=iso(-120), observed_at=iso(), asset_id="coingecko:abc",
            source_url="https://attacker.example/price", is_primary=True,
            source_status="ACCEPTED",
        )
        candidate = claim(forged, unit=None, timeframe=None)
        registry = self.engine.verify((candidate,), (forged,))
        result = registry.results[0]
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertEqual(result.supporting_evidence_ids, ())
        self.assertEqual(result.independent_source_count, 0)
        self.assertIn("EVIDENCE_PROVENANCE_UNTRUSTED", result.issues)

    def test_caller_supplied_authority_metadata_does_not_replace_adapter_proof(self):
        forged = EvidenceRecord(
            source_id="forged-coingecko-record", source_family="coingecko_market",
            source_kind="MARKET", publisher="CoinGecko market data",
            subject="coingecko:abc", claim_key="market.price", value=100.0,
            published_at=iso(-30), observed_at=iso(), asset_id="coingecko:abc",
            unit="USD", timeframe="spot",
            source_url="https://api.coingecko.com/api/v3/coins/markets",
            is_primary=False, source_status="ACCEPTED",
            source_authority_id="coingecko_market",
            independence_group="coingecko_market",
        )
        registry = self.engine.verify(
            (claim(forged),), (forged,),
        )
        self.assertEqual(registry.results[0].state, "UNVERIFIED")
        self.assertEqual(registry.results[0].supporting_evidence_ids, ())

    def test_source_family_aliases_cannot_make_same_publisher_independent(self):
        observed = iso()
        first = trusted_evidence_record(
            source_id="publisher-copy-a", source_family="provider-alias-a",
            source_kind="SECONDARY", publisher="Same Publisher",
            subject="coingecko:abc", claim_key="market.price", value=100.0,
            published_at=iso(-120), observed_at=observed, asset_id="coingecko:abc",
            source_url="https://same-publisher.example/a", is_primary=False,
            source_status="ACCEPTED",
        )
        second = trusted_evidence_record(
            source_id="publisher-copy-b", source_family="provider-alias-b",
            source_kind="SECONDARY", publisher="Same Publisher",
            subject="coingecko:abc", claim_key="market.price", value=100.0,
            published_at=iso(-120), observed_at=observed, asset_id="coingecko:abc",
            source_url="https://same-publisher.example/b", is_primary=False,
            source_status="ACCEPTED",
        )
        candidate = claim(
            first, unit=None, timeframe=None,
            evidence_ids=(first.evidence_id, second.evidence_id),
        )
        registry = self.engine.verify((candidate,), (first, second))
        self.assertNotEqual(registry.results[0].state, "CORROBORATED")
        self.assertEqual(registry.results[0].independent_source_count, 1)

    def test_market_adapter_rejects_unknown_provider_endpoint_as_authority(self):
        unknown = MarketObservation(
            asset_id="coingecko:abc", provider="binance_spot",
            endpoint="https://attacker.example/api/v3/ticker/24hr",
            observed_at=iso(), price=100.0, currency="USD",
            freshness_by_field={"price": "FRESH"},
        )
        evidence = self.engine.evidence_from_market_observation(unknown)
        self.assertEqual(evidence[0].source_status, "UNVERIFIED")
        self.assertFalse(evidence[0].is_primary)

    def test_unknown_trend_source_cannot_claim_social_authority(self):
        signal = TrendSignal(
            topic="ABC", source="caller_invented_social",
            observed_at=iso(), asset_ids=("coingecko:abc",),
            source_item_id="fake-item",
        )
        evidence = self.engine.evidence_from_trend_signal(signal)
        self.assertTrue(all(item.source_status == "UNVERIFIED" for item in evidence))
        self.assertTrue(all(not item.is_primary for item in evidence))

    def test_approved_market_provider_endpoints_bind_canonical_authority_groups(self):
        observed = iso()
        published = iso(-30)
        binance = MarketObservation(
            asset_id="coingecko:abc", provider="binance_spot",
            endpoint="https://data-api.binance.vision/api/v3/ticker/24hr",
            observed_at=observed, published_at=published, source_timestamp=published,
            price=100.0, currency="USDT", data_hash="1" * 64,
            field_availability={"price": "AVAILABLE"},
            freshness_by_field={"price": "FRESH"},
        )
        coingecko = MarketObservation(
            asset_id="coingecko:abc", provider="coingecko_markets",
            endpoint="https://api.coingecko.com/api/v3/coins/markets",
            observed_at=observed, published_at=published, source_timestamp=published,
            price=100.0, currency="USDT", data_hash="2" * 64,
            field_availability={"price": "AVAILABLE"},
            freshness_by_field={"price": "FRESH"},
        )
        records = (
            self.engine.evidence_from_market_observation(binance)
            + self.engine.evidence_from_market_observation(coingecko)
        )
        self.assertEqual({item.source_family for item in records}, {
            "binance_spot_market", "coingecko_market",
        })
        self.assertTrue(all(item.source_status == "ACCEPTED" for item in records))
        self.assertTrue(all(not item.is_primary for item in records))
        claims = self.engine._source_assertion_claims(records)
        registry = self.engine.verify(claims, records)
        self.assertEqual(registry.results[0].state, "CORROBORATED")
        self.assertEqual(registry.results[0].independent_source_count, 2)

    def test_mutating_an_issued_evidence_record_invalidates_its_provenance_proof(self):
        evidence = trusted_evidence_record(
            source_id="tamper-proof", source_family="trusted-fixture",
            source_kind="PRIMARY", publisher="Trusted Fixture",
            subject="coingecko:abc", claim_key="market.price", value=100.0,
            published_at=iso(-30), observed_at=iso(), asset_id="coingecko:abc",
            unit="USD", timeframe="spot", is_primary=True, source_status="ACCEPTED",
        )
        object.__setattr__(evidence, "publisher", "Attacker")
        candidate = claim(evidence)
        registry = self.engine.verify((candidate,), (evidence,))
        self.assertEqual(registry.results[0].state, "UNVERIFIED")
        self.assertIn("EVIDENCE_PROVENANCE_UNTRUSTED", registry.results[0].issues)


    def test_binance_spot_evidence_accepts_only_endpoint_bound_approved_ingestion_receipt(self):
        from unittest.mock import patch
        from layer1.source_receipts import create_source_ingestion_receipt

        observed = iso()
        pair = {
            "symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT",
            "status": "TRADING", "isSpotTradingAllowed": True,
            "permissionSets": [["SPOT"]],
        }
        endpoint = "https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT"
        canonical_pair = {
            "symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT",
            "status": "TRADING", "isSpotTradingAllowed": True,
            "permissionSets": [["SPOT"]],
        }
        pair_hash = hashlib.sha256(json.dumps(
            canonical_pair, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        payload = {
            "authority_id": "binance_spot_exchange_info",
            "endpoint": endpoint,
            "server_time": int(datetime.fromisoformat(observed).timestamp() * 1000),
            "observed_at": observed,
            "pair": canonical_pair,
            "pair_sha256": pair_hash,
        }
        key = b"approved-spot-ingestion-key-material-32bytes"
        receipt = create_source_ingestion_receipt(
            payload, authority_id="binance_spot_exchange_info",
            key_id="spot-key-v1", signing_key=key,
        ).to_dict()
        receipt_bundle = {"ABCUSDT": {"payload": payload, "receipt": receipt}}
        env = {
            "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": key.hex(),
            "BINANCE_SPOT_INGESTION_KEY_ID": "spot-key-v1",
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "spot-key-v1",
        }
        with patch.dict(os.environ, env, clear=False):
            evidence = self.engine.evidence_from_binance_spot_pairs(
                "coingecko:abc", [pair], observed_at=observed,
                allowed_quote_assets=("USDT",), expected_base_asset="ABC",
                source_receipts=receipt_bundle,
            )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].source_status, "ACCEPTED")
        self.assertEqual(evidence[0].source_authority_id, "binance_spot_exchange_info")
        self.assertEqual(evidence[0].source_receipt_key_id, "spot-key-v1")
        self.assertFalse(evidence[0].is_primary)

    def test_binance_spot_receipt_rejects_tampered_pair_and_unapproved_key(self):
        from unittest.mock import patch
        from layer1.source_receipts import create_source_ingestion_receipt

        observed = iso()
        pair = {
            "symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT",
            "status": "TRADING", "isSpotTradingAllowed": True,
            "permissionSets": [["SPOT"]],
        }
        endpoint = "https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT"
        payload = {
            "authority_id": "binance_spot_exchange_info", "endpoint": endpoint,
            "server_time": int(datetime.fromisoformat(observed).timestamp() * 1000),
            "observed_at": observed, "pair": pair,
            "pair_sha256": hashlib.sha256(json.dumps(
                pair, sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest(),
        }
        key = b"approved-spot-ingestion-key-material-32bytes"
        receipt = create_source_ingestion_receipt(
            payload, authority_id="binance_spot_exchange_info",
            key_id="spot-key-v1", signing_key=key,
        ).to_dict()
        env = {
            "BINANCE_SPOT_INGESTION_HMAC_KEY_HEX": key.hex(),
            "BINANCE_SPOT_INGESTION_KEY_ID": "spot-key-v1",
            "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "",
        }
        with patch.dict(os.environ, env, clear=False):
            unapproved = self.engine.evidence_from_binance_spot_pairs(
                "coingecko:abc", [pair], observed_at=observed,
                expected_base_asset="ABC",
                source_receipts={"ABCUSDT": {"payload": payload, "receipt": receipt}},
            )
        self.assertEqual(unapproved[0].source_status, "UNVERIFIED")
        self.assertIsNone(unapproved[0].source_authority_id)
        changed_pair = {**pair, "permissionSets": [["SPOT", "MARGIN"]]}
        with patch.dict(os.environ, {**env, "BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS": "spot-key-v1"}, clear=False):
            tampered = self.engine.evidence_from_binance_spot_pairs(
                "coingecko:abc", [changed_pair], observed_at=observed,
                expected_base_asset="ABC",
                source_receipts={"ABCUSDT": {"payload": payload, "receipt": receipt}},
            )
        self.assertEqual(tampered[0].source_status, "UNVERIFIED")
        self.assertIsNone(tampered[0].source_authority_id)


if __name__ == "__main__":
    unittest.main()


class OnChainPersistedReceiptRestorationTests(unittest.TestCase):
    def test_persisted_onchain_evidence_without_signed_receipt_is_not_retrusted(self):
        from unittest.mock import patch
        import layer1.evidence_verification as evidence_module

        forged = EvidenceRecord(
            source_id="obs-forged-restore",
            source_family="alchemy",
            source_kind="ONCHAIN",
            publisher="alchemy",
            subject="coingecko:ethereum",
            claim_key="onchain.transaction_hash",
            value="0x" + "b" * 64,
            published_at=iso(-30),
            observed_at=iso(),
            asset_id="coingecko:ethereum",
            mapping_id="eth-mainnet-native-v1",
            timeframe="ethereum-mainnet",
            is_primary=True,
            source_status="ACCEPTED",
            status_value="FINALIZED",
            source_authority_id="onchain_receipt",
            independence_group="onchain:ethereum-mainnet:alchemy",
            source_receipt_key_id="test-key-v1",
        )
        with patch.object(
            evidence_module, "_TRUSTED_ONCHAIN_RECEIPT_KEY_IDS", frozenset({"test-key-v1"}),
        ):
            evidence_module._restore_evidence_record_proof(forged)
            self.assertIsNone(evidence_module._evidence_proof(forged))
            self.assertEqual(evidence_module._effective_evidence_status(forged), "UNVERIFIED")
            self.assertFalse(evidence_module._effective_evidence_primary(forged))

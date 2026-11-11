# Candidate Identity & Deduplication (Module 6)

## Hard gates

A candidate is built only for a canonical CoinGecko asset ID and retains the Module 3 Binance Spot eligibility decision. Market, event and trend evidence is validated for asset match and freshness. Missing or stale evidence is rejected/deferred with explicit reason codes; an announcement or trend signal cannot override eligibility.

## Candidate identity

Candidate identity is deterministic and source-aware without making provider IDs the queue key:

1. **Event-backed candidate:** `asset_id + event_cluster_ids`. A local event cluster is derived from the canonical asset, normalized event type/title and event day (`event_at` when available, otherwise `published_at`). Provider source IDs remain attached as evidence, but another provider reporting the same normalized asset/event does not create a second candidate. A materially different title/type/event day creates a new cluster.
2. **Trend-only candidate:** `asset_id + trend_cluster_ids`. Trend cluster IDs use normalized topic, canonical asset IDs and distinct content hashes. A syndicated copy with the same content hash adds provenance but does not create a new candidate; a new independent content hash can represent a material update.
3. **Market-only candidate:** `asset_id + validated market observation references`.

Eligibility and market/trend/event evidence remain attached to the candidate. Re-saving the same candidate ID updates its evidence references, so new corroborating sources are retained without duplicating the queue item.

The local event cluster ID is a grouping fingerprint, not a Binance/provider event ID. It uses exact normalized title/type/day matching; no fuzzy semantic matching is claimed. If source titles differ materially, the system keeps separate candidate identities rather than guessing they describe the same event.

## Research-priority boundary

Candidate state `READY_FOR_RESEARCH` means only that the candidate passed the discovery/eligibility evidence gates. It does not mean the post is approved or ready to publish. The publication gateway continues its own fresh eligibility and duplicate-publication protections.

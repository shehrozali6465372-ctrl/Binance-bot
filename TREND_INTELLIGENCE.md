# Trending Narrative Intelligence (Module 5)

## Runtime sources

- CoinGecko Trending observations.
- Market-derived gain/volume observations backed by the same validated CoinGecko market payloads used by Layer 1 market intelligence.
- Official Binance CMS announcements are ingested separately by Module 4 as event evidence. They are not fetched through the legacy undocumented BAPI and are not silently converted into attention signals.

The synthetic narrative provider is disabled and returns no data. The legacy topic-to-coin mapping is a display hint only; it never assigns canonical asset identity. Layer 1 accepts only explicit `coingecko:<id>` asset references from provider records.

## Normalization and clustering

1. Normalize topic names by case-folding and tokenizing alphanumeric terms (for example, `BTC_SURGE` and `btc surge` share a topic key).
2. Deduplicate repeated observations of the same provider item by normalized topic, source, item ID and canonical asset IDs, retaining the newest observation.
3. Cluster by `(normalized_topic, canonical_asset_ids)`. The asset set is part of the key, so the same topic cannot merge unrelated assets.
4. `source_count` counts distinct providers. `independent_source_count` counts distinct verified SHA-256 content hashes, so syndicated copies of the same content count once.
5. If content hashes are absent, independence is conservative: signals for the same normalized topic and asset are treated as one unknown content group, not independent corroboration.

Cluster IDs are based on normalized topic, canonical asset IDs and distinct content hashes—not provider IDs—so another provider reporting the same content does not create a duplicate trend candidate. A new independent content hash is a material cluster update. Clusters are persisted in `layer1_trend_clusters`; candidates retain their cluster IDs in `evidence_refs_json`. Each cluster is explicitly labeled `ATTENTION_ONLY_NOT_EVENT_PROOF`. Trends can prioritize research but cannot replace official event evidence, Module 3 canonical identity/Spot eligibility, or final publication revalidation.

## Confidence limits

- Trend rank and source counts are attention signals, not proof of a listing, partnership, token event or market-moving catalyst.
- Market-derived trend records share the market payload's content hash; they are not independent corroboration of that same market payload.
- No synthetic/demo fallback is used when providers fail. Missing or malformed evidence is rejected or reported unavailable.

# Market Analysis Engine (Module 8)

## Purpose

Produce reproducible market facts from validated provider observations while keeping provider-reported fields, independently calculated returns, and interpretation separate.

## Inputs and comparison rules

- Current and historical `MarketObservation` records.
- Historical return baselines must match canonical asset ID, provider, currency and a comparable timestamp.
- One-hour baselines must be within 15 minutes of the target timestamp; 24-hour baselines must be within 60 minutes.
- Benchmark observations must be a distinct asset and match provider and currency. Relative return is asset return minus benchmark return, expressed in percentage points.
- Cross-provider price conflicts require the same canonical asset and currency, fresh prices and observations within five minutes of the current quote.

## Calculations and quality controls

- Calculate 1h/24h returns only from timestamped stored observations. Untimestamped `sparkline_in_7d.price` arrays are explicitly excluded from return calculations.
- Preserve the provider-reported 24h percentage change as a separate fact; it is not substituted for an independently calculated return.
- `volume_24h / market_cap * 100` is named volume-to-market-cap ratio / turnover proxy, never relative volume.
- Flag history gaps at or above two hours and potential price outliers when an observation deviates more than 20% from the series median. Outliers are flagged for review, not silently removed.
- Missing baselines, benchmarks, fields and same-currency comparisons remain explicit unknowns. No missing value becomes zero.
- Market movement and announcement timing do not establish causation. The engine emits no causal hypotheses; interpretation belongs to later research with evidence.

## Persistence and runtime

`Layer1Store` retains market observations and an additive `layer1_market_analyses` table with the full analysis payload, quality flags and evidence hashes. The Layer 1 runtime analyzes each successfully normalized observation against persisted history and, when a sufficiently recent stored BTC benchmark exists, compares against that benchmark. It performs no extra provider request for Module 8.

When the repository has no timestamped baseline (the current common case), analysis is deliberately `PARTIAL`; return values remain null and the 7-day sparkline is not repurposed as hourly/daily history. No synthetic backfill or new provider has been added.

## Current limitations

- The existing runtime normally receives only a current CoinGecko markets observation per asset per cycle. Timestamped history accumulates only across successful prior cycles; it does not guarantee a full 1h/24h history.
- Benchmark comparison is opportunistic and uses only a stored, recent BTC observation from the same provider/currency. It is unavailable if BTC was not previously collected.
- Historical data retention/compaction and long-term analysis calibration remain future work; no external database schema was changed.

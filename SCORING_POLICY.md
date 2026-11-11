# Relevance Scoring Policy (Module 7)

## Implemented engine

`RelevanceScoringEngine` is deterministic, versioned and explainable. Current score version is `layer1-relevance-v1`. Current weights in code are:

- Event materiality: 0.30
- Source credibility: 0.25
- Freshness: 0.20
- Audience relevance: 0.15
- Novelty: 0.10

Each component must be explicitly supplied as a finite value from 0 to 100. A hard-gated candidate cannot be promoted by a score. Ranking is deterministic and the score never authorizes publication.

## Runtime behavior and limitation

The current runtime persists an explicit deferred score with missing component values rather than inventing values. In particular, audience relevance and novelty do not yet have approved, calibrated production definitions; event materiality/source credibility scales also need a reviewed baseline. Until those definitions and thresholds are approved and tested against a representative historical dataset, the runtime does not emit a positive weighted score or replace the existing candidate-selection behavior.

This is an intentional safety boundary, not a claim that Module 7's production ranking is complete. A candidate marked `READY_FOR_RESEARCH` has passed discovery/eligibility gates only. It is not scored as publication-ready and is not authorized to publish.

## Activation requirements

1. Define each component's scale, direction, evidence inputs and missing-value behavior.
2. Establish deterministic source-credibility and event-materiality mappings from documented evidence.
3. Define audience relevance using an approved audience profile and validated market/liquidity metrics.
4. Define novelty using persistent candidate/event history and material-update identity.
5. Backtest and review component distributions, correlations and rank stability; version any approved change.
6. Preserve component values, evidence references, score version and reason for every score/deferred decision.

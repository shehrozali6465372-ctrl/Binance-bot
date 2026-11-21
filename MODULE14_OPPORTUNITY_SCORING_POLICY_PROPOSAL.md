# Module 14 — Opportunity Scoring Policy Proposal

**Status:** PROPOSAL ONLY — NOT APPROVED FOR RUNTIME
**Research cut-off:** 2026-11-22
**Scope:** Binance Square Write-to-Earn Agent, Module 14 — Opportunity Evaluation Engine
**Activation:** PROHIBITED until evidence instrumentation, historical calibration, owner sign-off, and separate runtime acceptance are complete.

> This document proposes a research and validation framework. It intentionally defines no numeric weights, no score cut-offs, no per-factor floors, and no production factor values. Nothing in this document changes the current fail-closed runtime behaviour.

## 1. Executive decision

The locked architecture already specifies six dimensions: **evidence strength, timeliness, materiality, audience usefulness, novelty, and risk**. The existing implementation names the final factor `risk_control`. This proposal preserves those six keys; it does not add parallel factors or borrow the Module 7 relevance weights.

Module 14 should answer one narrow question:

> Given the exact asset, point-in-time evidence, event state, previous publication history, and documented risks, is this research sufficiently substantiated, current, material, useful, genuinely new, and responsibly bounded to justify creating an editorial brief?

It must not answer whether an asset is a good investment, predict a return, issue a trade signal, or authorize publication. `PROCEED` may only authorize the next editorial stage. Publication remains subject to all later content, visual, authorization, quota, and publisher controls.

**Critical design principle:** scoring is subordinate to hard gates. A high aggregate score must never rescue an ineligible asset, stale or incomplete critical research, contradicted facts, unresolved critical claims, unsupported causality, a withdrawn/disputed event, or a platform-policy violation.

## 2. Current verified implementation state

Read-only source inspection of the continuation worktree at commit `3c093688daacd3d99f679830c99eba1919b826a5` found:

- `layer1/opportunity.py` defines exactly six factors: `evidence_strength`, `timeliness`, `materiality`, `audience_usefulness`, `novelty`, and `risk_control`.
- `OpportunityPolicy` currently requires a complete weight map, finite non-negative weights summing to 1, two ordered thresholds, and a positive eligibility freshness bound.
- The engine already applies several non-compensatory decisions before scoring: Binance eligibility, eligibility freshness, research completeness, event state, contradictions, unresolved critical claims, unsupported causal framing, and duplicate angle without a material update.
- `main.py` currently passes `factors=None` and `policy=None`; it also passes `unsupported_causal_framing=False` and `materially_new=False`. The duplicate-angle input is currently derived from a publication cooldown rather than semantic comparison.
- Therefore the scheduled runtime deliberately persists `DEFER` with `APPROVED_OPPORTUNITY_SCORING_POLICY_NOT_CONFIGURED`. This is the correct safe state until real factor providers and an approved policy exist.
- `SCORING_POLICY.md` documents Module 7, not Module 14. Its weights must not be reused here.

## 3. Decision architecture: hard gates before soft scoring

The following are proposed gate groups. They are not a licence to weaken the current engine; they are a checklist for completing and validating its existing contract.

### 3.1 Reject / block conditions

A score must not override:

1. **Asset identity and listing eligibility:** canonical asset mapping is ambiguous, wrong, or mismatched; Binance Spot listing eligibility cannot be verified against the current official exchange symbol state; or the pair is not in an eligible trading state.
2. **Evidence integrity:** source provenance is fabricated or invalid, critical claims are contradicted, a material fact has no claim-level supporting evidence, or a required identity/network mapping is unverified.
3. **Event integrity:** a critical event is withdrawn or disputed, or the research package is in a rejected state.
4. **Unsupported claims:** a causal assertion exceeds the underlying evidence, critical unknowns remain, or the proposed editorial angle requires presenting speculation as fact.
5. **Policy / abuse:** the proposed content would violate applicable Binance Square rules, including misinformation, market manipulation, misleading promotion, or prohibited repetitive/bot-driven spam. A platform-policy violation is not a small risk deduction.

Use the engine's explicit `REJECT`, `RESEARCH_MORE`, and `DEFER` states according to the reason. Do not collapse all failures into a score of zero.

### 3.2 Defer / obtain more evidence

Defer where required data are missing, stale, outside the calibrated field-specific freshness window, or not sufficiently attributable. Examples include unavailable order-book depth for a liquidity-sensitive claim, unclear event revision linkage, unresolved on-chain token mapping, or unknown source independence.

**Missing is not zero.** Missing, stale, conflicting, or unverified fields must never be imputed to a neutral score. They produce an explicit unavailable state and, where decision-critical, `DEFER` or `RESEARCH_MORE`.

### 3.3 Soft scoring only after gates pass

Only candidates which pass the hard gates and have all required factor inputs should receive six factor evaluations. Scores must be deterministic from a frozen point-in-time evidence snapshot and policy version. LLM output must not supply or override numeric factor values, weights, thresholds, gate results, or source credibility.

## 4. Six-factor definitions and evidence rubric

The descriptions below define what each factor should measure. They do **not** assign weights or numeric values. During calibration, each factor should receive explicit qualitative anchor examples and only later be mapped to the engine's numeric range.

### 4.1 Evidence strength — `evidence_strength`

**Question:** How well is the specific opportunity thesis supported by relevant, attributable, asset-correct evidence?

Evaluate:

- **Source authority for the claim:** primary issuer / exchange / regulator / protocol documentation versus reputable secondary reporting versus commentary or social attention. Authority is claim-specific: an exchange is authoritative for its own listing status, not necessarily for an independent security assessment.
- **Claim-to-source fit:** does each material claim point to the exact source record, field, time period, and asset? A source existing in the package is not proof that it supports every claim.
- **Verification state:** use claim-level `VERIFIED` / `CORROBORATED` outcomes and accepted evidence IDs. Qualified inference, hypothesis, unknown, and contradicted records must remain distinct.
- **Independence:** corroboration should be measured by genuinely independent source families / origins. Syndicated articles, copied press releases, common wire copy, and multiple reposts of one announcement are not independent confirmations.
- **Identity and lineage:** exact canonical asset, contract / network / mapping, source item ID, content hash, publication/update timestamp, and revision lineage where available.
- **Completeness:** whether the evidence supports the scope and materiality asserted, rather than a narrow fact being stretched to a broad claim.

**Do not count:** the number of URLs alone, social engagement, trend ranks, LLM confidence, repeated copies of the same announcement, or an on-chain transfer as proof of a named wallet's real-world identity.

**Existing inputs:** `EvidenceRecord`, `Claim`, `ClaimRegistry`, claim verification results, `ResearchPackage.verified_facts`, `disputed_claims`, `unknown_claims`, source coverage and evidence IDs.

**Known limitation:** the research package's source-kind coverage is not proof of claim-level support or source independence. A source-dependency graph and explicit per-factor provenance snapshot are required before production scoring.

### 4.2 Timeliness — `timeliness`

**Question:** Is the evidence still current and is the information still useful at this exact decision time?

Evaluate:

- Distinguish event time, publication time, source update time, provider source timestamp, local observation time, and decision cutoff.
- Apply freshness by source, field, event class, provider cadence, and intended use. A single universal age limit is not defensible for every data field.
- Identify event lifecycle: upcoming, developing, active, resolved, stale, withdrawn, or disputed. A resolved event may remain educationally useful but should not be described as breaking/current.
- Compare when the information became public with the market's observed reaction. A newly ingested item is not necessarily newly known to the market; earlier price/volume movement can signal diffusion, leakage, or unrelated factors, and should be reported as uncertainty rather than proof.
- Use consistent measurement windows. Binance `ticker/24hr` is a rolling 24-hour statistic, not an aligned UTC-day event window. Event-study windows must use explicitly timestamped bars and a declared pre/post interval.

**Do not count:** ingestion time as publication time, current cache time as source update time, or a fresh data fetch as evidence that the underlying event is new.

**Existing inputs:** `MarketObservation.observed_at`, `source_timestamp`, `published_at`, `freshness_by_field`; announcement `published_at`, `updated_at`, `event_at`; research cutoff; event lifecycle; on-chain `block_time` and `observed_at`.

**Known limitation:** policy needs calibrated freshness distributions for each provider/field/use case. Current hard eligibility age is not a substitute for factor-specific freshness.

### 4.3 Materiality — `materiality`

**Question:** Does the verified development materially change the asset's operation, economic position, market access, risk, or user-relevant understanding?

Evaluate the actual scope and mechanism, not headline drama:

- **Asset / market access:** official listing, delisting, pair status change, market suspension, trading or withdrawal restrictions.
- **Protocol / technical:** confirmed upgrade, exploit, outage, vulnerability remediation, chain halt, governance execution, or material integration.
- **Token economics:** verified issuance, burn, supply, unlock / vesting, treasury, fee or utility changes, including who is affected and when.
- **Regulatory / institutional:** binding decision, official enforcement, formal approval, or documented institutional integration; distinguish a final action from a proposal, rumour, filing, or comment.
- **Market structure:** objectively measured liquidity, spread, depth, volatility, and benchmark-relative movement where these help quantify market impact.
- **Scope and persistence:** affected users, assets, networks, venues, amount / share of supply where verifiable, duration, reversibility, and severity.

Market reaction is corroborating context, not a causal verdict. Where used, compare returns and volume with the asset's own historical baseline and an appropriate benchmark; inspect spread and available depth as well as headline 24-hour volume. A sharp price or volume spike by itself is not evidence that a catalyst is genuine, beneficial, sustainable, or caused the move.

**Do not bias toward positive news.** A verified delisting, exploit, outage, or negative regulatory action can be highly material and worth explaining. The factor measures significance, not bullishness.

**Existing inputs:** official `AnnouncementEvidence`, event lifecycle / event graph, verified claims, `MarketObservation`, `MarketAnalysisResult` (returns, relative benchmark return, turnover ratio, quality flags), and exact-mapping on-chain summaries.

**Known limitation:** market model persists selected price/volume/cap fields and derived returns, but does not yet establish a complete persisted order-book depth / bid-ask spread feature set or robust event-specific baselines.

### 4.4 Audience usefulness — `audience_usefulness`

**Question:** Does this research answer a real Binance Square reader question with enough context to be worth publishing?

Evaluate whether the verified package can clearly explain:

- What exactly happened, and what is confirmed versus unconfirmed?
- Why this matters to the asset, its users, holders, builders, or market participants.
- Who or what is affected, and what is outside the evidence scope?
- What changed compared with the previous known state?
- What risks, caveats, alternative explanations, or next verification points should a reader understand?

Reward precise explanation, decision-useful context, educational value, clear chronology, and traceable implications. Avoid rewarding generic price commentary, hype, empty summaries, or engagement forecasts.

**Do not count:** trend rank, likes, follower counts, viral reach, or search interest as proof of truth or usefulness. Attention may help choose what to investigate, but cannot upgrade claim verification.

**Existing inputs:** research question, verified facts, qualified inferences, event states, claim-level evidence, market-analysis facts / hypotheses / unknowns, and editorial strategy requirements.

**Known limitation:** current scheduled runtime does not have a calibrated audience utility rubric or structured reader-question assessment. Any qualitative annotation should be reviewed and recorded separately from factual evidence.

### 4.5 Novelty — `novelty`

**Question:** Is there genuinely new information or a materially changed understanding compared with what this system has already covered?

Evaluate:

- Exact canonical asset, event identity, event revision, and prior editorial brief / draft / post history.
- Whether new source material adds a material fact, changes verified status, changes event lifecycle, corrects a previous error, or adds a new affected scope.
- Semantic angle overlap, not just exact-title or hash equality.
- Time since last publication only as context. A cooldown is a safety heuristic, not a novelty proof.
- Whether the proposed angle answers a distinct reader question rather than paraphrasing the same update.

A new timestamp, refreshed market quote, newly scraped copy, or translated/rephrased headline does not automatically make an item novel. A correction or material update can be novel even when it concerns an old event.

**Existing inputs:** event IDs / revisions / lifecycle transitions, source IDs and hashes, publication history, research package versions, editorial brief / draft history and asset identity.

**Known limitation:** current `duplicate_angle` is derived from a publication cooldown and `materially_new` is hardcoded false in scheduled runtime. A bounded semantic duplicate detector and structured material-delta evidence are required before this factor can be trusted.

### 4.6 Risk control — `risk_control`

**Question:** Are material risks identified, evidenced, transparently bounded, and safe to communicate to readers?

**Direction is important:** a high `risk_control` value should mean that risks are well identified and responsibly handled. It must **not** mean that the token is safe, low-risk as an investment, or likely to rise.

Evaluate:

- **Market integrity:** thin liquidity, wide spread, shallow order book, extreme volatility, concentrated activity, coordinated promotion, suspicious volume / price dislocation, and pump-and-dump red flags.
- **Evidence risk:** unresolved identity, stale sources, unverified attribution, conflicting sources, incomplete mappings, uncertain source lineage, and overstated causal claims.
- **On-chain interpretation:** network / token mapping, finality, reorg state, bridge / wrapped-asset duplication, exchange / smart-contract address context, and the distinction between a transfer and a buy/sell or intent inference.
- **Communication / platform risk:** misleading financial claims, fake certainty, manipulated charts, undisclosed promotion, repeated spam-like content, prohibited direct financial advice, and unsupported predictions.
- **Operational / legal context:** relevant security incident, regulatory uncertainty, sponsorship / conflicts, source permission, and copyright / image provenance.
- **Disclosure quality:** whether limitations, missing data, alternative explanations, event uncertainty, and non-causal interpretation are stated clearly.

Hard platform prohibitions remain gates; they must not be averaged into a score. Risk scoring only applies to residual risks that can be responsibly disclosed and bounded.

**Existing inputs:** content safety findings, event and claim states, evidence verification, market liquidity / volatility inputs where available, on-chain mapping and validation / finality fields, publication history, and platform rules.

**Known limitation:** current `risk_control` has no production factor provider. Spread/depth, wallet/entity attribution confidence, concentration, promotion disclosure, and a unified risk register are not yet available as complete typed decision inputs.

## 5. Cross-factor controls: prevent double-counting and false confidence

| Interaction | Required policy treatment |
|---|---|
| Evidence strength vs timeliness | Source authority / claim support and data age are separate dimensions. A reputable but stale source is not fresh; a fresh but unverified post is not strong evidence. |
| Multiple articles vs independent evidence | Collapse syndication / shared-origin copies into one lineage group. Do not award independent corroboration for copied text. |
| Trend signals vs evidence | Existing `TrendCluster.confidence_limit` is `ATTENTION_ONLY_NOT_EVENT_PROOF`. Trend clusters can help discovery / audience context only; never count them as proof or claim corroboration. |
| Price / volume vs materiality | Treat price and volume as observed market reaction. Do not infer causality from co-movement or count the same return once as materiality and again as timeliness. |
| Novelty vs source count | Novelty depends on the delta from the system's prior coverage, not the number of new URLs or repeated copies. |
| Risk vs negative sentiment | Risk control is about whether risks are known and handled, not whether the headline is negative or positive. Do not punish responsible reporting of a negative but verified event. |
| On-chain activity vs intent | A transfer is a transfer. Without corroborated attribution and transaction context, do not call it a whale buy, sell, accumulation, or a named entity's activity. |
| Audience usefulness vs popularity | Reader utility is a content-quality judgement; engagement / trend rank is not a substitute for truth or usefulness. |

The engine's current single weighted sum is compensatory: a very high value in one dimension can mathematically offset a weak value in another. Before activation, calibration must test whether a simple weighted sum is acceptable. If evidence strength or risk control need non-compensatory minimum floors, those floors must be defined and validated from adjudicated historical examples—or the relevant failure modes must remain hard gates. Do not add arbitrary floors to make sample candidates pass.

## 6. Source-to-factor map

| Existing typed source / record | Legitimate use | Not legitimate evidence for |
|---|---|---|
| `EvidenceRecord` + `ClaimRegistry` | source lineage, claim support / contradiction, claim identity, timestamps, primary flag | blanket truth from source count alone |
| `ResearchPackage` | verified facts, inferences, disputed / unknown claims, cutoff, gaps | claim-level support based only on source-kind coverage |
| `AnnouncementEvidence` + event lifecycle | official event content, published / updated / event time, revision state | assuming a CMS fingerprint is a stable provider article ID |
| `MarketObservation` | field-provenanced price, volume, cap, history and freshness | causal explanation, complete liquidity assessment without order book |
| `MarketAnalysisResult` | return windows, benchmark-relative performance, turnover context, hypotheses / unknowns | price prediction or attribution to a catalyst without independent analysis |
| `TrendSignal` / `TrendCluster` | attention / discovery context, observed trend and source lineage | event proof, claim verification, independent confirmation when sources are dependent |
| `OnChainObservation` + validation | exact mapping, network, block / tx identity, block time, finality | named wallet attribution, buy/sell intent, cross-network aggregate amount |
| `TransferAggregationResult` | per-mapping / per-network transfer counts, threshold state, unique endpoint counts and rejections | summing bridged / wrapped amounts across networks or labeling all transfers as exchange flows |
| publication / brief / draft history | duplicate angle, material delta, past reader-question coverage | novelty derived only from cooldown |

Every calculated feature must retain: canonical asset ID; event / package ID; source/evidence IDs; exact field and measurement window; provider and source timestamps; observation cutoff; transformation / baseline version; missingness / quality flags; and factor-rubric version. The immutable decision snapshot should eventually bind this provenance, not only the final six numbers.

## 7. Data required before a production factor provider can be built

The current repository does not demonstrate all the following. Treat them as implementation/data gaps, not as values to guess:

1. A point-in-time historical corpus of accepted claims, source IDs, dependency groups, event revisions, market observations, decisions, and publication history.
2. Structured source-dependency / syndication grouping so repeated reports do not masquerade as independent confirmation.
3. Persisted order-book spread and depth observations (plus timestamp / sampling window) for material liquidity-sensitive claims.
4. Asset-specific and event-category-specific market baselines, benchmark selection, and explicit event windows.
5. A verified semantic material-delta / duplicate-angle record tied to exact prior briefs, drafts, and publications.
6. Complete risk inputs for market manipulation indicators, verified project/security events, on-chain mapping/finality, and attribution quality.
7. An immutable factor provenance structure: factor value, factor subfeatures, source refs, rule IDs, missing fields, window, code/rubric version, and reviewer override trail.
8. Independent labels for whether a historical research package was editorial-worthy at its original cutoff, not merely whether it later received high engagement or its token price rose.

Until these inputs exist, a partially populated score must not be used to unlock `PROCEED`.

## 8. Calibration and historical backtesting plan

### Phase A — Build a point-in-time evaluation dataset

- Reconstruct only information that was actually available at each historical decision cutoff. Prevent look-ahead leakage from later announcement edits, later prices, later on-chain attribution, or later event outcomes.
- Include positive, neutral, negative, corrected, withdrawn, disputed, low-liquidity, high-volatility, maintenance, exploit, listing / delisting, governance, tokenomics, regulatory, and market-structure cases.
- Preserve assets that later delisted / failed where historical Binance eligibility can be reconstructed. Do not sample only surviving or successful projects.
- Group splits by event and asset, and use chronological walk-forward / out-of-time validation. Random row splits alone are not acceptable where the same event / asset can leak across partitions.
- Label outcomes using at least two independent reviewers and a documented adjudication protocol. Labels must judge editorial suitability from the information available at the time—not later market return, post virality, or whether the thesis was profitable.

### Phase B — Establish factor rubrics and inter-reviewer consistency

- Create anchor examples at each qualitative factor level, including borderline and adversarial cases.
- Measure reviewer agreement and investigate factors that cannot be judged consistently.
- Record disagreements and overrides; do not quietly average subjective assessments.
- Test whether six factors are empirically distinguishable or whether their definitions overlap. Remove duplicated subfeatures rather than rewarding the same phenomenon several times.

### Phase C — Fit and compare policy candidates

- Compare transparent baseline rules with constrained candidate models. The current engine expects non-negative weights summing to 1, so any fitted candidate must respect that contract or be treated as a separately reviewed architecture change.
- Fit weights only on training data after labels and features have been quality-checked. Do not copy weights from Module 7, academic paper coefficients, another exchange, or another asset universe.
- Choose PROCEED / DEFER boundaries using explicit costs of false PROCEED versus missed editorial opportunities. False PROCEED must be treated as materially more costly when it allows weakly sourced or manipulative claims into content creation.
- Evaluate whether non-compensatory evidence / risk floors are required. Test policy sensitivity to small changes in weights, thresholds, baselines, and reviewer labels.
- Compare performance by event type, liquidity band, asset size, market regime, provider/source family, and time period. Aggregate accuracy can hide dangerous subgroup failures.

### Phase D — Out-of-time evaluation and acceptance criteria

Report, at minimum:

- precision / positive predictive value of PROCEED;
- recall of independently adjudicated editorial-worthy cases;
- false-PROCEED rate and its confidence interval;
- RESEARCH_MORE / DEFER / REJECT distribution and reason codes;
- performance by event category, liquidity and market regime;
- factor-level calibration / reliability where probabilistic meaning is claimed;
- sensitivity, ablation and correlated-feature diagnostics;
- rate of missing / stale / unverified factor inputs;
- reviewer agreement and override rate;
- drift after deployment.

Use chronological out-of-time evaluation, confidence intervals / resampling where suitable, and a frozen holdout not used for factor or threshold fitting. Engagement, impressions, and readership may be monitored as secondary editorial outcomes, but must not be used as ground-truth labels for factual evidence or market merit.

### Phase E — Shadow mode and governance

Only after separate owner approval of the calibrated policy:

1. Version and sign the exact factor rubric, source allowlist / field contracts, weights, thresholds, floors, and hard gates.
2. Run in shadow mode against live, read-only evidence; persist proposed decisions but do not create drafts or publish from them.
3. Compare shadow results with independent human review and monitor false-PROCEED examples.
4. Require a separate explicit approval before wiring the policy into scheduled runtime or enabling the positive editorial path.
5. Maintain rollback to the existing fail-closed state; version changes require re-validation and immutable decision lineage.

## 9. Methodological references and limits

The following research informs the design; it does **not** supply Module 14 weights or decision cut-offs.

- **Binance Square Community Guidelines** — official platform policy, page updated 2026-11-06. It addresses false / unverified statements, misleading promotions, market manipulation, spam and repetitive / automated posting; it also encourages valid, current information and clear, substantive explanations. These are platform-policy gates and quality constraints, not scoring coefficients.
  https://www.binance.com/en/support/faq/detail/ecb50ef2012f40b2a2c4f72eaa5b569f
- **Binance Spot API — General endpoints / exchange information** — current symbol status and trading rules are authoritative for Binance exchange eligibility; eligibility belongs in a hard gate.
  https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-endpoints
- **Binance Spot API — Market data endpoints** — 24-hour ticker statistics, klines, order book and book ticker provide different observation types and windows. A rolling 24-hour ticker must not be mistaken for an aligned daily or event window.
  https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
- **CoinGecko API — Coin Markets** — provides market cap, volume, price-change fields and `last_updated`; field provenance and provider update time should be retained.
  https://docs.coingecko.com/reference/coins-markets
- **CFTC — Beware Virtual Currency Pump-and-Dump Schemes** — warns about thinly traded tokens, social-media tips, sudden price spikes, and false urgency. Supports manipulation / liquidity risk checks; it is not a token-specific risk verdict.
  https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/beware_virtual_currency_pump_dump.html
- **FATF — Virtual Assets: Red Flag Indicators of Money Laundering and Terrorist Financing** — supports scrutiny of unusual transaction patterns, size / frequency and suspicious activity; blockchain address visibility does not on its own establish the identity of the person behind an address.
  https://www.fatf-gafi.org/en/publications/methodsandtrends/documents/virtual-assets-red-flag-indicators.html
- **FATF — Updated Guidance for a Risk-Based Approach to Virtual Assets and VASPs** — additional background on virtual-asset risks and attribution limitations.
  https://www.fatf-gafi.org/content/dam/fatf-gafi/guidance/Updated-Guidance-VA-VASP.pdf
- **BIS — Regulating cryptocurrencies: assessing market reactions** — event-study research illustrates that reactions differ by event type and that market information may move before a public event timestamp. It informs event-window design, not our factor weights.
  https://www.bis.org/publications/regulating-cryptocurrencies-assessing-market-reactions
- **Economics Letters (2025), “Market reactions to Crypto-Specific announcements…”** — empirical announcement research examines return, volume / volatility and wallet-activity responses across crypto announcements. Different response variables and event categories reinforce that one market metric should not stand in for materiality.
  https://doi.org/10.1016/j.econlet.2025.112305
- **Journal of Behavioral and Experimental Finance (2026), “Tuning into the news: Sentiment-driven high-frequency movements in cryptocurrency markets”** — recent high-frequency research reports category-dependent reactions; sentiment-driven price movement should not be interpreted as verified fundamentals.
  https://doi.org/10.1016/j.jbef.2026.101183
- **Finance Research Letters (2026)** — event-study research also reports heterogeneous reactions by event class, further arguing against a one-size-fits-all market-response score.
  https://doi.org/10.1016/j.frl.2026.110401
- **Federal Reserve (2026), Supervisory Guidance on Model Risk Management** — used solely as a methodological reference for conceptual soundness, data quality, independent validation, out-of-time testing, outcomes analysis and ongoing monitoring. This bank supervisory guidance is not asserted to be legally binding on this project.
  https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm

## 10. Approval and implementation gates

This proposal is ready for technical review, not runtime activation. The following must be completed in sequence:

- [ ] Confirm factor definitions and boundaries; resolve any overlap.
- [ ] Build / verify all source-backed typed features and point-in-time provenance.
- [ ] Obtain sufficient historical examples and independently adjudicated labels.
- [ ] Complete chronological backtesting, subgroup analysis, sensitivity and false-PROCEED review.
- [ ] Present empirical weights / thresholds / any floors with evidence, uncertainty and limitations for explicit owner approval.
- [ ] Add factor provenance to immutable decision snapshots and tests.
- [ ] Add tests proving hard gates cannot be overridden by any score.
- [ ] Run shadow-only acceptance; verify no editorial / publication side effects.
- [ ] Obtain separate approval before enabling scheduled runtime.

**Until every required gate is satisfied, keep `policy=None` / `factors=None` in scheduled runtime and preserve `DEFER`.**

## 11. Repository change boundary for this proposal

This proposal is documentation only. It does not change `layer1/opportunity.py`, `main.py`, `SCORING_POLICY.md`, database schemas or data, provider credentials, GitHub workflows, Neon, publisher / gateway code, schedules, or publishing behaviour. No live provider inference, Binance media upload, or real Binance Square publication is part of this work.

# Binance Square Write-to-Earn Agent — Master Code Audit

> **Status: AUDIT IN PROGRESS — NOT FINAL / NOT PRODUCTION CERTIFICATION**
> Audit baseline: `work/module9-continuation-local` at `d2e0ca4b96a33c500548f4726a0feb40430b532b`
> Review started: 2026-11-22
> Scope: locked 21-module architecture, runtime wiring, implementation, tests, persistence, provider contracts, publishing safety, deployment workflows.

## 1. Executive status

This file is the single consolidated audit record. It is not yet the final implementation authority because the complete 21-module codebase and all cross-layer paths have not yet been reviewed. Findings below are evidence-based; anything not inspected is explicitly `NOT VERIFIED` rather than presumed correct.

- Overall production readiness: **NOT VERIFIED / NOT CERTIFIED**.
- Full 21-module coverage: **IN PROGRESS**.
- End-to-end live provider and production database certification: **NOT VERIFIED**.
- No implementation changes were made as part of this audit. Existing worktree changes were preserved.

## 2. Audit baseline and preservation record

- Worktree: `/tmp/binance-w2e-continuation`
- Branch: `work/module9-continuation-local`
- HEAD: `d2e0ca4b96a33c500548f4726a0feb40430b532b`
- Separate checkout `/root/Binance-bot` was not used.
- Existing modifications at audit start (preserved):
  - `MODULE14_FACTOR_PROVENANCE_IMPLEMENTATION_STATUS.md`
  - `MODULE14_SOURCE_REFERENCE_RESOLUTION_AUDIT.md`
  - `PROJECT_CONTEXT.md`
  - `layer1/evidence_verification.py`
  - `layer1/opportunity.py`
  - `layer1/publication_postgres.py`
  - `main.py`
  - `tests/test_deepseek_generator.py`
  - `tests/test_evidence_verification.py`
  - `tests/test_opportunity_registry_resolution.py`
  - `tests/test_source_adapter_contracts.py`
  - untracked `BINANCE_SQUARE_AUTOMATION_COMPLIANCE_REVIEW_2026-11-22.md`
- Inventory observed: 30 Python implementation files (including `main.py`, `image_engine.py`, layer modules and scripts), 50 top-level Python test files, four GitHub workflow files, 24,386 implementation lines counted across the inspected Python files.
- This report is the only new audit artifact. No source code, DB, deployment, publisher configuration, or real Binance publication was changed.

## 3. Severity and status definitions

- **CRITICAL**: can cause unauthorized/duplicate publication, loss/corruption of durable state, or bypass of a core safety invariant.
- **HIGH**: material correctness, security, integrity, or production availability risk.
- **MEDIUM**: degraded coverage, reliability, observability, or maintainability with bounded impact.
- **LOW**: limited-impact cleanup or documentation issue.
- Module statuses: `PASS`, `FAIL`, `PARTIAL`, `NOT VERIFIED`.
- A `PASS` requires code-path inspection plus meaningful tests/evidence; absence of a known bug is not a pass.

## 4. Confirmed findings

### AUD-MAIN-001 — Persistence integrity check fails open on verification errors

- **Severity:** CRITICAL
- **Status:** CONFIRMED CODE DEFECT
- **Area:** Main runtime / duplicate-publication safety / legacy JSONL history guard
- **Evidence:** `main.py:882-895` documents that integrity uncertainty must fail closed. However:
  - `main.py:956-958`: `subprocess.TimeoutExpired` returns `True` when the file exists but is empty and Git history cannot be checked.
  - `main.py:959-961`: any other exception in that branch also returns `True`.
  - `main.py:1006-1011`: missing-file branch likewise returns `True` on Git timeout or generic Git-check failure.
  - `_run_once_impl()` invokes this check before continuing at `main.py:4543`.
- **Impact:** the code can authorize a run to proceed when it explicitly cannot establish whether the recent-publication history is complete. This contradicts the stated fail-closed contract and can undermine cooldown/duplicate protection.
- **Test coverage gap:** repository search found only tests that patch `_verify_persistence_integrity` to return `True`; no direct tests were found for timeout/error branches, empty/missing files with Git uncertainty, or corrupted non-empty JSONL.
- **Required closure:** change the decision model so inability to verify history is a blocked state (or a separately authenticated recovery state), not success; add isolated tests for every exception and file-state branch; prove no publish attempt occurs on uncertainty. Do not silently convert Git errors into first-run state.

### AUD-MAIN-002 — Single-run production entrypoint drops the trend-intelligence input

- **Severity:** HIGH
- **Status:** CONFIRMED RUNTIME INTEGRATION DEFECT
- **Area:** Module 5 trend intelligence → main orchestration / scheduled entrypoint
- **Evidence:**
  - `.github/workflows/run_bot.yml:61-72` sets `POST_INTERVAL: "0"` and runs `python main.py`, selecting single-run mode.
  - `main.py:6279-6283` constructs `hot_search_engine = HotSearchEngine(config)`.
  - `main.py:6290` calls `run_once(...)` without passing `hot_search_engine`.
  - `run_once()` accepts `hot_search_engine=None` (`main.py:6052`); it forwards that argument into `_run_once_impl()` (`main.py:6105`), where trend retrieval occurs only when the engine is supplied (`main.py:4540` and `_persist_layer1_market_intelligence` call path).
  - The loop entrypoint passes `hot_search_engine` (`main.py:6244`), so the two execution modes have inconsistent input coverage.
- **Impact:** the deployed GitHub Actions single-run path constructs but does not use the trend engine. Trend signals/clusters and trend-derived relevance inputs are absent from this path, despite the engine being initialized. This is a real cross-entrypoint integration gap, not a missing standalone module.
- **Required closure:** pass the initialized engine in single-run mode; add a regression test asserting `run_once` receives the engine and that a mocked trend source reaches the Layer 1 persistence/orchestration path. No live post is required.

## 5. Previously established findings to carry forward (not re-audited in this pass)

These findings were established in earlier focused reviews and must remain open/visible until their closure evidence is rechecked in the final audit:

### AUD-ONCHAIN-001 — On-chain acceptance receipt is caller-forgeable / not bound to provider response

- **Severity:** CRITICAL
- **Status:** OPEN — prior focused review
- `OnChainObservation` does not retain authenticated provider response material or a canonical raw-response hash/attestation. Provider/endpoint/finality identifiers are caller-supplied. `OnChainValidationResult` can be directly instantiated by callers. Evidence conversion accepts a matching public `ACCEPTED` result without proving that the engine created it or rerunning validation. Storage write boundaries revalidate shape, but persisted reads trust stored validation status without cryptographic provider authenticity.
- **Required closure:** trusted validation receipt bound to canonical observation fingerprint, eligibility and mapping snapshot; authenticated storage envelope/signature/HMAC for cross-process boundaries; replay protection/key rotation; adversarial forged-result and persisted-tamper tests for SQLite and PostgreSQL.

### AUD-ONCHAIN-002 — Asset mapping `VERIFIED` label is not reproducible source-backed verification

- **Severity:** HIGH
- **Status:** OPEN — prior focused review
- Mapping validation checks field shape, source type, HTTPS URL syntax, network/chain consistency and timestamps, but does not retrieve/retain official source evidence, source excerpt/hash, verifier identity, or expiry/revalidation. A generic HTTPS source can satisfy the application-level label.
- **Required closure:** exact official registry/document reference and retrieval timestamp; source payload/projection hash; contract/mint/issuer, network, decimals and token-standard proof; verifier/reviewer identity; expiry/revalidation; mismatch/staleness tests.

### AUD-ONCHAIN-003 — Individual Module 9 observations not demonstrated in main ClaimRegistry path

- **Severity:** HIGH
- **Status:** OPEN — prior focused review
- Main runtime ClaimRegistry rebuild was observed passing `onchain_summary_refs`, not individual `onchain_records`. Individual observations were not shown wired into the main evidence registry path. Confirm intended design and prove integration or explicitly classify summaries as the sole supported evidence interface.

### AUD-M14-001 — Module 14 production scoring policy is not activated or empirically calibrated

- **Severity:** HIGH
- **Status:** OPEN / FAIL-CLOSED DEFER
- Six factors are specified (`evidence_strength`, `timeliness`, `materiality`, `audience_usefulness`, `novelty`, `risk_control`), but production weights/thresholds/floors are not approved or enabled. Scheduled runtime uses `factors=None`, `policy=None`, and fail-closed DEFER. Historical point-in-time dataset sufficiency is not verified; Neon was suspended during the earlier review. Do not infer a score or borrow Module 7 weights.
- **Required closure:** source-backed feature providers; timestamped point-in-time history; independently adjudicated labels; chronological out-of-time evaluation; subgroup/sensitivity/false-PROCEED analysis; shadow mode; documented owner approval and separate activation approval.

### AUD-M21-001 — PostgreSQL durability/recovery acceptance remains incomplete

- **Severity:** HIGH
- **Status:** PARTIAL / OPEN
- Earlier review found disposable PostgreSQL acceptance insufficient for production cutover certification. `B-PG-02` remained partially accepted; positive PROCEED/content path, same-run stage-boundary failure injection, unknown-outcome reconciliation and duplicate recovery still require evidence. Production crash/restart/operator recovery drills and a real authorized DB environment were not verified.

### AUD-ANN-001 — Announcement WebSocket coverage has no historical replay guarantee

- **Severity:** HIGH
- **Status:** PARTIAL / OPEN
- Existing docs describe `PARTIAL_COVERAGE_NO_REPLAY`; a successful read is not proof of complete coverage. `ANNOUNCEMENT_DATABASE_URL` was absent in the prior runtime check. Do not claim full announcement coverage without replay/backfill and read-only role verification.

### AUD-MARKET-001 — Market analysis has incomplete historical baseline coverage

- **Severity:** MEDIUM
- **Status:** PARTIAL / OPEN
- Missing timestamped baselines yield partial/null analysis; sparkline points must not be repurposed as hourly/daily history or synthetic backfill.

## 6. Deployment/workflow observations requiring final validation

### AUD-WF-001 — Fixed-key cache freshness (superseded by AUD-WF-002)

- **Status:** SUPERSEDED — see `AUD-WF-002` for the confirmed stale-cache rollback path, official GitHub documentation and closure criteria.

## 7. Module coverage matrix — current state

| Module / area | Status | Audit evidence so far |
|---|---|---|
| M1 Configuration / orchestration | PARTIAL | Config validation, run lease and entrypoint wiring inspected; broader config and concurrency paths pending |
| M2 Market data intelligence | PARTIAL | Turnover metric semantics corrected locally; historical timestamped baseline coverage and live provider verification remain open |
| M3 Binance listing eligibility | PARTIAL | Runtime eligibility wiring observed; full engine/proof review pending |
| M4 Announcement intelligence | PARTIAL | Importer/runtime status and known coverage limitation carried forward; full code review pending |
| M5 Trend intelligence | PARTIAL | `AUD-MAIN-002` (MEDIUM): one-shot entrypoint omits trend inputs; continuous loop supplies them; trend signals are attention/discovery context, not event proof |
| M6 Candidate discovery | NOT VERIFIED | Pending |
| M7 Relevance scoring | NOT VERIFIED | Pending |
| M8 Market analysis | PARTIAL | Historical baseline limitation carried forward; full code review pending |
| M9 On-chain intelligence | FAIL / PARTIAL | `AUD-ONCHAIN-001/002/004/005` remain open; `AUD-ONCHAIN-003` closed as intended summary-only ClaimRegistry design |
| M10 Event graph | NOT VERIFIED | Pending |
| M11 Evidence verification | PARTIAL | Earlier focused review inspected adapter/claim path; full evidence engine review pending |
| M12 Event lifecycle | NOT VERIFIED | Pending |
| M13 Deep research | NOT VERIFIED | Pending |
| M14 Opportunity evaluation | FAIL / DEFER | AUD-M14-001; source provenance and policy activation incomplete |
| M15 DeepSeek integration | NOT VERIFIED | Provider workflow and client symbols inventoried; full request/response and safety review pending |
| M16 Editorial strategy | NOT VERIFIED | Pending |
| M17 Content generation | NOT VERIFIED | Pending |
| M18 Content verification / safety | NOT VERIFIED | Pending |
| M19 Cloudflare image generation | NOT VERIFIED | Provider workflow and image engine symbols inventoried; full review pending |
| M20 Visual QA | PARTIAL | visual-quality-v3 pixel tests pass locally; background-content review remains open |
| M21 Publication / persistence / recovery | FAIL / PARTIAL | AUD-MAIN-001, AUD-M21-001; publisher and workflow review pending |

## 8. Tests and verification evidence

- Audit inventory command completed.
- Focused visual/image tests were attempted: `python -m unittest tests.test_visual_quality tests.test_cloudflare_image_generation -q`. Both test modules failed to import because Pillow (`PIL`) is not installed in this remote worktree. No dependency was installed. Therefore the source-level false-PASS test design is confirmed, but the test execution itself is `NOT VERIFIED` in this environment.
- Prior focused regression verification (pre-audit baseline, already present in the worktree):
  - `python -m unittest tests.test_opportunity_registry_resolution tests.test_evidence_verification tests.test_source_adapter_contracts -q`: 117 tests, 0 failures, 2 skipped.
  - `python -m compileall -q layer1 tests main.py`: passed.
  - `git diff --check`: passed.
- Earlier full-suite discovery reported 630 tests, 61 skipped, 34 import/runtime errors and 0 assertion failures; this is historical evidence, not a current rerun.
- PostgreSQL DSN-gated tests were previously skipped because `TEST_POSTGRES_DSN` was absent. No production database was accessed.
- No real Binance post or live publisher action was performed.

## 9. Audit work remaining before this report can become final

1. Finish static/code-path review of `main.py` and `image_engine.py`, including all error paths and publication boundaries.
2. Review every `layer1/*.py` module and map it to the locked architecture owner, call sites, state stores and tests.
3. Review all 50 test files for missing edge cases, misleading mocks, untested branches and cross-module integration.
4. Inspect migrations, schemas, dependency manifests, GitHub workflows and operational scripts for drift, least privilege, deployment safety and durable-state semantics.
5. Build duplicate/dead/unreachable-code inventory with evidence; do not label code dead based only on grep or lack of obvious call sites.
6. Verify provider/API contracts against current official sources where they materially affect correctness; separate docs verification from live authenticated provider verification.
7. Reconcile all existing blocker registers and architecture invariants into this report without losing earlier findings.
8. Add exact line references, acceptance tests and ordered closure criteria for every final finding.
9. Run only safe isolated tests; never publish, deploy, migrate production, alter secrets, or access production DB without explicit approval.
10. Update this same file to `AUDIT COMPLETE — FINAL` only after all 21 modules and end-to-end integrations have been reviewed. Until then it is not the authoritative final go-live verdict.

### AUD-PUB-001 — SQLite publisher has a time-of-check/time-of-use gap for event and duplicate policy

- **Severity:** HIGH
- **Status:** CONFIRMED SQLITE/PERSISTENCE PARITY DEFECT
- **Area:** Module 21 publication authorization / event lifecycle concurrency
- **Evidence:**
  - SQLite path runs `validate_persisted_event_binding()` at `main.py:4178` and `validate_persisted_duplicate_policy()` at `main.py:4179-4181`, then builds the request and opens the network call at `main.py:4200-4222`.
  - `validate_persisted_duplicate_policy()` uses `BEGIN IMMEDIATE` but its transaction ends when the method returns (`layer1/publication_authorization.py:443-457`). `validate_persisted_event_binding()` performs independent reads and does not hold a lock through submission (`:459-496`).
  - Therefore another process can change event lifecycle state or relevant duplicate ledger rows after the final checks and before the Binance POST.
  - PostgreSQL path explicitly differs: `main.py:4349-4362` wraps the outbound POST in `store.authorized_submission_guard()`. `layer1/publication_postgres.py:378-416` holds symbol/event advisory locks and provenance row locks through the request; its comments explicitly cover the missing-row `NO_EVENT` case.
  - No equivalent SQLite submission guard or concurrency test was found in `tests/test_publisher_safety.py` / `tests/test_publication_authorization.py`.
- **Impact:** in SQLite mode, an event can be invalidated or a competing duplicate/cooldown condition can appear after preflight but before submission. The request may then be sent using stale authorization. This is a real race window; it is not present in the same form in the PostgreSQL path.
- **Required closure:** implement an SQLite-specific serialization/fencing design that covers both existing-event and `NO_EVENT` cases and safely handles the bounded HTTP operation; add multi-connection/process race tests that attempt event transition and competing publication exactly between final validation and request dispatch. Verify lock duration, busy timeout, process crash behavior and no deadlock. Do not hold a long SQLite write transaction around network I/O without explicitly proving operational safety.

### AUD-PUB-002 — SQLite attempt finalization permits missing or released quota reservation

- **Severity:** HIGH
- **Status:** CONFIRMED INVARIANT ENFORCEMENT DEFECT
- **Area:** Module 21 publication attempt/quota atomicity
- **Evidence:**
  - `main.py:3941-3947` returns from `_finish_attempt()` if the quota table does not exist; this is documented as legacy/private compatibility.
  - More importantly, when the quota table exists, `main.py:3948-3953` also returns if the attempt has no bound quota row or if the quota status is `RELEASED`. This occurs after the publication attempt row has already been updated to the requested terminal/unknown status (`main.py:3925-3936`) in the same transaction.
  - The normal authorized SQLite publishing path creates/reserves quota and binds the attempt before POST (`main.py:4120-4160`), so a missing or `RELEASED` quota row at finalization is an invariant violation, not a normal legacy case.
  - PostgreSQL implementation is stricter: `layer1/publication_postgres.py:527-542` raises if the attempt has no quota reservation and validates the quota state transition before updating either record.
  - Existing PostgreSQL transition tests explicitly reject `SUBMITTING -> RELEASED` (`tests/test_publication_postgres.py:24-37`); SQLite `_finish_attempt()` bypasses equivalent enforcement for `RELEASED` because of the early return.
- **Impact:** an inconsistent/deleted/released quota row can be silently accepted while the publication attempt advances to `PUBLICATION_UNKNOWN` or `PUBLISHED_CONFIRMED`. This can leave the durable attempt and quota ledger inconsistent and can undercount daily usage/recovery state. The current normal path should not create this state, but the finalization boundary fails to detect it.
- **Required closure:** for authorized attempts, require exactly one quota reservation bound to that attempt and reject `RELEASED`/missing rows; keep the explicit legacy path separate and unreachable from authorized publishing. Add tests that delete the reservation, set it to `RELEASED`, and race a quota transition immediately before each attempt finalization. Assert the whole transaction rolls back and the attempt remains fenced.


### AUD-VIS-001 — Visual QA can PASS an image that contains none of the claimed text overlays

- **Severity:** HIGH
- **Status:** FIXED LOCALLY / HOSTED CI PENDING — original metadata-only false-pass reproduced; see superseding Section 76
- **Area:** Module 20 visual quality / rendered-artifact integrity
- **Evidence:**
  - `tests/test_visual_quality.py:17-19` creates a plain solid-color `1080x1350` PNG (`Image.new("RGB", (1080, 1350), "navy")`) with no text rendered into its pixels.
  - `tests/test_visual_quality.py:28-60` writes a sidecar claiming the image contains `MARKET UPDATE` and `$ABC`, including bounding boxes, font sizes and fill colors.
  - `tests/test_visual_quality.py:62-67` asserts that `VisualQualityEngine.validate()` returns `PASS` for this blank image and metadata.
  - `layer1/visual_quality.py:201-236` validates the sidecar's claimed labels, geometry and contrast metadata, but does not inspect image pixels to prove that the labels are actually present/rendered. It validates image bytes/hash/dimensions separately, which proves file identity, not text visibility.
  - The active image composer does render text in `image_engine.py:823-841`, but the QA engine does not verify those rendered pixels; a blank/replaced image plus a freshly matching sidecar can pass the QA contract.
- **Impact:** a visual validation record marked `PASS` does not prove that the required text is visible in the actual image. Publication authorization can therefore rely on a false-positive visual QA result.
- **Required closure:** add a pixel-grounded verification method (e.g. OCR with confidence/region checks, or deterministic render-mask/overlay composition whose pixel output is independently reproducible and compared). Replace the blank-image PASS fixture with a test that must reject it; add tampered/erased-text and shifted-text pixel tests. Keep image hash bound to the exact final bytes and validate before authorizing upload.


### AUD-MKT-001 — CoinGecko turnover percentage is consumed as an `x` volume-spike ratio

- **Severity:** HIGH
- **Status:** FIXED LOCALLY / HOSTED CI PENDING — original metric-semantics defect confirmed; see superseding Section 77
- **Area:** Module 2 market data → Module 5 trend signals → candidate scoring/research narrative
- **Evidence:**
  - `main.py:2410-2418` reads CoinGecko `total_volume` and `market_cap`, then computes `volume_ratio = min(max(0.3, volume_24h / max(market_cap, 1) * 100), 10.0)`.
  - That expression is 24-hour turnover as a percentage of market capitalization (clamped to 0.3–10); it is not current volume divided by historical average volume, nor a provider-reported `x` volume multiple.
  - The value is then used as a volume-spike threshold in `main.py:2500`, `:2817-2831`, and as a movement/candidate gate at `:1144-1147`.
  - The same value is described as `%.1fx volume` at `main.py:2969`, and candidate/filter logs use `x vol` at `:1147`, `:1178-1180`, `:4837-4839`. `ResearchEngine._volume_analysis()` partly relabels it as an internal heuristic (`:3078-3099`), but other runtime consumers still call it a volume ratio/spike.
  - Skills Hub uses a different formula (`volume24h / marketCap * 5`) at `main.py:2108`, showing the same field is not even consistently normalized across providers; Skills Hub is currently disabled in the runtime.
- **Impact:** a turnover-rate proxy is presented/consumed as a volume multiple or spike. Thresholds such as `>2.0` mean roughly >2% turnover under the CoinGecko path, not 2x historical volume. This can mis-rank candidates and produce inaccurate descriptions of market activity.
- **Required closure:** rename and type the metric as a turnover/market-cap ratio with explicit units and source; do not call it a volume spike or `x` multiple. If actual volume surge is needed, derive it from timestamped current and baseline volume windows with provider provenance, minimum sample count, staleness checks and documented comparison period. Add source-specific normalization tests and remove mixed-provider reuse of one untyped field.

### AUD-CODE-001 — Skills Hub scoring/provider subsystem is unreachable from the current runtime

- **Severity:** MEDIUM
- **Status:** CONFIRMED INTERNAL DEAD-PATH / LEGACY CANDIDATE
- **Area:** Main candidate discovery and scoring
- **Evidence:**
  - `main.py:4601-4605` explicitly says the undocumented Skills Hub BAPI is disabled and sets `skills_used = False`, `skills_candidates = []`.
  - `main.py:1954-2308` still contains the complete `SkillsHubEngine` fetch, parsing and weighted scoring implementation.
  - `main.py:4855-4895` only enters the Skills Hub score branch if `skills_used` is true; with the hard-coded false flag, the branch is unreachable in the current entrypoint. The runtime always uses the MarketScanner heuristic branch at `:4890-4895`.
  - Repository search found no instantiation/call of `SkillsHubEngine` outside its class definition; the class itself and its associated `skills_candidates` local are therefore not part of the active pipeline.
- **Impact:** retained undocumented-provider code and a second scoring system increase maintenance/audit surface and create a misleading impression that Skills Hub contributes to live discovery. This is not evidence that the class is safe or production-ready.
- **Required closure:** keep the provider explicitly disabled unless official contract/permission is verified; either remove/archive the unreachable implementation in a separately approved cleanup or document it as intentionally quarantined. Do not silently reactivate it. Audit the active MarketScanner ranking separately; do not reuse the legacy Skills Hub weights.


### AUD-SCORE-001 — Active MarketScanner ranking uses undocumented heuristic coefficients

- **Severity:** MEDIUM
- **Status:** CONFIRMED ACTIVE HEURISTIC; POLICY JUSTIFICATION NOT FOUND
- **Area:** Candidate ranking before editorial selection
- **Evidence:**
  - Current runtime hard-disables Skills Hub (`main.py:4601-4605`), so candidates do not use `SCORE_WEIGHTS` or the old Skills Hub scoring engine.
  - The active fallback branch computes `heuristic = min(abs(coin.change_24h) * 3 + coin.turnover_ratio_pct * 10, 100)` at `main.py:4890-4895` and sorts candidates by this score at `:4903-4904`.
  - This is a ranking heuristic, not the Module 14 policy; the code path does not attach a calibration dataset, empirical validation, factor provenance, or an approved policy version to the coefficients `3` and `10`.
  - `turnover_ratio_pct` is the provider-reported 24h turnover-to-market-cap percentage, not an average-volume multiple; see Section 77 for the semantic correction.
  - The Module 14 runtime call explicitly supplies `factors=None` and `policy=None` (`main.py:4753-4758`), so this heuristic must not be represented as a production opportunity score or allowed to override the fail-closed Module 14 DEFER decision.
- **Impact:** it changes candidate ordering and which candidates are examined first, but it is not currently an authorized PROCEED/PUBLISH policy. Its coefficients are unsupported by the inspected source and its volume input has ambiguous semantics.
- **Required closure:** either remove the active ranking formula or document it strictly as a non-authoritative discovery ordering heuristic with source-backed inputs, bounded influence and a policy version. If it is intended to influence publish eligibility, require historical point-in-time data, adjudicated labels, out-of-time validation, sensitivity/false-PROCEED analysis and explicit approval. It must never bypass Module 14 hard gates.


### AUD-M14-002 — Opportunity evaluator can PROCEED on six raw numbers without registry-bound factor provenance

- **Severity:** HIGH
- **Status:** CONFIRMED ACTIVATION-PATH GAP; CURRENT RUNTIME REMAINS FAIL-CLOSED
- **Area:** Module 14 scoring engine / factor provenance enforcement
- **Evidence:**
  - `OpportunityEvaluationEngine.evaluate()` accepts `factors: Mapping[str, float]` and `policy: OpportunityPolicy` (`layer1/opportunity.py:831-848`). When a policy is supplied and the six names/ranges are valid, it computes the weighted score and can return `PROCEED` (`:913-940`). It does not accept or resolve a factor-assessment envelope, ClaimRegistry snapshot, source refs, source hashes, claim refs, or provenance version.
  - The evaluator serializes only raw numeric `factors` into its input snapshot (`:942-987`); no `schema_version`, `factor_assessments`, or `registry_verification_id` is included.
  - The shared snapshot validator intentionally retains legacy schema-v1 compatibility (`:628-655`), so the raw evaluator snapshot remains valid as a legacy snapshot rather than being forced through v3/v4 registry-bound resolution.
  - Registry-bound v3/v4 validators exist separately (`:728-759`) and decision stores can verify them, but `evaluate()` does not invoke them or require a validated provenance token before returning PROCEED.
  - Unit tests explicitly demonstrate `test_deterministic_high_quality_research_proceeds` with raw numeric factors (`tests/test_opportunity.py:40-45`).
  - Current runtime is safely disabled: `main.py:4753-4758` passes `factors=None` and `policy=None`, so the actual scheduled path returns DEFER with `APPROVED_OPPORTUNITY_SCORING_POLICY_NOT_CONFIGURED`. This finding is about the unsafe future activation interface, not a claim that the current runtime publishes via Module 14.
- **Impact:** a future developer/operator could configure weights and pass six numeric values, causing PROCEED without the registry-bound factor evidence, cutoff, transformation/baseline and claim-support checks that the architecture requires. Schema/provenance code existing elsewhere does not protect this evaluator call.
- **Required closure:** make the evaluator accept only a validated, immutable factor-assessment object/snapshot that has passed v3/v4 exact-registry resolution; bind its digest and registry verification ID into the decision ID; reject raw `Mapping[str,float]` for production decisions. Keep legacy v1 reads for history, but do not allow legacy snapshots to create new production PROCEED decisions. Add a test that six raw floats plus a valid policy cannot PROCEED, and a positive test requiring exact registry-bound provenance.


### AUD-GIT-001 — Detached-HEAD history sync falls back to pushing the current commit to `main`

- **Severity:** CRITICAL
- **Status:** CONFIRMED BRANCH-TARGETING DEFECT
- **Area:** Operational safety / Git history persistence / GitHub Actions
- **Evidence:**
  - `.github/workflows/run_bot.yml:6` enables `workflow_dispatch`; the Actions UI permits selecting a branch for a manual run. `actions/checkout@v4` at `:21-25` uses its default ref (`github.ref`), which is normally checked out detached in Actions.
  - `_try_git_push()` reads `git rev-parse --abbrev-ref HEAD` (`main.py:723-727`). In detached checkout Git returns `HEAD`.
  - `main.py:786-792` explicitly maps both `unknown` and `HEAD` to target branch `main`, then pushes `HEAD:main`.
  - The workflow injects `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` (`.github/workflows/run_bot.yml:48`) and grants `contents: write` (`:13-14`). `_run_once_impl()` invokes `_retry_pending_push()` before scanning (`main.py:4548-4552`), and `_retry_pending_push()` calls `_try_git_push()` when post-history paths have pending changes.
- **Impact:** a manual workflow run selected on a non-main branch, with pending history changes, can attempt to push that branch's detached HEAD to `main`. If the commit is a fast-forward from main, feature-branch code/config changes can be introduced to main by the history-sync helper. If it is divergent, Git rejects it; the safety behavior is still wrong because target branch is guessed rather than proven.
- **Required closure:** never infer a target branch from detached HEAD. In Actions, require an explicit trusted ref and compare it to the checked-out commit/branch; only permit the intended protected branch. Otherwise fail closed and leave the history file pending. Add mocked tests for workflow_dispatch detached HEAD on a feature branch and for unknown branch state; assert there is no `git push` to main.

### AUD-GIT-002 — History commit can include unrelated pre-staged repository changes

- **Severity:** HIGH
- **Status:** CONFIRMED INDEX-ISOLATION DEFECT
- **Area:** Git persistence helper / source-control integrity
- **Evidence:**
  - `_try_git_push()` stages `published_posts.jsonl` and `posts/` (`main.py:742-749`) and then executes `git commit` with no pathspec (`:750-754`).
  - Git commit without a pathspec commits all staged index entries, not only the two paths this helper just added. Existing staged implementation/docs/config changes in a local or reused worktree are therefore included in the bot's commit.
  - Existing `tests/test_git_push_security.py` checks ephemeral token handling and remote URL immutability only (`:12-45`); it does not seed an unrelated staged file and verify it remains uncommitted.
- **Impact:** running the bot in a worktree with pre-staged user changes can commit and push unrelated source/config/document changes under the bot identity. This violates the helper's stated scope of saving post-history only.
- **Required closure:** isolate the index (temporary `GIT_INDEX_FILE`) or use a dedicated worktree/commit mechanism that cannot include pre-existing staged entries; verify the exact commit tree contains only explicitly approved history paths. Add a regression with a pre-staged source file and assert it remains outside the history commit. Do not rely on `git commit <path>` without understanding staged-index semantics.


### AUD-WF-002 — Immutable fixed-key cache can restore stale publication history over newer Git state

- **Severity:** CRITICAL
- **Status:** CONFIRMED WORKFLOW/DURABLE-STATE DEFECT
- **Area:** GitHub Actions workflow / post-history persistence and duplicate prevention
- **Evidence:**
  - `.github/workflows/run_bot.yml:38-43` restores `published_posts.jsonl` from the fixed key `post-history-${{ github.ref_name }}`; `:74-79` attempts to save the exact same key after every run.
  - GitHub's official dependency-cache documentation states that an existing cache cannot be changed; a new key is required to create a new cache. An exact key hit restores the cached files to the requested path. Source: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
  - Therefore the first cache created for a branch is immutable and subsequent saves under the same key do not refresh it. The restore step can overwrite the newer `published_posts.jsonl` already present in the fresh Git checkout with the old cached copy.
  - The runtime integrity guard at `main.py:900-906` treats any non-empty local history file as `INTEGRITY OK`; it does not compare its content/hash/sequence against the checked-out Git version.
  - `_retry_pending_push()` then treats the stale restored file as pending uncommitted history (`main.py:834-878`) and `_try_git_push()` can commit/push it (`:742-792`), potentially replacing newer history with the stale cached version.
- **Impact:** publication history can regress across scheduled runs. A stale cache can remove previously committed publication records from the working copy, pass the non-empty integrity check, and be pushed back to the branch. That can weaken cooldown and duplicate-post protection and corrupt the history ledger.
- **Required closure:** remove mutable publication history from Actions cache or use a genuinely versioned cache key with monotonic freshness and integrity binding. Git/DB must be the single durable authority; cache must never overwrite newer durable state. Before any history write, compare an authenticated content digest/version against the authoritative DB/Git record and fail closed on rollback. Add a two-run workflow simulation: run A updates history; run B restores the old cache; assert the new record remains and no stale rollback commit can occur.


## 10. External API contract spot-checks (documentation only)

- DeepSeek official API documentation currently lists `deepseek-flash` and `deepseek-v4-pro` as supported Chat Completions model IDs. The workflow's `DEEPSEEK_MODEL=deepseek-flash` matches the documented identifier. Sources: https://api-docs.deepseek.com/api/list-models/ and https://api-docs.deepseek.com/quick_start/pricing/
- DeepSeek's official Chat Completions contract accepts `thinking: {"type":"disabled"}` and `safety_check: {"level":"high"}`. `layer1/deepseek_client.py:142-154` sends both fields; this portion of the request contract is aligned with current docs. Source: https://api-docs.deepseek.com/api/create-chat-completion/
- This is an official-documentation contract check only. It is not authenticated live provider verification; the workflow `provider-verification.yml` exists, but no provider workflow was triggered in this audit.


## 11. Continuation verification — 2026-11-22 (same worktree, read-only audit)

### Runtime and repository identity re-confirmed
- Device: authorized localhost Desktop Commander device; worktree: `/tmp/binance-w2e-continuation`.
- Branch: `work/module9-continuation-local`; HEAD: `d2e0ca4b96a33c500548f4726a0feb40430b532b`.
- Existing tracked/untracked modifications remain present and were not staged, reset, overwritten, committed, or pushed.
- No production database, live provider credentials, Binance publisher, media upload, real Square post, deployment, migration, or dependency installation was used.

### Focused module test batch
- Executed using the existing isolated test interpreter `/tmp/binance-module11-test-venv/bin/python`:
  `tests.test_layer1_foundation`, `tests.test_market_analysis`, `tests.test_module4_announcement_importer`, `tests.test_module4_announcement_runtime_integration`, `tests.test_event_graph`, `tests.test_event_lifecycle`, `tests.test_research_package`, `tests.test_editorial_strategy`, `tests.test_content_generation`, `tests.test_content_verification`.
- Result: **219 tests, 0 failures, 0 errors**.
- This is focused unit/mock evidence only. It does not establish live Binance/CoinGecko/announcement-provider coverage or production database acceptance.
- The system Python interpreter still lacks Pillow; invoking the same test batch there caused five import errors from tests that import `main.py` and transitively import `image_engine.py`. The isolated venv is the valid focused result; no packages were installed.

### Additional source-level review notes
- Module 1 SQLite `RunLease` implementation in `layer1/foundation.py:123-277` uses `BEGIN IMMEDIATE`, exact run-ID ownership checks, conditional RUNNING-state update, and operator-confirmed interrupted-run recovery. No defect was confirmed in this source slice; this does not certify the separate PostgreSQL run-lease path or full crash/restart behavior.
- Module 2 canonical asset identity resolution and Module 3 Binance Spot eligibility code were exercised by the 219-test batch. Tests/logs demonstrate fail-closed behavior for stale identity timestamps and unavailable/invalid Binance metadata. This is mock/unit evidence, not live provider verification.
- Module 4 importer/event integration tests pass, but runtime output explicitly reports `PARTIAL_COVERAGE_NO_REPLAY`, `OBSERVED_ONLY_NO_HISTORICAL_REPLAY`, and in some cases `UNRESOLVED_NO_STABLE_PROVIDER_ID`. The announcement stream is not proven historically complete or revision-correlated for every source; retain PARTIAL status.
- Modules 12–13 focused graph/lifecycle/research tests are included in the 219 passing tests. Source review confirms graph validation rejects dangling entity/evidence references and duplicate stable IDs; event lifecycle requires a single canonical asset per event record and explicit verified resolution/withdrawal evidence; research packages are built from typed ClaimRegistry records with cutoff filtering and completeness states. This does not prove every cross-layer runtime path or PostgreSQL persistence parity.
- Module 18 content-verification source requires typed ClaimRegistry, canonical asset ID, exact claim attribution, asset-wide unresolved-claim checks, cashtag identity match, prohibited-trade-instruction checks, and a numeric validator callback. Missing numeric validator fails closed. No bypass confirmed in this source slice.

### Module status adjustment (limited to reviewed scope)
- M1: PARTIAL — SQLite lease implementation and focused tests pass; PostgreSQL lease parity and full crash/restart acceptance remain unverified.
- M2: PARTIAL — identity resolver unit coverage passes; live source freshness/availability not verified.
- M3: PARTIAL — Binance eligibility fail-closed mock tests pass; live exchange metadata not verified.
- M4: PARTIAL — importer and runtime integration tests pass; historical replay and stable revision lineage remain unavailable/unproven.
- M5: FAIL — scheduled single-run trend-engine omission remains AUD-MAIN-002.
- M12: PARTIAL — graph/lifecycle focused tests pass; full runtime and durable cross-store parity not certified.
- M13: PARTIAL — research package focused tests pass; no full end-to-end evidence provenance acceptance.
- M16–M18: PARTIAL — editorial/content verification unit tests pass in this batch; full generation-to-publication integration and production acceptance remain open.
- Overall report remains **AUDIT IN PROGRESS — NOT FINAL**. Do not interpret this focused pass as 21-module completion.


### Modules 14–21 focused regression batch
- Executed using the existing isolated interpreter `/tmp/binance-module11-test-venv/bin/python`:
  `test_opportunity`, `test_opportunity_claim_support`, `test_opportunity_registry_resolution`, `test_deepseek_client`, `test_deepseek_generator`, `test_editorial_strategy`, `test_content_generation`, `test_content_verification`, `test_cloudflare_image_generation`, `test_visual_quality`, `test_publication_authorization`, `test_publication_postgres`, `test_publication_runtime`, `test_publisher_safety`, `test_reconcile_publications`, `test_scheduled_persistence_safety`, `test_scheduled_postgres_acceptance`, `test_postgres_adapter_atomicity`.
- Result: **361 tests, 0 failures, 0 errors, 36 skipped**. The skipped cases are environment-gated integration tests and are not accepted as passes.
- Test log: `/tmp/audit-mod14-21-tests.log`.
- This test batch validates deterministic/mock behavior only. It does not establish a live PostgreSQL acceptance run, real publisher execution, real Cloudflare inference, or a live DeepSeek request.
- Existing critical/high findings remain open despite passing unit tests: Module 14 raw-factor activation interface, SQLite publisher race/quota ledger behavior, detached-HEAD Git push target, pre-staged index contamination, stale Actions cache rollback, visual QA metadata-vs-pixels false pass, and Module 21 PostgreSQL recovery acceptance.

### Test evidence totals for this continuation (do not merge overlapping test modules)
- Foundation/market/announcement/event/research/editorial/content focused batch: **219 passed, 0 failed**.
- On-chain focused batch: **206 passed, 0 failed, 14 skipped**.
- Modules 14–21 focused batch: **361 passed, 0 failed, 36 skipped**.
- These are separate invocations with overlapping test modules; do not sum them as unique test cases or describe them as one full-suite result.
- A full unittest-discovery attempt did not yield a final unittest summary in its captured log and is therefore **INCONCLUSIVE**, not a pass or fail.


### Cross-layer integration verification — Module 7 and Module 9 handoff
- `main.py:5626-5631` constructs candidate discovery and relevance-scoring engines.
- `main.py:4753-4758` and the Layer 1 persistence path pass all five Module 7 score components as `None` (`event_materiality`, `source_credibility`, `freshness`, `audience_relevance`, `novelty`). `RelevanceScoringEngine.score()` explicitly returns score 0 with a deferred reason when any component is missing (`layer1/foundation.py:2051-2081`). This is intentionally conservative, but it means Module 7 does not currently produce a usable ranked score from the main Layer 1 runtime.
- `RelevanceScoringEngine.WEIGHTS` is hard-coded at `layer1/foundation.py:2055-2056` (0.30/0.25/0.20/0.15/0.10). No source-backed calibration/approval record was identified in the active call path. These weights are dormant because the runtime supplies null components; do not activate them by inventing inputs.
- **Module 7 disposition:** PARTIAL / DEFERRED. Before activation, define each factor's observable data contract, source authority, freshness, normalization, missingness, correlation/dependence controls, historical validation and versioned approval. Ranking must remain non-authoritative and separate from Module 14 publish authorization.
- Main runtime calls `EventIntelligenceGraphEngine().rebuild_from_store(store, onchain_summary_refs=...)` and `EvidenceVerificationEngine().rebuild_from_store(store, onchain_summary_refs=...)`; it supplies aggregation summary refs, not individual normalized observations. This is the documented summary-only corroboration interface (`ONCHAIN_INTELLIGENCE.md`), so the absence of individual observations in the main ClaimRegistry path is intentional and is not counted as an open defect. See Section 37.
- The on-chain summary-to-candidate bridge at `main.py:5850-5908` only attaches qualifying summary IDs after the discovery candidate and exact Binance eligibility gates; on-chain is explicitly optional corroboration, not a discovery or publish-authority input. This is the intended safe direction, but does not cure the forged validation receipt/mapping provenance findings.


## 12. Reconciled module matrix after focused code review and test batches

This matrix supersedes the preliminary matrix in section 7. Status reflects the evidence actually available, not merely the existence of a module or passing isolated tests.

| Module | Current status | Reason |
|---|---|---|
| M1 Configuration / run lifecycle | PARTIAL | SQLite run lease and focused tests reviewed; PostgreSQL lease parity, multi-process crash/restart and operational recovery still not accepted |
| M2 Market intelligence / provider normalization | PARTIAL | Canonical identity and market normalization tests pass; historical baseline coverage and live provider verification remain incomplete |
| M3 Binance listing eligibility | PARTIAL | Exact Spot eligibility and fail-closed mock tests pass; live official metadata and independent identity proof not verified |
| M4 Announcement intelligence | PARTIAL | Importer/runtime tests pass; no historical replay and unstable provider revision IDs limit completeness |
| M5 Trend intelligence | PARTIAL | One-shot trend-engine wiring restored; turnover metric semantics and live trend-source coverage remain open |
| M6 Candidate discovery / filtering | PARTIAL | Discovery tests and source path reviewed; depends on partial announcement/market coverage and currently defers downstream scoring |
| M7 Relevance scoring | PARTIAL / DEFERRED | All five runtime components are passed as None; hard-coded weights lack evidence-backed calibration and are not active |
| M8 Market analysis | PARTIAL | Timestamped same-provider history logic exists and tests pass; runtime reports baseline unavailable, so analysis remains partial for current data |
| M9 On-chain ingestion / intelligence | FAIL / PARTIAL | 206 focused tests pass, 14 PostgreSQL skips; caller-forgeable validation receipt, mapping proof weakness and summary-only ClaimRegistry integration remain open |
| M10 Event graph | PARTIAL | Graph validation/build tests pass; main runtime rebuild is tied to current store/summary refs and full durable replay parity is not certified |
| M11 Evidence verification | PARTIAL | Prior 117-test focused batch and earlier 67-test module review pass; provider authenticity and end-to-end individual on-chain observation handoff remain open |
| M12 Event lifecycle | PARTIAL | Lifecycle tests pass; SQLite/PG cross-store parity and crash/replay acceptance not certified |
| M13 Deep research | PARTIAL | Typed registry, cutoff and completeness tests pass; no complete production-grade evidence source coverage/replay acceptance |
| M14 Opportunity evaluation | FAIL / DEFER | Current runtime correctly defers without approved policy, but evaluator can accept raw numeric factors and PROCEED without registry-bound provenance |
| M15 DeepSeek integration | PARTIAL | Client/generator mock tests pass; docs contract spot-check only, no current authenticated provider verification |
| M16 Editorial strategy | PARTIAL | Editorial tests pass; end-to-end production policy and durable persistence integration still open |
| M17 Content generation / draft provenance | PARTIAL | Draft and generator tests pass; exact end-to-end immutable provenance and PostgreSQL-only production path not certified |
| M18 Content verification / safety | PARTIAL | Claim-attribution and deterministic safety tests pass; no full runtime production acceptance and no evidence that every policy requirement is covered |
| M19 Cloudflare image generation | PARTIAL | Mocked generator tests pass; no live authenticated inference or operational cost/latency acceptance |
| M20 Visual QA | PARTIAL | Deterministic overlay pixel proof v3 implemented locally; generated-background OCR and live provider acceptance remain open |
| M21 Publication / persistence / recovery | FAIL / PARTIAL | 361 tests pass with 36 gated skips; critical Git/cache and SQLite authorization defects plus PostgreSQL recovery acceptance remain open |

### Duplicate / stale workflow inventory
- `github/workflows/run_bot.yml` is a second, legacy workflow file outside GitHub Actions' active `.github/workflows/` directory. It differs materially from `.github/workflows/run_bot.yml` (older two-hour cron, Python 3.10, older action versions, old secret names and duplicate/malformed `jobs:` key). GitHub Actions does not treat the root `github/workflows/` path as the active workflow directory. This is stale configuration, not a second active scheduled workflow. Keep it out of runtime assumptions; archive/remove only in a separately approved cleanup.
- Active workflow inventory: four files under `.github/workflows/`. The active publisher workflow requests `contents: write`, injects the GitHub token, and uploads `posts/`, `research/`, `prompts/`, `drafts/`, `images/`, `agent.db`, and `published_posts.jsonl` as artifacts. This deserves a separate artifact data-classification/retention review; no secrets were read or artifact uploaded in this audit.
- PostgreSQL migrations exist under `layer1/migrations/` for on-chain and publication stores. The active workflows include a guarded ephemeral PostgreSQL CI service in `.github/workflows/phase1-safety-tests.yml`; this is useful CI evidence, but no current live run was triggered from this audit. The local PG-gated test skips remain skips.

### Audit completion gate — still open
The focused batches now exercise all major module families, but the full suite attempt did not yield a final summary and this audit has not independently inspected every function/branch in every module or every one of the 50 top-level tests. Accordingly the report must remain **AUDIT IN PROGRESS — NOT FINAL** until the remaining exhaustive test/edge-case, migrations/contract and end-to-end review is actually completed. No production certification is implied.


## 13. Full test discovery and migration review — 22 November 2026

### Full repository unittest discovery (new definitive local result)
- Command: `/tmp/binance-module11-test-venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
- Result: **871 tests run in 40.274 seconds; OK; 63 skipped; 0 failures; 0 errors**.
- Captured log: `/tmp/audit-full-unittest-20261122.log` (summary at lines 146–148).
- This is the first completed full unittest-discovery result for this continuation. The 63 skips remain environment-gated and are not accepted as integration passes. In particular, PostgreSQL-backed acceptance remains unexecuted without the isolated `TEST_POSTGRES_DSN` and allowlisted target.
- The earlier 219/206/361 focused batches overlap and must not be added to this 871-test count. Full discovery includes the repository's current tracked and untracked test modules as present in this worktree.
- The suite's passing status does not close source-level defects already identified; the current tests do not exercise all fail-open timeout/error branches, detached-HEAD push target, unrelated pre-staged index contamination, stale immutable cache restore, SQLite authorization TOCTOU, or actual visual pixel/text verification.

### Migration runner and schema review
- `layer1/onchain_postgres.py:44-74` verifies migration checksums by filename using read-only access to `layer1_schema_migrations`; `:183-226` applies pending migrations in one transaction under a transaction-scoped advisory lock, verifies already-applied checksums, and rejects changed migration contents. The publication migration wrapper uses the same checksum runner and the separate `publication_postgresql` directory.
- `_split_sql_statements()` handles ordinary semicolons, single/double quoted strings, line comments, and nested block comments; it explicitly rejects dollar-quoted blocks and unterminated quotes/comments rather than splitting those incorrectly. Parser tests exist, but do not establish compatibility with arbitrary future PostgreSQL procedural migrations.
- The `0001_onchain_storage.sql` file uses plain `CREATE TABLE`/`CREATE INDEX` without `IF NOT EXISTS`; this is not by itself a rerun defect because the migration ledger skips a matching applied filename/checksum and applies the file transactionally. Editing an applied migration is rejected by checksum mismatch. Do not manually replay the SQL outside the runner.
- Publication migrations 0001–0004 are additive and predominantly use `IF NOT EXISTS`; the runner records each filename/checksum. No down/rollback migrations or tested downgrade path were found in the migration inventory. Rollback is therefore a separately engineered restore/forward-fix operation, not an available migration command.
- **Defense-in-depth schema gap (MEDIUM, recommended):** `layer1/migrations/postgresql/0001_onchain_storage.sql` defines `UNIQUE(network_id, asset_id, mapping_id)` on `layer1_onchain_asset_mappings`, but `layer1_onchain_observations.mapping_id` references only the mapping primary key. The observation row's own `asset_id` and `network_id` are not constrained by a composite FK to match the referenced mapping row. The application `PostgresOnChainStore.save_verified()` calls the domain validator before insertion, and `OnChainIntelligenceEngine.validate()` checks mapping/observation identity, so this is not demonstrated as a bypass through the normal method. A direct or future alternate SQL writer could nevertheless persist a cross-asset/network observation under another mapping. Recommend a composite FK `(network_id, asset_id, mapping_id)` referencing the existing unique key, with a migration and negative database test before production.
- No PostgreSQL server was contacted, no migration was applied, and no schema was modified during this review.

### End-to-end test scope qualification
- `tests/test_end_to_end_pipeline.py` exercises an orchestration path using synthetic fixtures, a mocked Cloudflare generator, a locally created solid-color image, and a manually constructed opportunity policy with hand-supplied weights and high factors. It verifies that the pipeline can pass its mocked gates; it does not establish that the scoring weights are source-calibrated, that a live provider generated the image, or that the visual QA detects missing text. The solid-color fixture also overlaps the false-positive visual QA finding `AUD-VIS-001`.
- This integration test does not invoke the real Binance publisher; no real publication was performed.

### Updated test/readiness disposition
- Full local unittest discovery: PASS (871 run, 63 skipped).
- PostgreSQL production-like acceptance: NOT VERIFIED (63 skips include environment-gated integration tests; no DSN configured/used in this audit).
- Live Binance/CoinGecko/announcement/DeepSeek/Cloudflare provider verification: NOT RUN.
- Real Square publication and recovery: NOT RUN.
- Module matrix in section 12 remains unchanged; passing tests do not supersede critical/high findings.
- Report status remains **AUDIT IN PROGRESS — NOT FINAL** because not every module's full branch surface, all provider contracts, every deployment/operations path, and PostgreSQL acceptance have been independently closed. Production readiness remains **NOT READY**.


## 14. Additional image-engine security and side-effect review — 22 November 2026

### `AUD-IMG-001` HIGH — legacy Git image uploader mutates repository credentials and can push unrelated staged changes (legacy path; active runtime call site not found)
- `image_engine.py:1147-1207` implements `_git_push_image()`. It writes `https://x-access-token:<token>@github.com/<repo>.git` into the persistent `origin` remote via `git remote set-url` (`:1188-1190`). The token therefore becomes part of the repository's local Git configuration and can remain after the process exits. The command's output is captured, but the credential is still persisted on disk until explicitly reset.
- The same method stages the image path (`:1192`) and invokes `git commit` without a pathspec (`:1193`), so any unrelated entries already staged in the shared index can be included in the image commit. It then performs `git pull --rebase` and `git push` (`:1194-1196`) without checking the return codes of the config/add/commit/pull operations before pushing. This creates a second route for unrelated repository mutation and branch publication.
- `image_engine.py:1033-1145` has a separate GitHub REST uploader which writes a new image to the current branch using a write-scoped GitHub token (`:1110-1127`). It is also a repository mutation, although it does not change the remote URL or use the local Git index.
- Call-site tracing: current `main.py:5427-5441` uses `upload_authorized_image(..., upload_fn=ImageUploader().binance_media_upload)`, the Binance presigned-media flow. No call to `binance_square_upload()`, `upload()`, `_git_push_image()`, or `_github_api_upload()` was found in the active main publication path. Thus these are confirmed unsafe legacy APIs, but this audit does **not** claim they are currently executed by the active publication path.
- Tests `tests/test_cloudflare_image_generation.py:158-183` cover only the REST uploader's no-redirect bearer-token transport. There are no tests asserting `_git_push_image()` does not persist credentials, contaminate the index, or push to an unexpected branch.
- Original disposition (superseded by Section 73): disable the legacy repository-upload fallback from production-facing interfaces. The active Binance media path remains separate.

### Active Binance media upload path — positive controls confirmed
- The active caller is `main.py:5427-5441`, which requires the publication authorization and passes the dedicated `binance_media_upload` function.
- `image_engine.py:1463-1504` checks dry-run/publisher-enabled state, authorization integrity, symbol/asset/content/image-hash binding, exact single-image requirement, 10 MiB limit, and copies the authorized bytes into a private temporary snapshot before invoking the upload callback. This prevents a source-file replacement between hash validation and upload.
- `image_engine.py:1262-1264` and `:1410-1441` enforce the presigned URL allowlist, no-redirect transport, bounded upload size and explicit HTTP 200/201 acknowledgment. `:1505-1518` validates the returned media URL against the Binance CDN host before accepting it.
- Existing tests cover redirect refusal, SSRF URL rejection, upload size/status, poll-after-success ordering, final CDN host, and authorization/hash failure. These are useful positive controls; they do not establish a live Binance provider contract or end-to-end production acceptance.

### Scope qualification
- This pass inspected image-engine upload call sites, security checks, and focused tests only. It does not close the full image-engine function/branch review, nor the remaining repository-wide audit completion gate.
- No network call, image upload, Git mutation, commit, push, or real Binance publication was performed.


## 15. Module 9 continuation — trust boundary, PostgreSQL integration and provider transport review (22 November 2026)

### AUD-ONCHAIN-001 — caller-constructible acceptance inputs remain a confirmed trust-boundary weakness
- **Status:** CONFIRMED DESIGN/TRUST-BOUNDARY GAP; no external exploit demonstrated.
- OnChainAssetMapping, OnChainObservation, and OnChainValidationResult are public frozen dataclasses (layer1/onchain.py:50-98). Freezing prevents mutation after construction; it does not authenticate who constructed the object or the source data.
- OnChainIntelligenceEngine.validate() accepts an EligibilityDecision based on caller-supplied fields including status, source, identity_proof_status, a 64-hex-character identity_proof_data_hash, pair strings and timestamps (layer1/onchain.py:223-258). The validator does not recompute the hash against a provider payload or independently retrieve the Binance/CoinGecko evidence.
- Mapping validation checks mapping_status == VERIFIED, a source-type enum and that source_url is syntactically HTTPS (layer1/onchain.py:140-193). It does not enforce a source-host allowlist, fetch/verify the cited mapping record, validate a signed attestation, or enforce an expiry/max age for verified_at.
- Observation validation checks caller-provided provider labels, endpoint ID, hashes, timestamps and finality-reference strings (layer1/onchain.py:270-312). It does not bind the accepted object to a retained raw provider response, response digest, authenticated receipt, or independently queried canonical header in this validation method.
- The positive fixture in tests/test_onchain_intelligence.py:17-28, 45-75 directly constructs a synthetic ELIGIBLE decision with "a" * 64 as the proof hash, a mapping labelled VERIFIED, and a fabricated observation; the test expects ACCEPTED at :77-79. This proves structural validation can accept caller-created evidence-shaped values. It does not prove a malicious external caller can reach this internal API in the deployed process.
- OnChainStore.save_verified() and PostgresOnChainStore.save_verified() rerun this same validator before persistence; they do not independently establish source authenticity. Read paths also trust stored validation status (layer1/onchain.py:388-433; layer1/onchain_postgres.py:623-654).
- **Impact:** the ACCEPTED state currently means the supplied object fields are internally consistent under the configured rules, not that the official-source or provider evidence has been independently authenticated and is reproducible.
- **Required closure:** define a trusted ingestion boundary that creates proof objects only after source-specific verification; persist raw/minimized source payloads or immutable content-addressed evidence with hashes, retrieval timestamps, source identity, expiry and verifier version; enforce official host/contract allowlists and mapping freshness; prevent arbitrary callers from asserting VERIFIED/ACCEPTED state. Add adversarial tests that mutate status, source URL, timestamps and proof hash while keeping other fields plausible.

### AUD-ONCHAIN-002 — mapping provenance lacks host binding and freshness/expiry enforcement
- **Status:** CONFIRMED VALIDATION GAP (carried-forward finding refined).
- source_type is restricted to a small enum, but source_url passes when any HTTPS scheme and non-empty netloc are present (layer1/onchain.py:164-170); no host is tied to the selected source type or network.
- verified_at is parsed and rejected only when more than five minutes in the future (:183-190). An arbitrarily old mapping can still pass _validate_mapping() and list_verified_mappings() (:419-433, with PostgreSQL counterpart layer1/onchain_postgres.py:641-654).
- Aggregation rechecks observation freshness and current eligibility, but it does not impose an age/expiry policy on the mapping source attestation (layer1/onchain_aggregation.py:143-181).
- **Impact:** stale or unrelated HTTPS source references can continue to be labelled VERIFIED indefinitely. The field checks are not reproducible official-source verification.
- **Required closure:** approved source host/path rules per mapping source type/network, payload identity binding, verification timestamp maximum age/expiry, and tests for stale and cross-host references. Do not guess expiry windows; calibrate and document them.

### AUD-ONCHAIN-005 — PostgreSQL stores are not pluggable into current worker/aggregation pipeline
- **Status:** CONFIRMED IMPLEMENTATION/INTERFACE INCOMPATIBILITY; already recorded in PROJECT_CONTEXT.md and MODULES_11_21_GAP_REGISTER.md, reconcile rather than duplicate.
- All four workers enforce concrete SQLite types in constructors: Bitcoin layer1/onchain_bitcoin_worker.py:23-36, EVM :29-43, Solana layer1/onchain_solana_worker.py:18-32, and XRPL layer1/onchain_xrpl_worker.py:26-36.
- OnChainTransferAggregator and its ingestion-store binding similarly require concrete SQLite OnChainStore / OnChainIngestionStore (layer1/onchain_aggregation.py:79-88, 197-212, 400-412).
- PostgreSQL equivalents are separate classes (layer1/onchain_postgres.py:229-240, 564-573) and do not subclass the SQLite stores. Consequently, existing worker and aggregation constructors reject the PostgreSQL adapters.
- PROJECT_CONTEXT.md:2476 and :1347 already record this exact limitation. It is not a new finding and must not be counted twice.
- **Impact:** PostgreSQL persistence implementations cannot currently be substituted into the production ingestion/aggregation worker pipeline without an adapter/interface refactor. Passing PostgreSQL-only persistence tests does not prove end-to-end PostgreSQL ingestion.

### AUD-ONCHAIN-004 — provider HTTP response bodies are read without an explicit byte limit
- **Severity:** MEDIUM (resource-exhaustion hardening gap).
- **Status:** CONFIRMED MISSING RESOURCE BOUND; no observed incident.
- ReadOnlyJsonRpcTransport.get_json() calls response.read() without a maximum (layer1/onchain_providers.py:139-140); call() does the same at :177-178.
- The JSON is decoded only after the entire body is buffered (:155-160, :193-198). Provider pagination bounds requested record counts, but those limits do not cap the actual HTTP response body returned by a remote endpoint.
- Existing transport tests exercise redirects, envelopes and error redaction (tests/test_onchain_providers.py:257-320) but no oversized/chunked response rejection was found in the inspected test inventory.
- **Impact:** a malformed, compromised or unexpectedly large provider response can consume unbounded process memory before schema validation. This is a resilience/resource-exhaustion risk, not an SSRF or credential disclosure finding.
- **Required closure:** bounded streaming reads with a strict per-transport maximum, early Content-Length rejection where present, safe handling of chunked responses, and tests for oversized bodies. Choose limits based on the largest legitimate provider page/transaction response rather than arbitrary tiny values.

### PostgreSQL fresh-process test inventory — correction to earlier gap wording
- The current tests/test_onchain_postgres.py does define fresh-process reopen tests:
  - test_ingestion_checkpoint_and_event_survive_fresh_process_reopen (around lines 125-177).
  - test_verified_onchain_observation_survives_fresh_process_reopen (around lines 179-239).
- Both are in the PostgresOnChainIngestionTests class guarded by @unittest.skipUnless(TEST_DSN, "TEST_POSTGRES_DSN is not configured") (:40-45). They exist as test definitions but were not executed in the 22 November local full-suite run because TEST_POSTGRES_DSN was absent.
- Therefore, the correct status is **fresh-process acceptance tests implemented, execution against the current local snapshot not verified**. Any earlier statement that these tests do not exist is superseded. This does not establish that the current uncommitted version has passed a live PostgreSQL test run.

### Module 9 disposition after this pass
- Core structural validators and SQLite ingestion/reorg journaling have substantial deterministic test coverage.
- Provider adapter response size is unbounded.
- Acceptance evidence is caller-constructible and not source-authenticated.
- Mapping references are not host-bound or age-limited.
- PostgreSQL persistence adapters exist, and fresh-process tests exist, but the worker/aggregation path is still SQLite-concrete and PostgreSQL execution remains environment-gated.
- No provider credentials were read; no external chain provider, PostgreSQL server, production database, migration, or publishing endpoint was contacted.
- Module 9 remains **FAIL / PARTIAL**. No production certification is justified.

## 16. Modules 10 and 12 — event graph conflict resolution and lifecycle evidence boundary (22 November 2026)

### AUD-GRAPH-001 — equal-timestamp relationship conflict resolution prefers weaker status lexicographically
- **Severity:** MEDIUM
- **Status:** CONFIRMED DETERMINISTIC LOGIC DEFECT; isolated local reproduction completed.
- GraphRelationship.validate() allows status values CONFIRMED, POSSIBLE and UNKNOWN (layer1/event_graph.py:114-124).
- EventIntelligenceGraphEngine.build() deduplicates relationships by stable relationship ID. For equal observed_at timestamps it compares (status, confidence) tuples lexicographically (layer1/event_graph.py:229-236).
- Lexical ordering makes UNKNOWN sort above POSSIBLE and CONFIRMED. Therefore, with identical relationship identity, timestamp and confidence, an UNKNOWN edge replaces a CONFIRMED edge.
- Isolated reproduction using two project entities and two RELATED_TO relationships with identical IDs/timestamps/confidence produced: input statuses [CONFIRMED, UNKNOWN], retained status UNKNOWN. No repository files were modified by the reproduction.
- Existing tests/test_event_graph.py has no conflict-resolution test for equal-timestamp differing statuses; inspected grep found no coverage of this tie-break behavior.
- **Impact:** graph output can downgrade a more certain relationship to UNKNOWN based solely on string ordering. This can misrepresent the strongest available edge status in graph consumers.
- **Required closure:** define an explicit semantic status precedence (or reject conflicting duplicate IDs) and add permutation-invariant tests for all status/confidence combinations. Do not infer confidence as a probability; the class explicitly documents it as a deterministic weight.

### AUD-LIFE-001 — direct lifecycle API trusts caller-supplied VERIFIED state and arbitrary resolution evidence reference
- **Severity:** MEDIUM (internal trust-boundary gap; no external caller path demonstrated).
- **Status:** CONFIRMED API-LEVEL VALIDATION GAP; active scheduled runtime uses the safer registry-derived sync path.
- EventLifecycleStore.observe() accepts verification_state as a string and allows resolved/withdrawn transitions when that string is in VERIFIED_STATES and resolution_evidence_id is merely a non-empty string (layer1/event_lifecycle.py:160-185).
- The method does not resolve resolution_evidence_id against a ClaimRegistry, validate a corresponding claim result, or verify that the cited evidence is attributable to the exact event and resolution claim.
- Existing tests/test_event_lifecycle.py:144-175 explicitly demonstrate that an arbitrary string such as evidence:resolution-1 or evidence:withdrawal-1 is sufficient when the caller supplies verification_state=VERIFIED. This tests the current interface contract but does not prove the cited evidence exists or is verified.
- The PostgreSQL counterpart repeats the same caller-provided state/reference pattern (layer1/event_lifecycle_postgres.py:80-110 and transition logic around :160-175).
- Main scheduled runtime calls sync_announcements() with the ClaimRegistry produced by EvidenceVerificationEngine (main.py:5957-5959); it does not pass resolved=True or withdrawn=True in this call. Thus this is not evidence of an active scheduled-run bypass.
- sync_announcements() derives verification state from claim/result associations, but it accepts a generic registry-shaped object and does not itself invoke verify_claim_registry_payload() or validate that each result.claim_id matches the paired claim.claim_id (layer1/event_lifecycle.py:340-400; PostgreSQL counterpart :177-232). The normal main path supplies the verifier's in-memory result; the public method does not enforce that provenance at its boundary.
- **Impact:** other internal callers can create CONFIRMED/RESOLVED/WITHDRAWN lifecycle states by supplying status labels and references rather than verifiable claim evidence. This is an API trust-boundary issue, not proof of external exploitability.
- **Required closure:** make lifecycle transition methods consume a verified, typed claim result/evidence bundle rather than caller-supplied status strings; verify claim/result identity, evidence membership, asset/event scope and source lineage. Keep direct administrative overrides separately authenticated and audited. Add negative tests for fabricated registries, mismatched claim IDs, missing evidence IDs and cross-event resolution evidence.

### Module 10/12 disposition
- EventGraph validates entity/relationship IDs and dangling references, prohibits causal edge types without a causal contract, and constrains relationship confidence to a finite [0,1] value.
- The equal-timestamp status tie-break is a new confirmed defect and remains open.
- EventLifecycle's normal main path derives state from Module 11 results, but the lower-level public transition API trusts caller-supplied verification labels and resolution references.
- Modules 10 and 12 remain PARTIAL; neither is production-certified.
## 17. Module 13 — research package provenance and persistence integrity review (22 November 2026)

### AUD-RESEARCH-001 — research package hash is not recomputed by SQLite/PostgreSQL stores or verified on read
- **Severity:** MEDIUM (data-integrity control gap).
- **Historical status (22 Nov):** CONFIRMED STORE-BOUNDARY GAP; no database tampering or production impact demonstrated. See remediation/verification in Section 81 (24 Nov 2026).
- DeepResearchEngine.build() computes package_hash from a canonical payload of research inputs/outputs (layer1/research_package.py:225-247).
- SQLite ResearchPackageStore.save() serializes asdict(package), removes version/package_id, and stores package_hash and payload without recomputing the hash against the canonical builder payload (layer1/research_package.py:272-321). load_latest() deserializes and returns the payload without validating package_hash.
- PostgreSQL validate_research_package_input() checks that package_hash is lowercase 64-character hex and payload is finite JSON, but does not recompute the digest (layer1/publication_postgres.py:1336-1357). _save_research_package() persists the supplied hash/payload pair, and _load_latest_research_package() returns the stored pair without digest verification (:1359-1417).
- PostgresResearchPackageStore.save() forwards package.package_hash and payload to that store helper (layer1/publication_runtime.py:26-43).
- The current API therefore enforces hash syntax and immutable-key reuse, but not that the hash actually commits to the stored research payload. A corrupted/mismatched hash-payload pair can be stored and later returned as if intact.
- **Impact:** the package hash is not currently an effective corruption-detection check at the persistence boundary. Downstream provenance consumers cannot rely on load_latest() alone to establish payload/hash consistency.
- **Required closure:** define one canonical hash payload contract excluding package_id/version/package_hash; recompute and compare before insert; recompute on every load; add SQLite and PostgreSQL tests for mismatched hash, altered stored payload and serializer consistency. If malicious database-writer tampering is in scope, use an authenticated MAC/signature with key separation; an unkeyed digest alone cannot authenticate an authorized database writer.

### AUD-RESEARCH-002 — research builder trusts typed ClaimRegistry state without validating its origin or registry digest
- **Severity:** MEDIUM (internal trust-boundary gap; no external caller path demonstrated).
- **Status:** CONFIRMED API-LEVEL TRUST ASSUMPTION.
- DeepResearchEngine.build() requires isinstance(registry, ClaimRegistry), then builds result_by_id directly from registry.results and consumes registry.claims/evidence_records (layer1/research_package.py:112-160). It does not rerun EvidenceVerificationEngine.verify(), validate that every result.claim_id has exactly one matching claim, or verify a persisted registry digest at this boundary.
- ClaimRegistry is a public frozen dataclass with public constructor (layer1/evidence_verification.py:278-294); callers can construct a registry-shaped object and ClaimVerificationResult values without running EvidenceVerificationEngine.verify().
- The normal main.py path builds the registry with EvidenceVerificationEngine().rebuild_from_store() before calling DeepResearchEngine.build() (main.py:4643-4649, :4725-4732). Thus this is a boundary hardening issue, not evidence that the normal scheduled path currently supplies fabricated results.
- **Impact:** callers that can invoke the research builder directly can label claims VERIFIED/CORROBORATED through constructed registry objects. Typed shape alone is not proof that the verifier produced the results.
- **Required closure:** accept a verifier-issued immutable/opaque registry handle or validate registry consistency and an authenticated verification snapshot at the builder boundary. Add negative tests for manually constructed results, duplicate/mismatched claim IDs, missing evidence records and altered registry contents.

### Module 13 disposition
- Research package selection applies canonical asset scope, cutoff-time filtering, latest-claim selection and source-kind coverage gaps; non-factual claims are separated from verified facts.
- Persistence versioning is append-only/idempotent by research key and package hash, but the package hash is not recomputed on save/load.
- Registry trust remains an internal caller assumption at the builder boundary.
- Module 13 remains PARTIAL; reproducible persistence integrity and production source completeness are not certified.
## 18. Module 15 — DeepSeek transport resource-bound review (22 November 2026)

### AUD-LLM-001 — DeepSeek response body is buffered without an explicit byte limit
- **Severity:** MEDIUM (resource-exhaustion hardening gap).
- **Status:** CONFIRMED MISSING RESOURCE BOUND; no observed provider incident.
- DeepSeekClient._fetch() reads the complete HTTP response with response.read() (`layer1/deepseek_client.py:109-114`) and returns the full byte string before JSON decoding.
- chat() then decodes the entire body (`:169-176`) and validates the expected completion schema. The configured max_tokens bounds requested generation tokens, but it does not impose a transport-level maximum on the received HTTP body.
- The default endpoint is restricted to the official DeepSeek HTTPS origin and redirects are rejected; those are positive controls, but they do not bound response memory use.
- Existing tests/test_deepseek_client.py cover request contract, timeout/retry, redirect and malformed response behavior. No oversized or chunked response-body rejection test was found in the inspected test inventory.
- **Impact:** a malformed or unexpectedly large response can be fully buffered in memory before validation, creating a process resource-exhaustion risk. This is not a credential-forwarding or provider-origin bypass finding.
- **Required closure:** implement a bounded streaming read, reject excessive Content-Length when present, enforce a hard byte cap for chunked responses, and add oversized-body tests. Set the cap based on expected maximum completion and protocol overhead.

### Module 15 disposition update
- Official DeepSeek origin restriction, redirect refusal, bounded retry count, request-model allowlist and response envelope validation are positive controls.
- No live authenticated DeepSeek request was performed in this audit.
- Unbounded response buffering remains a medium hardening gap. Module 15 remains PARTIAL.
## 19. Module 16 — editorial brief identity and persistence integrity review (22 November 2026)

### AUD-EDITORIAL-001 — editorial brief hash is format-checked but not recomputed or verified on persistence/read
- **Severity:** MEDIUM (data-integrity control gap).
- **Status:** CONFIRMED STORE-BOUNDARY GAP; no production tampering demonstrated.
- EditorialStrategyEngine.build() computes brief_hash from a canonical payload containing event/angle identity, research package ID, outline, approved claims, prohibited claims, uncertainty notes, status and policy version (layer1/editorial_strategy.py:198-234).
- SQLite EditorialBriefStore.save() checks only status == READY, then uses the caller-provided brief_hash for idempotency/version identity and stores asdict(saved) without recomputing the hash against the canonical brief payload (layer1/editorial_strategy.py:109-139).
- PostgreSQL _validate_editorial_brief_input() verifies that brief_hash is a lowercase 64-character hex string and payload is finite JSON, but does not recompute the digest (layer1/publication_postgres.py:1426-1438). _save_editorial_brief() persists the supplied hash/payload pair, and _load_latest_editorial_brief() returns it without digest verification (:1441-1496).
- PostgresEditorialBriefStore.save() forwards brief.brief_hash and the dataclass payload to the PostgreSQL store (layer1/publication_runtime.py:48-66).
- **Impact:** the brief hash is not currently a reliable payload-integrity check at the storage boundary. An internally constructed READY brief with an unrelated well-formed hash can be stored; a mismatched stored payload/hash pair is not detected on load.
- **Required closure:** define a canonical brief-hash payload excluding generated ID/version metadata; recompute and compare before persistence and on every read; add SQLite/PostgreSQL mismatch and tamper tests. Keep database-writer authenticity separate from unkeyed digest integrity.

### Module 16 disposition
- Editorial strategy selects a deterministic format/angle from typed research-package contents and carries approved claim IDs, prohibited claims and uncertainty notes into the brief.
- The builder trusts ResearchPackage.completeness == READY and does not independently validate the package hash; this remains within the internal typed-object trust assumption recorded under AUD-RESEARCH-002.
- Editorial brief persistence has a separate hash-verification gap, now recorded as AUD-EDITORIAL-001.
- Module 16 remains PARTIAL.

## 20. Module 11 — evidence authority, independence and verification-boundary audit (22 November 2026)

### AUD-EVID-001 — caller-controlled provenance flags can manufacture primary verification or independent corroboration
- **Severity:** MEDIUM (public/internal API trust-boundary weakness; no external exploit path in the scheduled runtime was demonstrated).
- **Status:** CONFIRMED BY ISOLATED REPRODUCTIONS.
- `EvidenceRecord` is a public frozen dataclass. Its caller supplies `source_kind`, `publisher`, `source_family`, `source_url`, `lineage_id`, `source_status` and `is_primary` (layer1/evidence_verification.py:128-184). `validate()` checks basic types, enums, URL syntax and digest format, but does not bind those fields to a trusted provider identity, source host, endpoint, or verifier-issued ingestion receipt.
- `EvidenceVerificationEngine.verify()` accepts arbitrary `EvidenceRecord` instances and uses their caller-supplied `source_status` and `is_primary` when selecting support (lines 332-366 and 542-710). It does not require `source_kind == PRIMARY` when `is_primary=True`, nor independently resolve publisher/source-family authority.
- Isolated reproduction 1: constructed one evidence record with `source_kind=SECONDARY`, publisher `Unapproved Publisher`, source URL `https://attacker.example/data`, `source_status=ACCEPTED`, and `is_primary=True`. A matching medium-impact `CONFIRMED_FACT` claim returned **VERIFIED**, with no issues.
- Isolated reproduction 2: constructed two records with the same unapproved publisher, both `source_kind=SECONDARY` and `is_primary=False`, but caller-selected source families `alias-a` and `alias-b`. A claim linked to only one record returned **CORROBORATED** with `independent_source_count=2`. The independence counter unions records by the supplied lineage/content/source-family tokens (lines 776-808); it does not independently validate that distinct family names represent distinct publishers or ownership.
- **Positive controls / scope:** the official Binance announcement adapter calls `AnnouncementEvidence.validate()`, which requires publisher Binance and an approved HTTPS Binance host (layer1/foundation.py:1261-1276). The market-observation adapter deliberately sets `is_primary=False` because provider labels are caller-controlled (layer1/evidence_verification.py:974-1010). The normal scheduled workflow obtains observations through internal provider engines. No external endpoint accepting arbitrary `EvidenceRecord` payloads was identified in this audit.
- **Impact:** any internal caller that can construct evidence objects can assert ACCEPTED/PRIMARY status or manufacture two apparent independent source families. The verifier's output is therefore only as trustworthy as the caller that constructed the objects; its type and field validation do not establish source authenticity.
- **Required closure:** make authority a verifier-owned policy keyed by canonical provider identity, approved endpoint/host, supported claim fields and source class. Derive acceptance/primary status inside trusted adapters rather than accepting caller flags. Use canonical provider IDs and validated ownership/syndication lineage for independence; reject unknown provider aliases. Prefer verifier-issued opaque evidence handles or signed ingestion receipts at any boundary that accepts data from outside the trusted ingestion path. Add negative tests for SECONDARY+primary, unapproved host, forged ACCEPTED status, same-publisher/different-family aliases, and fabricated corroboration.
- **No fix applied in this audit pass:** changing the source authority policy without an owner-approved provider registry and source-to-field mapping would invent trust rules. Existing adapters and their passing tests were left unchanged.

### Module 11 verification and disposition
- Focused existing test run: `python -m unittest tests.test_evidence_verification tests.test_source_adapter_contracts -v` — **87 tests passed, 0 failed**.
- Additional isolated adversarial reproductions confirmed the two trust-boundary outcomes above; they were run as inline scripts and did not modify repository files.
- Positive controls verified in code: cross-asset evidence scoping; exact structured field/value/unit/timeframe/event matching; timestamp cutoff and optional max-age checks; stale evidence rejection; contradiction detection; conservative lineage-based syndication grouping; bounded deterministic compound/causal checks; exact announcement-body/title attribution; and SQLite snapshot digest verification.
- Existing limitations remain: the sentence splitter is a bounded deterministic grammar, not general semantic entailment; ambiguous elliptical/compound forms remain unresolved; claim/result objects and registries are publicly constructible; PostgreSQL snapshot execution depends on the configured integration test DSN. Do not interpret 87 focused tests as complete Module 11 acceptance.
- Module 11 remains **PARTIAL / NOT PRODUCTION-CERTIFIED**. No live provider request, production database write, Binance post, publisher activation, merge or deployment was performed.


## 21. Module 17 — draft versioning and validation-ledger audit (22 November 2026)

### AUD-DRAFT-001 — publication authorization can select an older PASS when validation timestamps tie
- **Severity:** MEDIUM (fail-open ordering defect in the final authorization read).
- **Status:** CONFIRMED BY DETERMINISTIC REPRODUCTION.
- DraftStore.latest_text_validation() and visual_validation() use `ORDER BY created_at DESC, rowid DESC` on SQLite (layer1/content_generation.py:327-341), so the last inserted record wins when timestamps tie. The existing `test_latest_validation_uses_insertion_order_when_timestamps_tie` covers these helper methods.
- The actual SQLite PublicationAuthorizationEngine does not use that helper for the final gate. It reads `content_draft_validation_results` using `ORDER BY created_at DESC, validation_id DESC` (layer1/publication_authorization.py:271-276); its visual-validation query uses the same non-sequential tie-break (lines 278-288).
- PostgreSQL publication authorization and media revalidation also use `ORDER BY created_at DESC, validation_id DESC` for text/visual validation records (layer1/publication_postgres.py:489-504 and :875-884). The validation_id is a deterministic SHA-256 digest of the validation payload, not an insertion sequence; lexicographic order has no temporal meaning.
- Deterministic SQLite reproduction: inserted PASS first with validation_id `ffff…`, then REJECT with validation_id `aaaa…`, both at the exact same created_at. DraftStore.latest_text_validation() correctly returned **REJECT** (rowid DESC), while the SQL used by PublicationAuthorizationEngine returned **PASS** (validation_id DESC). This demonstrates the final gate can disagree with the latest ledger decision.
- **Impact:** if validation timestamps collide, a later REJECT/NEEDS_REVISION can be hidden by an earlier PASS and the publication authorization path can accept stale approval. Timestamp ties are uncommon with microsecond clocks but are explicitly within the tested persistence contract and can occur under coarse clocks/concurrent writes/imported records.
- **Required closure:** persist a monotonic validation sequence/identity for both SQLite and PostgreSQL and use that same sequence in helper reads, authorization, revalidation and recovery. Do not use a content-derived hash as a chronology key. Add tests against the actual authorization and PostgreSQL final-gate queries with tied timestamps and PASS-then-REJECT / PASS-then-NEEDS_REVISION orderings.
- **No code change applied in this audit pass:** the PostgreSQL ordering fix requires a schema/migration decision and coordinated changes to all final-gate reads; changing only the SQLite helper would leave the production PostgreSQL path inconsistent.

### Module 17 verification and disposition
- Focused existing test run: `python -m unittest tests.test_content_generation -v` — **11 tests passed, 0 failed**.
- Drafts are append-only by asset/editorial brief key; exact content hashes are stored before text validation; identical draft hashes cannot be rebound to different research/brief/claim provenance. PostgreSQL draft insertion additionally checks that the persisted editorial brief belongs to the supplied research package.
- The final authorization path compares the exact draft content/hash and editorial brief/package binding. The newly confirmed validation-order mismatch remains open.
- Module 17 remains **PARTIAL** until validation chronology is consistent across the helper and final authorization paths and all Module 18 acceptance requirements are independently audited.


## 22. Module 18 — deterministic content-verification policy and editorial-boundary audit (22 November 2026)

### AUD-CONTENT-001 — content verification accepts verified claims outside the approved editorial brief
- **Severity:** MEDIUM (editorial-scope enforcement gap; factual evidence may be valid but the approved editorial policy can be bypassed).
- **Status:** CONFIRMED BY ISOLATED REPRODUCTION AND CALL-PATH INSPECTION.
- EditorialBrief stores `approved_claim_ids` and `prohibited_claims` (layer1/editorial_strategy.py:38-45); its renderer explicitly includes both lists (lines 68-76).
- Main calls `ContentVerificationEngine.validate()` with the full asset-scoped ClaimRegistry, symbol and asset ID, but does not pass the EditorialBrief or its approved/prohibited claim policy (main.py:5183-5191). The engine builds `verified_by_id` from every VERIFIED/CORROBORATED claim in that registry and approves any exactly attributed one (layer1/content_verification.py:54-139).
- The resulting claim IDs are persisted directly from `content_verification.approved_claim_ids` (main.py:5200-5205).
- SQLite and PostgreSQL publication authorization verify the draft's editorial brief ID and research-package binding, but the inspected authorization queries load only the brief's event/package identity; they do not compare the draft's claim IDs with the brief's `approved_claim_ids` or prohibited-claim list (layer1/publication_authorization.py:248-269; layer1/publication_runtime.py:176-185).
- Isolated reproduction: registry contained two individually VERIFIED claims (price and 24h change); the simulated EditorialBrief approved only the price claim. A draft referencing only the 24h-change claim returned **PASS** and persisted that non-approved claim ID in the result. The content validator has no brief-policy input, so the brief's allowlist cannot constrain it.
- **Impact:** DeepSeek can use a claim that is evidence-backed but outside the approved angle/scope or explicitly prohibited by the editorial brief. The current model prompt asks the model to follow the brief, but deterministic content validation and publication authorization do not enforce that boundary.
- **Required closure:** pass an immutable persisted EditorialBrief policy into content validation; require every referenced claim ID to be in its approved allowlist and absent from prohibited claims; bind the exact brief policy/hash to the draft. Repeat the subset check in SQLite and PostgreSQL authorization/final submission so the model and draft writer cannot bypass it. Add negative tests for unapproved and prohibited verified claims at validation, persistence and final authorization.

### AUD-CONTENT-002 — SOURCE_ASSERTION can pass without publisher attribution in the published text
- **Severity:** MEDIUM (source-meaning and attribution fidelity gap).
- **Status:** CONFIRMED BY ISOLATED REPRODUCTION.
- Module 11 deliberately distinguishes SOURCE_ASSERTION from independently established truth and renders the actual supporting publishers with an instruction to attribute the source assertion (layer1/evidence_verification.py:1761-1797).
- ContentVerificationEngine validates only that the sentence text exactly matches a VERIFIED/CORROBORATED claim. It does not inspect `claim.claim_type`, supporting publisher identities or whether the final sentence attributes a SOURCE_ASSERTION to that publisher (layer1/content_verification.py:103-139).
- Isolated reproduction: an official Binance AnnouncementEvidence body containing `$ABC will list at 12:00 UTC.` was adapted to a primary SOURCE_ASSERTION claim. A draft containing the exact `Detail: $ABC will list at 12:00 UTC.` claim text, with no Binance attribution, returned **PASS**. The cleaned output did not contain the publisher name. The source record was correctly attributable to Binance; the failure is in the final-text attribution gate.
- **Impact:** a statement that the evidence system classifies only as “the named source asserted this” can be emitted as an unqualified fact. This contradicts the explicit Module 11 rendering contract and the Module 18 requirement to preserve source meaning.
- **Required closure:** make source attribution part of the claim's canonical publishable text or add a deterministic attribution contract that binds each SOURCE_ASSERTION to its publisher and verifies the final sentence. Do not rely solely on the model prompt. Add tests for official announcements and secondary-source assertions, including missing, wrong and misleading publisher attribution.

### Module 18 additional acceptance gaps
- `TRADE_INSTRUCTION_PATTERNS` is a bounded regex list, not a complete semantic policy for personalized buy/sell/entry/exit advice, guarantees or manipulative wording. The current tests cover a few explicit phrases only; this cannot certify all natural-language variants.
- The DeepSeek prompt asks for 80–110 words and exactly four hashtags, but the deterministic validator does not enforce those bounds. The later main.py quality gate checks only configured minimum word count and minimum hashtag count; it does not enforce a maximum word count or exactly four hashtags. EditorialBrief min/max word limits are not supplied to ContentVerificationEngine.
- At the time of this audit snapshot, ContentVerificationEngine accepted any publicly constructed `ClaimRegistry`. Corrected on 24 Nov 2026: `ContentVerificationEngine.validate()` now requires the same verifier-issued, unchanged registry proof as `DeepResearchEngine.build()` (see Sections 61 and 63). EvidenceRecord source authenticity remains separately open under AUD-EVID-001.
- Focused existing test run: `python -m unittest tests.test_content_verification -v` — **15 tests passed, 0 failed**. The two reproductions above were separate inline scripts and did not modify repository files.
- Module 18 remains **PARTIAL / NOT PRODUCTION-CERTIFIED**. Exact claim attribution, ticker binding, cross-asset scoping, causal-claim rejection and unresolved-claim blocking are positive controls, but editorial allowlist enforcement and source attribution remain open.
- No live model call, production database write, Binance post, publisher activation, merge or deployment was performed.

## 23. Module 19 — Cloudflare Workers AI image-generation implementation audit (22 November 2026)

### Official provider contract cross-check
- The current official Cloudflare Workers AI model page lists @cf/black-forest-labs/flux-2-klein-4b as a Cloudflare-hosted Black Forest Labs text-to-image model and documents its Base64 image output. The page lists $0.000287 per output 512x512 tile and $0.000059 per input tile: https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/
- Cloudflare's 15 January 2026 launch documentation specifies the exact REST endpoint used by this implementation, multipart form data, prompt, width and height, a 256–1920 range for each dimension, and a fixed four-step inference process (no caller-adjustable steps): https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/
- The implementation's model ID, endpoint, multipart boundary construction and 1024x1024 dimensions match that official contract. It correctly does not send a steps parameter.
- **Cost estimate:** one 1024x1024 output covers four 512x512 output tiles. At the listed $0.000287/output-tile rate, estimated model output cost is approximately **$0.001148 per generated raw image**, excluding any account-specific billing adjustments or future price changes. No input image is used in the current prompt.
- The model page also identifies the model as a partner model and marks zero data retention in the current model listing. Verify account-level entitlements and applicable model terms before production use.

### Module 19 positive controls
- Direct REST call to Cloudflare's official account-scoped Workers AI endpoint; no image-generation aggregator.
- Bearer token is sent only to the official Cloudflare HTTPS endpoint; redirect-following is disabled.
- Prompt length and output dimensions are bounded; response body is read with a 20 MiB + 1 byte ceiling before rejecting overflow.
- Supports documented Base64 JSON image output and direct image responses; validates actual decodable bytes, decoded pixel count, dimensions, supported format and output-extension match.
- Final file is written through a temporary file and atomic replace; SHA-256, byte length, dimensions, format, model, request ID and generation timestamp are returned.
- Active ImageComposer prompt is intentionally generic and contains no ticker, price, chart, logo or factual claim. It overlays only deterministic MARKET UPDATE and the canonical ticker with Pillow; metadata records the prompt hash, raw-image hash, final-image hash, exact draft hash, dimensions and overlay geometry.
- The active main.py path calls ImageComposer. The legacy ImageIntelligenceEngine.generate() renderer remains in image_engine.py but is not called by the current main.py publication path; it still supports a separate trade-setup/confidence visual path and should not be mistaken for the active safe image pipeline. Its chart renderer requires supplied history of at least five points and otherwise shows a history-required label.

### Module 19 disposition
- No code defect was confirmed in the inspected active Cloudflare request/response path against the current official provider contract.
- No authenticated Cloudflare inference, account permission check, quota check, billing check or production image generation was performed. Official documentation confirms the model and API contract, not this account's access or successful runtime execution.
- Local image-generation tests could not run: the active RDC Python interpreter and the checked existing virtual environment both lack Pillow (ModuleNotFoundError: No module named 'PIL'). No package was installed and no environment was modified to work around this.
- Module 19 remains **PARTIAL / NOT PRODUCTION-CERTIFIED** pending a separately approved, non-publishing provider smoke test, account access confirmation, actual image artifact persistence and full image test execution.

## 24. Module 20 — visual QA and deterministic overlay verification audit (22 November 2026)

### Reconfirmation of existing AUD-VIS-001 (Section 13) — no duplicate finding added
- Historical reproduction: the sidecar claimed text/geometry while the test image was solid-color. Section 76 records the local pixel-grounded remediation; the old fixture was replaced with actual rendered glyph pixels.
- The active ImageComposer now records the approved font identity/hash and exact overlay origins. visual-quality-v3 independently re-renders the glyph mask and compares it with the final image pixels, so a blank/replaced/shifted overlay cannot pass with a self-consistent sidecar. The validator still does not OCR or semantically inspect the AI-generated background for unrelated text/logos/charts.
- This section is a Module 20 continuation note only. Section 13 remains the canonical finding and severity record; no second visual-QA finding is counted.

### Module 20 positive controls and disposition
- Exact 10 MiB image and 1 MiB sidecar read limits; 2,000,000 decoded-pixel cap checked before image loading; corrupt/decompression-bomb images fail closed.
- Requires exact 1080x1350 PNG, exact canonical asset/ticker, approved Cloudflare model, matching final-image and draft hashes, prompt hash format, generation-parameter bounds and deterministic overlay metadata.
- Rejects chart data references and numeric overlays unless absent; checks overlay boxes, minimum font size, conservative contrast, clipping and overlap.
- Visual test inventory now includes blank-image-with-matching-hash rejection, shifted-text rejection, solid-fill-rectangle rejection, font-fingerprint mismatch, draft/image mismatch, tampered hash, malformed sidecar, geometry/contrast/clipping, oversized-file, pixel-limit and decompression-bomb cases. Focused tests.test_visual_quality: **20 passed**.
- Module 20 remains **PARTIAL / NOT PRODUCTION-CERTIFIED**: deterministic overlay pixels are locally verified, but generated-background text/logo/chart detection and live Cloudflare artifact/provider acceptance remain open.
- No live image upload, Binance publication, merge or deployment was performed.


## 25. Git history-sync correction and retry recovery re-audit — 22 November 2026

### Superseding status for AUD-GIT-001 and AUD-GIT-002
- AUD-GIT-001: the original detached-HEAD-to-main fallback is **PARTIALLY CLOSED** in the active main.py history-sync helper. Current code rejects empty, HEAD, unknown and main before add/commit/push; focused mocked tests passed. The helper still does not enforce an explicit trusted workflow-ref allowlist, so retain PARTIAL status rather than claiming full workflow branch authorization.
- AUD-GIT-002: the active _try_git_push() index-contamination path is **CLOSED**. The commit now uses the explicit pathspec -- _POST_HISTORY_FILE posts/. An isolated temporary Git repository with an unrelated pre-staged source.py confirmed that the commit contains only published_posts.jsonl and leaves source.py staged. The legacy ImageUploader._git_push_image() path remains separately tracked under AUD-IMG-001 and is not included in this closure.
- Commit ec90e9ab4ed937e7b7c55f0722ec7a95f8f56b11 was pushed to the existing PR #14 branch. GitHub confirmed that exact head SHA and two hosted checks passed: mocked-safety-tests and isolated PostgreSQL integration acceptance. No duplicate PR was created.

### AUD-GIT-003 — committed-but-unpushed history is not detected by startup retry; clean-index path reports false success
- **Severity:** HIGH
- **Status:** CONFIRMED BY ISOLATED TEMPORARY-REPOSITORY REPRODUCTION.
- _try_git_push() returns True immediately when the path-scoped commit reports “nothing to commit”; it does not first verify whether local HEAD is already ahead of origin or whether the remote already contains HEAD (main.py:764-776).
- If a prior run successfully creates the history commit but the subsequent push fails, the worktree becomes clean while local HEAD remains ahead of origin. On the next run, _retry_pending_push() checks only git status --porcelain for the history file and posts/ (main.py:860-882). With a clean worktree it returns False and never checks the ahead-of-remote commit or retries the push.
- Isolated reproduction used a temporary local repository and a synthetic origin tracking ref: after a history-only commit was created locally while origin tracking remained at the previous commit, the worktree was clean, local HEAD was ahead, _retry_pending_push() returned False, and the tracking ref remained unchanged. No user repository, real remote or credential was used.
- **Impact:** publication history can remain committed locally but absent from GitHub after a transient push failure. The startup recovery helper then reports no work to retry. This can leave remote history stale and undermine duplicate/cooldown protection on later isolated workflow runners.
- **Required closure:** startup recovery must detect both uncommitted history changes and local commits ahead of the exact upstream branch. Before pushing ahead commits, verify their diff contains only approved history paths and fail closed on unknown/missing upstream. A “nothing to commit” result is not success until remote synchronization is verified. Add temporary-repository tests for commit-success/push-failure/restart, clean worktree ahead-of-origin, branch mismatch, and history-only ahead commits. Preserve unrelated staged and committed user changes.
- **No fix applied:** this recovery change needs a deliberate upstream/ref policy and commit-tree verification; it was documented, not modified during this audit continuation.

### Current Git-safety disposition
- Active _try_git_push(): branch guard and path-scoped commit protections are present; focused 4/4 tests passed; exact commit is on PR #14.
- Startup retry of already-committed-but-unpushed history remains **OPEN** (AUD-GIT-003).
- Legacy ImageUploader Git/REST repository upload fallbacks remain separately recorded as legacy unsafe paths; active main publication uses the authorized Binance media upload flow.


## 26. Module 21 — final publication, persistence and recovery audit (22 November 2026)

### Audit checkpoint and preservation
- Revalidated the existing worktree `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `ec90e9ab4ed937e7b7c55f0722ec7a95f8f56b11`.
- Existing modified and untracked files were preserved. No source-code repair, database migration/write, provider call, deployment, publisher activation or live Binance publication was performed in this pass.
- GitHub PR #14 remains OPEN / DRAFT / UNMERGED. Its head SHA matches the above commit. The two hosted checks on that commit (`mocked-safety-tests` and `Isolated PostgreSQL integration acceptance`) are SUCCESS. They validate the committed snapshot, not the separate uncommitted worktree modifications listed in Section 2.

### AUD-MAIN-001 — persistence-integrity verification still fails open
- **Latest status:** OPEN — CRITICAL; independently reconfirmed against current worktree.
- Current implementation remains at `main.py:892-1021`. For a missing history file, the code treats empty `git log` stdout as “never committed” without checking `returncode`; for an empty file, a `git log` timeout or generic exception returns `True` (`:966-971`); the missing-file timeout/error path also returns `True` (`:1016-1021`). The `git show` restoration branch likewise does not validate its command return code before treating empty output as a fresh empty history.
- Isolated reproduction with a temporary missing file and synthetic `git log` exit code 128 (`fatal: not a git repository`) returned `True` and created an empty history file. A second reproduction with an empty file and synthetic Git timeout also returned `True`. No real Git repository or user data was modified by either reproduction.
- A non-empty file is accepted on byte size alone (`:912-916`); malformed/truncated JSONL is not proven complete by that check. This remains an additional integrity gap within the same finding.
- **Closure:** make every Git verification error/timeout/nonzero exit a blocked result; validate restored Git content and every JSONL record; only allow first-run initialization after positively proving there is no tracked history and the repository/ref state is valid. Add direct tests for missing/empty/corrupt files, nonzero Git exits, timeouts and restore failures; prove `_run_once_impl` cannot reach publication on any uncertain state.

### AUD-MAIN-002 — one-shot scheduled entrypoint still omits trend intelligence
- **Latest status:** OPEN — HIGH; reconfirmed.
- `.github/workflows/run_bot.yml:61-72` selects one-shot execution (`POST_INTERVAL=0`, `MAX_ITERATIONS=1`, `python main.py`). `main()` constructs `HotSearchEngine` at `main.py:6291` but calls `run_once(...)` at `:6300` without passing it. The continuous `main_loop()` passes the engine at `:6253`.
- Isolated `main.main()` invocation with all provider/publisher constructors replaced by inert fakes captured seven positional arguments to `run_once` and no `hot_search_engine` keyword. No provider HTTP, model call or publication was made.
- **Closure:** pass `hot_search_engine=hot_search_engine` in the one-shot call and add a regression test that verifies the trend provider reaches the Layer 1 persistence/orchestration path. This is a small, isolated code fix but was not applied during this audit-only pass.

### AUD-PUB-001 — SQLite final authorization remains vulnerable to a TOCTOU race
- **Latest status:** OPEN — HIGH; current code-path inspection reconfirms.
- SQLite pre-submit checks call `validate_persisted_event_binding()` and `validate_persisted_duplicate_policy()` at `main.py:4188-4209`, then construct and send the POST at `:4210-4234`. The SQLite validation transactions complete before network dispatch; no serialization/fencing context spans the checks and request.
- The PostgreSQL path differs: `main.py:4353-4372` wraps the bounded POST in `authorized_submission_guard()`. `layer1/publication_postgres.py:378-416` holds symbol/event advisory locks and revalidates persisted authorization/provenance within the outer transaction, including the `NO_EVENT` case.
- **Impact:** a concurrent SQLite process can mutate event lifecycle or duplicate-policy state after the final check but before the POST. The SQLite path therefore lacks the concurrency guarantee present in the PostgreSQL path.
- **Closure:** design and test a SQLite-safe fencing/serialization mechanism for existing-event and `NO_EVENT` cases, with multi-connection/process races injected exactly between validation and dispatch. Do not simply hold a long write transaction over network I/O without proving lock/busy-timeout/crash behavior.

### AUD-PUB-002 — SQLite attempt finalization still accepts a missing/released quota row
- **Latest status:** OPEN — HIGH; independently reproduced against current code.
- `main.py:3912-3978` updates the publication attempt first, then checks the quota table. When the quota table exists, a missing reservation or `RELEASED` reservation returns normally at `:3962-3963`; the transaction therefore commits the attempt's new terminal/unknown status without a matching active quota ledger transition. The legacy no-quota-table branch at `:3954-3957` is separately documented, but the normal authorized path creates the quota schema and binds the attempt before submission.
- PostgreSQL `finish_authorized_attempt()` is stricter (`layer1/publication_postgres.py:527-542`): it requires a reservation and validates the quota state transition before updating either row.
- Isolated SQLite reproduction used a temporary test database and synthetic draft/authorization only: after binding an attempt to a quota reservation and changing that reservation to `RELEASED`, `_finish_attempt(..., 'PUBLISHED_CONFIRMED')` returned successfully. Persisted state became `publication_attempts.status=PUBLISHED_CONFIRMED` while `publication_quota_reservations.status=RELEASED`. No Binance request was made.
- **Closure:** in authorized attempts, require exactly one quota reservation bound to the attempt; reject missing/RELEASED/illegal states and let the whole transaction roll back. Keep any legacy ledger-only helper on an explicitly separate path that cannot be reached from authorized publishing. Add tests for missing, released and concurrently changed quota rows for each final status.

### AUD-M21-001 — PostgreSQL durability/recovery remains partially accepted, not production-certified
- **Latest status:** PARTIAL / OPEN — HIGH.
- Positive implementation controls inspected: PostgreSQL backend selection refuses silent SQLite fallback; runtime verifies expected migration checksums before constructing the store (`main.py:6169-6177`); run lease acquisition serializes the singleton lease with an advisory lock (`layer1/publication_postgres.py:1204-1233`); crash recovery requires explicit process-termination confirmation, expected run ID, operator identity and evidence, and never steals a lease based on age (`:1235-1293`); terminal lease finish updates the run and removes only the matching lease in one transaction (`:1295-1329`). Publication attempt reconciliation and quota state transitions are transactionally fenced in the PostgreSQL store.
- Test inventory includes fresh-process crash/recovery, process-kill rollback, lease serialization, unknown-attempt reconciliation, quota concurrency and the authorized-submission guard (`tests/test_publication_postgres.py`). The scheduled PostgreSQL acceptance suite has two real `run_once` acceptance tests (`tests/test_scheduled_postgres_acceptance.py`).
- **Execution limitation:** `TEST_POSTGRES_DSN`, `POSTGRES_DSN` and `ANNOUNCEMENT_DATABASE_URL` were all absent in the RDC environment (only presence booleans were checked; no secret values were read). PostgreSQL integration and scheduled acceptance tests are therefore DSN-gated and were not run against a database in this pass. The six pure PostgreSQL state-machine tests passed, but they do not prove real database locking, migrations, crash recovery or fresh-process durability.
- **Closure:** run the isolated PostgreSQL migration, scheduled-entrypoint, concurrent authorization, crash/process-kill and unknown-outcome reconciliation acceptance suites against an explicitly approved disposable test database; capture exact test output and database target identity without exposing DSNs. Then perform separately approved operator recovery and restore drills. Production DB access and migrations remain outside this audit authorization.

### AUD-GIT-003 — committed-but-unpushed history is not recovered
- **Latest status:** OPEN — HIGH; prior isolated temporary-repository reproduction remains valid.
- `_try_git_push()` still treats “nothing to commit” as success at `main.py:765-771` without verifying upstream synchronization. `_retry_pending_push()` checks only uncommitted status at `:867-884`; a clean worktree with local HEAD ahead of origin returns `False` at `:874-876` and never retries the push.
- **Closure:** inspect exact upstream/ref, detect ahead commits as well as dirty history files, verify every ahead commit touches only approved history paths, fail closed for missing/ambiguous upstream, and verify remote synchronization before reporting success. Add restart tests for commit-success/push-failure, clean-ahead state, branch mismatch and unrelated committed changes.

### Module 21 test and verification record
- Focused safe tests executed with an import-only Pillow shim (image operations were not exercised): **16 passed, 0 failed** across selected SQLite publisher-safety tests, selected scheduled lease tests and the reconciliation CLI tests. The shim was temporary under `/tmp`; no package was installed and no repository file was changed by it.
- Pure PostgreSQL state-machine tests: **6 passed, 0 failed**. These are unit tests only; no PostgreSQL DSN was available.
- A broader combined test attempt discovered/ran 66 tests but ended with **13 import errors** because Pillow (`PIL`) is missing in the RDC Python environment, plus **28 DSN-gated skips**. Do not report that combined attempt as passing. Image-dependent tests were not executed.
- `git diff --check`: PASS. `python -m compileall -q layer1 tests main.py image_engine.py`: PASS.
- No code, migration, database, provider or publishing configuration was changed. Only this audit report was appended.

### Module 21 disposition
- Module 21 is **FAIL / PARTIAL — NOT PRODUCTION-CERTIFIED**. Critical fail-open persistence integrity and high-severity SQLite publication race/quota consistency defects remain open. PostgreSQL durability has positive code and test design, but live isolated DB acceptance is unavailable in this environment. Operator recovery remains manual/explicit by design; it is not an automatic stale-lease timeout.


## 27. Consolidated blocker register — latest reconciled status (22 November 2026)

This register is authoritative over earlier duplicate/stale status text in the report. It contains **35 unique finding IDs**; repeated references to the same ID are one finding, not additional blockers.

| Finding ID | Severity | Latest disposition |
|---|---:|---|
| AUD-MAIN-001 | CRITICAL | FIXED — commit `5c0a320`; hosted CI verified (run `45039365667`); 11 focused integrity tests pass locally |
| AUD-MAIN-002 | MEDIUM | FIXED LOCALLY / HOSTED CI PENDING — one-shot `main()` passes its constructed HotSearchEngine to `run_once`; identity regression passes; full trend-provider acceptance remains separate |
| AUD-ONCHAIN-001 | HIGH | OPEN — caller-forgeable acceptance API; not currently wired into the production runtime |
| AUD-ONCHAIN-002 | HIGH | OPEN — mapping VERIFIED state lacks reproducible source proof/freshness |
| AUD-ONCHAIN-003 | HIGH | CLOSED — documented summary-only corroboration interface; no defect in the intended main path |
| AUD-ONCHAIN-004 | MEDIUM | PARTIALLY REMEDIATED / OPEN — bounded reader implemented; explicit operator cap and provider payload acceptance remain pending |
| AUD-ONCHAIN-005 | HIGH | FIXED LOCALLY / HOSTED CI PENDING — all four worker families and aggregator now pass real disposable PostgreSQL integration; store transaction, checkpoint, reorg, concurrency and restart tests pass |
| AUD-M14-001 | HIGH | OPEN / FAIL-CLOSED DEFER — production scoring policy not calibrated/approved/activated |
| AUD-M14-002 | HIGH | FIXED LOCALLY / HOSTED CI PENDING — raw numeric mappings now always DEFER with explicit provenance-required reason; no mapping can produce PROCEED |
| AUD-M21-001 | HIGH | PARTIAL / OPEN — dedicated PostgreSQL publication 55/55 plus atomicity/scheduled/claim-registry/Layer1/legacy 15/15 passed; production crash/recovery/operator drill and hosted CI remain outstanding |
| AUD-ANN-001 | HIGH | PARTIAL / OPEN — announcement stream has no historical replay guarantee |
| AUD-MARKET-001 | MEDIUM | PARTIAL / OPEN — incomplete timestamped historical market baselines |
| AUD-MKT-001 | HIGH | FIXED LOCALLY / HOSTED CI PENDING — renamed and typed as provider-sourced 24h turnover-to-market-cap percentage; all x-volume/spike claims removed; historical surge baseline remains unavailable |
| AUD-GRAPH-001 | MEDIUM | FIXED LOCALLY / NOT HOSTED-CI VERIFIED — explicit semantic status priority now wins equal-timestamp ties |
| AUD-LIFE-001 | MEDIUM | PARTIALLY REMEDIATED / OPEN — caller-asserted confirmation blocked; exact verifier-issued ClaimRegistry and asset/evidence linkage required; disposable PostgreSQL lifecycle suite 10/10 passed; typed resolution/withdrawal proof remains open |
| AUD-RESEARCH-001 | MEDIUM | FIXED LOCALLY / HOSTED CI PENDING — typed and legacy generic payload hashes recomputed on save/read in SQLite/PostgreSQL; dedicated disposable PostgreSQL tamper acceptance passed in 55/55 publication suite |
| AUD-RESEARCH-002 | MEDIUM | CLOSED — DeepResearchEngine and ContentVerificationEngine require verifier-issued in-process ClaimRegistry proof + content-digest mutation check; AUD-EVID-001 remains open for source provenance authenticity |
| AUD-LLM-001 | MEDIUM | FIXED LOCALLY / HOSTED CI PENDING — mandatory operator byte cap, bounded incremental read, Content-Length precheck and chunked overflow guard; no live provider acceptance |
| AUD-EDITORIAL-001 | MEDIUM | FIXED LOCALLY / HOSTED CI PENDING — typed and legacy generic brief hashes recomputed on save/read; dedicated disposable PostgreSQL tamper acceptance passed in 55/55 publication suite |
| AUD-EVID-001 | MEDIUM | PARTIALLY REMEDIATED / OPEN — provider/endpoint policy + in-process provenance proof implemented; CMS/Spot/on-chain receipts and durable source authentication remain open |
| AUD-DRAFT-001 | MEDIUM | CLOSED — SQLite + guarded disposable PostgreSQL migration/integration acceptance passed 24 Nov 2026; Module 17 remains PARTIAL for separate DeepSeek/semantic gaps |
| AUD-CONTENT-001 | MEDIUM | PARTIALLY REMEDIATED / OPEN — typed brief allowlist enforced through content gate and authorization; PostgreSQL execution pending |
| AUD-CONTENT-002 | MEDIUM | PARTIALLY REMEDIATED / OPEN — deterministic content gate now requires exact supporting-publisher attribution |
| AUD-PUB-001 | HIGH | IMPLEMENTED — HOSTED CI VERIFIED (run `45041348631`); production multiprocess/SLO acceptance remains open |
| AUD-PUB-002 | HIGH | IMPLEMENTED — HOSTED CI VERIFIED (run `45041348631`); production multiprocess/SLO acceptance remains open |
| AUD-VIS-001 | HIGH | FIXED LOCALLY / HOSTED CI PENDING — visual-quality-v3 re-renders approved font glyph masks and checks actual final-image pixels; generated-background OCR remains outside this finding |
| AUD-WF-002 | CRITICAL | FIXED — workflow cache restore/save actions removed in commit `5c0a320`; hosted CI verified (run `45039365667`) |
| AUD-GIT-001 | CRITICAL (original) | FIXED LOCALLY / HOSTED CI PENDING — GitHub Actions requires exact GITHUB_REF == checked-out branch and explicit non-main GIT_HISTORY_ALLOWED_REFS; empty/mismatched refs fail closed |
| AUD-GIT-002 | HIGH (original) | CLOSED for active `_try_git_push()` path — explicit pathspec prevents unrelated staged files entering its commit; does not close legacy image uploader path |
| AUD-GIT-003 | HIGH | FIXED LOCALLY / HOSTED CI PENDING — startup retry checks exact origin/current-branch upstream, detects clean ahead commits, validates every ahead commit path, rejects unrelated/behind/mismatched states, retries and verifies ls-remote HEAD |
| AUD-GIT-006 | MEDIUM | OPEN — scheduled-run delivery far below configured cadence; cause not isolated |
| AUD-GIT-007 | HIGH | REMEDIATED IN PR #14 WORKTREE / HOSTED CI PENDING / DEFAULT MAIN NOT ALIGNED — PR code has independent default-off gate; scheduled workflow now explicitly sets PUBLISHER_ENABLED=0 locally |
| AUD-IMG-001 | HIGH | FIXED LOCALLY / HOSTED CI PENDING — legacy GitHub REST/Git repository-write uploader interfaces are disabled; active authorized Binance media flow unchanged |
| AUD-SCORE-001 | MEDIUM | REMEDIATED LOCALLY / HOSTED CI PENDING — unsupported fallback coefficients removed; MarketScanner candidates retain discovery order and route to review without a synthetic score |
| AUD-CODE-001 | MEDIUM | REVIEW / CLEANUP — Skills Hub scoring/provider subsystem appears unreachable from current runtime; not independently established as a direct production exploit |
| AUD-WF-001 | — | SUPERSEDED by AUD-WF-002; do not count separately as an active blocker |


### AUD-GIT-006 — scheduled-run trigger cadence and pending-run replacement
- **Severity:** MEDIUM
- **Status:** OPEN — observed schedule delivery is materially below the configured cron cadence; the cause of the missing intervals is not established.
- The live default-branch workflow `.github/workflows/run_bot.yml` is configured with `schedule: "*/5 * * * *"`, job timeout of five minutes, concurrency group `binance-square-bot`, and `cancel-in-progress: false`. It does not set the optional `queue` property.
- Read-only GitHub Actions API inspection on 2026-11-22 fetched the latest 100 workflow runs for `main`: 92 were schedule events; only 4 scheduled runs were present in the trailing 24 hours (288 nominal five-minute intervals). Across the 92 schedule runs, observed inter-run gaps ranged from 183.6 to 632.6 minutes; median gap was 372.1 minutes. The latest four scheduled runs completed in 17, 35, 27 and 33 seconds respectively.
- These observations prove that the recorded schedule-run cadence is far below the configured five-minute cadence in the inspected window. They do **not** establish why events were absent or prove that concurrency replacement caused the gaps. No run-history evidence inspected here establishes a specific GitHub outage or account-level scheduling cause.
- Official GitHub Actions documentation states that a concurrency group permits one running and, by default, one pending run; a newly queued run replaces/cancels an existing pending run. `queue: max` permits up to 100 pending runs. GitHub also documents that scheduled events can be delayed or dropped under high load and that schedule triggers run only from the default branch. These platform behaviors make missed ticks possible, but do not by themselves explain the measured multi-hour gaps.
- **Operational impact:** if the intended contract is continuous five-minute opportunity scanning, the current observed delivery does not meet that cadence. If missed ticks are acceptable, that policy is not currently made explicit in the workflow contract. The PostgreSQL run lease serializes runs that actually start; it cannot create a run for a schedule event that was never delivered.
- **Required closure:** define whether missed ticks are acceptable or require catch-up; instrument expected-vs-actual scheduled-run timestamps and alert on a justified gap; if catch-up is required, use durable, idempotent scheduled-run keys/queueing rather than blindly setting `queue: max`, which can create stale backlog. Add tests for missed-tick detection, idempotent catch-up and bounded backlog. Do not change the live schedule or concurrency policy until the catch-up contract is approved.
- **No fix applied:** no workflow, database, schedule, publisher, credential, deployment or live run was changed or triggered during this audit.



### AUD-GIT-007 — default-branch scheduled workflow does not include PR publisher safeguards
- **Severity:** HIGH
- **Status:** OPEN — confirmed branch/configuration drift and confirmed successful live publications from existing default-branch scheduled runs.
- GitHub's official workflow-events documentation states that `schedule` events run only from the repository's default branch and use the latest commit on that branch: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- Live `main` workflow `.github/workflows/run_bot.yml` (blob `108489069c61baf01e4cbb00497a9d312fd276c7`) sets `DRY_RUN: "0"` and injects `SQUARE_API_KEY`; its scheduled trigger is `*/5 * * * *`. It has no `PUBLISHER_ENABLED` environment gate.
- Live `main.py` (blob `0a2d9345382c2b3ebf5abf0cb02ade9bbf03cd91`) parses `DRY_RUN=0` as `dry_run=False`. Its `PostPublisher.publish()` calls `_try_square_api()` when dry-run is false, and the latter uses the configured Square API key for the Binance Square content API. The scheduled `run_once()` path invokes `publisher.publish()`; no separate `PUBLISHER_ENABLED` guard exists in this main-branch code.
- By contrast, PR #14 branch workflow blob `fcac84e6609f6dc9e181842c4b9bfbeb0c379d6a` sets `DRY_RUN: "1"`; its corresponding `main.py` has `publisher_enabled` defaulting false and refuses live publishing unless explicitly enabled. PR #14 remains OPEN / DRAFT / UNMERGED. Therefore these PR safeguards do not protect the default-branch scheduled execution today.
- Read-only job-log verification of the four latest scheduled main-branch runs found successful live publication log entries in run `44994076788` (2026-11-22 06:31:34 UTC: “Native image publish SUCCESS” and “Published successfully with link”) and run `44942640356` (2026-11-21 19:45:59 UTC: same success indicators). Run IDs `45035124759` and `44964305187` had no matching publish-success line in the filtered log review. URLs and post body content were not reproduced. This confirms that at least two existing main-branch scheduled runs successfully published; it does not attribute those posts to this audit session.
- **Required closure:** decide and approve the intended production activation contract; ensure the default-branch workflow and code are aligned with that contract before treating PR safeguards as operational. Verify the live main-branch workflow config, publisher gate and audit trail after any approved change. Do not merge, deploy, toggle DRY_RUN, change credentials or dispatch the workflow as part of this audit.
- **No diagnostic-initiated publication or production change:** this audit did not dispatch a workflow, call Binance, change workflow/publisher code, credentials, schedule or deployment. The two successful posts above were produced by pre-existing scheduled main-branch runs.


### Reconciliations and counting rules
- The early Section 26 `AUD-MAIN-001` OPEN status and Section 27 initial OPEN row are historical and superseded by Sections 30–31: commit `5c0a320` fixed the integrity gate and removed publication-history cache actions; hosted CI run `45039365667` passed. The current authoritative status is FIXED, not OPEN.
- The original Section 4 / Section 27 HIGH rating for `AUD-MAIN-002` is refined in Section 41 to MEDIUM: the defect drops attention/discovery context in one-shot mode but does not bypass eligibility, evidence or publication authorization gates.
- `AUD-GIT-001` and `AUD-GIT-002` original section statuses are superseded by Section 25 and this register. The branch guard is partial closure; path-scoped commit is closed only for the active helper. `AUD-IMG-001` remains independent and open.
- `AUD-WF-001` is superseded by `AUD-WF-002`; it is not a second cache finding.
- Module 20 reconfirms `AUD-VIS-001`; it is not a duplicate visual finding.
- Module 19 documentation verification is not equivalent to an authenticated Cloudflare runtime/account test. Module 21 CI checks on PR #14 are not equivalent to a production database recovery drill.
- Severity reflects potential impact, not evidence of an observed production incident. Findings explicitly limited to internal API trust boundaries or legacy/unreached code remain qualified as such.


## 28. Final production-readiness decision and 21-module coverage snapshot (22 November 2026)

### Decision

**NO-GO — PARTIAL / NOT PRODUCTION-READY / NOT CERTIFIED**

This is the final decision for the reviewed evidence, not a claim that all 21 modules have been exhaustively audited. Module 21's focused publication/recovery audit and the consolidated register are complete for this continuation checkpoint; the overall 21-module master audit remains **IN PROGRESS** because several modules and end-to-end paths are still explicitly NOT VERIFIED or only partially reviewed.

Reasons production readiness cannot be approved:
1. Critical `AUD-MAIN-001` can allow execution when Git history integrity cannot be established; this directly weakens duplicate/cooldown protection.
2. Critical `AUD-WF-002` can restore stale publication history over newer Git state in the workflow cache path.
3. High `AUD-ONCHAIN-001` leaves a caller-forgeable provider-acceptance trust boundary in the Module 9 library API; repository reachability review did not find it wired into the current production runtime.
4. High `AUD-PUB-001` and `AUD-PUB-002` leave SQLite authorization concurrency and attempt/quota consistency gaps.
5. High `AUD-MAIN-002` omits trend intelligence from the actual one-shot workflow entrypoint.
6. Module 14 scoring remains fail-closed DEFER and has no approved, empirically calibrated production policy; no PROCEED policy may be invented or activated to make the pipeline appear complete.
7. PostgreSQL crash/recovery acceptance was not executed against a disposable DB in this environment; no production DB access, migrations or operator recovery drill was authorized.
8. Visual pixel verification and image-dependent test execution remain incomplete; Pillow is unavailable in the RDC runtime.
9. Additional high/medium evidence, research, editorial, content, provider-resource and source-provenance findings remain open in Section 27.

### Latest module coverage snapshot

| Module | Latest status | Main outstanding evidence / blocker |
|---|---|---|
| M1 Configuration / orchestration | PARTIAL | Runtime wiring and lease behavior reviewed; broader end-to-end failure matrix pending |
| M2 Market data intelligence | PARTIAL | AUD-MKT-001 metric semantics fixed locally; AUD-MARKET-001 historical baseline gap remains open |
| M3 Binance listing eligibility | PARTIAL | Full provider/source proof and runtime acceptance not certified |
| M4 Announcement intelligence | PARTIAL | `AUD-ANN-001` replay/backfill and read-only DB role evidence missing |
| M5 Trend intelligence | PARTIAL | one-shot wiring restored; provider coverage, trend provenance and production acceptance remain unverified |
| M6 Candidate discovery | NOT VERIFIED | Full module and cross-layer behavior not completed |
| M7 Relevance / scoring | PARTIAL | `AUD-SCORE-001` fallback heuristic removed locally; Skills Hub policy/provider path and broader module acceptance remain unverified |
| M8 Market analysis | PARTIAL | `AUD-MARKET-001` historical baseline coverage incomplete |
| M9 On-chain intelligence | FAIL / PARTIAL | `AUD-ONCHAIN-005` fixed locally with all four PostgreSQL-backed workers + aggregator tested; `AUD-ONCHAIN-001`, `002`, `004` and runtime activation remain open; `AUD-ONCHAIN-003` closed as documented summary-only ClaimRegistry design |
| M10 Event graph | PARTIALLY REMEDIATED | `AUD-GRAPH-001` fixed locally; hosted CI and broader graph review pending |
| M11 Evidence verification | PARTIAL | `AUD-EVID-001` partially remediated; exact provider mapping is enforced, but CMS/Spot/on-chain receipts and durable source authentication remain open |
| M12 Event lifecycle | PARTIALLY REMEDIATED | `AUD-LIFE-001` caller-asserted confirmation blocked; verifier-issued ClaimRegistry required; dedicated PostgreSQL lifecycle suite 10/10 passed; typed resolution/withdrawal proof remains unimplemented |
| M13 Deep research | PARTIALLY REMEDIATED | `AUD-RESEARCH-001` generic typed/legacy payload digests fixed and PostgreSQL 55-test suite passed; primary-source completeness still correctly returns `RESEARCH_MORE` when PRIMARY evidence is absent |
| M14 Opportunity evaluation | FAIL / DEFER | `AUD-M14-001/002`; no approved source-backed calibrated production scoring policy |
| M15 DeepSeek integration | PARTIAL | `AUD-LLM-001` fixed locally / hosted CI pending; live provider verification and deployed byte-cap provisioning remain unverified |
| M16 Editorial strategy | PARTIALLY REMEDIATED | `AUD-EDITORIAL-001` generic typed/legacy payload digests fixed and PostgreSQL 55-test suite passed; full provider/editorial acceptance remains open |
| M17 Content generation | PARTIAL | `AUD-DRAFT-001` CLOSED after SQLite + PostgreSQL sequence-based gate acceptance; live DeepSeek and semantic quality gaps remain |
| M18 Content verification / safety | PARTIALLY REMEDIATED | `AUD-CONTENT-001/002` allowlist and source attribution gates added; persisted-validation trust and hosted acceptance remain |
| M19 Cloudflare image generation | PARTIAL | Provider docs cross-checked; no authenticated runtime/account smoke test; Pillow unavailable |
| M20 Visual QA | PARTIAL | AUD-VIS-001 deterministic overlay pixel proof v3 fixed locally; generated-background OCR and live acceptance remain open |
| M21 Publication / persistence / recovery | PARTIAL | Dedicated PostgreSQL publication suite 55/55 and additional atomicity/scheduled/legacy/claim-registry suites 15/15 passed; broader crash/recovery and hosted CI evidence remain open |

### Ordered closure plan
1. `AUD-MAIN-001` and `AUD-WF-002` are fixed and hosted-CI verified; retain regression coverage and monitor Git-history integrity on scheduled runs.
2. Close remaining Module 21 authorization/quota consistency defects (`AUD-PUB-001`, `AUD-PUB-002`). Their fixes are now pushed and hosted-CI verified, but the SQLite database-wide writer-lock trade-off and production multiprocess/SLO acceptance remain open. Decide explicitly whether SQLite live publishing is supported; if not, enforce PostgreSQL-only live mode rather than relying on undocumented operational assumptions.
3. Correct the one-shot trend-engine wiring (`AUD-MAIN-002`) and add a non-publishing regression test.
4. Complete approved disposable PostgreSQL acceptance, concurrency, crash/restart, unknown-outcome and operator recovery tests for `AUD-M21-001`.
5. Resolve Module 9 source trust and mapping provenance (`AUD-ONCHAIN-001/002`), implement PostgreSQL-compatible worker/store interfaces (`AUD-ONCHAIN-005`), and add bounded provider response reads (`AUD-ONCHAIN-004`). `AUD-ONCHAIN-003` is closed as intended summary-only corroboration.
6. Establish and independently approve Module 14's source-backed scoring features, point-in-time data, adjudicated labels, out-of-time evaluation and false-PROCEED analysis before activation (`AUD-M14-001/002`).
7. Close evidence/research/editorial/draft/content/visual findings with exact provenance and adversarial tests; run Pillow-dependent image tests in an approved environment.
8. Finish the remaining NOT VERIFIED module and end-to-end workflow reviews, reconcile the architecture and blocker registers, then update this report's top-level status only when every required module has evidence.

### Final operational boundary
- No real Binance Square post, live publisher activation, Cloudflare inference, production DB access, DB migration, deployment, or merge was performed.
- The audit report is local and uncommitted. PR #14 remains open/draft/unmerged at the previously verified SHA. The existing dirty worktree was preserved.
- Do not label this project production-ready or enable live publication on the strength of passing unit tests or the two hosted checks alone.


## 29. Live GitHub Actions cache-path verification — 22 November 2026

### Read-only GitHub evidence
- Queried repository Actions cache metadata through the GitHub REST API (read-only). Three exact-key caches currently exist:
  - `post-history-main`, ref `refs/heads/main`, cache ID `5314977375`, compressed archive size 187 bytes, created 2026-06-27, last accessed 2026-11-22 14:52:03 UTC.
  - `post-history-layer-1/module9-onchain-continuation`, cache ID `10673024359`, ref `refs/heads/layer-1/module9-onchain-continuation`, archive size 8,881 bytes, created 2026-11-17.
  - `post-history-layer-1/module9-onchain-intelligence`, cache ID `10667904032`, ref `refs/heads/layer-1/module9-onchain-intelligence`, archive size 8,892 bytes, created 2026-11-17.
- Read-only workflow-run metadata showed scheduled `run_bot.yml` runs on `main`; latest inspected run was `45035124759`, event `schedule`, created 2026-11-22 14:51:56 UTC, completed successfully.
- Filtered logs for run `45035124759` (only cache and history-integrity lines; no secrets or full logs emitted) confirm:
  1. Restore step got an exact `Cache hit for: post-history-main`.
  2. It received the full 187-byte cache archive and restored successfully.
  3. Runtime then reported `published_posts.jsonl exists but is empty (0 bytes)`.
  4. Runtime positively found 62,535 bytes in Git and restored the checked-out history to a 62,536-byte file.
  5. It then loaded 52 coins from 221 history lines.
  6. The save step attempted the same immutable key and failed to reserve it (`another job may be creating this cache`), then emitted `Cache save failed` warning.
- This is important qualification: **the latest observed main-branch run did not demonstrate an actual stale non-empty history rollback**. Its cache was empty and the existing empty-file recovery restored Git history correctly. Do not state that this specific run erased or replaced the 52-coin history; logs prove the opposite.

### Updated interpretation of AUD-WF-002
- **Status:** OPEN — CRITICAL design flaw / stale non-empty cache rollback remains unexcluded; no observed rollback in the inspected latest run.
- The fixed-key cache behavior is confirmed by official GitHub docs: an existing cache cannot be changed, and an exact key restores its saved contents. The exact main cache and the exact-hit/failed-save behavior are also confirmed by the run log.
- The observed cache's restored file was empty. The current integrity code has a recovery branch for this exact empty-file case and successfully restored the Git version in run `45035124759`.
- The remaining failure mode is specifically **non-empty stale cache content**: `_verify_persistence_integrity()` immediately returns `True` for any non-empty local history file (`main.py:910-916`) without comparing it to the Git checkout or durable PostgreSQL ledger. A stale non-empty cache can therefore bypass the empty-file recovery path. The actual cache archive contents for the two non-main refs were not downloaded or inspected; their metadata sizes are not a substitute for file contents and no stale payload claim is made about them.
- **Closure remains:** remove publication history from Actions cache and rely on a single durable authority, or introduce a cryptographically verified monotonic version/digest reconciliation that cannot overwrite newer Git/DB state. Add a test with a stale but valid-looking non-empty JSONL cache against a newer Git history and assert fail-closed/reconciliation without data loss. Do not use a mutable cache key/version scheme as a replacement for the durable source of truth.

### AUD-MAIN-001 operational confirmation
- The latest scheduled run also confirms the fail-open cases are not needed for the observed empty-cache recovery: the Git restore path can succeed without relying on timeout/error permissiveness.
- However, the earlier isolated reproductions remain valid: Git `log` exit code 128 and timeout both allowed an empty/missing history to pass. These are separate failure paths from the successful restore observed in run `45035124759`.

### Evidence boundary
- GitHub Actions cache metadata and filtered logs were read only. No cache was deleted, changed, restored into the RDC worktree, or re-saved. No workflow was dispatched or rerun. The latest scheduled run's own logs are historical evidence, not a new test triggered by this audit.


## 30. AUD-MAIN-001 / AUD-WF-002 — fail-closed history integrity and cache-path removal — 22 November 2026

### Implementation applied on the existing local continuation worktree
- Replaced the permissive `_verify_persistence_integrity()` path with a fail-closed verification sequence:
  - Resolve and validate the Git worktree root; reject history paths outside the repository.
  - Verify Git `HEAD` / unborn-branch state and require successful repository/ref checks.
  - Check every Git subprocess return code; timeout, nonzero exit, invalid ref, missing object, decode error or unexpected exception blocks the cycle.
  - Check `git show HEAD:<path>` success before using committed history.
  - Strictly parse every non-empty JSONL line as an object with a non-empty symbol and ISO timestamp.
  - Compare canonical record multiplicities so local JSONL must contain every committed baseline record; valid current-run appended records remain allowed.
  - Restore missing/empty local history only from a successfully retrieved and validated Git baseline; otherwise initialize an empty ledger only after positively verifying a valid unborn branch/no committed history.
- Removed both `actions/cache/restore@v4` and `actions/cache/save@v4` steps for `published_posts.jsonl` from `.github/workflows/run_bot.yml`. No mutable Actions cache is now a publication-history input or output. Existing historical cache objects were not deleted; they are no longer referenced by this workflow.
- The scheduled workflow remains `DRY_RUN: "1"`. Existing `Config.validate()` still rejects GitHub Actions live publishing unless PostgreSQL persistence is configured. PostgreSQL remains the durable publication ledger for any future GitHub Actions live mode; no live mode was enabled.

### TDD and verification evidence
- RED: the new isolated regression tests failed against the prior implementation for malformed non-empty JSONL, Git nonzero exit, Git timeout and missing committed records.
- GREEN: `tests/test_persistence_integrity.py`: **11 passed, 0 failed**. Cases cover malformed JSONL, Git log/show nonzero exits, timeout, stale/missing committed records, verified restore, valid first-run, valid append-only extension, broken branch ref and workflow cache absence.
- Existing `tests/test_scheduled_persistence_safety.py`: **21 passed, 0 failed**.
- Combined focused result: **32 passed, 0 failed**.
- Because the RDC runtime does not have Pillow or psycopg installed, the focused test process used temporary import-only Pillow class/module stubs and a psycopg exception-class shim. No image-processing behavior or PostgreSQL driver/database behavior was simulated or claimed as tested.
- `python -m compileall -q main.py tests/test_persistence_integrity.py`: PASS.
- `git diff --check`: PASS.
- `actionlint` is not installed in the RDC environment; no GitHub Actions workflow run was dispatched. YAML was inspected as a focused textual diff only.

### Finding disposition
- `AUD-MAIN-001`: **FIXED IN LOCAL WORKTREE — hosted PR verification pending**. Git errors/timeouts and malformed or stale history no longer produce a permissive `True`.
- `AUD-WF-002`: **CACHE RESTORE/SAVE PATH REMOVED IN LOCAL WORKTREE — hosted PR verification pending**. Old cache objects remain untouched and inert because the workflow no longer references cache actions.
- This does not close `AUD-GIT-003` (Git push synchronization) or establish PostgreSQL durability/crash-recovery acceptance (`AUD-M21-001`). The overall project remains **NO-GO / PARTIAL / NOT PRODUCTION-READY**.
- No real Binance post, publisher/gateway change, production DB access, migration, workflow dispatch, deployment, merge, commit or push was performed in this step. Existing unrelated dirty files remain preserved.

## 31. Hosted PR verification — commit 5c0a320 — 22 November 2026

- Pushed commit 5c0a32088d15b3653ed39cad9ddf5ba919bfe066 to the existing remote branch layer-1/module9-onchain-continuation using a normal fast-forward push. No force push.
- Re-queried GitHub: PR #14 remains OPEN / Draft / Unmerged; PR head SHA, remote branch SHA and local HEAD all equal 5c0a32088d15b3653ed39cad9ddf5ba919bfe066.
- New GitHub Actions run 45039365667 (Phase 1 Safety Tests, push event) completed successfully:
  - mocked-safety-tests: PASS; log reports 864 tests run.
  - Isolated PostgreSQL integration acceptance: PASS; log reports 92 tests run, including the real PostgreSQL adapter/recovery integration test step against its isolated CI database.
  - gh pr checks 14: both checks PASS.
- This provides hosted PostgreSQL acceptance evidence for this commit's PR test workflow; it does not mean production Neon/DB was accessed. The CI step explicitly verified its isolated database target before migrations.
- Read-only check of run_bot.yml run history showed the latest scheduled run still predates this push (45035124759, 2026-11-22 14:51:56Z). No workflow_dispatch, no new scheduled publisher run, and no Binance Square post was triggered by this work.
- Push contained only the intended workflow removal, the _verify_persistence_integrity() replacement, and the new regression test file. The pre-existing unrelated expected_base_asset edit in main.py was explicitly left unstaged and remains in the dirty worktree. All other pre-existing dirty files were preserved.
- Local worktree documentation updates remain uncommitted; the master audit report remains untracked/local. PR #14 was not merged or marked ready.
- Node.js 20 deprecation annotations appeared for existing actions/checkout@v4 and actions/setup-python@v5; both jobs nevertheless passed. This is a maintenance warning, not a failure of these checks.
- Project status remains NO-GO / PARTIAL / NOT PRODUCTION-READY because unrelated critical/high findings remain open, including AUD-ONCHAIN-001/002, AUD-ONCHAIN-005, AUD-MAIN-002, AUD-M14-001/002, AUD-GIT-003, and the remaining source/evidence/content/visual and policy gaps.


## 32. Publication SQLite authorization/quota race audit — 22 November 2026

### AUD-PUB-002 — SQLite attempt finalization can commit without a valid quota reservation
**Confirmed by source trace and isolated reproduction.**
- Source: main.py, PostPublisher._finish_attempt() around lines 3900–3978.
- The method updates publication_attempts first inside a SQLite transaction, then checks whether the quota table exists. If the table exists but no reservation is found for attempt_id, if the reservation is RELEASED, or if quota status already equals the target, it returns normally.
- Returning normally from the SQLite connection context commits the earlier attempt status update. The missing/RELEASED branches therefore do not roll back the attempt transition.
- Quota schema: layer1/publication_authorization.py creates publication_quota_reservations with reservation_id primary key and a partial unique index on non-null attempt_id. This prevents two rows from binding the same attempt, but does not guarantee a bound row still exists at finalization.
- Isolated reproduction used a temporary SQLite DB and no network:
  1. Create attempt, bind a reservation, set it SUBMITTING, delete reservation, call _finish_attempt(..., PUBLISHED_CONFIRMED): no exception; attempt committed PUBLISHED_CONFIRMED; quota MISSING.
  2. Repeat but change reservation status to RELEASED: no exception; attempt committed PUBLISHED_CONFIRMED; quota remains RELEASED.
- Existing test test_sqlite_attempt_and_quota_are_finalized_atomically_after_remote_confirmation only patches PublicationAuthorizationEngine.mark_quota_status. _finish_attempt performs direct SQL updates and does not call that method; the test asserts final_status_calls == [] and therefore does not exercise missing/released quota invariants.
- Production relevance: Config.from_env defaults persistence_backend to sqlite. GitHub Actions live mode is separately blocked unless PostgreSQL is selected, but non-GitHub deployments can still configure/use SQLite. Actual deployed backend was not inspected in this audit.
- Severity remains HIGH. The attempt ledger can claim terminal publication confirmation while quota ledger does not, weakening quota accounting and authorization/attempt/reservation consistency.
- Required closure: preserve legacy ledger-only compatibility only when the quota table truly does not exist; when authorization schema exists, require exactly one bound reservation for the attempt, verify authorization_id/reservation identity and legal source status, and update attempt + reservation in one transaction. Missing, RELEASED, mismatched, duplicate or illegal reservation state must raise and roll back the attempt update. Add regressions for missing row, RELEASED, wrong reservation binding, illegal state and injected concurrent mutation; keep legacy no-quota-table tests separate.

### AUD-PUB-001 — SQLite final authorization check is not fenced through network submission
**Confirmed by source trace and deterministic isolated race injection.**
- Source: main.py SQLite publish() path around lines 4014–4234. It calls persisted duplicate/event validation before attempt reservation, and again after reservation immediately before constructing the request. These validators run in separate SQLite operations; there is no SQLite transaction/lock that remains held across the final check and _open_binance_publish_no_redirect(...).
- PublicationAuthorizationEngine.validate_persisted_duplicate_policy() opens BEGIN IMMEDIATE inside its own context and returns/commits before the HTTP request. validate_persisted_event_binding() performs its read separately. The attempt/quota reservation is durable, but it does not serialize subsequent event lifecycle writes through the POST.
- Isolated reproduction used a second SQLite connection to change lifecycle state from CONFIRMED to WITHDRAWN exactly when the mocked transport function was invoked, after the final checks. Mocked transport returned a synthetic success response; publisher returned PUBLISHED_CONFIRMED even though persisted event state was WITHDRAWN. The mocked transport was called once; no real HTTP/network request and no Binance post occurred.
- PostgreSQL contrast: layer1/publication_postgres.py authorized_submission_guard() holds an outer transaction and event/symbol advisory locks across the yielded bounded POST; validate_authorized_attempt_before_submit() rechecks persisted authorization, event, quota and duplicate policy under that guard.
- Severity remains HIGH. A mutable lifecycle or duplicate-policy fact can change after SQLite validation but before the remote side effect. The test proves the race window; it does not claim that a live deployment has experienced this race.
- Required closure: define a SQLite serialization/fencing design that prevents conflicting lifecycle/duplicate-policy writes between final validation and request dispatch, including NO_EVENT insertion. Do not blindly copy a long transaction around network I/O: prove lock duration, busy timeout, process crash/rollback, concurrent publisher behavior, and unresolved remote outcome recovery. Add deterministic second-connection race tests for event update, NO_EVENT insertion, recent-post insertion and competing reservation, asserting no transport invocation when a conflict wins.

### Audit boundary and status
- Both reproductions used isolated temporary SQLite files, synthetic data, and a mocked transport boundary. No production DB, external network, Binance API, live post, publisher configuration, schema migration or source code was modified.
- Existing PostgreSQL path is structurally stronger for these two specific invariants, but this audit did not inspect any production PostgreSQL/Neon instance or deployed environment variables.
- AUD-PUB-001 and AUD-PUB-002 remain OPEN pending approved code changes and new regression tests. No implementation was applied because the prior approval was scoped to AUD-MAIN-001 and AUD-WF-002.
- Project remains NO-GO / PARTIAL / NOT PRODUCTION-READY.


## 33. Approved SQLite publication fixes — 22 November 2026

**Approval:** The user explicitly approved implementation of both `AUD-PUB-001` and `AUD-PUB-002` in this existing continuation worktree. This section supersedes the OPEN implementation status recorded in Section 32; it does not change the overall production-readiness verdict.

### AUD-PUB-001 — implementation pushed; hosted CI PASS
- SQLite `publish()` now acquires `BEGIN IMMEDIATE` before its final persisted event/duplicate-policy checks and holds the SQLite write fence through `urllib` request dispatch and response-header receipt. Competing SQLite writers cannot change event lifecycle state, insert a previously absent event for a `NO_EVENT` authorization, add recent posts, or create a competing quota reservation between the final check and POST dispatch.
- The response body is read only after the SQLite transaction has been released. This avoids holding the write lock during body parsing and subsequent local persistence. The request uses `min(HTTP_TIMEOUT_SECONDS, 15)` as its socket timeout and the existing bounded response reader (1 MiB + 1 byte detection); urllib's socket timeout is not a strict total wall-clock deadline.
- `validate_persisted_duplicate_policy()` now reuses an already active SQLite transaction instead of issuing a nested `BEGIN IMMEDIATE`.
- Deterministic multi-connection tests prove that event withdrawal, `NO_EVENT` insertion, recent-post insertion and a competing quota reservation are blocked at the mocked transport dispatch boundary. A separate response-body test proves the lock is released before body reading. Pre-gate event withdrawal and `NO_EVENT` insertion are rejected without invoking transport; the existing post-insertion regression also confirms no transport call when the conflicting record wins before the final gate.
- Operational trade-off: SQLite has a database-wide writer lock, not PostgreSQL-style row/advisory locks. Competing writers may wait or receive `database is locked` depending on their connection timeout. The test uses a second connection with a 50 ms timeout and verifies this behavior. The lock is deliberately limited to final validation + request dispatch/header acquisition, not response-body reading or local post persistence. This does not establish a multi-process production load/SLO benchmark.

### AUD-PUB-002 — implementation pushed; hosted CI PASS
- Added an additive `authorization_id` column migration to the SQLite `publication_attempts` ledger. When the authorization engine initializes, it safely backfills pre-existing in-flight attempts only from a non-empty bound reservation whose symbol exactly matches; it does not invent identities for missing/mismatched rows. A migration regression preserves the old attempt and verifies the new column.
- `PublicationAuthorizationEngine.bind_attempt()` now verifies that the reservation exists, is RESERVED and unbound, has an authorization identity, and belongs to the same symbol as the attempt. It binds the reservation and copies the same authorization ID to the attempt in one SQLite transaction.
- `PostPublisher._finish_attempt()` preserves the legacy ledger-only path only when the quota table truly does not exist. If the quota table exists, it now requires exactly one reservation bound to the attempt; checks matching attempt ID, symbol and authorization ID; and enforces the allowed quota source-state transition. Missing, RELEASED, identity-mismatched, wrong-symbol, duplicate or illegal-state reservations raise inside the transaction, rolling back the attempt update.
- The binding-failure path catches finalization failure, reports that no request was sent and leaves the durable attempt fenced rather than allowing an exception to escape or falsely finalizing it.

### TDD and local verification
- Added 15 publisher regressions covering missing reservation, RELEASED reservation, authorization identity mismatch, illegal quota state, symbol mismatch during binding, bind failure/no transport, event withdrawal and `NO_EVENT` conflicts before the final gate, second-connection writer serialization for event/NO_EVENT/recent-post/competing-reservation mutations, lock release before response-body reading, and the 15-second maximum socket-timeout cap.
- RED evidence: the first eight new regressions failed against the pre-fix code (four quota consistency cases and four transport-boundary concurrency cases). GREEN evidence: the same eight passed after implementation. Follow-up tests passed as well.
- Latest focused command `python -m unittest tests.test_publisher_safety tests.test_publication_authorization`: **71 passed, 0 failed**. It used a temporary import-only Pillow shim because Pillow is not installed in the RDC environment; no image processing was executed by this focused test set.
- A broader local discovery run excluding five dependency-blocked modules passed **821 tests, 0 failures, 63 skipped** before the final response-body-lock-boundary refinement. The final refinements are covered by the latest 71-test focused run.
- Unfiltered local discovery attempted 896 tests and reported 59 errors, 63 skips and no assertion failures. The errors are attributable to absent Pillow (`PIL.Image.new` unavailable under the import-only shim) and absent `psycopg`; therefore this is **not** a full-suite pass. GitHub Actions CI installs Pillow and PostgreSQL dependencies and must be used for complete verification.
- `python -m compileall -q main.py layer1 tests/test_publisher_safety.py` and `git diff --check` passed after the implementation.

### Scope and current disposition
- Only `main.py`, `layer1/publication_authorization.py` and `tests/test_publisher_safety.py` were intentionally changed for these fixes. Pre-existing unrelated dirty files and the unrelated pre-existing `main.py` `expected_base_asset` edit were preserved and must not be swept into the code commit.
- No real Binance request, live Square post, production DB/Neon connection, production migration, workflow dispatch, deployment, PR merge or gateway restart was performed.
- Hosted GitHub Actions run `45041348631` completed successfully on commit `3d9ba509d2743c307e8d003419e048982bd5c9b1`: `mocked-safety-tests` PASS (**879 tests, 62 skipped**) and `Isolated PostgreSQL integration acceptance` PASS. The isolated DB target was verified before migrations. `gh pr checks 14` reports both checks PASS.
- PR #14 remains OPEN / Draft / Unmerged. Its head, the remote continuation branch and local HEAD all equal `3d9ba509d2743c307e8d003419e048982bd5c9b1`. No second PR was created and no merge was performed.
- `AUD-PUB-001` and `AUD-PUB-002` are **IMPLEMENTED — HOSTED CI VERIFIED** for the tested code paths. This does not certify production deployment, multiprocess load/SLO behavior, production SQLite configuration or the overall 21-module system; those remain operational/independent readiness work.
- Project remains **NO-GO / PARTIAL / NOT PRODUCTION-READY** because independent critical/high findings remain open, including `AUD-ONCHAIN-001`, `AUD-MAIN-002`, `AUD-GIT-003`, Module 14 policy readiness, visual QA and Module 21 operator recovery.


## 34. Hosted verification of approved SQLite publication fixes — 22 November 2026
- Commit `3d9ba509d2743c307e8d003419e048982bd5c9b1` was pushed fast-forward to the existing `layer-1/module9-onchain-continuation` branch.
- GitHub Actions run `45041348631` completed with conclusion `success`:
  - `mocked-safety-tests`: PASS — **879 tests, 62 skipped**; dependencies installed; Python compile step passed.
  - `Isolated PostgreSQL integration acceptance`: PASS — test database target validated before migrations; isolated service container initialized and stopped normally.
- `gh pr checks 14`: both required checks PASS. PR #14 remains OPEN / Draft / Unmerged. Local HEAD, remote branch SHA and PR head SHA were independently verified equal to `3d9ba509d2743c307e8d003419e048982bd5c9b1`.
- Node.js 20 deprecation warning remains for existing `actions/checkout@v4` and `actions/setup-python@v5`; it did not fail either job.
- No production DB/Neon connection, production migration, live publishing workflow dispatch, Binance API POST, deployment or merge.
- The 879-test hosted mocked suite supersedes the local full-suite dependency limitation for repository CI. Local focused suite remains 71 passed / 0 failed; local unfiltered discovery was blocked by absent Pillow/psycopg in the RDC environment.
- `AUD-PUB-001` and `AUD-PUB-002` are now IMPLEMENTED — HOSTED CI VERIFIED for the tested SQLite paths. Production multiprocess load/SLO verification and overall project readiness remain separate. Project remains NO-GO / PARTIAL / NOT PRODUCTION-READY because other critical/high findings remain open.


#### AUD-GIT-007 mitigation update — 2026-11-23
- User explicitly approved temporarily changing the default-branch workflow `.github/workflows/run_bot.yml` from `DRY_RUN: "0"` to `DRY_RUN: "1"`.
- Applied only that one-line workflow change directly to `main` using GitHub Contents API. Commit: `4525cabe1260fd5b25414010d2cf16b387119edd`; resulting workflow blob: `4dfc5f3b1acc48c22d0c3763776dcbdadf7d6c6f`.
- Read-after-write verification on `main` confirmed `DRY_RUN: "1"`; schedule and Square credential injection remain otherwise unchanged. No workflow dispatch or manual run was triggered. The latest Actions run list contained only older completed runs at verification time; no in-progress run was shown.
- **Important residual side effect:** inspected main-branch `main.py` generates/uploads a Binance image before invoking `publisher.publish()`; that image-upload path is not guarded by `dry_run`. The one-line mitigation prevents the content publish call but does not establish zero Binance network activity or prevent image uploads. No broader code change was made because approval was limited to the workflow dry-run switch.
- Status: live content publishing is temporarily switched to dry-run on default branch; full no-network diagnostic mode is not established. AUD-GIT-007 remains OPEN until code/workflow safeguards are aligned and independently verified.

## 35. Module 9 trust-boundary and mapping provenance re-verification — 22 November 2026

### AUD-ONCHAIN-001 — confirmed library trust-boundary weakness; severity refined for current reachability
- Re-ran `python -m unittest tests.test_onchain_intelligence`: **28 passed**. The positive fixture constructs `EligibilityDecision`, `OnChainAssetMapping` and `OnChainObservation` directly, including the literal 64-character proof hash `"a" * 64`, and `OnChainIntelligenceEngine.validate()` returns `ACCEPTED`. `OnChainStore.save_verified()` then persists that accepted result after rerunning the same field validator. The dataclasses are frozen, but immutability is not source authentication.
- The provider transport parses JSON responses and returns decoded dictionaries/results; it does not retain a raw-response digest, signed receipt, immutable response artifact or provider-authenticated acceptance object that is bound into the `OnChainObservation` passed to `validate()`.
- `EligibilityDecision.identity_proof_data_hash` is checked only for 64-hex syntax in `onchain.py`; the on-chain engine does not recompute it from a retained CoinGecko response. Mapping and observation provenance fields are caller-supplied values checked structurally, not independently fetched or authenticated by this API.
- **Reachability qualification (important):** a repository-wide call-site search found `OnChainTransferAggregator(...)` only in tests; all four worker constructors are instantiated only in tests; `OnChainStore.save_verified(...)` call sites are tests only; and current `main.py` scheduled/one-shot `run_once()` calls do not supply `onchain_aggregation_by_asset`. The main runtime parameter defaults to `None`, and no in-repository production orchestrator constructs the workers/aggregator or injects their results. Therefore this review confirms a trust-boundary flaw in the library API and a blocker before Module 9 activation, but does **not** demonstrate a currently reachable production exploit or a live external attack path.
- **Severity correction:** the prior CRITICAL label overstated demonstrated current exploitability. Reclassify to **HIGH — pre-activation trust-boundary blocker**. Keep OPEN; do not call it fixed or exploitable from an external interface without further evidence.
- Required closure remains source-specific ingestion/verification that binds raw/minimized response evidence, digest, endpoint/provider identity, retrieval time and verifier version to the accepted record; mapping source-host/path/contract validation; and a trust boundary preventing arbitrary evidence-shaped values from asserting ACCEPTED. A process-local private constructor token alone is not a cryptographic source-authenticity proof.

### AUD-ONCHAIN-002 — two deterministic acceptance reproductions confirmed
- `OnChainIntelligenceEngine._validate_mapping()` restricts `source_type` to the enum but accepts any URL whose parsed scheme is `https` and whose netloc is non-empty (`layer1/onchain.py:156-162`). It does not bind `source_type` to an approved host/path/network or verify that the referenced page contains the exact asset/contract/issuer.
- The same validator parses `verified_at` and rejects timestamps more than five minutes in the future, but imposes no maximum age (`layer1/onchain.py:188-193`). `OnChainStore.list_verified_mappings()` and `PostgresOnChainStore.list_verified_mappings()` reuse this validator without a mapping-expiry rule. Aggregation separately checks eligibility and observation freshness, not mapping-attestation age (`layer1/onchain_aggregation.py:143-181`).
- Deterministic isolated reproduction using the existing accepted BTC fixture and fresh observation:
  - A mapping `verified_at` timestamp **10 years old** returned `ACCEPTED / ONCHAIN_OBSERVATION_VERIFIED`.
  - `source_url=https://attacker-controlled.invalid/fake-official-token-list` also returned `ACCEPTED / ONCHAIN_OBSERVATION_VERIFIED`.
  - No HTTP/network request was made; both values were supplied directly to the validator.
- **Reachability qualification:** as documented for AUD-ONCHAIN-001, current repository runtime does not instantiate the on-chain worker/aggregator pipeline or pass on-chain results into `run_once()`. This is a confirmed validation flaw and pre-activation blocker, not evidence of an externally reachable current production exploit.
- **Required closure:** curated host/path/contract allowlists per source type and network, exact payload identity binding, and source/network-specific mapping validity windows. Do not invent TTL values: derive and document them from official source update behavior, provider/network operating characteristics, and an explicit risk policy. Test stale mappings at validation, list, aggregation and PostgreSQL read boundaries.

### Scope / disposition
- No source files, schemas, configuration, database, provider, network or publication workflow were changed in this review.
- `AUD-ONCHAIN-001` remains OPEN (HIGH, pre-activation trust-boundary blocker); `AUD-ONCHAIN-002` remains OPEN (HIGH, source-host/freshness validation gap).
- Overall project remains **NO-GO / PARTIAL / NOT PRODUCTION-READY**. The lack of Module 9 runtime wiring is itself a separate integration blocker; do not count it as a duplicate of these two validation findings.
## 36. Module 9 provider response resource-boundary audit — 22 November 2026

### AUD-ONCHAIN-004 — unbounded provider response-body reads
- `ReadOnlyJsonRpcTransport.get_json()` and `.call()` in `layer1/onchain_providers.py` both execute `response.read()` with no byte argument. Neither path checks `Content-Length`, applies a maximum decoded/raw body size, or incrementally stops after a configured limit. The entire response is held in memory before UTF-8 decoding and `json.loads()`.
- This applies to Alchemy JSON-RPC and REST reads and the Chainstack XRPL JSON-RPC adapter, because both adapter factories construct the same transport. The transport timeout is not a response-size bound and does not cap JSON parsing memory/CPU.
- Adapter-level pagination/count controls are not a substitute for a byte limit: Ethereum asset-transfer `max_count` allows up to 1,000 records; Solana full transaction pages allow up to 100 records with `transactionDetails=full`; XRPL `account_tx` allows up to 1,000; and EVM `eth_getLogs` is range-bounded but does not impose a maximum returned log count. A single record or nested transaction can itself be large.
- Existing tests: `python -m unittest tests.test_onchain_providers` — **44 passed, 0 failed**. These tests cover transport envelopes, redirects, API-key redaction, provider pagination and chain-specific validation, but no oversized-response rejection.
- Isolated no-network reproduction: a mocked JSON-RPC response containing a **2,097,203-byte** JSON body (2 MiB string payload plus envelope) was fully read, decoded and returned by `ReadOnlyJsonRpcTransport.call()`. The mock's `read()` received no size argument. This demonstrates absence of a transport byte cap; it does not demonstrate a live provider incident or external unauthenticated exploit.
- **Reachability qualification:** current repository runtime still does not wire the Module 9 worker/aggregator pipeline into `run_once()`. This remains a pre-activation resource-exhaustion hardening blocker, not evidence of a currently reachable production endpoint.
- **Required closure:** define a documented maximum raw response size based on official provider response schemas, documented maximum page sizes, and representative worst-case full-transaction/log payloads; enforce it while streaming (read at most limit + 1), reject oversized or inconsistent `Content-Length`, and fail closed before JSON decoding. Cover both REST and JSON-RPC, absent/misleading Content-Length, chunked/streamed bodies, exact-limit and limit+1 cases, and verify no unbounded read. Do not pick an arbitrary cap without checking provider-supported payload sizes and the actual query shapes.
- Severity remains **MEDIUM — OPEN**. No code/config/schema/DB/provider/network/publisher changes were made. Project remains **NO-GO / PARTIAL / NOT PRODUCTION-READY**.

## 37. Module 9 ClaimRegistry design clarification and finding-ID reconciliation — 22 November 2026

### AUD-ONCHAIN-003 — CLOSED: summary-only corroboration is the documented main-path contract
- `main.py` passes `onchain_summary_refs` to both `EventIntelligenceGraphEngine.rebuild_from_store()` and `EvidenceVerificationEngine.rebuild_from_store()`; it does not pass `onchain_records`.
- `EvidenceVerificationEngine.rebuild_from_store()` supports both optional inputs, but its normal caller supplies only summary refs. `evidence_from_onchain_summary()` requires `threshold_met is True`, validates canonical summary identity/amount/time fields, and marks the resulting evidence `is_primary=False` with source family `module9_canonical_store`.
- `ONCHAIN_INTELLIGENCE.md` explicitly states that on-chain evidence is corroborative only, on-chain-only evidence cannot create a discovery candidate, and the main pipeline persists only corroboration summary IDs/counts. Thus the main path's summary-only interface matches the documented design; individual observation records remain in the Module 9 canonical store and are not intended to become primary ClaimRegistry assertions.
- `python -m unittest tests.test_evidence_verification`: **78 passed, 0 failed**. The attempted combined run with `tests.test_onchain_candidate_integration` could not import that module because Pillow (`PIL`) is absent in the RDC environment; the evidence-verification module itself then ran separately and passed. Do not report the candidate integration module as passed in this environment.
- The lower-level `evidence_from_onchain_observation()` helper remains a separate optional adapter and must not be treated as a production trust boundary. Its caller-supplied `OnChainValidationResult` concern is covered by `AUD-ONCHAIN-001`; do not promote individual observation evidence into the main path until that trust-boundary issue is resolved.
- Disposition: **CLOSED as intended architecture**, not implemented code. This does not close Module 9 runtime worker wiring, provider authenticity, mapping provenance, or PostgreSQL compatibility.

### AUD-ONCHAIN-005 — HIGH / OPEN: PostgreSQL stores cannot be passed to current workers/aggregator
- This is the separate interface incompatibility previously mislabeled `AUD-ONCHAIN-003` in older audit sections. It is assigned a unique ID here; the authoritative register now keeps `AUD-ONCHAIN-003` for the ClaimRegistry design clarification above.
- All four worker constructors explicitly require concrete SQLite `OnChainStore` and `OnChainIngestionStore` instances. `OnChainTransferAggregator` and `bind_ingestion_store()` also enforce those concrete SQLite classes with `isinstance()` checks.
- `PostgresOnChainStore` and `PostgresOnChainIngestionStore` are separate classes, not subclasses of the SQLite store classes. The current worker/aggregator constructors therefore reject the PostgreSQL adapters; PostgreSQL persistence tests alone do not establish end-to-end PostgreSQL ingestion.
- Impact: a PostgreSQL-backed Module 9 worker service cannot be assembled from the existing store adapters without introducing shared protocols/abstractions or explicit PostgreSQL-compatible workers/aggregator. This is distinct from the fact that Module 9 workers are not currently started by `run_once()`.
- Required closure: design a narrow storage protocol based on actual worker/aggregator operations, implement PostgreSQL parity without weakening transactional/canonical-event guarantees, and run isolated PostgreSQL worker + aggregator acceptance tests. No blanket refactor or DB migration is authorized by this audit.
- No code/schema/DB/Neon/provider/publisher changes were made. `AUD-ONCHAIN-005` remains HIGH / OPEN; overall project remains NO-GO / PARTIAL / NOT PRODUCTION-READY.

## 38. Module 14 raw-factor evaluator activation boundary — 22 November 2026

### AUD-M14-002 — confirmed: raw numeric factors can produce PROCEED outside registry-bound provenance
- `OpportunityEvaluationEngine.evaluate()` accepts a plain `Mapping[str, float]` and an `OpportunityPolicy`. If the six factor names are present, values are finite and within 0–100, and the other hard gates pass, it computes the weighted score and can return `PROCEED`. It does not require a factor-assessment envelope, exact ClaimRegistry verification ID, source/claim references, source hashes, cutoff, transformation/baseline metadata, or a previously validated provenance object.
- The evaluator's own input snapshot serializes only the raw `factors` mapping and gate inputs. It does not contain `schema_version`, `factor_assessments`, or `registry_verification_id`. The v3/v4 exact-registry validators and persistence checks exist elsewhere in `layer1/opportunity.py`, but `evaluate()` does not invoke them or require their result before returning `PROCEED`.
- Reproduction used only a synthetic in-process fixture and no provider/database/network: six raw factor values of `90`, a test-only policy with weights summing to 1 and thresholds 75/50, current ELIGIBLE status, READY research and CONFIRMED event returned `PROCEED` with score `90.0`. The resulting snapshot keys contained `factors` but neither `registry_verification_id` nor `factor_assessments`.
- Existing test `test_deterministic_high_quality_research_proceeds` in `tests/test_opportunity.py` explicitly verifies the raw-number path. `python -m unittest tests.test_opportunity`: **38 passed, 0 failed**.
- **Current runtime qualification:** `main.py` calls the evaluator with `factors=None` and `policy=None`. The scheduled path therefore remains fail-closed and returns DEFER when it reaches the scoring gate. This finding concerns the unsafe future activation/API boundary; it is not evidence that the current scheduled runtime can publish through Module 14.
- Severity remains **HIGH — OPEN**. Required closure: production evaluation must accept only a validated immutable factor-assessment object/snapshot that has passed exact registry-bound v3/v4 source resolution and factor-specific claim-support/independence checks; bind its digest and registry verification ID into the decision identity; reject raw `Mapping[str, float]` for production PROCEED. Preserve legacy v1 reads for history without allowing legacy snapshots to create new production PROCEED decisions. Add negative raw-number and positive exact-registry acceptance tests.
- No code, policy, weights, thresholds, factor values, provider, DB/Neon, runtime activation, publisher, workflow, deployment, commit, push or merge changes were made. `AUD-M14-002` remains OPEN; `AUD-M14-001` remains OPEN / FAIL-CLOSED DEFER. Overall project remains NO-GO / PARTIAL / NOT PRODUCTION-READY.

## 39. Module 14 live platform-policy and calibration-evidence review — 22 November 2026

### AUD-M14-001 — remains HIGH / OPEN / FAIL-CLOSED DEFER
- Reviewed the existing `MODULE14_OPPORTUNITY_SCORING_POLICY_PROPOSAL.md` and `MODULE14_FEATURE_DATA_AVAILABILITY_AUDIT.md` before further work. They already define the six-factor qualitative rubric, hard-gate precedence, point-in-time provenance, independent human labels, chronological out-of-time validation, shadow mode and approval gates. No duplicate proposal was created.
- Fresh official Binance Square research: W2E Terms last updated 2026-10-16; W2E upgrade effective 2026-10-19; Community Guidelines updated 2026-11-06. The current rules support hard compliance gates for manipulation, undisclosed conflicts, misleading/fabricated content, fake engagement, spam and plagiarism. They encourage valid/current research, transparency, clear logic and genuine interaction.
- W2E terms describe 7-day trading-commission and 30-day engagement reward windows. These are reward-attribution windows, not source freshness TTLs. Engagement bonus weights account for engagement type and engaging-account standing/activity at Binance's discretion; numerical weights/ranking logic are not publicly disclosed. Do not reverse-engineer or invent them.
- Consequence for scoring: hard policy violations cannot be offset by other factor values; engagement/reward/trading-conversion outcomes are not ground truth for truth or editorial usefulness; duplicate-content eligibility does not itself provide a semantic novelty score. Public platform rules justify qualitative gates, not Module 14 numeric weights.
- Read-only local inventory: only `published_posts.jsonl` matched local CSV/JSONL/Parquet/SQLite/DB inventory; no local SQLite/database, CSV, or Parquet historical calibration dataset was found in this worktree. This is a repository-local inventory only; it does not establish the absence/presence of data in external stores. No production DB/Neon rows were read; Neon remains suspended; CI PostgreSQL data is synthetic.
- No historical production row counts, coverage duration, sample sizes, reviewer labels, inter-rater agreement or out-of-time evaluation are verified. Therefore no defensible weights, thresholds, floors or factor values can be selected from current evidence.
- Decision: existing proposal is consistent with current public rules; keep `policy=None` / `factors=None`, preserve fail-closed DEFER. `AUD-M14-001` remains OPEN. No score/policy values or runtime changes made. See Section 12 of `MODULE14_OPPORTUNITY_SCORING_POLICY_PROPOSAL.md` for the official source cross-check.

### External sources checked
- Binance Square W2E Terms (last updated 2026-10-16): https://www.binance.com/en/square/post/377977188380155
- Binance W2E upgrade announcement (effective 2026-10-19): https://www.binance.com/en/support/announcement/detail/d9c84b68e9ab4ef29bee0cc53dfdabd2
- Binance Square Community Guidelines (updated 2026-11-06): https://www.binance.com/en/support/faq/detail/ecb50ef2012f40b2a2c4f72eaa5b569f

No code, DB/Neon, provider, publisher, workflow, runtime, weights, thresholds, commit, push, merge or deployment changes were made. Overall project remains NO-GO / PARTIAL / NOT PRODUCTION-READY.

## 40. AUD-MAIN-001 current-state re-verification — 22 November 2026

### Disposition: FIXED — no new code change required
- Re-inspected current `main.py:_verify_persistence_integrity()` at lines 898 onward. `_run_git()` checks every Git subprocess return code and raises on nonzero exit; timeouts and unexpected exceptions reach a fail-closed `False` result. The function verifies repository root and history path containment, distinguishes a valid unborn local branch from broken Git state, validates committed and local JSONL records, and compares canonical record multiplicities so local history cannot omit committed records. Missing/empty history is restored only from verified committed bytes; an empty first-run ledger is initialized only after a verified valid unborn-branch state.
- Re-inspected `_run_once_impl()` at `main.py:4582-4588`: a false integrity result returns from the cycle before pending Git push retry, scanning, research, draft generation or publication.
- No-network orchestration reproduction patched `_verify_persistence_integrity()` to return false and `_get_today_post_count()` to return zero. `_run_once_impl()` returned `False`; publisher `publish()` call count was **0**; `_retry_pending_push()` call count was **0**. This directly verifies the fail-closed cycle boundary without invoking any provider or publisher.
- `tests.test_persistence_integrity`: **11 passed, 0 failed**. The RDC host lacks Pillow, so the test process injected temporary import-only `PIL` module/class stubs; no image operation was called.
- `tests.test_scheduled_persistence_safety`: **21 passed, 0 failed** using temporary import-only Pillow stubs and a minimal psycopg exception-class shim. These tests do not establish real PostgreSQL driver/database behavior.
- Historical hosted verification remains recorded in Section 31: commit `5c0a32088d15b3653ed39cad9ddf5ba919bfe066`; GitHub Actions run `45039365667`, mocked safety suite reported 864 tests PASS and isolated PostgreSQL integration acceptance reported 92 tests PASS; PR #14 checks both PASS at that commit. Later commits on the same existing PR branch include the publisher fixes and documentation verification. No new workflow dispatch or real post was made in this re-verification.
- `AUD-MAIN-001` is **FIXED / HOSTED-CI VERIFIED**. `AUD-WF-002` is **FIXED / HOSTED-CI VERIFIED** (cache restore/save steps removed; historical cache objects were not deleted). No code, workflow, schema, DB/Neon, provider, publisher, deployment, commit, push or merge changes were made in this pass.
- Module 21 remains FAIL / PARTIAL because `AUD-PUB-001/002` have remaining operational acceptance caveats, `AUD-M21-001` lacks an approved disposable PostgreSQL crash/recovery drill, and `AUD-GIT-003` remains open. Overall project remains **NO-GO / PARTIAL / NOT PRODUCTION-READY**.

## 41. AUD-MAIN-002 one-shot trend-input wiring re-verification — 22 November 2026

### AUD-MAIN-002 — MEDIUM / OPEN: one-shot mode constructs but does not pass HotSearchEngine
- Current `main()` at `main.py:6316-6332` constructs `hot_search_engine = HotSearchEngine(config)` and then calls `run_once(config, scanner, announcement_engine, research, generator, publisher, posted_symbols)` without passing it. `run_once()` and `_run_once_impl()` both accept `hot_search_engine=None`; `_run_once_impl()` fetches trend records only when this argument is non-None (`main.py:4661-4665`).
- The continuous `main_loop()` path constructs the same engine and passes it positionally to `run_once()` (`main.py:6244-6285`). The execution modes therefore have inconsistent trend-input coverage.
- `.github/workflows/run_bot.yml` currently selects one-shot mode (`POST_INTERVAL: "0"`, `MAX_ITERATIONS: "1"`, `run: python main.py`) and has `DRY_RUN: "1"`. No workflow was dispatched and no post was made in this audit.
- Isolated no-network reproduction patched all constructors with inert fakes and captured the call to `run_once()`: seven positional arguments, no keyword arguments; the constructed `HotSearchEngine` object was not present in the call. No provider HTTP, model call or publisher request occurred.
- `_persist_layer1_market_intelligence()` validates, normalizes, clusters and persists supplied trend signals, and passes per-asset matching trends into `CandidateDiscoveryFilteringEngine.build()`. The candidate engine can use fresh matching trend signals as a discovery input and retains trend/cluster references. `HotSearchEngine` currently gathers CoinGecko Trending and market-derived attention signals; official Binance CMS announcements are separately ingested by Module 4.
- **Severity refinement:** these trends are attention/discovery context, not proof of an event or primary factual claims. The omission can suppress trend-only discovery and remove trend persistence/cluster context from the scheduled one-shot path, reducing recall and coverage. It does not bypass Binance Spot eligibility, evidence verification, opportunity hard gates, content QA or publication authorization. The current workflow is also explicitly DRY_RUN. Therefore the appropriate current rating is **MEDIUM**, not HIGH.
- Existing one-shot lease tests exercise `main()` and the run lease but do not assert that the constructed trend engine reaches `run_once()`; no regression test currently covers this argument.
- **Required closure:** pass `hot_search_engine=hot_search_engine` (or the matching positional argument) in the one-shot `run_once()` call; add a regression test capturing the exact engine identity and a non-publishing integration test proving mocked trend records reach Layer 1 persistence/candidate construction. Keep trend data attention-only and do not use it to bypass event/source evidence gates.
- No code/workflow/runtime/provider/publisher/DB changes were made. `AUD-MAIN-002` remains MEDIUM / OPEN pending explicit approval for code modification and regression tests. No new commit, push, workflow dispatch, deployment, merge or live post.


## 2026-11-22 — AUD-GIT-006 GitHub Actions scheduled-run concurrency and trigger reliability
- Read-only inspection of `.github/workflows/run_bot.yml`: the workflow is scheduled every five minutes and also supports `workflow_dispatch`; the single `run-agent` job has `timeout-minutes: 5`, `concurrency.group: binance-square-bot`, and `cancel-in-progress: false`. No `queue` property is configured.
- Current official GitHub Actions concurrency documentation states the default queue behavior permits at most one running and one pending item per concurrency group; a newer pending run replaces/cancels the existing pending run. The documented `queue: max` option permits up to 100 pending items. Therefore `cancel-in-progress: false` protects the active run but does NOT guarantee every scheduled/manual trigger is retained when runs overlap. The five-minute schedule and five-minute job timeout make overlap plausible; no live Actions run-duration distribution was inspected, so actual frequency is unknown.
- Official GitHub schedule-event documentation states scheduled workflows run only from the default branch and can be delayed during high load; sufficiently high load can cause scheduled jobs to be dropped. This is a platform delivery limitation, not a repository-code defect. The current repository workflow file is configured with `DRY_RUN=1`, `POST_INTERVAL=0`, `MAX_ITERATIONS=1`.
- Repository test inventory includes PostgreSQL scheduled-run acceptance checks that verify a completed run releases the singleton `layer1_run_lease` and checks the resulting run row. This DB lease can serialize runs that actually start, but it cannot recover a scheduled trigger that GitHub never creates or a pending trigger superseded before execution. No production/Neon DB, live workflow history, or current run-duration metrics were inspected in this pass.
- **Disposition:** `AUD-GIT-006` MEDIUM / OPEN as a scheduling/coverage reliability limitation. It is not evidence of duplicate execution or lost publication data. Closure requires an explicit scheduling policy (whether skipped ticks are acceptable), a durable catch-up mechanism if every interval matters, and tests that distinguish trigger delivery from DB lease serialization. Do not change concurrency settings blindly: queueing all five-minute ticks can create backlog and stale work.
- Official references reviewed 2026-11-22: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax (concurrency queue semantics); https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows (schedule default-branch, delay and dropped-trigger behavior).
- No code, workflow, DB/Neon, provider, publisher, gateway, deployment, Git branch, commit, push, merge or real post changes. `git diff --check` passed after this documentation-only entry. Existing unrelated dirty files remain preserved. Overall project remains NO-GO / PARTIAL / NOT PRODUCTION-READY.

## AUD-GIT-005 — FIX IMPLEMENTED LOCALLY (2026-11-22)

The Git subprocess result-handling defect has been addressed in the continuation worktree:
- _try_git_push() now rejects a failed/empty git rev-parse --short HEAD result before staging.
- Both scoped git add operations are checked. Any staging failure returns false and prevents commit/push; this avoids interpreting a later nothing-to-commit message as success after a failed stage.
- _retry_pending_push() now checks git status return code and fails closed rather than treating a failed status query as a clean worktree.
- Added four regression tests for short-SHA failure, each staging failure, and retry status failure.

Verification:
- Focused tests.test_git_push_security: 8 passed, 0 failed.
- The remote device lacks Pillow; the test invocation used import-only Pillow module shims so no image functionality was exercised. No dependency was installed.
- Full suite and hosted CI verification remain pending.
- No commit, push, PR update, deployment, or live publishing action was performed.

Status: FIXED LOCALLY; NOT YET HOSTED-CI VERIFIED.

## 42. Module 14 producer-declared hash semantics and registry version typing — 23 November 2026

- **Finding:** market evidence previously labelled any non-empty `MarketObservation.data_hash` as a canonical parsed-provider-JSON hash. Trend evidence inferred the same hash kind from source-name strings. These are caller-controlled fields; digest format and provider label do not prove the serialization contract.
- **Correction:** `MarketObservation.data_hash_kind` and `TrendSignal.content_hash_kind` are explicit fields with `UNSPECIFIED` defaults and allowlist validation. Known in-repository producers set `CANONICAL_PARSED_PROVIDER_JSON_SHA256` only where they compute the hash over the parsed provider object. Evidence adapters pass through declared semantics and no longer infer them. HotSearch's one-shot record bridge carries the explicit kind. Legacy stored payloads remain readable as `UNSPECIFIED`.
- **Additional structural finding:** registry `schema_version` accepted booleans/floats due Python numeric equality. Claim-support and source-resolution paths now require exact integer versions; source resolution also validates hash-contract version as exact integer 3 or 4.
- **TDD:** RED reproduced incorrect inferred hash kinds and bool/float version acceptance. GREEN added explicit producer, legacy, persistence, tamper-boundary and exact-type tests.
- **Verification:** combined local suite **293 passed, 0 failed, 2 skipped**; compileall and `git diff --check` passed. Temporary import-only Pillow shims were used for main-import tests because Pillow is absent in the RDC environment; no image operation was performed. Two PostgreSQL acceptance tests remain skipped because `TEST_POSTGRES_DSN` is not configured.
- **Limit:** this is metadata/consistency hardening, not producer authentication or proof that provider data is true. No PostgreSQL/Neon/production DB, migration, scoring activation, publisher, gateway, workflow, live post, commit, push or merge occurred. Module 14 remains NO-GO until PostgreSQL acceptance and separate calibration/evaluator blockers are closed.

## 43. AUD-MAIN-002 one-shot HotSearchEngine wiring — 23 November 2026

- **Finding:** one-shot `main()` constructed `HotSearchEngine(config)` but called `run_once()` without passing the optional engine. The continuous loop already passed it. The scheduled one-shot workflow therefore omitted CoinGecko Trending and market-derived trend signals from the Layer 1 discovery/persistence path.
- **Correction:** one-shot `main()` now passes the exact constructed instance as `hot_search_engine=hot_search_engine`.
- **Regression evidence:** a no-network test patches constructors and `run_once()` and asserts exact object identity. The companion trend persistence test verifies provider-declared hash kind survives the main-to-Layer1 persistence bridge. RED reproduced the missing argument; GREEN passes.
- **Disposition:** FIXED LOCALLY, not hosted-CI verified. No workflow dispatch or live scan was run. Trend data remains attention/discovery context only; it does not become event proof or bypass eligibility/evidence gates.

## 44. AUD-ONCHAIN-004 — official provider limits reviewed; byte ceiling intentionally not guessed — 23 November 2026

### Verified official API constraints
- Alchemy Transfers API: `maxCount` can request up to 1,000 results; responses paginate with `pageKey`, whose documented TTL is 10 minutes. Official docs: https://www.alchemy.com/docs/reference/transfers-api-quickstart and https://www.alchemy.com/docs/data/transfers-api/transfers-endpoints/alchemy-get-asset-transfers
- Alchemy Solana `getTransactionsForAddress`: up to 1,000 signatures or 100 full transactions per request. The current adapter requests `transactionDetails=full`, `limit=100`. Official docs: https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-transactions-for-address
- Alchemy Bitcoin `get-address`: `pageSize` defaults to 1,000 and has a documented maximum of 1,000; detail modes include `txids`, `txslight`, and `txs`. The current adapter requests `pageSize` up to 1,000 with `details=txs`. The public page does not state a maximum response-body byte size or fully define the `txslight` response schema. Official docs: https://www.alchemy.com/docs/chains/bitcoin/utxo-api-endpoints/utxo-api-endpoints/get-address
- Alchemy Ethereum `eth_getLogs`: docs state responses are capped at 150 MB; block-range constraints depend on chain/plan. Current adapter limits requests to 10 blocks and filters by one mapped contract plus Transfer topic. Official docs: https://www.alchemy.com/docs/chains/ethereum/ethereum-api-endpoints/eth-get-logs
- XRPL `account_tx`: `limit` is a positive integer, but the server is not required to honor it; pagination uses a server marker. The public method docs do not publish a response-byte maximum. Current adapter defaults to 200 and allows 1,000. Official docs: https://xrpl.org/docs/references/http-websocket-apis/public-api-methods/account-methods/account_tx
- Alchemy's note that some Solana `getBlock` responses exceed 10 MB applies to full block payloads; the current `fetch_solana_block_header()` requests `transactionDetails=none`, so it is not a size bound for `getTransactionsForAddress`. Reference: https://support.alchemy.com/articles/5946341734-why-does-solana-getblock-sometimes-time-out-or-run-slow-and-how-do-i-fix-it

### Disposition
- These page/count limits do not establish a raw-byte bound for all request shapes. Only `eth_getLogs` has an explicit documented 150 MB response cap among the inspected methods. Bitcoin full transaction details, XRPL nested `meta.AffectedNodes`, Solana full transaction metadata/log messages and Alchemy transfer pages lack a common published byte ceiling.
- A global 150 MB cap would leave an unnecessarily large raw-body/JSON-parse memory exposure. A guessed smaller cap (for example 16 MB) could reject valid provider responses, especially full-transaction/log pages. The audit therefore does **not** invent a global byte cap.
- `AUD-ONCHAIN-004` remains **MEDIUM / OPEN**. Before implementation, measure representative upper-bound JSON payloads for each actual query shape, verify Alchemy account plan and endpoint behavior, then select method-specific raw-byte ceilings. The transport change must still reject oversized or inconsistent `Content-Length` and stream at most `limit + 1` bytes before JSON decoding.
- No source/config/test/provider/DB/Neon/worker/publisher/workflow changes were made in this research pass. No live API call was made. Project remains NO-GO / PARTIAL / NOT PRODUCTION-READY.


## 45. AUD-ONCHAIN-004 — follow-up schema-bound review — 23 November 2026

Additional official provider/protocol documentation was checked to determine whether the unresolved response-size ceiling can be derived from record schemas:
- Alchemy Bitcoin `get-address` documents `pageSize` maximum 1,000 and `details=txs` as an available detail mode, but publishes no maximum byte size, maximum transaction count per address-page record beyond the page count, or detailed `txs` response schema/size ceiling. The adapter currently requests up to 1,000 full-detail transaction records. Official reference: https://www.alchemy.com/docs/chains/bitcoin/utxo-api-endpoints/utxo-api-endpoints/get-address
- Solana documents transaction wire-size limits (legacy/v0 1,232 bytes; v1 4,096 bytes), but that does not bound the JSON RPC response: full transaction metadata separately includes `innerInstructions`, `logMessages`, token balances, loaded addresses and optional return data. The JSON-structure reference documents these as arrays/objects but gives no aggregate response-byte maximum or per-string maximum for log messages. Thus the wire-size limit cannot be used as the full JSON response cap. Official references: https://solana.com/docs/core/transactions and https://solana.com/docs/rpc/json-structures
- XRPL `account_tx` documents `limit` as a positive integer and explicitly says the server is not required to honor it. The example response includes a variable-length `meta.AffectedNodes` array and nested node fields, while the public method reference does not publish a response-byte ceiling. Official reference: https://xrpl.org/docs/references/http-websocket-apis/public-api-methods/account-methods/account_tx

Disposition unchanged: these docs strengthen the case that request record counts and protocol transaction sizes are not equivalent to complete serialized JSON response bounds. No defensible provider-specific byte ceilings can be derived from the public docs reviewed. `AUD-ONCHAIN-004` remains MEDIUM / OPEN pending representative response telemetry from an authorized provider account (or an explicit operator memory-budget policy with a documented truncation/retry strategy). No credentials or provider environment values were read; the remote environment currently has none of the Alchemy/Chainstack/PostgreSQL-related variables set. No provider calls, database connections, code changes, tests, workflow dispatches, or publication actions were performed in this follow-up.


## 46. AUD-ONCHAIN-005 — PostgreSQL worker/aggregator incompatibility reproduced — 23 November 2026

### Confirmed implementation boundary
- `PostgresOnChainStore` (`layer1/onchain_postgres.py`) and `PostgresOnChainIngestionStore` are independent classes; neither subclasses the corresponding SQLite implementation (`OnChainStore` in `layer1/onchain.py`, `OnChainIngestionStore` in `layer1/onchain_ingestion.py`). Their public method names/signatures are largely parallel, but nominal type identity is enforced before any store operation.
- All four worker constructors (`BitcoinAddressIngestionWorker`, `EvmTransferIngestionWorker`, `SolanaAddressIngestionWorker`, `XrplIssuedCurrencyIngestionWorker`) reject mapping/ingestion stores unless they are instances of the concrete SQLite classes. `OnChainTransferAggregator.__init__`, `bind_ingestion_store()`, `aggregate()` and `aggregate_store()` impose the same concrete SQLite restrictions.
- The PostgreSQL mapping adapter does expose `engine`, `list_verified_mappings`, and `get_latest_accepted_observation`, which are used by the aggregation logic. The PostgreSQL ingestion adapter exposes the worker/aggregator methods (`get_checkpoint`, `commit_page`, `get_block_hash`, `reconcile_block`, `get_event`, `get_solana_slot_journal`, `list_all_events`). The principal confirmed blocker is the concrete `isinstance` gate, not an absence of the broad method surface.
- `PostgresOnChainIngestionStore.commit_page()` deliberately requires `expected_cursor` and `scope_identity` for optimistic concurrency and scope binding. All inspected worker commit sites supply both. PostgreSQL reorg reconciliation requires explicit provider and scope; the inspected worker call sites supply both. This is a stricter contract that must be retained in any abstraction, not relaxed to SQLite's optional arguments.
- `main.py` currently contains no imports, construction or `run_once()` wiring for any of the four Module 9 workers or `OnChainTransferAggregator`. Therefore the PostgreSQL worker incompatibility is a pre-activation integration blocker, not evidence of a presently running Module 9 production ingestion path.

### No-database reproduction
- Created uninitialized Python objects with `object.__new__` for the two PostgreSQL adapter classes; this did not open a connection or execute SQL.
- Verified `isinstance(PostgresOnChainStore_object, OnChainStore)` and `isinstance(PostgresOnChainIngestionStore_object, OnChainIngestionStore)` both return `False`.
- Attempted construction of each of the four workers with those PostgreSQL adapter objects and valid inert configuration. All four deterministically raised their `ValueError` concrete-store guard before provider/store use. Constructing `OnChainTransferAggregator` with the PostgreSQL mapping object likewise raised `ValueError: mapping_store must be the verified OnChainStore`.
- This directly reproduces the blocker without a PostgreSQL DSN, driver connection, provider call, database write or migration.

### Regression suite and limits
- `python3 -m unittest tests.test_onchain_bitcoin_worker tests.test_onchain_evm_worker tests.test_onchain_solana_worker tests.test_onchain_xrpl_worker tests.test_onchain_aggregation tests.test_onchain_postgres`: **73 tests run, 0 failures/errors, 14 skipped**.
- The 14 PostgreSQL integration tests were skipped because `TEST_POSTGRES_DSN` is not configured. The PostgreSQL adapter import/contract test ran, but it does not prove live PostgreSQL transaction or worker/aggregator compatibility. No test database was contacted.

### Required remediation design (not implemented)
- Introduce narrow structural protocols (or explicit adapters) for the mapping store and ingestion store based on the methods actually consumed. Do not use broad inheritance solely to satisfy `isinstance`.
- Preserve the PostgreSQL-specific safety requirements: explicit `(network_id, provider, scope)` identity; mandatory expected checkpoint snapshot; stale-checkpoint rejection; transactional page/event/block/slot updates; advisory/row locking; monotonic reorg tombstones and explicit canonical re-inclusion policy.
- Ensure aggregation can consume both stores while preserving `engine.validate()` and current accepted-mapping/observation semantics. Consider a shared storage bundle/factory so workers cannot accidentally mix SQLite and PostgreSQL stores.
- Add constructor acceptance tests for all four PostgreSQL-backed workers and aggregator; SQLite regression coverage; parity tests for checkpoint, reorg, Solana slot journal, deduplication, restart/replay and concurrent checkpoint advancement; then run full isolated PostgreSQL acceptance against an explicitly approved disposable `TEST_POSTGRES_DSN`.
- Do not connect to Neon/production or apply migrations as part of this work. Runtime wiring into `main.py` remains a separate explicit architecture/activation decision.

Disposition: `AUD-ONCHAIN-005` remains **HIGH / OPEN**. No code, schema, DB, provider, worker runtime wiring, publisher, workflow, deployment, commit, push or merge changes were made. Project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.

## 47. AUD-ONCHAIN-001 — signed acceptance receipt hardening (local remediation slice) — 23 November 2026

### Change summary
- Added version-1 HMAC-SHA256 acceptance receipts to OnChainValidationResult. A successful validation now binds the receipt to canonical SHA-256 fingerprints of the exact OnChainObservation and the combined EligibilityDecision + OnChainAssetMapping + OnChainObservation snapshot.
- Signing requires an explicitly injected key of at least 32 bytes and a configured key ID. The key ID is included in the signed envelope; verification requires the expected key ID. No key material is generated, stored, logged, or committed by this change.
- OnChainIntelligenceEngine.validate() now fails closed with UNAVAILABLE / ONCHAIN_RECEIPT_SIGNING_NOT_CONFIGURED when all ordinary checks pass but receipt signing is not configured. It does not emit an unsigned ACCEPTED result.
- EvidenceVerificationEngine.evidence_from_onchain_observation() no longer treats a caller-constructed ACCEPTED result plus matching identifiers as primary accepted evidence. It requires a valid signed receipt and explicit verification key; the configured expected key ID is also required. rebuild_from_store() forwards those explicit verification settings.
- SQLite and PostgreSQL observation read paths now authenticate persisted ACCEPTED receipts against the configured verification key and current expected key ID. A tampered/unauthenticated record is downgraded to UNVERIFIED; the latest-accepted lookup ignores invalid receipts.
- Receipt verification covers the observation payload fingerprint, validation identity, receipt version, key ID, evidence-snapshot fingerprint, reason code and reason. HMAC comparisons use constant-time comparison.

### TDD and verification
- RED: the new receipt regression initially failed because OnChainIntelligenceEngine.__init__() did not accept the signing-key contract. The test also specifies that caller-created ACCEPTED results must not become accepted evidence.
- GREEN: signed receipt, wrong-key, wrong-key-ID, observation-tamper, no-key fail-closed, and SQLite persisted-payload-tamper tests pass.
- Focused Module 9/evidence/source-adapter batch: 197 tests, 0 failures/errors, 14 skipped. The 14 skips are PostgreSQL integration cases because TEST_POSTGRES_DSN is not configured.
- Full repository suite using the isolated test virtualenv: 927 tests, 0 failures/errors, 63 skipped.
- compileall for changed Python modules and git diff --check passed.

### Explicit residual limitations — finding remains OPEN
- This change authenticates that a holder of the configured HMAC key issued a receipt for the exact supplied eligibility/mapping/observation snapshot. It does not prove the upstream provider response itself was authentic or that the supplied observation was derived from that response.
- OnChainObservation still does not retain a provider-response digest or immutable raw/minimized response artifact. Current Module 9 worker paths do not construct and submit these individual OnChainObservation objects to the acceptance engine; repository call-site review still shows the individual-observation evidence adapter is not activated by main.py.
- HMAC is a shared-secret scheme: signing and verification use the same key. Deployment must inject the key only from a protected secret manager into the trusted validation boundary and the intended verifier; do not expose it to untrusted callers, plugins, logs, repository files, or public configuration. Key rotation/key-ring support and operational secret provisioning are not implemented here.
- PostgreSQL integration behavior remains unverified because no disposable TEST_POSTGRES_DSN was provided. No PostgreSQL, Neon, production DB, migration, provider endpoint, or Binance publishing action was performed.
- Therefore AUD-ONCHAIN-001 is PARTIALLY REMEDIATED / OPEN, not closed. Closure still requires source-specific provider-response binding, trusted worker ingestion wiring, key provisioning/rotation policy, and disposable PostgreSQL tamper/fresh-process acceptance.
- AUD-ONCHAIN-002, AUD-ONCHAIN-004, and AUD-ONCHAIN-005 remain independently OPEN. Overall project status remains PARTIAL / NOT PRODUCTION-READY / NO-GO.
- No commit, push, merge, deployment, workflow dispatch, live publication, or production data mutation occurred.

## 48. AUD-ONCHAIN-005 — narrow storage protocol remediation design (design-only; no code change) — 23 November 2026

### Required structural contracts derived from actual call sites
- `OnChainMappingStoreProtocol`: `list_verified_mappings(network_id=None)`, `get_latest_accepted_observation(mapping_id)`, and an `engine` exposing the same `validate(eligibility, mapping, observation, now=...)` contract. The aggregator uses all three; workers use the mapping list.
- `OnChainIngestionStoreProtocol`: `get_checkpoint(cursor_key)`, `commit_page(...)`, `get_block_hash(network_id, provider, scope, block_number)`, `reconcile_block(network_id, block_number, canonical_block_hash, provider, scope)`, `get_solana_slot_journal(network_id, provider, scope, start_slot, end_slot)`, `get_event(event_id, network_id, provider, scope)`, and `list_all_events(canonical_only=False)`.
- AST call-site inventory across all four workers and `OnChainTransferAggregator` found no additional store methods required by these components. `save_verified()` and `get_observation()` are persistence API methods, not worker/aggregator dependencies.

### Safety semantics the abstraction must preserve
- Treat `expected_cursor` and `scope_identity=(network_id, provider, scope)` as mandatory at the worker-facing `commit_page` protocol boundary. All inspected worker call sites already supply both. SQLite may retain broader optional defaults internally for legacy/direct callers; the protocol must not let worker code omit either.
- Keep PostgreSQL's `commit_page` transaction atomic across transfer-event inserts/recanonicalization, canonical block/slot journal writes, and checkpoint advancement. Preserve its advisory transaction lock, checkpoint row lock, cursor snapshot comparison, cursor-key/scope binding, and rollback-on-conflict behavior.
- Require explicit `provider` and `scope` for `reconcile_block` in the protocol. PostgreSQL currently raises if either is omitted; all worker call sites pass both. Do not weaken PostgreSQL's scope-qualified reorg tombstoning.
- Preserve canonical event identity collision checks, monotonic canonical/reorg state transitions, canonical block/slot journal consistency, and Solana skipped-slot semantics. No generic CRUD abstraction or inheritance coupling is needed.
- Keep aggregator access to the mapping store's configured validation engine and signed-receipt-aware `get_latest_accepted_observation`; protocol acceptance must not bypass receipt verification or the fail-closed no-key behavior.

### Proposed implementation shape
- Add a small `layer1/onchain_protocols.py` module with `typing.Protocol` contracts (runtime-checkable only if supported by the repository's minimum Python version). Avoid making PostgreSQL classes inherit SQLite implementations.
- Change worker and aggregator annotations/imports to the protocols and replace concrete SQLite `isinstance` checks with narrow structural contract validation. At runtime, validate that required attributes are callable and that the mapping store exposes a compatible engine; do not rely on `hasattr` alone.
- Keep the existing SQLite and PostgreSQL adapters as independent implementations. Do not alter SQL schema, migrations, DSNs, connection lifecycle, provider clients, worker seeds, `main.py` runtime wiring, or scoring/publication behavior in this slice.

### TDD / acceptance plan before implementation
- RED tests: construct both adapter shapes without a database connection and prove all four worker constructors currently reject PostgreSQL-shaped stores; add protocol contract tests that verify the precise required callable surface.
- GREEN tests: prove SQLite adapters remain accepted; PostgreSQL adapter instances with inert/fake connections and an explicitly configured test receipt engine satisfy the same worker constructor contracts without any provider calls or SQL execution; verify aggregator accepts both structural adapters using a controlled fake mapping-store response.
- Negative tests: reject missing/non-callable methods, a mapping store without a validation engine, and any commit invocation that omits the expected cursor or scope identity at the protocol boundary. Retain all current concrete SQLite tests.
- Regression/semantic tests: verify the worker call sites still pass checkpoint snapshots and exact scope identity; verify reorg reconciliation always includes provider+scope; retain SQLite and PostgreSQL atomicity/conflict tests unchanged.
- Database acceptance remains a separate gate: run worker+aggregator integration against an explicitly approved disposable PostgreSQL database (`TEST_POSTGRES_DSN`), including competing checkpoint writers, stale cursor rejection, event/block/slot/checkpoint atomic rollback, reorg tombstoning and restart/resume. No production Neon connection.

### Disposition
- This is an interface-only remediation design. No source or test code was changed for AUD-ONCHAIN-005 in this step; no DB/provider/Neon/publisher operation was performed.
- `AUD-ONCHAIN-005` remains HIGH / OPEN until implementation, local regressions, and disposable PostgreSQL acceptance pass. `main.py` runtime activation is explicitly out of scope and remains a separate approval/gate.
- Existing worktree state and HEAD were preserved (`work/module9-continuation-local`, `60ec380c28e07f8498eed9a4647c345538382bf2`). Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.

## 49. AUD-ONCHAIN-005 — structural storage protocol implementation (local; PostgreSQL execution acceptance pending) — 23 November 2026

### Implementation
- Added `layer1/onchain_protocols.py` with `OnChainMappingStoreProtocol`, `OnChainValidationEngineProtocol`, and `OnChainIngestionStoreProtocol`. These are structural typing contracts; PostgreSQL adapters do not inherit from SQLite implementations.
- Mapping contract covers `list_verified_mappings`, `get_latest_accepted_observation`, and the validation engine's `validate` capability.
- Ingestion contract covers checkpoint reads/commits, block hash reads, scope-qualified reorg reconciliation, Solana slot journals, event lookup, and canonical event listing.
- Added constructor-time structural validation to all four workers (Bitcoin, EVM, Solana, XRPL) and to `OnChainTransferAggregator` / its ingestion-store binding. The guard verifies required methods are callable, the mapping store has a callable validation engine, and ingestion adapter signatures accept the required `expected_cursor`, `scope_identity`, `provider`, and `scope` keyword arguments.
- Worker and aggregator type annotations now use the protocols. Existing SQLite and PostgreSQL adapter implementations remain independent; no inheritance, schema, migration, or SQL transaction code was changed.

### TDD and verification
- RED: `tests.test_onchain_store_protocols` initially failed on all four PostgreSQL-shaped worker constructors and the aggregator constructor; the protocol module and mandatory keyword contract were absent. Negative guard tests also exposed the old generic SQLite-only rejection.
- GREEN: new tests prove all four worker constructors and the aggregator accept uninitialized PostgreSQL adapter objects with a test-only validation engine and no database connection, SQL execution, or provider call. Negative tests reject missing methods, missing validation engine, and ingestion adapters whose methods cannot accept the required checkpoint/scope keywords.
- Focused Module 9 batch (new protocol tests + all four worker suites + aggregator + PostgreSQL adapter contract tests): **83 tests, 0 failures/errors, 14 skipped**. PostgreSQL integration tests skipped because `TEST_POSTGRES_DSN` is not configured.
- After adding runtime signature validation and its negative regression, new protocol tests: **11 passed, 0 failed**.
- Final full repository suite after all source/test changes: **938 tests, 0 failures/errors, 63 skipped** using `/tmp/binance-module11-test-venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
- `compileall` for all changed Module 9 Python files and `git diff --check` passed.

### Acceptance boundary and remaining work
- The confirmed nominal type mismatch at worker/aggregator construction is remediated in code. Mark the finding **PARTIALLY REMEDIATED / OPEN**, not closed.
- No disposable PostgreSQL DSN was available. The 14 PostgreSQL integration cases in the focused batch and 63 full-suite skips were not executed against a real PostgreSQL server. Therefore actual PostgreSQL worker page commits, row/advisory locking, cursor compare-and-swap, transaction rollback, reorg journaling, and worker+aggregator end-to-end behavior remain unverified.
- Before closing: run the worker and aggregator acceptance matrix against an explicitly approved disposable PostgreSQL database; include concurrent checkpoint writers, stale cursor rejection, atomic rollback across events/block-or-slot journal/checkpoint, reorg tombstoning/recanonicalized replay, and restart/resume. No production Neon access.
- `main.py` remains intentionally unwired to Module 9 workers/aggregator. This implementation only makes the adapters structurally pluggable; it does not activate ingestion or imply production readiness.
- No live provider, PostgreSQL/Neon, production database, migration, Binance publishing, commit, push, merge, deployment, or workflow dispatch was performed. Existing dirty worktree state and HEAD were preserved.


## 50. AUD-ONCHAIN-002 / AUD-ONCHAIN-004 — continuation snapshot re-verification — 23 November 2026

### AUD-ONCHAIN-002 — mapping source and freshness gap remains reproducible
- Re-read the current OnChainIntelligenceEngine._validate_mapping() implementation and both persistence read paths. The validator still checks the source-type enum and HTTPS URL syntax, but does not bind a source host/path to the network/source type and does not enforce a maximum mapping age. SQLite and PostgreSQL list_verified_mappings() continue to call this validator.
- Reproduced the current validator behavior with the existing BTC mapping identity (coingecko:bitcoin, btc-mainnet-native-v1) and a verified_at timestamp of 2016-11-23: both https://attacker-controlled.invalid/fake-official-token-list and https://bitcoin.org/ return no mapping-validation error. This is a direct no-network call to _validate_mapping(); it does not claim the complete evidence pipeline returns ACCEPTED.
- No source changes were made. Correct remediation cannot safely invent an expiry TTL or authoritative host/path matrix. Those values require a reviewed mapping-source policy tied to each source type/network, plus documented update cadence and revalidation expectations. Until that policy exists, keep AUD-ONCHAIN-002 HIGH / OPEN.

### AUD-ONCHAIN-004 — unbounded transport reads reconfirmed
- Current ReadOnlyJsonRpcTransport.get_json() and .call() still use unbounded response.read() before UTF-8 decoding and JSON parsing. The shared transport therefore still has no enforced response-body byte ceiling or early Content-Length rejection.
- A defensible default byte ceiling is not derivable from the current public provider record-count limits alone. Do not introduce an arbitrary cap that silently rejects legitimate full transaction pages. Closure still requires either representative maximum legitimate payload measurements for each request shape or an explicitly approved process memory budget, followed by bounded streaming reads and oversized/chunked-response tests.
- AUD-ONCHAIN-004 remains MEDIUM / OPEN. No provider request, code change, test fixture mutation, database access, or workflow action was performed.

### Scope and disposition
- This was a read-only local audit continuation. No source behavior, schema, configuration, credentials, database, provider, publisher, workflow, deployment, Git index, commit, or remote branch was changed.
- AUD-ONCHAIN-002 and AUD-ONCHAIN-004 remain open. AUD-ONCHAIN-003 remains closed as the intended summary-only corroboration contract. AUD-ONCHAIN-005 remains partially remediated/open pending disposable PostgreSQL execution acceptance. Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 51. AUD-GRAPH-001 — equal-timestamp relationship deduplication status ordering — 23 November 2026

### Reproduction and correction
- The graph builder deduplicates relationships by stable relationship ID. For equal observed_at timestamps it previously compared `(status, confidence)` tuples lexicographically. Because `UNKNOWN` sorts after `CONFIRMED`, an UNKNOWN edge could replace a CONFIRMED edge even at identical timestamp and confidence.
- Added a regression that supplies same-identity, same-timestamp edges in both input orders: CONFIRMED at confidence 0.4 and UNKNOWN at 0.99. RED reproduced the defect: UNKNOWN was retained.
- Replaced lexical status ordering with explicit semantic priority `CONFIRMED > POSSIBLE > UNKNOWN`; confidence is the secondary tie-break only within the same status. Existing newest-observation-first behavior is unchanged.

### Verification
- Focused event-graph suite, including the new order-independent regression: **13 tests passed, 0 failed**.
- Full isolated repository suite: **939 tests, 0 failures/errors, 63 skipped** (`python -m unittest discover -s tests -p 'test_*.py'`, isolated virtualenv).
- No live provider, production DB, PostgreSQL/Neon, publication, workflow, deployment, or Git remote action occurred.

### Disposition
- `AUD-GRAPH-001` is **FIXED LOCALLY / NOT HOSTED-CI VERIFIED**. Graph semantics changed only for equal-timestamp duplicate relationship conflict resolution. No unrelated graph behavior or persistence schema changed.
- Worktree remains on `work/module9-continuation-local`; HEAD remains `60ec380c28e07f8498eed9a4647c345538382bf2`. All existing unrelated dirty/untracked changes preserved. No staging, commit, push, or merge.
- Project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 52. AUD-RESEARCH-001 / AUD-EDITORIAL-001 — typed package/brief hash integrity hardening (local; legacy generic API and PostgreSQL execution gates remain) — 23 November 2026

### AUD-RESEARCH-001 — canonical research-package digest checks
- Added a single canonical content projection for the typed `ResearchPackage` payload. Generated/storage metadata (`research_key`, `package_id`, `version`, `package_hash`) is excluded; all research content, including cutoff, source coverage, facts, inferences, disputed/unknown claims, event states and gaps, remains hash-bound.
- `ResearchPackageStore.save()` now recomputes the digest before insert/idempotent reuse. `load_latest()` recomputes the digest and compares it with both the payload digest and the immutable row `package_hash` before returning the record.
- The PostgreSQL validation and read paths now perform the same digest/identity/cutoff checks for the complete typed research-package payload. Historical generic JSON payloads used by low-level compatibility tests remain accepted under the legacy syntax-only contract; that generic API path is not certified as content-integrity protected and remains a residual boundary.
- TDD RED: added tests for caller-supplied mismatched package hash, altered SQLite stored payload, and altered complete typed payload at the PostgreSQL validation boundary; all three failed before implementation. GREEN: all pass.

### AUD-EDITORIAL-001 — canonical editorial-brief digest checks
- Added a canonical content projection for the typed `EditorialBrief`, excluding only generated `brief_id`, `version`, and `brief_hash`; all editorial policy fields, approved claim IDs, prohibited claims, uncertainty notes, length bounds and policy version remain hash-bound.
- SQLite `EditorialBriefStore.save()` now recomputes the digest before insert. Idempotent reuse checks the existing stored payload digest before returning the prior identity.
- PostgreSQL save validation and load paths now recompute and compare the digest and bind payload event/angle/research-package identity to row identity for complete typed brief payloads. Historical generic low-level JSON payloads retain compatibility and remain a residual unverified path.
- TDD RED: new mismatched-hash, tampered stored-payload, and PostgreSQL validator tamper tests failed before implementation. GREEN: all pass.

### Verification
- Focused research/editorial/PostgreSQL contract suite: **98 tests, 0 failures/errors, 28 skipped**. Skips are PostgreSQL DSN-gated cases.
- `compileall` for changed implementation and test files passed; `git diff --check` passed.
- Full isolated repository suite after Module 10/13/16 changes: **948 tests, 0 failures/errors, 63 skipped**.

### Disposition and residuals
- `AUD-RESEARCH-001` and `AUD-EDITORIAL-001` are **PARTIALLY REMEDIATED / OPEN**. Typed application payload paths now verify unkeyed content digests, but low-level legacy generic payload compatibility remains syntax-only; PostgreSQL integration/tamper/fresh-process acceptance was not executed because no disposable `TEST_POSTGRES_DSN` is configured. Unkeyed SHA-256 detects accidental/mismatched content but does not authenticate a malicious database writer.
- No database, Neon, migration, provider, publisher, workflow, deployment, commit, push or merge operation was performed. Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 53. AUD-LIFE-001 — caller-asserted resolution/withdrawal evidence disabled at lifecycle boundary — 23 November 2026

### Reproduction and correction
- The direct SQLite and PostgreSQL `observe()` APIs previously accepted `verification_state='VERIFIED'` plus any non-empty `resolution_evidence_id` string to transition an event to RESOLVED or WITHDRAWN. The value was copied into transition evidence references without resolving it against a verifier-issued claim/evidence result.
- Added a no-database regression for both direct API variants. RED reproduced acceptance of arbitrary caller strings for both resolution and withdrawal.
- Both SQLite `EventLifecycleStore.observe()` and PostgreSQL `PostgresEventLifecycleStore.observe()` now fail closed if callers set `resolved`, `withdrawn`, or `resolution_evidence_id`. The error explicitly requires verifier-issued proof; arbitrary string IDs can no longer create terminal state transitions.
- The normal `sync_announcements()` path is unchanged. It derives ordinary event verification state from the ClaimRegistry; it does not request resolution/withdrawal transitions.

### Verification
- `tests.test_event_lifecycle`: **26 passed, 0 failed**.
- `tests.test_event_lifecycle_postgres`: **9 run, 0 failures, 6 skipped**; the new PostgreSQL adapter guard test executes without a database, while six integration cases remain DSN-gated.
- No PostgreSQL/Neon database, provider, publisher or production service was contacted.

### Disposition and limitation
- `AUD-LIFE-001` is **PARTIALLY REMEDIATED / OPEN**. Caller-supplied evidence strings can no longer assert resolution/withdrawal. This is deliberately fail-closed: the current product path has no verifier-issued, event-scoped resolution/withdrawal proof contract, so direct terminal transitions are disabled rather than pretending to validate them. A future implementation must bind a trusted verifier result to the exact event, resolution claim, source and evidence before restoring this capability.
- Existing tests that expected arbitrary string IDs to resolve/withdraw were replaced with explicit rejection and no-state-change assertions. No schema or migration change.
- No commit, push, merge, workflow, deployment or publishing action. Project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 54. AUD-CONTENT-001 — editorial allowlist enforced through validation, draft persistence and publication authorization — 23 November 2026

### Implementation
- `ContentVerificationEngine.validate()` now requires an intact typed READY `EditorialBrief`. It recomputes the canonical brief content hash, uses only the brief's approved claim IDs, rejects verified claims outside that allowlist, and rejects any referenced claim whose normalized text appears in the brief's prohibited-claims list.
- `main.py` now passes the exact `best_editorial_brief` into content verification. The end-to-end test uses the persisted brief returned by `EditorialBriefStore`.
- SQLite `DraftStore.save_draft()` now resolves the persisted brief, verifies its canonical hash/READY status and exact research-package binding, and requires every draft claim ID to be a subset of its approved allowlist.
- SQLite publication authorization repeats the claim-subset check against the persisted brief when creating authorization and again during persisted event-binding revalidation. Tampered or incomplete allowlists fail closed.
- PostgreSQL `PostgresPublicationAuthorizationEngine` performs the same typed brief/hash/allowlist check before creating authorization and during revalidation. `PostgresPublicationStore.save_publication_authorization()` and the final durable-attempt submission path repeat the subset check against the persisted brief payload.
- Historical generic low-level PostgreSQL editorial JSON payloads remain readable/writable for compatibility in non-authorizing paths, but cannot pass the publication authorization boundary because they do not satisfy the typed READY brief contract.

### TDD and verification
- Added tests proving a VERIFIED claim outside the editorial allowlist is rejected, a tampered typed brief is rejected, a draft store refuses claim IDs outside the persisted brief allowlist, and tampering with the SQLite persisted brief allowlist invalidates an existing authorization.
- The new content/draft/auth tests passed along with existing regression tests: focused set **60 tests, 0 failures/errors** across publication runtime, SQLite publication authorization, content generation and content verification.
- PostgreSQL persistence tests: **54 tests, 0 failures/errors, 28 skipped**. The DB-backed authorization/final-attempt tests remain skipped because no disposable `TEST_POSTGRES_DSN` is configured. The PostgreSQL runtime fake-store contract test was updated to use a valid typed brief payload.
- compileall and `git diff --check` passed for the changed modules and tests.

### Disposition
- `AUD-CONTENT-001` is **PARTIALLY REMEDIATED / OPEN** until disposable PostgreSQL integration proves the authorization and final-attempt SQL paths against the real schema, including persisted-brief tampering. The deterministic content gate and SQLite persistence/authorization paths now enforce the allowlist.
- No provider, production DB/Neon, migration, publishing, commit, push, merge, deployment or workflow action occurred. Project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 55. AUD-CONTENT-002 — SOURCE_ASSERTION publisher attribution enforced in the deterministic content gate — 23 November 2026

### Reproduction and correction
- A SOURCE_ASSERTION claim can be VERIFIED only in the limited sense that its named publisher made the assertion. The prompt renderer already tells the model to attribute such claims, but the deterministic content gate previously accepted the exact claim text without checking the final sentence named the publisher.
- Added regressions for a verified Binance announcement-body assertion. RED reproduced the gap: the unqualified exact claim text was accepted by the old gate. Tests also cover correct Binance attribution and misleading CoinGecko attribution.
- ContentVerificationEngine now resolves the actual supporting evidence IDs for each SOURCE_ASSERTION, derives publisher names from those exact evidence records, and requires one of these explicit sentence prefixes: "According to <publisher>:" or "<publisher> said/stated/reported:". The remaining sentence must still exactly match the claim text after normalization. Missing publisher metadata and wrong publisher names fail closed.
- The end-to-end fixture's market-price claim was corrected to CONFIRMED_FACT; it had been incorrectly relabelled SOURCE_ASSERTION despite being a structured market metric. The announcement-body claim remains a source assertion and must be attributed.

### Verification
- tests.test_content_verification: 20 tests passed, 0 failed.
- Content verification + end-to-end regression: 21 tests passed, 0 failed.
- Focused content/draft/authorization/runtime suite passed before this source-attribution addition: 60 tests, 0 failures/errors. Full repository suite is to be rerun after this latest change.
- No provider, production database, publication, or workflow operation was performed.

### Disposition and limitation
- AUD-CONTENT-002 is PARTIALLY REMEDIATED / OPEN. The deterministic application content gate now preserves source-assertion semantics and exact publisher attribution. It does not independently authenticate the upstream publisher identity; that remains governed by Module 11 evidence/source trust controls. A caller that bypasses the content engine and directly forges a PASS validation record is a separate persisted-validation trust-boundary concern and is not certified closed here.
- Project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 56. AUD-CONTENT-001/002 — full-suite regression checkpoint after editorial-scope and attribution gates — 23 November 2026
- Fixed test fixtures in `tests/test_publisher_safety.py` to persist real typed READY editorial briefs before draft creation; the previous fixtures inserted generic `{}` brief payloads only after `DraftStore.save_draft()`, which no longer satisfies the enforced persisted-brief contract. The operator-reconciliation fixture was updated the same way.
- `tests.test_publisher_safety`: **52 tests passed, 0 failed** after fixture correction.
- Final full isolated repository suite after all Module 10/12/13/16/17/18 changes: **957 tests, 0 failures/errors, 63 skipped**, command `/tmp/binance-module11-test-venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
- `compileall` across all changed implementation/test modules passed; `git diff --check` passed.
- The 63 skipped tests still include PostgreSQL DSN-gated acceptance. No disposable `TEST_POSTGRES_DSN` was configured, so PostgreSQL worker/authorization/final-attempt SQL paths remain unexecuted. No production Neon/database, migration, provider, publishing, commit, push, merge, deployment, or workflow operation occurred.
- Current work remains local/uncommitted on `work/module9-continuation-local`; project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.

## 57. AUD-DRAFT-001 — validation chronology sequence hardening (SQLite local fix; PostgreSQL acceptance blocked) — 24 November 2026

### Reproduction and impact
- Re-read the section 21 finding against the live continuation worktree, including SQLite table creation/upgrade, append-only insert methods, publication authorization, publisher final gate, PostgreSQL migration runner, PostgreSQL authorization, durable-attempt validation, and latest-validation store APIs.
- The defect was present in both SQLite authorization and the actual publisher final gate: each selected by `created_at DESC, validation_id DESC`, while the digest ID has no temporal semantics. PostgreSQL authorization, durable-attempt validation and latest-record reads had the same unsafe digest tie-break.
- Added two actual SQLite authorization regressions. RED: with identical timestamps, PASS inserted first under `ffff…` and later REJECT / NEEDS_REVISION under `aaaa…`, both authorization attempts unexpectedly succeeded. This reproduced the real gate defect, not merely the DraftStore helper behavior.

### SQLite implementation
- Added nullable `validation_sequence INTEGER` to new SQLite text and visual validation tables. Existing databases receive an additive `ALTER TABLE ... ADD COLUMN`; existing rows are deliberately left NULL rather than assigned a fabricated sequence from rowid.
- New text and visual validation inserts allocate a monotonically increasing per-ledger sequence in the insert statement. Partial unique indexes protect sequence uniqueness; chronology indexes cover the draft/image scope, timestamp and sequence.
- Added shared `load_latest_validation_record()`. It selects the maximum persisted timestamp; if multiple rows share that timestamp and any lacks a sequence, it raises an ambiguity error. If tied rows all have sequences, the highest sequence wins. A single legacy row with no sequence remains readable.
- `DraftStore.latest_text_validation()`, `visual_validation()`, SQLite `PublicationAuthorizationEngine`, and the final `main.py` publisher gate now use this same selector. The publisher gate also fails closed on legacy chronology ambiguity and releases the reservation before any network POST.

### PostgreSQL implementation and migration safety
- Added additive migration `layer1/migrations/publication_postgresql/0005_validation_chronology.sql`. It adds nullable BIGINT sequence columns, separate PostgreSQL sequences/defaults for future text and visual validation rows, partial unique indexes and chronology indexes.
- Migration deliberately performs **no UPDATE/backfill**. Existing PostgreSQL validation rows remain NULL because their original insertion order cannot be reconstructed reliably from the content-derived ID or tied timestamps. No `ctid`, row physical order, or guessed historical sequence is used.
- PostgreSQL `_load_latest_validation()` now uses the sequence after timestamp and rejects tied latest legacy rows if any tied row has NULL sequence. New inserts obtain sequence values from the column default. The existing per-draft / per-image advisory lock in the save path serializes same-scope validation writes around sequence allocation.
- PostgreSQL publication authorization, final durable-attempt validation/revalidation, and public latest-validation read methods all use `_load_latest_validation()`. Reconciliation of unknown external outcomes remains operator-only and does not automatically resubmit a post.
- The previous migration files were not edited. Migration 0005 is additive and has a source-level test proving it does not backfill historical rows.

### TDD and verification
- RED: both actual SQLite authorization regressions failed before the fix because the old SQL selected the older PASS.
- GREEN: PASS → REJECT and PASS → NEEDS_REVISION tied-timestamp tests now fail closed at actual SQLite authorization. Separate final publisher tests cover both text outcomes and both visual outcomes; the network opener is asserted not called. Helper tests cover text and visual latest selection, plus ambiguous legacy rows and additive upgrade behavior.
- PostgreSQL integration tests were added for actual authorization with PASS → REJECT and PASS → NEEDS_REVISION at an identical timestamp, visual latest-record ordering, and ambiguous legacy tied rows. They are DSN-gated and were **not executed** in this environment.
- Focused publisher/authorization/content-generation/PostgreSQL contract batch: **146 tests, 0 failures/errors, 28 skipped**. Additional visual-revision and migration-contract tests passed.
- Full isolated repository suite: **966 tests, 0 failures/errors, 63 skipped** using `/tmp/binance-module11-test-venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
- `compileall -q main.py image_engine.py layer1 tests` passed; `git diff --check` passed.
- `TEST_POSTGRES_DSN` is unset. No PostgreSQL server was contacted, migration was applied, or production database/Neon connection attempted.

### Disposition and residual risk
- `AUD-DRAFT-001` is **PARTIALLY REMEDIATED / OPEN**, not FIXED. SQLite helper, authorization and final publisher gates now share sequence-based ordering locally. PostgreSQL source and migration design are implemented, but real disposable PostgreSQL acceptance remains a release criterion.
- Before closure, run migration 0005 and the new integration tests against an explicitly approved disposable PostgreSQL database. Verify migration application/checksum, sequence defaults for new inserts, tied PASS → REJECT and PASS → NEEDS_REVISION authorization denial, visual revalidation, final durable-attempt denial, and legacy tied-row fail-closed behavior. Do not use production Neon.
- Legacy PostgreSQL records with tied maximum timestamps remain intentionally ambiguous and cannot be authorized until a new, independently sequenced validation record supersedes them at a later timestamp or the data is otherwise resolved through an approved audited process. No historical order is claimed.
- Module 17 remains **PARTIAL**; live DeepSeek generation and broader semantic editorial acceptance are separate gaps. Project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.
- Worktree/branch/HEAD were not reset or changed. No staging, commit, push, merge, deployment, workflow dispatch, provider call, media upload or real Binance Square publication occurred.

### Disposable PostgreSQL environment availability
- Checked the RDC host for a disposable PostgreSQL target. `TEST_POSTGRES_DSN` is unset; `postgres`, `initdb`, and `pg_ctl` are unavailable; no PostgreSQL container/image is present.
- The host's `docker` command resolves to an `udocker` wrapper, not a Docker Engine CLI; it does not support the `docker run --detach/--publish` invocation needed to create an isolated loopback-only PostgreSQL service. The attempted start was rejected before a container was created. No PostgreSQL connection or migration was attempted.
- Next required action: provide/configure an explicitly disposable database named `binance_onchain_test` with `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST=127.0.0.1` (or an explicitly approved isolated test host). Then run the DSN-gated tests; never substitute production Neon.

## 58. AUD-DRAFT-001 — SQLite sequence generator made non-reusable — 24 November 2026
- Final design review identified that `MAX(validation_sequence)+1` could reuse a previously committed number if the highest validation row were deleted. Although validation records are intended to be append-only, this was weaker than the required monotonic identity contract.
- Replaced the MAX-based allocator with a shared SQLite `validation_sequence_ledger` table whose `sequence INTEGER PRIMARY KEY AUTOINCREMENT` is the monotonic source for both text and visual validation rows. Sequence allocation and validation insertion occur in the same SQLite transaction. Gaps caused by idempotent duplicate inserts are acceptable; committed sequence values are not reused after validation-row deletion.
- Existing SQLite databases still receive additive nullable validation_sequence columns. The sequence ledger is advanced beyond any already-assigned non-NULL values during upgrade; legacy NULL rows remain NULL and tied ambiguous history still fails closed. No rowid backfill is performed.
- Added regression: delete a committed validation row, insert a later decision, and prove the new sequence is greater than the deleted record's sequence.
- Focused SQLite content-generation / authorization / publisher-safety suite after this refinement: **93 tests passed, 0 failed**.
- Final full isolated suite after this refinement: **967 tests, 0 failures/errors, 63 skipped**. `compileall` and `git diff --check` passed.
- PostgreSQL migration and integration status is unchanged: source-level migration tests pass, but `TEST_POSTGRES_DSN` remains unset and no disposable PostgreSQL environment could be provisioned on the RDC host. AUD-DRAFT-001 remains **PARTIALLY REMEDIATED / OPEN** pending actual PostgreSQL acceptance.

## 59. AUD-DRAFT-001 — disposable PostgreSQL provisioning re-check — 24 November 2026
- Corrects the environment note in section 57: PostgreSQL 16.15 client and server binaries are installed under `/usr/lib/postgresql/16/bin`; `psql` and `pg_isready` are on PATH. No existing PostgreSQL cluster was registered or listening.
- Attempted to initialize a dedicated temporary cluster at `/tmp/binance-w2e-pgdata-aud-draft-20261124`, loopback-only on port 55432, with the intended isolated database `binance_onchain_test`. Both normal initialization and an explicit mmap shared-memory configuration failed during PostgreSQL bootstrap with: `could not create shared memory segment: Function not implemented` / `shmget(...)`.
- Independently verified the container/kernel limitation with `ipcmk -M 56`, which returned `create share memory failed: Function not implemented`. Thus this is not missing PostgreSQL binaries or an application DSN issue: the execution environment does not implement System V shared memory required by this PostgreSQL build. No database cluster was completed, no server started, no database connection was made, and no migration was applied.
- The only attempted data directory was created by this task and PostgreSQL initdb removed its contents on failure. Port 55432 is closed. No production DB/Neon was contacted.
- Focused regression/contract verification rerun: `tests.test_content_generation`, `tests.test_publication_authorization`, `tests.test_publisher_safety`, and the migration additive-contract test — **94 tests passed, 0 failures/errors**. `git diff --check` passed.
- Required next dependency: run acceptance on an isolated host/container runtime that supports SysV shared memory (working Docker Engine/VM or native PostgreSQL host), or provide an explicitly disposable `binance_onchain_test` DSN that passes `tests.postgres_test_support.validate_postgres_test_target`. The DSN must not point to production Neon. Keep AUD-DRAFT-001 OPEN until the actual migration and integration acceptance pass.


## 2026-11-24 — guarded PostgreSQL environment trace (read-only; write gate remains blocked)
- Located the existing credential file at `/tmp/binance-deepseek-verify/.env` (regular file, mode `0600`, owner root). It contains only `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST`. Values were parsed in-process; no secret/DSN/host value was printed, copied into the repository, or exported to the interactive shell.
- Ran `tests.postgres_test_support.validate_postgres_test_target()` against the loaded values. Guard passed: connected database identity is `binance_onchain_test`, remote host matches the explicit allowlist, TLS mode is required, and psycopg reports client-side TLS active.
- Additional read-only session check: PostgreSQL 16.16; `pg_stat_ssl.ssl = false`; `pg_is_in_recovery() = false`; database CREATE privilege is present. Client-to-endpoint TLS being active does **not** satisfy this project's stricter acceptance prerequisite because the PostgreSQL backend session itself reports TLS false.
- Neon endpoint metadata for the known disposable branch reports endpoint `module9-disposable-test` currently active. No endpoint start/restart/suspend action was issued in this check.
- Per the existing B-PG-01 acceptance rule, stopped after read-only preflight. Did **not** run DSN-gated integration tests, apply migration 0005, or perform any database write. The local shell still has `TEST_POSTGRES_DSN` unset; the .env was not sourced into the shell.
- Required next step: obtain an owner-authorized disposable PostgreSQL endpoint whose live session returns `pg_stat_ssl.ssl = true`, then re-run the guarded preflight before migration/integration writes. Never substitute production Neon.
- AUD-DRAFT-001 remains PARTIALLY REMEDIATED / OPEN; project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 60. AUD-DRAFT-001 — disposable PostgreSQL acceptance and closure — 24 November 2026
### Guarded target and TLS interpretation
- Loaded the existing mode-0600 environment file `/tmp/binance-deepseek-verify/.env` in-process. It contains the two test variables `TEST_POSTGRES_DSN` and `TEST_POSTGRES_ALLOWED_HOST`; no secret values were emitted or copied into repository files.
- `tests.postgres_test_support.validate_postgres_test_target()` passed against the actual connection: database `binance_onchain_test`, exact host allowlist, TLS-required DSN, SCRAM channel binding required, and `conn.pgconn.ssl_in_use is True` for the client-to-Neon-proxy connection.
- The additional `pg_stat_ssl.ssl=false` value reports the PostgreSQL backend session and is not a failed client-to-proxy TLS handshake. The current repository guard explicitly verifies client-to-proxy TLS. Neon documents SCRAM-SHA-256-PLUS channel binding support in its proxy and `channel_binding=require` on top of `sslmode=require`: https://neon.com/blog/postgres-needs-better-connection-security-defaults. The earlier audit note that treated backend `pg_stat_ssl.ssl=false` as proof that client TLS was absent was over-strict and is superseded for Neon proxy targets.
### Migration and database acceptance
- Applied `0005_validation_chronology.sql` using the repository migration runner. The migration ledger checksum matches the checked-in migration SHA-256. Both `content_draft_validation_results.validation_sequence` and `visual_validation_results.validation_sequence` exist as nullable BIGINT columns with their expected `nextval(...)` defaults. Existing validation rows were not backfilled.
- Full `tests.test_publication_postgres` module against the guarded disposable database: **55 tests passed, 0 failures/errors, 0 skipped** (206.295 seconds).
- The database tests exercised tied-timestamp PASS→REJECT and PASS→NEEDS_REVISION authorization denial, visual latest ordering, ambiguous legacy NULL-sequence ties failing closed, and final durable-attempt text/visual revalidation denial after a newer same-timestamp non-PASS result.
- Final durable-attempt integration coverage was extended to verify both text and visual failure statuses after an authorization had captured PASS. The publisher integration test's transport is a deterministic mock; no live Binance request or post was made.
- Full local isolated repository suite after these changes: **967 tests, 0 failures/errors, 63 skipped**. The skipped tests are the local suite without the DB environment; PostgreSQL publication coverage was separately executed above. `git diff --check` passed.
### Residual cleanup and disposition
- One stale synthetic test fixture remains in the disposable DB: a single `FAILED_CONFIRMED` row with the test-only `test-authorized-attempt:` idempotency prefix, one related quota reservation and one related authorization, and no remote post ID. It is not a production record and does not affect the validation chronology acceptance. Direct exact-key cleanup was blocked by the execution safety layer; no deletion was performed. The current test now cleans both its fixture key and publisher-generated key. Any separate cleanup requires approval.
- **AUD-DRAFT-001: CLOSED** for the confirmed validation-chronology ordering defect. SQLite and PostgreSQL selectors, authorization, visual validation, and final durable-attempt gates now use sequence-aware ordering; ambiguous legacy ties fail closed.
- Module 17 remains **PARTIAL** for independent live DeepSeek and semantic editorial-quality gaps. B-PG-01 process-kill rollback and operational failover acceptance remains a separate NOT VERIFIED item.
- Historical sections 57–59 describe earlier checkpoints and are superseded by this acceptance record. The summary matrix below is updated accordingly.
- No production database, live Binance provider, real media upload, real Square post, commit, push, merge or deployment was used.


## 61. AUD-RESEARCH-002 — verifier-issued ClaimRegistry boundary — 24 November 2026
### Reproduction
- Added a RED test constructing a public `ClaimRegistry` with a caller-supplied `ClaimVerificationResult(state="VERIFIED")`. Before the fix, `DeepResearchEngine.build()` accepted it and produced a package; the test failed because the expected `ValueError` was not raised.
### Remediation
- `ClaimRegistry` now carries a private in-process verification proof issued only by the internal verifier factory after `EvidenceVerificationEngine.verify()` completes. The proof contains a private issuer-token identity and SHA-256 digest of canonical `ClaimRegistry.to_dict()` content.
- The proof field is not constructor-settable and is omitted from serialized snapshots. `assert_verifier_issued_and_unchanged()` rejects manual construction, subclassing, and any nested-content mutation after issuance.
- `DeepResearchEngine.build()` invokes this assertion before reading claims/results/evidence. `scope_registry_to_asset()` first validates the incoming proof and then issues a new proof for the filtered registry.
- The normal main path remains compatible: it calls `EvidenceVerificationEngine.rebuild_from_store()`, scopes the registry, verifies package-derived claims, and passes the verifier-issued result to the builder.
### Adversarial coverage and verification
- Tests cover manually constructed VERIFIED results, duplicate claim IDs, mismatched result IDs, missing evidence records, altered nested registry contents, and continued acceptance of a valid asset-scoped registry.
- Focused research/evidence/registry/adapter tests: **106 passed, 0 failures/errors, 6 skipped**.
- Full isolated repository suite: **975 tests, 0 failures/errors, 63 skipped**. `compileall` and `git diff --check` passed.
### Scope and disposition
- **AUD-RESEARCH-002: CLOSED** for the internal research-builder trust assumption.
- This is an in-process API-origin/integrity proof, not a cryptographic signature against arbitrary hostile Python code with introspection or module access. A serialized registry snapshot does not retain the in-process proof; reconstructed registries must be reverified.
- **AUD-EVID-001 remains OPEN**: the verifier can still receive caller-constructed evidence records with caller-controlled source provenance/primary flags. Do not treat this closure as source authenticity certification.
- **AUD-RESEARCH-001 remains PARTIALLY REMEDIATED / OPEN** for the legacy generic PostgreSQL package-payload path.
- Module 13 remains PARTIAL; this finding closure does not certify production source completeness or the entire module.


## 62. AUD-EVID-001 — repeated reproduction and source-authority policy gate — 24 November 2026
### Reproduction after AUD-RESEARCH-002 closure
- The new ClaimRegistry in-process proof correctly establishes that the registry object came from `EvidenceVerificationEngine`; it does not authenticate each EvidenceRecord supplied to that verifier.
- Re-ran the isolated adversarial cases against current code:
  - A manually constructed record with `source_kind=SECONDARY`, unapproved publisher, attacker-controlled HTTPS URL, `source_status=ACCEPTED`, and `is_primary=True` still yields **VERIFIED**.
  - Two records with the same publisher but different caller-selected `source_family` aliases still yield **CORROBORATED**, `independent_source_count=2`.
- `MarketObservation.validate()` validates field shapes and timestamps but does not bind provider/endpoint to an approved host registry. `evidence_from_market_observation()` explicitly documents provider identifiers as caller-controlled labels and forces non-primary. `TrendSignal.source` also selects source family. `evidence_from_onchain_observation()` accepts the receipt verification key/key ID as caller arguments. The announcement adapter validates Binance publisher/host, but its CMS source ID is a local payload fingerprint, URL is the landing page, and the CMS worker's canonical payload-hash contract is absent.
### Runtime source inventory (observed, not yet an approved authority policy)
| Runtime source | Current observed identity / endpoint | Conservative proposed authority |
|---|---|---|
| Binance announcement CMS | Binance publisher; official Binance host; imported CMS row with local payload-fingerprint ID and landing-page URL | Primary only for announcement title/body/event type after a trusted CMS ingestion receipt and payload-hash contract; otherwise attributed/unverified |
| Binance Spot exchangeInfo | `api.binance.com/api/v3/exchangeInfo?permissions=SPOT` | Primary only for `binance_spot.eligible`; require endpoint-bound fetch receipt |
| Binance 24h ticker | `data-api.binance.vision/api/v3/ticker/24hr` | MARKET, non-primary by default; only market claim keys |
| CoinGecko markets | `api.coingecko.com/api/v3/coins/markets` | MARKET, non-primary by default; only market claim keys |
| CoinGecko trending | `api.coingecko.com/api/v3/search/trending` | SOCIAL/attention only; not a factual market or listing source |
| MarketScanner gainer/volume | Derived from market observations | DERIVED; not independent from upstream market provider |
| Module9 canonical transfer summary | Derived from Module9 canonical store | DERIVED ONCHAIN, non-primary until trusted receipt provenance; not independent from raw observations |
| Alchemy / Chainstack | Alchemy for Bitcoin/Ethereum/Solana/BSC; Chainstack for XRPL | ONCHAIN only with centrally configured trusted receipt key IDs and network/provider binding |
| Local publication ledger | Internal persisted publication history | Internal primary only for `publication.last_posted`; not external market evidence |
### Required owner decision before remediation
- Approve or replace the proposed provider mapping. The policy must define canonical provider IDs and aliases, exact host/path allowlists, claim keys each provider may support, source class and primary authority, ownership/syndication groups used for independence, and the trusted Module9 receipt key IDs.
- Unknown provider aliases must fail closed. Caller-supplied `source_family`, `source_status`, `is_primary`, and arbitrary receipt keys must not establish authority. Trusted adapters should derive those values from a provider policy and endpoint-bound ingestion receipt.
- **No code change applied for AUD-EVID-001 in this pass.** Choosing source authority without owner approval would invent business trust policy. Finding remains **OPEN / POLICY APPROVAL REQUIRED**; Module 11 remains PARTIAL.


## 63. Shared ClaimRegistry consumer hardening — 24 November 2026
- Review after Section 61 found `ContentVerificationEngine.validate()` was another typed-registry consumer and still accepted a manually constructed `ClaimRegistry`.
- Added the same `registry.assert_verifier_issued_and_unchanged()` boundary check used by `DeepResearchEngine.build()`.
- Added RED/GREEN tests for manual registry reconstruction and nested-content mutation at the content-verification boundary.
- Final full local suite after this change: **977 tests, 0 failures/errors, 63 skipped**. `compileall` and `git diff --check` passed.
- This completes the typed-ClaimRegistry consumer scope for AUD-RESEARCH-002. It does not authenticate EvidenceRecord source origins; AUD-EVID-001 remains OPEN / POLICY APPROVAL REQUIRED.


### PostgreSQL compatibility follow-up after Section 63
- Re-ran `PublicationPostgresResearchPackageTests.test_research_editorial_draft_validation_image_and_opportunity_survive_fresh_process` against the guarded disposable DB after the ContentVerificationEngine proof check: **1 passed, 0 failures/errors** (12.812 seconds). No schema changes.


## 64. AUD-EVID-001 — approved source-authority policy implementation — 24 November 2026
### Implemented controls
- Added an in-process `EvidenceRecord` provenance issuer proof and canonical payload digest. A raw manually constructed record is not trusted even if it claims `is_primary=True`, `source_status=ACCEPTED`, or includes caller-supplied authority metadata. Mutating an issued record invalidates its proof.
- Added a narrow authority policy:
  - Binance Spot market data: HTTPS host `api.binance.com` or `data-api.binance.vision`, exact path `/api/v3/ticker/24hr`, MARKET/non-primary, and only price/change/volume/market-cap claim keys.
  - CoinGecko markets: HTTPS host `api.coingecko.com`, exact path `/api/v3/coins/markets`, MARKET/non-primary, same four market claim keys.
  - CoinGecko trending: HTTPS host `api.coingecko.com`, exact path `/api/v3/search/trending`, SOCIAL/non-primary, only trend-topic claims.
  - Local publication ledger: PRIMARY only for `publication.last_posted`.
- Source independence is now based on the canonical authority group in the proof, not caller-selected `source_family`. Same-provider aliases cannot manufacture independent sources; shared content/lineage also collapses duplicated sources.
- Unknown market provider/endpoint and unknown trend source produce UNVERIFIED records. MarketScanner-derived gainer/volume topics remain DERIVED and cannot be used as independent evidence. `TrendSignal.source_endpoint` is persisted for the CoinGecko trending endpoint binding.
- Binance announcement CMS records are explicitly SECONDARY/non-primary/UNVERIFIED until the trusted CMS receipt and canonical payload-hash contract exist. Binance Spot eligibility records are UNVERIFIED until endpoint-bound fetch receipt support exists. Module9 on-chain evidence requires a centrally approved receipt key ID; the configured allowlist is empty, so even a correctly signed receipt with an unapproved ID remains UNVERIFIED. Canonical Module9 summaries remain derived and UNVERIFIED.
- Opportunity evidence replay now carries authority metadata, validates it against the policy, and fails closed for legacy v1 evidence-strength snapshots lacking the metadata. The in-process proof itself is not serialized.
### Regression and integration verification
- Adversarial tests cover fabricated PRIMARY/ACCEPTED records, caller-supplied authority metadata without an issuer proof, source-family alias inflation, mutation after issuance, unknown provider endpoints, unknown trend sources, and exact approved endpoint/provider mapping.
- Focused test batch: **242 tests passed, 0 failures/errors, 2 skipped**.
- Full local suite: **984 tests passed, 0 failures/errors, 63 skipped**.
- PostgreSQL `tests.test_claim_registry_postgres` + `tests.test_publication_postgres`: **57 tests passed, 0 failures/errors, 0 skipped** against the guarded disposable database. No production database was used.
- `compileall` and `git diff --check` passed.
### Residual risks and disposition
- The proof is an in-process API-origin/integrity guard, not a cryptographic signature against arbitrary hostile Python code with module introspection.
- Persisted authority metadata is validated against the policy but is not protected by a durable MAC/signature. An endpoint string alone does not prove a specific HTTP response was fetched. A durable authenticated ingestion-receipt contract is still required for source authenticity across process/database boundaries.
- Binance announcement CMS has no trusted ingestion receipt/canonical payload contract in this repository; Binance Spot eligibility has no endpoint-bound fetch receipt; no centrally approved Module9 receipt key IDs are configured. These sources remain UNVERIFIED by design.
- **AUD-EVID-001: PARTIALLY REMEDIATED / OPEN.** Module 11 remains PARTIAL. Required next step is durable signed/verified source-ingestion receipts and approved Module9 key IDs; do not relax fail-closed status without them.
- No live provider, media upload, Binance Square post, production database, commit, push, merge or deployment was used.


## 65. AUD-EVID-001 — durable source-ingestion receipt primitive (24 November 2026; foundational slice only)
- Added `layer1/source_receipts.py`: receipt v1 uses HMAC-SHA256 with domain separation. The signed envelope binds version, canonical authority ID, key ID, and SHA-256 of a canonical finite-JSON payload. Verification requires a caller-supplied verification keyring plus explicit trusted key-ID allowlist, and compares hashes/signatures in constant time. Receipt serialization is strict and JSON-compatible.
- TDD evidence: new `tests/test_source_ingestion_receipts.py` first failed on missing module import (RED), then passed **7/7** after implementation (GREEN). Coverage includes exact payload binding, payload tampering, wrong authority, wrong key, unapproved/unknown key ID, short signing key, invalid key ID, durable dict round-trip, and malformed envelope rejection.
- Security meaning: the receipt proves that a holder of the configured shared secret attested to the exact canonical payload. It does not independently establish that the payload originated from Binance; that depends on the trusted ingestion boundary and how it constructs the payload.
- CMS integration is blocked by a missing upstream contract in this repository. The checked-in `layer1/announcement_importer.py` is a downstream read-only PostgreSQL importer. It reads `binance_announcement_events` rows; the upstream CMS ingestion worker and its canonical response/content-hash contract are not present. Generating a new HMAC receipt in this downstream importer would only authenticate the row after ingestion, not the original provider response. No such false assurance was added.
- Spot integration remains pending. `main.py::_get_binance_listed` is the response fetch/validation boundary; the next implementation must receipt the exact validated exchangeInfo response/snapshot there, carry the envelope into the evidence record and durable ClaimRegistry, and verify it on reconstruction. It must not be promoted unless centrally approved key material and key IDs are provisioned.
- Module9's separate on-chain HMAC acceptance receipt remains configured with an empty central trusted-key-ID allowlist. The generic source receipt does not bypass that control.
- No production keys, provider requests, CMS database connections, PostgreSQL migrations, publishing, or deployments were used.
- Status: **AUD-EVID-001 PARTIALLY REMEDIATED / OPEN**. This primitive is not production integration or certification. Module 11 remains PARTIAL; project remains NOT PRODUCTION-READY / NO-GO.


### Verification addendum — 24 November 2026
- Receipt primitive focused tests: **8 passed** after an additional RED/GREEN case for strict JSON payload types.
- Final full suite: **992 tests, 0 failures/errors, 63 skipped** (53.753s). compileall and git diff --check passed.
- Worktree: 54 tracked modified, 10 untracked, 0 staged; branch/HEAD unchanged. No commit, push, merge, deployment, provider call, production DB access, or publishing.


## 66. AUD-EVID-001 — Binance Spot fetch-to-evidence durable receipt integration (24 November 2026)
- Integrated HMAC receipt minting into `main.py::_get_binance_listed`, at the response boundary after successful HTTPS response/schema/time validation. One receipt is created per eligible pair and binds `binance_spot_exchange_info`, exact `https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT` endpoint, provider serverTime, local observed_at, canonical selected pair projection, and its SHA-256 digest.
- Receipt bundles are carried in the in-memory snapshot and passed into `EvidenceVerificationEngine.evidence_from_binance_spot_pairs`. Evidence becomes ACCEPTED under a non-primary, policy-bound authority only when the exact payload and HMAC verify against an explicitly allowlisted key ID. Receipt metadata and signature are serialized in ClaimRegistry evidence; replay revalidates the receipt using the same provisioned keyring. Missing, altered, malformed, unapproved, or unavailable keys fail closed to UNVERIFIED.
- `main._revalidate_binance_spot_asset` now blocks final Spot eligibility authorization unless at least one exact eligible pair has a valid approved receipt. This means no configured receipt key = no final publication eligibility. This is intentionally fail-closed.
- Rotation-safe configuration: secret JSON keyring `BINANCE_SOURCE_RECEIPT_HMAC_KEYRING_JSON` (key ID -> hex key), active `BINANCE_SPOT_INGESTION_KEY_ID`, central allowlist `BINANCE_SOURCE_RECEIPT_TRUSTED_KEY_IDS`. Previous keys must remain in keyring and allowlist while their persisted receipts remain in active registries. Legacy one-key fallback `BINANCE_SPOT_INGESTION_HMAC_KEY_HEX` supported. Never put key values in repository files.
- CMS integration remains blocked by missing upstream worker/schema contract; signing the downstream read-only CMS database rows would not establish original provider-response provenance and was deliberately not implemented. Obtain the actual upstream worker or a contract signed off by its owner. Module9's trusted on-chain key allowlist remains empty and is not bypassed.
- Tests cover fetch-boundary receipt minting, adapter validation, persisted JSON reconstruction, tamper rejection, unapproved/missing key fail-closed, and keyring rotation. Full suite pending final verification. Status remains AUD-EVID-001 PARTIALLY REMEDIATED / OPEN, Module 11 PARTIAL, overall NOT PRODUCTION-READY / NO-GO.


### Final verification — 24 November 2026
- Focused receipt/Spot/evidence/opportunity/Layer1/DeepSeek batch: **271 passed, 0 failures/errors, 2 skipped**.
- Full isolated unittest suite: **999 tests, 0 failures/errors, 63 skipped** (55.388s).
- Guarded disposable PostgreSQL acceptance (`tests.test_claim_registry_postgres` + `tests.test_publication_postgres`): **57 passed, 0 failures/errors, 0 skipped** (204.813s). Test target was validated against the explicit allowed host; no production/Neon database was accessed.
- `compileall` and `git diff --check` passed. Final Git state: `work/module9-continuation-local` / `60ec380c28e07f8498eed9a4647c345538382bf2`; 55 tracked modified, 11 untracked, 0 staged. No commit, push, merge or deploy.
- AUD-EVID-001 is still PARTIALLY REMEDIATED / OPEN: CMS upstream worker receipt contract is external and absent; production Spot keyring and approved key IDs are not provisioned; Module9 trusted key IDs remain empty. Project remains NOT PRODUCTION-READY / NO-GO.


## 67. AUD-ONCHAIN-006 — persisted Module 9 receipt replay authentication and key rotation (24 November 2026)

### Finding and reproduction
- A read of `layer1/evidence_verification.py` showed `_restore_evidence_record_proof()` could restore `onchain_receipt` authority after checking only that `source_receipt_key_id` belonged to `_TRUSTED_ONCHAIN_RECEIPT_KEY_IDS`. The persisted EvidenceRecord did not contain the original Module 9 HMAC envelope or its signed observation/validation payload.
- Conditional exploit precondition: an operator later populates the trusted Module 9 key-ID allowlist. Under that configuration, a forged serialized ONCHAIN record carrying caller-selected `ACCEPTED`, `is_primary=True`, and the allowlisted key ID could be assigned a new in-process provenance proof without proving possession of the signing key.
- TDD RED reproduced the behavior: the forged record with no receipt produced a non-null `_EvidenceProvenanceProof`, effective status ACCEPTED, and effective primary true. This was a local library/persisted-registry trust-boundary issue; the current Module 9 trusted-key environment was not configured and no production path was activated.

### Remediation implemented locally
- Added `layer1/onchain_receipt_config.py` with explicit operator-controlled keyring/allowlist parsing:
  - `ONCHAIN_RECEIPT_HMAC_KEYRING_JSON` — JSON map of key IDs to hex keys (minimum 32 bytes).
  - `ONCHAIN_RECEIPT_ACTIVE_KEY_ID` — optional active signer; if present it must exist in the keyring and trusted allowlist.
  - `ONCHAIN_RECEIPT_TRUSTED_KEY_IDS` — explicit comma-separated trusted receipt IDs.
- Empty configuration leaves signing/trust disabled. Malformed or inconsistent values fail closed. Verification-only mode may keep old trusted keys without selecting an active signer. No secret/key is generated or supplied by code.
- Added `OnChainIntelligenceEngine.from_env()` and key-ID-aware verification for persisted receipts. SQLite and PostgreSQL store read paths now select the verification key by each stored receipt's own key ID, allowing trusted historical receipts to survive active-key rotation.
- Individual Module 9 EvidenceRecords now retain a signed receipt envelope and the exact serialized observation/validation payload. Both first-time evidence issuance and ClaimRegistry restore re-verify HMAC, key ID, receipt version/signature, observation identity, exact event time, network/provider-derived independence group and corresponding evidence fields before primary provenance can be issued/restored.
- TDD also reproduced the key-rotation defect: a valid old-key receipt became UNVERIFIED after switching the active signer. The store now verifies against the old receipt key ID when that ID remains explicitly trusted and its key remains provisioned.

### Verification
- Focused Module 9/evidence/opportunity regression batch after the final change: **39 passed, 0 failures/errors**.
- Full isolated repository suite: **1008 tests, 0 failures/errors, 63 skipped**.
- `python -m compileall -q main.py image_engine.py layer1 tests`: PASS.
- `git diff --check`: PASS.
- All three Module 9 environment variables were checked for presence only and reported NOT CONFIGURED. No secret values were read or printed.

### Disposition and limits
- **AUD-ONCHAIN-006: HIGH — FIXED LOCALLY; HOSTED CI NOT VERIFIED.**
- `AUD-ONCHAIN-001` remains PARTIALLY REMEDIATED / OPEN. HMAC proves an application-key holder attested to the supplied eligibility/mapping/observation snapshot; it does not authenticate the upstream RPC/provider response or prove that the snapshot was derived from that response. The individual observation evidence path is not wired into `main.py`.
- No PostgreSQL/Neon database or migration was used. PostgreSQL store call sites now use the same key-ID-aware verifier, but no live PostgreSQL worker/store acceptance was performed after this change. The 63 skipped full-suite tests remain environment-gated.
- No live provider request, production secret provisioning, Binance Square post, publisher activation, workflow dispatch, deployment, commit, push or merge occurred. Project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.

### AUD-ONCHAIN-006 final exact-field regression addendum
- The final replay verifier also binds `event_at` to the signed observation's `block_time` and requires the exact network/provider-derived independence group (`onchain:{network_id}:{provider}`). New tests reject caller-rebound event time and source-independence group.
- Final focused Module 9/evidence/PostgreSQL-adapter run: **54 tests, 40 passed, 14 skipped, 0 failures/errors**. Final full isolated suite remains **1008 tests, 0 failures/errors, 63 skipped**. Compileall and diff-check passed after the final code change.


## 68. AUD-ONCHAIN-002 — evidence-based source-policy design and owner decision gate (24 November 2026)

- Reconnected to the existing continuation worktree and verified branch `work/module9-continuation-local`, HEAD `60ec380c28e07f8498eed9a4647c345538382bf2`; all existing dirty/untracked work was preserved and nothing was staged.
- Re-inspected `layer1/onchain.py::_validate_mapping()`, SQLite `OnChainStore.list_verified_mappings()`, PostgreSQL `PostgresOnChainStore.list_verified_mappings()`, all four worker mapping-selection paths, aggregation mapping reads, and the Module 9 tests.
- Confirmed the finding remains reproducible at the validation boundary: source labels are enum-checked but not bound to exact hosts, paths, network, or asset identity; HTTPS URL syntax alone passes; `verified_at` has a future-time guard but no maximum age/expiry. Both store read paths reuse the same validator; workers consume those returned mappings; aggregation has no independent mapping-age expiry.
- Fixture review found generic/non-authoritative URLs (for example `bitcoin.org` for BTC, `example.org/token` for a generic EVM token, and generic project URLs in other chain fixtures). These fixtures cannot establish an authoritative source policy and must not be mistaken for production allowlist evidence.
- No repository-owned mapping-source ingestion/review service was found that fetches the cited source, validates project-domain ownership, extracts the exact contract/mint/issuer/currency/decimals tuple, records a canonical payload hash, and issues a verifier-bound mapping receipt.
- Created `ONCHAIN_MAPPING_SOURCE_POLICY_PROPOSAL.md` as a design/approval gate. It defines source-class semantics, the exact mapping identity to bind, source evidence metadata, exact-host/SSRF controls, per-network/source-class expiry decisions, test acceptance, and owner decisions required before implementation. It deliberately contains no guessed domains or TTL values.
- **No source behavior or tests were changed.** This is intentional: adding arbitrary host allowlists or expiry windows would create false authority and could reject legitimate sources or accept unsafe ones. AUD-ONCHAIN-002 remains HIGH / OPEN pending owner-approved source matrix and freshness policy.
- No provider/network request, database/Neon connection, migration, key provisioning, publisher/workflow action, deployment, Git index change, commit, push, or merge occurred. Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 69. AUD-ONCHAIN-004 — bounded provider response reads (24 November 2026)

### TDD reproduction and implementation
- Confirmed both `ReadOnlyJsonRpcTransport.get_json()` and `.call()` previously invoked unbounded `response.read()` before UTF-8 decoding and JSON parsing.
- Added RED tests first. Six focused tests failed against the old implementation: missing explicit cap was accepted; the transport lacked the cap argument; default adapters and `from_env()` did not require an operator limit.
- Implemented a shared bounded incremental reader for both REST and JSON-RPC response bodies. It checks `Content-Length` before reading, rejects malformed declared lengths, reads in bounded chunks with a one-byte overflow probe, and raises stable `RESPONSE_TOO_LARGE` / `INVALID_CONTENT_LENGTH` / `INVALID_RESPONSE_BODY` errors without exposing endpoint URLs or body contents.
- The transport requires an explicit positive integer `max_response_bytes`; no arbitrary default was added. Default Alchemy and Chainstack XRPL adapter construction requires the same parameter. Their `from_env()` constructors require `ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES` as a positive base-10 integer and fail closed when absent or malformed.
- Custom injected transport factories remain an explicit dependency-injection seam used by tests; any non-test custom factory must enforce an equivalent byte ceiling itself.

### Verification
- Initial RED: 6 targeted tests failed against the old transport as expected.
- Focused provider adapter suite after implementation and additional edge cases: **53 passed, 0 failures/errors**.
- The new tests cover missing/invalid limits, Content-Length early rejection without body reads, chunked/undeclared oversized responses, exact-boundary acceptance, JSON-RPC response bounding, malformed Content-Length rejection, and explicit environment wiring for both adapters.
- Full repository suite, compileall and diff-check are pending this section's final verification and will be recorded only after execution.

### Disposition and limits
- **AUD-ONCHAIN-004: PARTIALLY REMEDIATED / OPEN.** The code path is bounded when configured and default adapter initialization refuses to proceed without a configured limit. The actual `ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES` value is not provisioned; representative maximum legitimate provider payload measurements and a justified operational safety margin are still required. No live provider request was made.
- No database/Neon, migration, key, publisher, workflow, deployment, commit, push or merge action occurred. Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


### AUD-ONCHAIN-004 final verification addendum — 24 November 2026
- Full isolated repository suite after the bounded transport implementation: **1017 tests, 0 failures/errors, 63 skipped** (52.414s test runtime).
- Focused `tests.test_onchain_providers`: **53 passed, 0 failures/errors**.
- `python -m compileall -q main.py image_engine.py layer1 tests`: PASS.
- `git diff --check`: PASS.
- Presence-only environment check: `ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES` is **NOT CONFIGURED**. No provider secret/value was read or displayed.
- Final worktree: branch `work/module9-continuation-local`, HEAD `60ec380c28e07f8498eed9a4647c345538382bf2`, 57 tracked modified, 14 untracked, 0 staged. The increase is the new policy proposal, bounded transport implementation/tests, and documentation updates; pre-existing dirty work remains intact.
- No live provider request was made; no database/Neon, migration, publisher, workflow, deployment, commit, push or merge action occurred. AUD-ONCHAIN-004 remains PARTIALLY REMEDIATED / OPEN pending a justified cap value and approved provider acceptance.


## 70. AUD-ONCHAIN-001 — provider response provenance boundary re-audit (24 November 2026)

### Finding and disposition

**AUD-ONCHAIN-001 remains HIGH / PARTIALLY REMEDIATED / OPEN.** The current HMAC acceptance receipt is materially stronger than the earlier unsigned status object: it binds a key holder's signature to the exact application-supplied eligibility, mapping, observation, and validation envelope, and persisted receipt replay is now key-ID-aware. It still does not establish that the observation was derived from an authentic upstream provider response.

### Confirmed code evidence

- `layer1/onchain.py:72-105`: `OnChainObservation` contains provider and endpoint labels, block/transaction identifiers, timestamps, and finality labels, but no raw/canonical provider response digest, request identity, or transport attestation.
- `layer1/onchain.py:218-252`: `verify_acceptance_receipt()` verifies the HMAC and observation fingerprint. It has no provider response or response-attestation input to verify.
- `layer1/onchain.py:254-283`: `_signed_acceptance_result()` fingerprints and signs the supplied `EligibilityDecision`, `OnChainAssetMapping`, and `OnChainObservation`. Signing establishes the signer attested to those objects; it cannot independently establish their origin.
- `layer1/onchain_providers.py:183-205, 223-255`: bounded raw HTTP bytes are read and parsed, but only decoded JSON/result values are returned. Raw response bytes, their digest, and a request/response identity are discarded at this boundary.
- `layer1/onchain_providers.py:270-288`: `ProviderDataPage` has provider/network/scope/records/pagination/finality fields but no response attestation or normalized projection digest.
- `layer1/onchain_evm_worker.py:195-238`, `layer1/onchain_bitcoin_worker.py:208-251`, `layer1/onchain_solana_worker.py:247-314`, and `layer1/onchain_xrpl_worker.py:225-292`: workers validate response-shaped records, normalize events, and persist pages/checkpoints without carrying a verifiable transport receipt into those records.
- `layer1/onchain_aggregation.py:146-185`: eligibility source/status/hash shape and timestamps are checked, but the aggregator does not independently verify a fetch-bound Spot receipt at this boundary before using the decision and latest observation.
- `tests/test_onchain_intelligence.py:18-29, 43-80`: fixtures directly construct eligibility, mapping, and observation objects and expect the engine to accept them. This is appropriate unit isolation, but it confirms the public acceptance API receives application objects, not provider-origin proofs.
- Runtime search: no Module 9 worker/aggregator activation or `evidence_from_onchain_observation()` call was found in `main.py`; this is a library trust-boundary defect, not evidence that the current scheduled publisher is consuming these observations.

### Important security interpretation

A SHA-256 response digest alone is integrity metadata, not authentication. A local HMAC receipt proves that a holder of the HMAC key attested to a payload. It is not a provider signature. If the upstream provider has no documented response-signing protocol, the defensible provenance claim is limited to a trusted ingestion service receiving bytes over a verified TLS connection from an explicitly approved provider endpoint, validating them, and attesting to the exact normalized projection. This still trusts the provider, TLS trust roots, local host, and ingestion signer.

### Design artifact

Created `ONCHAIN_PROVIDER_RESPONSE_ATTESTATION_DESIGN.md` (design-only). It specifies approved provider profiles, request identity, exact raw response hashing, multi-call derivation manifests, trusted ingestion-only signing, honest provenance labels, atomic persistence/replay, key rotation, and adversarial tests. It explicitly prohibits guessed host policies, provider signature algorithms, proxy policy, TLS pinning, and freshness values.

### No code implementation in this pass

Do not wire a raw response digest into `OnChainObservation` as if that alone solved authenticity. A correct implementation must link every response used to derive an event (page, transaction detail, finalized head, and canonical block/ledger header) to a normalized projection and event identity, then issue a receipt only inside the trusted ingestion boundary. Current worker event ingestion and the separate observation acceptance API are not yet joined by that contract. Implementing a partial digest field now would create a misleading assurance label.

### Required next steps

1. Obtain owner approval for exact provider IDs, hostnames, network/method profiles, proxy/TLS trust policy, signer custody, and provenance wording.
2. Implement typed request/response attestations and a derivation manifest in the transport/adapter/worker path using TDD.
3. Make production acceptance consume verified attested records, not arbitrary caller-constructed objects.
4. Add cross-store tamper, replay, restart, rotation, and worker-to-aggregator acceptance tests.
5. Run the PostgreSQL worker/aggregator acceptance only against a separately approved disposable database. Do not wire the workers into production runtime until the separate activation decision.

**Disposition:** AUD-ONCHAIN-001 remains **HIGH / PARTIALLY REMEDIATED / OPEN**. No provider request, secret provisioning, database access, migration, runtime activation, deployment, publication, commit, push, or merge occurred. Overall project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 71. AUD-GIT-001 — explicit GitHub Actions history-push ref authorization (24 November 2026)

### TDD reproduction
- Re-read `_try_git_push()` and `tests/test_git_push_security.py` in the active continuation worktree. The existing guard rejected `main`, detached HEAD, and unknown branch state, but accepted any other named local branch in GitHub Actions without checking the workflow's immutable full ref or an operator-approved target list.
- Added three RED regressions: an Actions run with an empty allowlist must not stage/commit/push; a local checkout that differs from `GITHUB_REF` must not stage/commit/push; and an exact allowlisted non-main ref matching the checkout may push only to that branch. The first two failed against the old implementation because it returned success and attempted a push.

### Remediation applied locally
- `_try_git_push()` now, when `GITHUB_ACTIONS=true`, requires all of the following before any `git add`, commit, or push: `GITHUB_REF` is a branch ref; it exactly equals `refs/heads/<current local branch>`; `GIT_HISTORY_ALLOWED_REFS` is non-empty; every configured entry is a branch ref and excludes `refs/heads/main`; and the current workflow ref is an exact member of that allowlist. No wildcard or inferred fallback is accepted.
- The target branch is now always the already-validated current branch. The legacy detached/unknown-to-main fallback expression was removed.
- `.github/workflows/run_bot.yml` passes the repository variable `vars.GIT_HISTORY_ALLOWED_REFS` into the process. An unset/empty variable intentionally disables Git history pushes. The scheduled `main` workflow remains denied by the existing non-main guard. An operator must deliberately configure exact branch refs before any non-main Actions workflow can write history.
- Non-Actions local execution retains its existing named-non-main-branch behavior; the new workflow-ref allowlist is enforced specifically inside GitHub Actions.

### Verification
- RED: 2 new negative tests failed against the previous code; the positive exact-ref test also exercises the intended authorized case.
- GREEN: `tests.test_git_push_security`: **11 passed, 0 failures/errors**.
- Full isolated suite: **1020 tests, 0 failures/errors, 63 skipped**.
- `python -m compileall -q main.py tests/test_git_push_security.py`: PASS.
- `git diff --check`: PASS.
- No GitHub Actions workflow was dispatched; `actionlint`/hosted CI verification was not performed in this step.

### Disposition and boundaries
- **AUD-GIT-001: FIXED LOCALLY / HOSTED CI PENDING.** Exact workflow ref, local checkout and operator allowlist must all agree. Until an operator sets the repository variable to an explicitly approved non-main branch ref, Actions history pushes remain disabled.
- This does not close `AUD-GIT-003` (pending committed-but-unpushed history detection) or `AUD-IMG-001` (legacy image uploader Git/REST mutation path).
- Worktree remains on `work/module9-continuation-local`, HEAD `60ec380c28e07f8498eed9a4647c345538382bf2`; no staging, commit, push, merge, workflow dispatch, deployment, database access, migration, live provider request or Binance Square publication occurred. All pre-existing dirty files were preserved.
- Overall project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 72. AUD-GIT-003 — committed-but-unpushed publication history recovery (24 November 2026)

### Reproduction and TDD
- Re-read `_try_git_push()`, `_retry_pending_push()`, and the existing Git security tests in the active continuation worktree. The startup helper only inspected scoped uncommitted status. A clean worktree with a local publication-history commit ahead of `origin/<branch>` was treated as “nothing to retry”.
- Added temporary-repository regressions using a disposable local bare remote (no GitHub network or credentials): clean local history commit ahead of origin, ahead commit containing unrelated application code, absent upstream, and upstream branch mismatch. The clean-ahead recovery regression failed against the previous implementation.
- Added a direct regression proving a “nothing to commit” result must not be reported as success or push arbitrary existing commits outside the verified recovery path.

### Remediation applied locally
- `_retry_pending_push()` now requires a named non-main branch and, in GitHub Actions, the exact checked-out `GITHUB_REF` plus explicit non-main `GIT_HISTORY_ALLOWED_REFS` authorization.
- Requires the exact upstream `origin/<current branch>` and an existing remote-tracking ref. Missing/ambiguous/mismatched upstreams fail closed. A remote-ahead branch also fails closed rather than attempting a non-fast-forward update.
- Detects both dirty publication-history paths and clean local commits ahead of the exact upstream. It enumerates every ahead commit and rejects the entire recovery if any commit changes a path other than `_POST_HISTORY_FILE` or `posts/`. This prevents unrelated committed work from being swept into a retry push.
- `_try_git_push()` no longer treats “nothing to commit” as unconditional success. Only `_retry_pending_push()` can authorize pushing an existing ahead commit, and only after the preceding upstream/tree checks.
- After the retry push reports success, the recovery helper performs an authenticated `git ls-remote --heads origin <branch>` and requires the advertised remote SHA to equal local `HEAD` before returning success. Authentication remains process-scoped through Git environment config; no token is written to `.git/config`, a remote URL, or command arguments.

### Verification
- RED: the clean-ahead recovery regression failed against the previous implementation.
- GREEN focused suite: `tests.test_git_push_security` **16 passed, 0 failures/errors**. Temporary bare-remote push behavior was simulated by updating the isolated local bare ref via local Git fetch; no real remote was contacted.
- Full isolated repository suite: **1025 tests, 0 failures/errors, 63 skipped**.
- `python -m compileall -q main.py tests/test_git_push_security.py`: PASS. `git diff --check`: PASS.
- Negative cases confirmed fail-closed: unrelated ahead commit, missing upstream, and upstream branch mismatch. Positive case confirmed clean history-only ahead commit is pushed by the recovery path and remote ref is verified at local HEAD.

### Disposition and boundaries
- **AUD-GIT-003: FIXED LOCALLY / HOSTED CI PENDING.** No GitHub workflow was dispatched; hosted Actions verification remains outstanding. The local bare-remote test simulates the ref update and is not proof of GitHub authentication/branch protection behavior.
- Together with Section 71, `AUD-GIT-001` and `AUD-GIT-003` are locally remediated but not yet hosted-CI verified. `AUD-GIT-002` remains closed only for the active `_try_git_push()` path; `AUD-IMG-001` remains a separate legacy uploader issue.
- Worktree remains on `work/module9-continuation-local`, HEAD `60ec380c28e07f8498eed9a4647c345538382bf2`. No staging, commit, push, merge, workflow dispatch, deployment, database access/migration, live provider request or Binance Square publication occurred. Existing unrelated dirty work was preserved.
- Overall project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 73. AUD-IMG-001 — disable legacy GitHub repository image upload APIs (24 November 2026)

### Call-path and risk confirmation
- Re-inspected `ImageUploader` and repository-wide Python call sites. The active `main.py` publication path uses `upload_authorized_image(..., upload_fn=ImageUploader().binance_media_upload)`. No production call site was found for `binance_square_upload()`, `upload()`, `_github_api_upload()`, or `_git_push_image()`.
- The legacy `_git_push_image()` implementation persisted a token-bearing `origin` URL, staged the image into the shared Git index, committed without a pathspec, and attempted pull/rebase/push without checking intermediate command results. The legacy REST method also wrote image files to a repository branch selected from environment/default behavior.

### TDD and remediation
- Replaced the prior test that asserted only no-redirect REST transport with a regression requiring all legacy repository-write entrypoints to fail closed without invoking Git subprocesses, HTTP transports, or copying an image into the repository.
- RED: the new regression failed before the fix: `binance_square_upload()` returned an unverified `main`-branch raw URL after mocked REST/Git failures instead of refusing the legacy path.
- Disabled `binance_square_upload()`, generic `upload()`, `_github_api_upload()`, and `_git_push_image()`. They now return `None` / `(None, False)` and emit sanitized deprecation warnings; no token is read, no HTTP request is made, no Git config/index is touched, and no repository file is copied. Updated the class documentation to state that the only supported upload path is the authorization-bound Binance native media flow.
- Active `binance_media_upload()` and `upload_authorized_image()` were not changed. Their existing authorization/hash binding, presigned-host allowlist, no-redirect upload, bounded bytes, status acknowledgement and Binance CDN validation remain the supported path.

### Verification
- New legacy-path regression: **1 passed**.
- Focused Cloudflare/media suite: **32 passed, 0 failures/errors**.
- Full isolated repository suite after both AUD-GIT-003 and AUD-IMG-001 changes: **1025 tests, 0 failures/errors, 63 skipped**.
- `python -m compileall -q image_engine.py tests/test_cloudflare_image_generation.py`: PASS; full `compileall -q main.py image_engine.py layer1 tests`: PASS; `git diff --check`: PASS.
- All tests use mocks/temporary directories; no real GitHub REST request, Git push, Binance upload, provider call, or post occurred.

### Disposition and boundaries
- **AUD-IMG-001: FIXED LOCALLY / HOSTED CI PENDING.** The legacy APIs are intentionally disabled, not replaced with another repository mutation mechanism. External consumers that directly depended on those legacy methods will now receive no upload; repository search found no active internal caller.
- This does not change or certify the active Binance native media upload against a live provider. No workflow dispatch, staging, commit, push, merge, deployment, database access/migration, live provider request or Binance Square publication occurred.
- Worktree remains on `work/module9-continuation-local`, HEAD `60ec380c28e07f8498eed9a4647c345538382bf2`; pre-existing dirty work was preserved. Overall project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 74. AUD-MAIN-002 — one-shot trend-engine wiring re-verification (24 November 2026)

- The historical Section 41 finding described a missing `hot_search_engine` argument in `main.main()`. Re-inspected the current active worktree: `main()` constructs `HotSearchEngine(config)` and passes that exact instance as `hot_search_engine=hot_search_engine` to `run_once()` (current `main.py:6505-6519`).
- `_run_once_impl()` consumes the injected engine by calling `get_trending(force_refresh=True)` and passes the returned records to `_persist_layer1_market_intelligence()` (`main.py:4841-4845`). The persistence function validates and converts those records into `TrendSignal` objects before storing and using them in candidate discovery (`main.py:5811-5832` and downstream trend clustering/candidate construction).
- Existing regression `tests.test_trend_hash_provenance.TrendHashProvenanceTests.test_one_shot_main_passes_the_constructed_hot_search_engine_to_run_once` verifies object identity at the entrypoint; focused run **1 passed**. The full isolated suite also passed **1025 tests, 0 failures/errors, 63 skipped**, including the trend provenance and Layer 1 persistence tests.
- No duplicate code patch was made: the correct wiring and regression were already present in the current uncommitted continuation worktree. This entry reconciles the stale earlier audit disposition rather than reimplementing the same fix.
- **AUD-MAIN-002: FIXED LOCALLY / HOSTED CI PENDING.** This closes the specific one-shot argument omission only. Module 5 remains PARTIAL because provider coverage, trend-source quality/provenance and production acceptance are not certified. No live trend provider call or publication was made.


### AUD-IMG-001 test artifact cleanup note
- The initial RED reproduction ran the old uploader from the repository working directory and created `images/image.png` (1,878-byte synthetic test fixture). It was identified because it was absent from the pre-test Git status, hashed, and removed as a test-created artifact before the final status check. No user image or pre-existing file was deleted. The replacement regression runs from a temporary working directory and verifies no repository copy is created.


## 75. AUD-M14-002 — block PROCEED from caller-supplied raw numeric factors (24 November 2026)

### TDD reproduction
- Re-inspected `OpportunityEvaluationEngine.evaluate()` and the existing six-factor unit tests. With a test-only policy, all six caller-supplied raw values set to 90, fresh ELIGIBLE status, READY research and CONFIRMED event, the evaluator returned `PROCEED` with score 90.0. The input was only a plain `Mapping[str, float]`; no registry verification ID or factor-level source provenance was required.
- Added a regression asserting that the same raw numeric mapping must produce `DEFER`, no score, and `REGISTRY_BOUND_FACTOR_PROVENANCE_REQUIRED`, with the snapshot explicitly labelling the input `UNVERIFIED_RAW_MAPPING`. RED reproduced the prior `PROCEED`.

### Remediation applied locally
- Removed weighted-score calculation from the raw-mapping branch of `OpportunityEvaluationEngine.evaluate()`. A complete, finite, in-range raw mapping is recorded only as unverified diagnostic input and returns `DEFER` with `REGISTRY_BOUND_FACTOR_PROVENANCE_REQUIRED`. Invalid/incomplete maps continue to defer with their existing validation reasons.
- The decision snapshot now includes `factor_input_trust` (`UNVERIFIED_RAW_MAPPING` or `MISSING`) so raw values cannot be mistaken for validated assessments during later inspection.
- Updated legacy unit expectations: high raw values no longer produce PROCEED; distinct raw inputs still bind distinct decision IDs; hard gates retain their precedence.
- No replacement registry-bound scoring engine, weights, thresholds, floors, factor values or production policy was invented. The v3/v4 exact-registry validators remain validation primitives; they are not yet a calibrated scoring contract. The active runtime already supplies `factors=None`, `policy=None`, and remains fail-closed DEFER.

### Verification
- RED: the new raw-mapping regression failed before the change (`PROCEED` observed).
- Focused `tests.test_opportunity`: **38 passed, 0 failures/errors** after updating expectations.
- Full isolated repository suite: **1026 tests, 0 failures/errors, 63 skipped**.
- `python -m compileall -q main.py image_engine.py layer1 tests`: PASS. `git diff --check`: PASS.

### Disposition and boundaries
- **AUD-M14-002: FIXED LOCALLY / HOSTED CI PENDING** for the identified raw-numeric-to-PROCEED path. No caller-supplied mapping can currently produce a PROCEED decision through this evaluator.
- **AUD-M14-001 remains HIGH / OPEN / FAIL-CLOSED DEFER.** There is still no approved, empirically calibrated factor rubric and no production registry-bound scoring/assessment API. This remediation deliberately disables raw scoring rather than pretending the policy is ready. Module 14 remains FAIL / DEFER and the project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.
- No live provider, DB/Neon, workflow, publisher, deployment, commit, push, merge or Binance Square publication occurred.


## 76. AUD-VIS-001 — deterministic pixel-grounded text overlay verification (24 November 2026)

### TDD reproduction
- Reproduced the original false PASS: a solid-color 1080x1350 PNG with no text pixels and a sidecar claiming MARKET UPDATE / $ABC returned PASS. Added a new regression that rewrites the sidecar after blanking the image, so its final_image_hash matches the blank bytes; the regression still requires rejection. RED observed PASS before the fix.
- Added a shifted-text regression where the final image contains the correct words but at different coordinates while the sidecar/hash are internally consistent. Added a solid-fill-rectangle regression to prevent a uniform colored box from being mistaken for glyphs, and a font-fingerprint mismatch regression.

### Remediation applied locally
- VisualQualityEngine now decodes the same bounded image-byte snapshot used for SHA-256 and performs pixel-level overlay validation against the exact final image.
- Added a fixed font registry entry for LIBERATION_SANS_BOLD. Each overlay item must provide font_id, the exact font_sha256, font_size_px, origin_xy, bbox, fill_rgb, and expected text. The validator loads only the allowlisted font, verifies its fingerprint, re-renders the expected glyph mask, verifies the exact text bounding box, and compares core glyph pixels to the expected fill while checking that the same fill does not occupy the surrounding non-glyph mask area.
- The image composer now records the exact font fingerprint and render origin for both MARKET UPDATE and the ticker. It no longer falls back to Pillow's unspecified default font: if the approved font is unavailable, image composition fails closed rather than emitting an unverifiable overlay.
- Bumped the visual validation contract to visual-quality-v3 across generation, validation, publication authorization, runtime, and PostgreSQL acceptance checks. Existing v2 visual attestations are not accepted as current authorization evidence; images must be regenerated and revalidated under v3 before publication.

### Verification
- tests.test_visual_quality: **20 passed, 0 failures/errors**.
- Related publication/authorization/runtime/PostgreSQL tests: **162 passed, 28 skipped** in the focused batch before the final two visual regressions; the full suite below includes all current tests.
- Full isolated repository suite: **1030 tests, 0 failures/errors, 63 skipped**.
- python -m compileall -q main.py image_engine.py layer1 tests: PASS. git diff --check: PASS.

### Disposition and boundaries
- AUD-VIS-001: FIXED LOCALLY / HOSTED CI PENDING for the specific false-PASS in which the required deterministic overlay text is absent, shifted, or replaced by a uniform fill.
- This is not OCR and does not prove arbitrary semantic content in the generative background is safe. Module 20 remains PARTIAL until background text/logo/chart inspection, live Cloudflare artifact acceptance, and full operational verification are complete.
- No live Cloudflare request, Binance media upload, publisher call, real post, DB/Neon access, migration, workflow dispatch, commit, push, merge or deployment occurred. Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 77. AUD-MKT-001 — correct CoinGecko turnover metric semantics and provenance (24 November 2026)

### TDD reproduction
- Reproduced the original calculation: CoinGecko total_volume divided by market_cap, multiplied by 100, clamped to 0.3–10, was stored as volume_ratio and consumed as an x-volume/spike signal. The Skills Hub legacy path used a different scale (ratio multiplied by 5), so the same field was not comparable across providers.
- Added a regression with a provider payload containing total_volume = 2.5 billion and market_cap = 10 billion. It requires an exact 25.0% ratio, explicit PCT_MARKET_CAP_24H unit, coingecko_markets source, and no legacy volume_ratio field. The old clamped formula would have returned 10.0 and failed.

### Remediation applied locally
- Renamed the Coin field and all internal consumer payloads from volume_ratio to turnover_ratio_pct. Coin.as_dict now carries turnover_metric_unit=PCT_MARKET_CAP_24H and the source identity (for example coingecko_markets).
- CoinGecko calculation now preserves the exact finite provider-derived percentage (24h total volume / market capitalization * 100) rather than clamping it into an artificial 0.3–10 scale. The disabled Skills Hub legacy path uses the same percentage units and is explicitly marked skills_hub_legacy.
- Renamed the MarketScanner volume_spikes API to high_turnover_assets with a validated min_turnover_pct threshold. Derived trend source is market_turnover, not market_volume, and it emits market_activity_score rather than misusing hot_search_score.
- Updated ResearchEngine, candidate filters, image-card labels, DeepSeek research text and prompts: they now describe 24h turnover relative to market cap and explicitly state that this is not a historical-volume multiple, volume spike, order-book depth or measured audience demand. Missing values default to zero context rather than a fabricated 1.0%.
- Removed turnover-derived claims of Square audience interest and volume confirmation. Order-book depth/slippage is explicitly not inferred from turnover percentage.
- Evidence verification recognizes market_turnover as a market-derived source. Tests and source-adapter fixtures were updated to the new source and metric contract.

### Verification
- New provider-normalization regression: 1 passed; it verifies 25.0% exact arithmetic, unit, source and absence of the old field.
- Focused market/trend/source/image/DeepSeek batch: **186 passed, 0 failures/errors**.
- Full isolated repository suite: **1031 tests, 0 failures/errors, 63 skipped**.
- python -m compileall -q main.py image_engine.py layer1 tests: PASS. git diff --check: PASS.

### Disposition and boundaries
- AUD-MKT-001: FIXED LOCALLY / HOSTED CI PENDING for metric semantics and provider-unit consistency.
- This does not create a historical volume-spike signal. No timestamped current-vs-baseline volume window, minimum sample count or comparison-period policy exists; AUD-MARKET-001 remains OPEN. The turnover percentage is market-activity context only, not proof of a surge, liquidity, order-book depth or audience/search demand. Module 2 remains PARTIAL.
- No live CoinGecko request, Skills Hub activation, provider call, publisher call, DB/Neon access, workflow dispatch, commit, push, merge, deployment or Binance Square publication occurred.


## 78. AUD-LLM-001 — bounded DeepSeek response-body transport (24 November 2026)

### TDD reproduction
- Added regressions proving `DeepSeekClient` must reject missing, zero, negative, boolean, fractional, and string byte limits. The new tests failed against the old constructor because it accepted no response-size budget.
- Added transport regressions for declared oversized `Content-Length` (reject before any body read), malformed `Content-Length` (reject before body read), undeclared/chunked oversized bodies (stop at the configured ceiling plus one overflow-probe byte), and an exactly-at-limit valid completion (accept).
- RED result: all four initial response-bound tests failed against the unbounded client (one assertion failure and three constructor errors).

### Remediation applied locally
- `DeepSeekClient` now requires an explicit positive integer `max_response_bytes`; no implicit default or guessed limit was introduced.
- `_read_bounded_response()` checks a declared `Content-Length` before reading, rejects malformed values, then reads incrementally with bounded `read(size)` calls and a one-byte overflow probe. Both declared and undeclared bodies are prevented from being fully buffered above the configured byte budget.
- The DeepSeek client returns no response on an over-limit or malformed body; the response-validation boundary logs only the exception type and does not log body contents or credentials. Existing retry policy is unchanged; byte-limit validation errors are not retried as transient transport failures.
- `Config` reads `DEEPSEEK_MAX_RESPONSE_BYTES` as an explicit positive base-10 integer. If a DeepSeek API key is configured, configuration validation requires this cap. The DeepSeek generator passes the configured limit to the client. Missing/invalid configuration fails closed; no arbitrary deployment value was added.

### Verification
- Focused DeepSeek client + generator suite: **44 passed, 0 failures/errors**.
- Three cross-module configuration-order regressions initially exposed validation-order changes; the cap validation was moved after the existing live-mode, persistence-backend and publisher-enable checks. All five targeted configuration regressions then passed.
- Full isolated repository suite: **1038 tests, 0 failures/errors, 63 skipped**.
- `python -m compileall -q main.py image_engine.py layer1 tests`: PASS. `git diff --check`: PASS.

### Disposition and boundaries
- **AUD-LLM-001: FIXED LOCALLY / HOSTED CI PENDING** for unbounded DeepSeek response buffering.
- The runtime/deployment value of `DEEPSEEK_MAX_RESPONSE_BYTES` has not been provisioned or live-verified in this pass. Operators must choose a ceiling based on the configured output-token limit and measured legitimate response-envelope sizes plus documented overhead; do not copy the test-only 65,536-byte fixture value into production without that assessment. If `DEEPSEEK_API_KEY` is configured while the cap is absent, `Config.validate()` now blocks startup.
- No live DeepSeek API call, secret read, database access/migration, publisher action, Binance Square post, workflow dispatch, deployment, stage, commit, push or merge occurred. Existing unrelated dirty files were preserved. Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 79. AUD-ONCHAIN-005 — complete structural protocol call-shape validation (24 November 2026)

### TDD reproduction
- Re-inspected the four worker constructors, aggregator, protocol definitions, SQLite adapters and PostgreSQL adapter methods.
- Existing `require_ingestion_store()` checked that methods existed and only required `expected_cursor` / `scope_identity` on `commit_page`; it did not verify optional keyword arguments (`allow_recanonicalized`, `canonical_blocks`, `canonical_slots`) that workers actually pass. A store missing these arguments passed constructor validation and would fail only after a worker began ingestion.
- Existing `require_mapping_store()` checked only `engine.validate`, while the aggregator later dereferences `engine.freshness_limits_seconds`. An engine without the network freshness policy passed the constructor guard and could fail during aggregation.
- Added two RED regressions: an incomplete `commit_page` signature and a validation engine without `freshness_limits_seconds`. Both tests failed before the implementation change because no `ValueError` was raised.

### Remediation
- `OnChainValidationEngineProtocol` now explicitly declares `freshness_limits_seconds: Mapping[str, int]`. `require_mapping_store()` requires a non-empty mapping with non-empty network IDs and positive, non-boolean integer limits.
- `require_ingestion_store()` now uses `inspect.signature(...).bind(...)` with the exact worker/aggregator call shapes. It validates all checkpoint, scope, recanonicalization, canonical block/slot, event lookup and event-list arguments rather than checking method names alone.
- Added a contract test against the actual `PostgresOnChainStore` and `PostgresOnChainIngestionStore` class method signatures without opening a DB connection. Test fixtures now configure the required network freshness policy explicitly.

### Verification and acceptance boundary
- Protocol suite: **14 passed, 0 failures/errors**.
- Focused Module 9 worker/aggregator/PostgreSQL-adapter batch: **87 tests, 0 failures/errors, 14 skipped**. The 14 skips are PostgreSQL DSN-gated integration cases.
- Full isolated repository suite: **1041 tests, 0 failures/errors, 63 skipped**. `compileall` and `git diff --check`: PASS.
- Attempted a dedicated disposable local PostgreSQL 16 cluster. The remote execution sandbox does not implement the required `shmget` shared-memory syscall (`Function not implemented`); PostgreSQL exited before startup. No database was created, no migration ran, and `TEST_POSTGRES_DSN` remains unset. This is an environment limitation, not a passing database acceptance result.
- `AUD-ONCHAIN-005` remains **PARTIALLY REMEDIATED / OPEN**. Actual worker + aggregator transaction, concurrency, reorg, crash/restart and fresh-process acceptance against disposable PostgreSQL is still required. No Module 9 runtime activation in `main.py`.
- No live provider call, production DB/Neon connection, secret access, migration, publisher action, Binance Square post, workflow dispatch, deployment, stage, commit, push or merge. Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 80. AUD-LIFE-001 — verifier-issued lifecycle confirmation boundary (24 November 2026)

### TDD reproduction
- Reproduced that the public SQLite and PostgreSQL `observe()` APIs accepted caller-supplied `verification_state="VERIFIED"` without any ClaimRegistry; the SQLite path could create `CONFIRMED` state and the PostgreSQL adapter proceeded to database access.
- Reproduced that `sync_announcements()` accepted a manually reconstructed `ClaimRegistry` with caller-supplied VERIFIED results and accepted a registry mutated after verification because it only read `claims` and `results` attributes.
- Added four regressions (direct SQLite confirmation, manually reconstructed registry, post-verification registry mutation, direct PostgreSQL confirmation before DB access). All four failed against the previous implementation (three false-accept failures and one DB access before rejection).

### Remediation
- Both SQLite and PostgreSQL `observe()` now reject VERIFIED/CORROBORATED states unless an exact verifier-issued ClaimRegistry is supplied and unchanged. This blocks caller-supplied status strings from creating CONFIRMED/DEVELOPING states.
- Both `sync_announcements()` paths require exact `ClaimRegistry` type and `assert_verifier_issued_and_unchanged()`. They validate claim/result pairing, unique claim/evidence identities, evidence membership, and supported verification states.
- Lifecycle material-claim states are now linked by exact generated announcement evidence ID and exact asset ID; a verified claim for another asset cannot confirm this event. The same helper is used by SQLite and PostgreSQL adapters.
- The active `main.py` path already passes the ClaimRegistry produced by `EvidenceVerificationEngine`; no runtime wiring change was required.
- Direct `resolved`/`withdrawn` flags and arbitrary resolution evidence IDs remain disabled. A positive typed verifier-issued resolution/withdrawal contract is not implemented and was not invented in this pass.

### Verification and disposition
- RED: all four new trust-boundary regressions failed before the implementation.
- Focused lifecycle tests: **39 tests, 33 passed, 6 skipped, 0 failures/errors** (PostgreSQL DSN-gated tests skipped).
- Full isolated repository suite: **1045 tests, 0 failures/errors, 63 skipped**.
- `compileall` and `git diff --check`: PASS.
- `AUD-LIFE-001` is **PARTIALLY REMEDIATED / OPEN**: caller-asserted confirmation is blocked; typed resolution/withdrawal evidence remains a separate open contract. Dedicated disposable PostgreSQL lifecycle integration was subsequently executed: 10/10 passed (see Section 82).
- No database, migration, live provider, publisher, Binance Square post, workflow dispatch, deployment, stage, commit, push or merge occurred. Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 81. AUD-RESEARCH-001 and AUD-EDITORIAL-001 — legacy generic payload hash integrity (24 November 2026)

### TDD reproduction
- The typed ResearchPackage / EditorialBrief paths already recomputed their canonical content digests, but the low-level PostgreSQL compatibility APIs accepted arbitrary generic JSON payloads after validating only hash syntax and JSON finiteness. Their read paths likewise skipped digest verification for generic payloads.
- Added RED tests for generic research save validation, generic research load tampering, generic editorial save validation, and generic editorial load tampering. All four failed before remediation because the mismatched hash/payload pairs were accepted.

### Remediation
- `research_package_payload_hash()` now has two explicit canonicalization modes: typed research packages exclude generated/storage identity fields; legacy generic JSON payloads hash the complete object, preserving the historical `json.dumps(sort_keys=True, separators=(",", ":"))` ASCII-escaped byte contract.
- SQLite `ResearchPackageStore.load_latest()` now verifies both typed and legacy generic payload hashes. This protects older generic rows rather than silently trusting them.
- PostgreSQL `validate_research_package_input()` recomputes the digest for both typed and generic payloads before write. `_load_latest_research_package()` recomputes it for both payload types on every read. Typed metadata/cutoff consistency checks remain in place.
- `editorial_brief_payload_hash()` applies the same typed-versus-generic canonicalization rule. PostgreSQL `_validate_editorial_brief_input()` verifies every generic or typed payload before write; `_load_latest_editorial_brief()` verifies every generic or typed payload on read. Typed row metadata checks remain.
- Generic hashes retain the legacy ASCII-escaped canonical JSON behavior so existing low-level API callers that hash with default `json.dumps()` remain compatible. Typed package/brief hashes retain their existing canonical typed schema rules.

### Verification
- Research package suite: **28 passed**. Editorial strategy suite: **34 passed**. Combined focused suite: **62 passed, 0 failures/errors**.
- Full isolated repository suite: **1055 tests, 0 failures/errors, 63 skipped**.
- `compileall` and `git diff --check`: PASS.
- `AUD-RESEARCH-001` and `AUD-EDITORIAL-001`: **FIXED LOCALLY / HOSTED CI PENDING** for code-level digest verification. Dedicated disposable PostgreSQL integration subsequently executed, including generic payload read-tamper rejection; 55/55 publication tests passed (see Section 82).
- No production DB/Neon connection, migration, live provider, publisher, Binance Square post, workflow dispatch, deployment, stage, commit, push or merge occurred. Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 82. Dedicated disposable PostgreSQL acceptance — all four on-chain workers and publication/lifecycle persistence (24 November 2026)

### Target safety
- Located and parsed the pre-existing mode-0600 `/tmp/binance-deepseek-verify/.env` in-process. It contains only the dedicated test DSN and exact allowed-host setting; no credential/DSN values were emitted, copied to the repository, or exported to the interactive shell.
- `validate_postgres_test_target()` passed. The target database was verified as the dedicated `binance_onchain_test` test database with exact host allowlist and TLS/channel-binding requirements. Production Neon/database was not used.
- The approved disposable test database was used for migrations and isolated test fixtures only. No production schema or data was touched.

### Real PostgreSQL integration results
- `tests.test_onchain_postgres`: **19/19 passed**. This includes real PostgreSQL-backed end-to-end Bitcoin, EVM/BNB Smart Chain, Solana and XRPL worker ingestion through the mapping and ingestion stores, followed by `OnChainTransferAggregator` acceptance; existing checkpoint, block/slot journal, rollback, reorg, concurrency and fresh-process persistence tests also passed. Worker providers were deterministic fakes; no external chain/provider endpoint was called.
- `tests.test_event_lifecycle_postgres`: **10/10 passed**, including verifier-issued ClaimRegistry enforcement, semantic paraphrase/status-change behavior, persistence and fresh-process reopen.
- `tests.test_publication_postgres`: **55/55 passed**, including generic research/editorial payload tamper-on-read rejection and existing authorization, quota, idempotency and durable-store contracts.
- Additional PostgreSQL suites (`test_postgres_adapter_atomicity`, `test_scheduled_postgres_acceptance`, `test_claim_registry_postgres`, `test_layer1_postgres`, `test_legacy_postgres`): **15/15 passed**.
- Total dedicated PostgreSQL acceptance across these suites: **99 tests, 0 failures/errors/skips**.

### Scheduled runtime acceptance finding
- The scheduled acceptance fixture initially expected `DEFER` because the scoring policy is not configured, while its actual typed research package contained only MARKET evidence and lacked the required PRIMARY source kind. The engine correctly returned `RESEARCH_MORE`; this was not weakened. The acceptance was corrected to assert `MISSING_REQUIRED_SOURCE_KINDS:PRIMARY`, `RESEARCH_PACKAGE_NOT_COMPLETE`, zero draft generation, zero authorization, zero publish call and child-process persistence/reload. The corrected scheduled test passed.
- This confirms the research gate is fail-closed when PRIMARY evidence is missing. It does not establish that live announcement/CMS/primary-source ingestion is available.

### Updated dispositions
- `AUD-ONCHAIN-005`: **FIXED LOCALLY / HOSTED CI PENDING** — actual PostgreSQL-backed worker/aggregator tests cover all four network families; hosted CI still required. Module 9 overall remains FAIL/PARTIAL because `AUD-ONCHAIN-001`, `002`, `004`, owner-approved source mapping policy and runtime activation remain open.
- `AUD-LIFE-001`: remains **PARTIALLY REMEDIATED / OPEN** because typed resolution/withdrawal proof is not implemented, although caller-asserted confirmation is blocked and PostgreSQL integration passes.
- `AUD-RESEARCH-001` and `AUD-EDITORIAL-001`: **FIXED LOCALLY / HOSTED CI PENDING** with actual disposable PostgreSQL generic payload tamper-on-read tests passing.
- M21 is now **PARTIAL**, not certified: PostgreSQL authorization/quota/storage and scheduled acceptance suites pass, but full crash/recovery/operational acceptance and hosted CI remain outstanding.

### Boundaries
- Full non-DSN local suite after code/test changes: **1059 tests, 0 failures/errors, 67 skipped** (the 67 are gated integration tests; the dedicated PostgreSQL suites above were separately executed).
- No live Binance provider call, real Binance Square post, live DeepSeek request, production Neon/database access, production migration, deployment, workflow dispatch, stage, commit, push or merge. Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 83. AUD-CONTENT-003 — caller-forgeable persisted text-validation PASS blocked at application write boundary (24 November 2026)

### TDD reproduction
- Reproduced that SQLite `DraftStore.save_text_validation()` accepted caller-supplied `status="PASS"` with only a draft hash, arbitrary reason strings and arbitrary validation version. Publication authorization later trusted the latest persisted PASS for that draft hash. The new RED regression failed because the store did not raise.
- The same public write contract existed in `PostgresPublicationStore.save_text_validation()`; the PostgreSQL regression was added to prove rejection occurs before database access.

### Remediation
- `ContentVerificationResult` now carries an in-process issuer token and payload digest over status, draft hash, asset identity, approved claim IDs, reasons, clean content and validation version. `ContentVerificationEngine.validate()` issues the proof only after the deterministic content gate completes.
- SQLite and PostgreSQL text-validation stores require an exact, unchanged verifier-issued result for every PASS write. They compare the result's PASS state, exact draft hash, validation version and reasons against the requested persisted row. Caller-created dataclass instances, raw status-only writes and modified copies fail closed.
- The active `main.py` publication pipeline passes the exact result produced by `ContentVerificationEngine.validate()` into persistence. Non-PASS audit outcomes remain persistable without a PASS proof.
- Added regression coverage for raw caller-asserted PASS, manually constructed result objects, and a verifier-issued result modified after issuance. Added a PostgreSQL adapter guard test that rejects raw PASS before any DB call.

### Verification
- RED: the raw SQLite caller-PASS regression failed before the fix (the store accepted the forged PASS).
- Focused content, authorization, publication runtime, publisher safety and PostgreSQL state-machine tests: **184 tests, 0 failures/errors, 28 skipped**.
- Dedicated disposable PostgreSQL publication suite: **56/56 passed**, including the new PostgreSQL no-database-access guard and the existing database-backed publication integration tests. The target was revalidated against the dedicated `binance_onchain_test` database using the mode-0600 test environment file; no DSN or credential was printed.
- Full isolated repository suite: **1062 tests, 0 failures/errors, 67 skipped**. `compileall` and `git diff --check`: PASS.

### Disposition and residual risk
- The public application write APIs can no longer turn caller-supplied PASS strings or fabricated/mutated result objects into an authorization-grade text-validation row. **AUD-CONTENT-003 is PARTIALLY REMEDIATED / OPEN; hosted CI pending.**
- This is an in-process capability boundary, not a durable cryptographic signature over the stored row. A principal with direct write access to the database can still forge a row and recompute its unkeyed validation digest. Closing that residual threat requires a separately approved durable verifier-receipt/key-custody design and read-time signature verification; no key, secret or policy was invented here.
- Module 18 remains PARTIAL. The overall project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.
- No live provider, production DB/Neon, production migration, Binance publication, workflow dispatch, deployment, stage, commit, push or merge occurred. Existing dirty worktree changes were preserved.


## 84. AUD-EVID-001 — source receipt keyring configuration now fails closed on inconsistent trust policy (24 November 2026)

### TDD reproduction
- Compared the source-ingestion receipt keyring loader with the stricter Module 9 receipt-key configuration contract.
- Added regressions for duplicate trusted key IDs, a configured active signer missing from the trusted allowlist, an active signer missing from the keyring, and a trusted key ID missing from the keyring.
- All four expected-rejection cases failed before the change: the source receipt loader returned the inconsistent keyring/trust configuration without raising. This created operator configuration ambiguity and made the source-receipt contract weaker than the already implemented on-chain receipt contract.

### Remediation
- load_source_receipt_config_from_env() now validates trusted key ID syntax, rejects duplicates, requires every trusted ID to resolve to a provisioned key, and requires any configured active signer to exist in the keyring and be explicitly trusted.
- Verification-only keyrings remain supported by omitting the active signer. The single-key migration variables remain supported, but the signer must still be explicitly trusted.
- Error messages describe the failed configuration property only; key material is never included.

### Verification
- Source receipt, Binance Spot receipt integration and evidence verification batch: 104 tests, 0 failures/errors.
- Full isolated repository suite: 1065 tests, 0 failures/errors, 67 skipped.
- compileall and git diff --check: PASS.
- No live Binance request was made; receipt integration uses mocked provider responses and test-only keys. No production secret was read.

### Disposition and limits
- This closes the inconsistent source receipt keyring configuration behavior, but does not close AUD-EVID-001: the CMS importer still does not issue or verify durable CMS source receipts, and durable source identity/authenticity, CMS worker contract and hosted CI remain open. Do not treat the presence of a signed Binance Spot fixture as CMS acceptance.
- Overall remains PARTIAL / NOT PRODUCTION-READY / NO-GO. No production DB, migration, publisher, live provider, Binance Square post, workflow dispatch, deployment, stage, commit, push or merge occurred.


## 2026-11-24 — AUD-EVID-001 upstream CMS producer contract trace (read-only)

**Status: OPEN / BLOCKED ON UPSTREAM WORKER CHANGE AND TRUSTED KEY PROVISIONING. No remediation was deployed.**

### Evidence inspected
- Local downstream importer: `layer1/announcement_importer.py`. It selects `source_id`, `content_hash`, event fields and timestamps from `binance_announcement_events`; it has no receipt column or receipt verification path.
- Local source contract: `ANNOUNCEMENT_PIPELINE.md` and `AnnouncementEvidence` validation in `layer1/foundation.py`.
- Read-only GitHub source inspected on branch `integration/binance-cms-worker-main`: `announcement-worker/src/normalize.js` (blob `1e6c5f482bff8cfc3c4a5540162f1ffdb816321c`), `announcement-worker/src/store.js` (blob `6631c0662fc9f6162e9d37e4f7026d7ce6b0609f`), and `announcement-worker/src/worker.js` (blob `402630ed25fae88760ed39eb15d431fd0b17706d`).

### Confirmed producer behavior and limitations
1. `normalizeAnnouncementMessage()` parses the CMS SDK message, validates the `DATA` envelope/topic and normalizes `catalogId`, `catalogName`, `publishDate`, title, body and disclaimer. `contentHash` is SHA-256 over the worker's canonical JSON serialization of that normalized projection. `sourceId` is a separate local SHA-256 fingerprint of `catalogId + publishDate + title`.
2. The normalized object retains `rawPayload`, but that field is the normalized projection, not the original raw WebSocket frame bytes. The producer does not retain an original provider response signature or a documented Binance-signed payload envelope.
3. `AnnouncementStore` persists the normalized fields and `raw_payload` into `binance_announcement_events`; the schema has no receipt/signature/key-ID columns or receipt side table. The insert is `ON CONFLICT (content_hash) DO NOTHING`.
4. `worker.js` receives messages from the Binance CMS SDK WebSocket stream, calls the normalizer, then persists the normalized event. There is no receipt creation or signature verification step in this producer path.
5. Consequently, a receipt minted by the downstream importer would only attest that the importer observed a database row. It would not authenticate the original provider message or establish that the CMS worker itself was trusted. Such a downstream signature must not be used to mark Binance announcement evidence VERIFIED or PRIMARY.

### Required producer-side integration contract (proposal; not implemented)
- The trusted CMS worker must create a versioned HMAC receipt at its ingestion boundary after receiving and validating the CMS SDK message, binding at minimum: authority ID, key ID, topic, catalog ID, source ID, normalized content hash, published timestamp, observed timestamp, and an explicit schema/normalizer version.
- The receipt must be persisted atomically with the normalized announcement row (or in a separately constrained one-to-one table with an enforceable foreign key/unique key). Duplicate-content behavior must preserve the original receipt and reject receipt/payload mismatch.
- The importer must select the receipt envelope and verify it against an operator-provisioned verification keyring and explicit trusted-key-ID allowlist before saving evidence. Missing, malformed, wrong-authority, untrusted-key, or mismatched receipts must be rejected and counted separately; no fallback signature generation in the importer.
- HMAC proves attestation by the holder of the worker key, not a Binance-origin digital signature. The trust policy must explicitly identify the worker execution boundary, key custody, rotation/revocation, replay behavior, and audit trail. If Binance-origin authenticity is required, obtain a provider-signed contract/payload rather than overstating worker HMAC semantics.
- Preserve the current unresolved identity semantics: `source_id` remains a local fingerprint, `source_url` remains the landing page, and revisions cannot be confidently correlated without a provider-stable article ID/permalink.

### Acceptance gates
- Upstream worker tests: canonical payload/hash determinism, signature creation, key rotation, duplicate idempotency, DB atomicity, tamper/mismatch rejection, queue/reconnect behavior, and no secret logging.
- Cross-component integration: producer writes row+receipt; importer reads and verifies exact receipt; tampering with any bound field rejects the row; old/untrusted key IDs fail closed; no receipt means no trusted CMS evidence.
- Only after trusted key provisioning and hosted CI/staging acceptance may CMS evidence provenance be reconsidered. No live Binance request, CMS worker deployment, DB/Neon access, migration, workflow dispatch, commit, push, or publication was performed in this trace.

### Worktree checkpoint
- Branch `work/module9-continuation-local`; HEAD `60ec380c28e07f8498eed9a4647c345538382bf2` before this documentation-only addendum. Existing modifications and untracked files preserved; no staging/commit/push.


## 2026-11-24 — AUD-EVID-001 CMS producer receipt + downstream verification implementation (local only)

**Disposition: PARTIALLY REMEDIATED / OPEN.** This is a code-level implementation slice across two isolated worktrees. It is not hosted CI, staging, live CMS, provider-authenticity or production acceptance.

### Worktree isolation and provenance
- Existing Layer 1 continuation worktree was preserved at `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `60ec380c28e07f8498eed9a4647c345538382bf2`.
- A separate CMS worker worktree was created at `/tmp/binance-cms-worker-receipts`, branch `work/cms-worker-receipts`, based on the verified PR #2 head `55ff3e6a409a6f2b7b944c43772140b788556223`. The existing `/root/Binance-bot` worktree was not edited.
- Both worktrees remain uncommitted; no stage, commit, push, merge, workflow dispatch or deployment occurred.

### Producer implementation (CMS worker worktree)
- Added `announcement-worker/src/receipts.js`: version-1 HMAC-SHA256 receipt envelope compatible with the shared Python `SourceIngestionReceipt` contract. It signs a canonical payload binding authority, schema version, topic, catalog ID, local source fingerprint, normalized content hash, catalog name, event type, title, body, disclaimer, publisher, source URL and canonical UTC publication/observation timestamps.
- CMS signing uses a dedicated keyring and authority, separate from Binance Spot: `BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON`, `BINANCE_CMS_RECEIPT_ACTIVE_KEY_ID`, `BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS`. Key material is not committed or printed. Duplicate JSON keys, malformed/short keys, duplicate trusted IDs, missing keys, and active IDs not explicitly trusted are rejected.
- `worker.js` signs immediately after the SDK message is normalized and before persistence. If no key is configured in local/offline mode, it can retain an unreceipted row but records `DEGRADED`; partial/inconsistent configuration aborts before pool creation. The scheduled workflow requires and validates all receipt signing settings and scopes credentials to the validation/runtime steps, not dependency installation.
- `store.js` writes event and receipt in one parameterized INSERT. Missing receipts are SQL NULL; the store never invents one. The worker deliberately retains no SELECT permission on the receipt column.
- Added additive migration `announcement-worker/migrations/002_ingestion_receipts.sql`, nullable `ingestion_receipt JSONB`; existing rows remain unreceipted. `001_initial_schema` SQL/checksum remains unchanged. Migrator now applies/checksums migrations 001 then 002 transactionally.
- PostgreSQL integration test now expects both migration versions, verifies importer SELECT of the receipt and worker SELECT denial. This integration test was skipped locally because no disposable PostgreSQL endpoint was available.

### Downstream importer implementation (Layer 1 continuation worktree)
- Added CMS-only verification configuration loader in `layer1/source_receipts.py`; it uses a separate CMS keyring/trusted-ID allowlist and never uses the Spot active signing key. Missing configuration returns an empty trust set; partial or malformed configuration fails closed.
- `layer1/announcement_importer.py` now selects `catalog_id`, `catalog_name`, `disclaimer`, and `ingestion_receipt`, reconstructs the same canonical timestamp/payload projection, and verifies the HMAC, authority, key ID and payload binding before saving `AnnouncementEvidence`.
- Missing, malformed, tampered or untrusted receipts increment `untrusted_rows` and are not persisted. `main.py` reports this separately and exposes `UNVERIFIED_RECEIPTS_NO_TRUSTED_CMS_EVIDENCE` when the feed contains only untrusted rows.
- `.github/workflows/run_bot.yml` passes only the CMS verification keyring and trusted IDs to the agent runtime. No CMS key has been provisioned.
- `ANNOUNCEMENT_PIPELINE.md` documents the contract and operational gates.

### Verification
- CMS worker Node suite: **62 passed, 0 failed, 1 skipped**. The skipped test is PostgreSQL role/TLS integration; no local Docker daemon or test PostgreSQL was available.
- Layer 1 full isolated Python suite: **1076 tests, 0 failures/errors, 67 skipped**.
- Focused importer/receipt tests: **32 passed** after the final loader and workflow assertions.
- Fixed Node-produced receipt vector is verified by the Python verifier. Cross-language canonicalization uses database-normalized UTC timestamps with six fractional digits.
- `compileall`, Node syntax checks and `git diff --check` passed. No real Binance CMS/Spot request, production DB/Neon, production migration, secret provisioning, live post, workflow dispatch, hosted CI or deployment was performed.

### Residual controls / blockers
- HMAC proves attestation by the configured worker key holder over a normalized message received through the authenticated SDK stream. It is **not a Binance-origin digital signature**. Do not label CMS evidence provider-signed or fully verified from this receipt alone.
- `source_id` remains a local fingerprint, and `source_url` remains the announcements landing page; stable provider article identity and revision correlation remain unresolved.
- Before this finding can close: apply migration 002 only in a verified disposable/staging CMS database; run the producer+importer against the same PostgreSQL instance with least-privilege roles; verify DB tamper/read/write boundaries; provision CMS signing and verification keys via approved secret management; pass hosted CI/staging acceptance; and verify the deployed worker and feed coverage. No production DB or deployment action is authorized by this code change.
- AUD-EVID-001 remains PARTIALLY REMEDIATED / OPEN; Module 11 remains PARTIAL. Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.


## 2026-11-24 — AUD-EVID-001 disposable PostgreSQL importer acceptance test added (not locally executed)
- Added `tests/test_module4_announcement_importer_postgres.py`, guarded by `validate_postgres_test_target()` before any schema creation/write. It creates a unique schema inside the explicitly named `binance_onchain_test` database, verifies JSONB receipt round-trip + legacy NULL rejection, then mutates a signed row and expects HMAC verification to reject it. Cleanup is registered even if setup/test fails.
- Wired the test into `.github/workflows/phase1-safety-tests.yml` isolated PostgreSQL job and expanded PR base-branch triggers to include `layer-1/**`.
- Local run: both PostgreSQL integration cases skipped because `TEST_POSTGRES_DSN` is absent; no Docker daemon was available. The test is not claimed as executed against PostgreSQL or hosted CI. Python mocked importer and fixed cross-language vector tests remain green.
- Latest full isolated Python suite: **1078 tests, 0 failures/errors, 69 skipped**. The two new importer PostgreSQL tests account for two of the skips in this local environment. CMS worker Node suite remains **62 passed, 0 failures, 1 skipped**.
- No DB connection/migration, workflow dispatch, commit, push or deployment. AUD-EVID-001 remains PARTIALLY REMEDIATED / OPEN; overall project remains NOT PRODUCTION-READY / NO-GO.


## 85. Publication safety re-audit — AUD-MAIN-001, AUD-PUB-001, AUD-PUB-002 (25 November 2026)

### Scope and method
- Re-read the active implementation in `main.py`, the existing master-audit findings, and the focused regression suites in the current Layer 1 continuation worktree.
- No production provider, database, migration, deployment, or publishing action was performed. All publisher transport tests use controlled local test fixtures/mocks.
- This addendum supersedes older OPEN dispositions for the specific code paths below; it does not certify the whole Module 21 publication lifecycle.

### AUD-MAIN-001 — publication-history integrity fail-open
- Current `_verify_persistence_integrity()` now treats Git command non-zero exits, timeouts, malformed UTF-8/JSONL, invalid records, missing committed records, and invalid repository/ref state as blocked outcomes.
- It verifies repository root and history path containment, checks command return codes, validates each JSONL object and its symbol/timestamp fields, and only initializes an empty ledger after positively verifying a valid unborn branch/no committed history.
- Empty/missing local history can be restored only from a successfully retrieved and validated committed Git baseline.
- Focused verification: `tests.test_persistence_integrity` — **11 tests, 0 failures/errors**. Covered broken branch state, corrupt JSONL, valid restoration, valid first-run initialization, Git non-zero exit, Git timeout, restore failure, missing committed records, and valid local extension of committed baseline.
- CI evidence: branch workflow run `45505900356` completed SUCCESS for code commit `054737dbf0d51c03b5289147605af58b038e3ef8`; its mocked safety job runs full Python unittest discovery. The later `7acbb8f` commit adds documentation only.
- Disposition: **FIXED IN CURRENT BRANCH / HOSTED CI PASS** for the identified fail-open defect. This does not certify correctness of every JSONL consumer or all Git synchronization/recovery paths; related Git findings remain separate.

### AUD-PUB-001 — SQLite final authorization TOCTOU
- Current SQLite submission path acquires `BEGIN IMMEDIATE` before the final persisted event-binding and duplicate-policy checks and holds the SQLite write reservation across the bounded HTTP request dispatch and response-header acquisition.
- The lock is released before response-body reading and local persistence. The socket timeout is capped at 15 seconds. This intentionally narrows the serialized interval to the check-to-submit boundary rather than holding the lock during body processing.
- Regression coverage includes concurrent quota reservation, event withdrawal, `NO_EVENT` insertion, and recent-post insertion through the transport boundary, plus lock release before response-body read and bounded timeout behavior.
- Focused verification: `tests.test_publisher_safety` — **56 tests, 0 failures/errors**. The concurrency tests use separate SQLite connections and controlled transport fixtures; no live Binance request was made.
- Disposition: **FIXED IN CURRENT BRANCH / HOSTED CI PASS** for the identified SQLite final-check-to-dispatch race under the implemented bounded transport guard. Residual operational risk remains: SQLite writers can be blocked for the bounded request-header interval, and production workload contention/lock-timeout behavior has not been measured. PostgreSQL uses its separate advisory-lock guard.

### AUD-PUB-002 — SQLite attempt/quota finalization consistency
- Current `_finish_attempt()` updates the attempt and quota reservation in one SQLite transaction. In the authorized path it requires exactly one reservation bound to the attempt, matching authorization ID, attempt ID and symbol, and validates the permitted source quota state before transition.
- Missing, released, mismatched, or illegal reservation state raises and rolls back the attempt update; it can no longer silently commit a terminal attempt without a valid quota transition.
- Regression coverage includes missing reservation rollback, released reservation rollback, authorization identity mismatch, illegal source state, successful atomic finalization, and quota-binding failure before any request dispatch.
- Focused verification: `tests.test_publisher_safety` — **56 tests, 0 failures/errors**.
- Disposition: **FIXED IN CURRENT BRANCH / HOSTED CI PASS** for the reproduced missing/released quota inconsistency. The legacy no-quota-table private ledger-only path remains isolated as documented in code; it is not the normal authorized submission path.

### Verification summary and limits
- `tests.test_persistence_integrity`: **11/11 PASS**.
- `tests.test_publisher_safety`: **56/56 PASS**.
- Both test modules ran with the isolated interpreter `/tmp/binance-module11-test-venv/bin/python`.
- Hosted Layer 1 CI run `45505900356` is SUCCESS on code commit `054737d`; latest branch tip `7acbb8f` is documentation-only after that tested code commit.
- No live publisher, live Binance provider, real Square post, production DB/Neon, production migration, secret access, deployment, workflow dispatch, stage, commit, push, or merge occurred during this re-audit.
- Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**. Module 21 remains **PARTIAL**, because end-to-end operational recovery, deployed runtime, provider acceptance, and remaining independent publication/security findings are not certified.


## 86. Git history write/recovery safety re-verification — AUD-GIT-001 and AUD-GIT-003 (25 November 2026)

### Current implementation and tests
- Re-read `_try_git_push()`, `_retry_pending_push()`, and `.github/workflows/run_bot.yml`.
- In GitHub Actions, `_try_git_push()` requires a branch-valued `GITHUB_REF`, exact equality with the checked-out local branch, a non-empty explicit `GIT_HISTORY_ALLOWED_REFS` allowlist, valid branch-ref entries, and exact allowlist membership before staging/commit/push. Main, detached HEAD, mismatched refs and absent allowlists fail closed.
- `run_bot.yml` supplies `vars.GIT_HISTORY_ALLOWED_REFS`; an unset variable disables workflow history writes. No repository variable was changed in this pass.
- `_retry_pending_push()` requires an exact non-main upstream, rejects missing/mismatched upstreams and remote-ahead state, detects clean local commits ahead of origin, permits only commits touching publication-history paths, and verifies the advertised remote SHA after push. Authentication is passed through process-scoped Git config, not persisted in the remote URL or repository config.
- Focused verification: `tests.test_git_push_security` — **16/16 PASS**. The clean-ahead recovery test uses an isolated local bare remote; negative cases cover unrelated commits, missing upstream, mismatched upstream, detached HEAD, main, missing allowlist and checkout/workflow-ref mismatch.
- Hosted Layer 1 workflow run `45505900356` completed SUCCESS for code commit `054737d`; its full Python unittest discovery includes the Git security tests. This verifies test execution in hosted CI, not an authenticated write against the live repository or branch-protection policy.

### Disposition
- `AUD-GIT-001`: **FIXED IN CURRENT BRANCH / HOSTED TEST CI PASS** for the detached/main/ambiguous workflow-ref push fallback. Actual scheduled GitHub Actions history writes remain disabled unless an operator explicitly configures exact approved refs.
- `AUD-GIT-003`: **FIXED IN CURRENT BRANCH / HOSTED TEST CI PASS** for the reproduced clean-ahead history recovery gap, with local bare-remote simulation. Live GitHub push authentication/branch protection remains unexercised.
- No workflow dispatch, repository variable change, real GitHub write, stage, commit, push, merge, deployment, DB/provider call or publication occurred during this re-audit.
- Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


## 87. Module 9 owner-policy gate and focused re-audit — 25 November 2026

### Re-audit scope
- Re-read `ONCHAIN_MAPPING_SOURCE_POLICY_PROPOSAL.md`, `ONCHAIN_PROVIDER_RESPONSE_ATTESTATION_DESIGN.md`, `layer1/onchain.py`, `layer1/onchain_providers.py`, SQLite/PostgreSQL mapping reads, and focused Module 9 tests.
- No implementation, provider request, database access, migration, secret provisioning, runtime activation, deployment, or publication was performed.

### AUD-ONCHAIN-001 — provider response provenance
- Reconfirmed the current HMAC acceptance receipt binds the supplied application eligibility/mapping/observation snapshot, but not raw provider response bytes or the multi-call derivation chain.
- Transport currently returns decoded JSON/results; `ProviderDataPage` carries no request/response attestation. Workers normalize and persist response-shaped records without a verifiable transport receipt. Aggregation does not independently verify a fetch-bound receipt.
- The provider attestation design remains design-only. It correctly distinguishes trusted ingestion-service TLS attestation from an actual provider digital signature and requires every response used in event derivation to be linked to a typed derivation manifest.
- Disposition: **HIGH / PARTIALLY REMEDIATED / OPEN**. Do not add a raw response hash alone and label it authentic; no provider host/method/TLS/proxy policy or signer custody was approved in this pass.

### AUD-ONCHAIN-002 — mapping source authority and freshness
- Reconfirmed `_validate_mapping()` checks source-type labels and HTTPS URL syntax, but does not bind source labels to exact host/path/network/asset assertions. `verified_at` is future-checked but not aged/expired. SQLite and PostgreSQL mapping list methods reuse the same validator, so neither read path applies source-specific expiry.
- The mapping policy proposal still requires owner decisions on authoritative source/host/path matrix, project-domain association, corroboration policy, source-class/network-specific expiry, verifier identity/key custody and fixture classification.
- Disposition: **HIGH / OPEN**. No arbitrary allowlist, corroborator rule, or TTL was invented. Existing mappings must not be treated as reproducible source-backed proof solely because `mapping_status=VERIFIED`.

### AUD-ONCHAIN-004 — bounded provider responses
- Reconfirmed the transport enforces an explicit positive byte cap, checks declared Content-Length before reading, streams with a one-byte overflow probe, and rejects malformed lengths/oversized bodies. Default Alchemy and Chainstack adapter construction requires an explicit cap; `from_env()` requires `ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES`.
- Presence-only runtime environment check: `ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES`, `ALCHEMY_API_KEY`, `CHAINSTACK_XRPL_ENDPOINT`, `ONCHAIN_RECEIPT_HMAC_KEYRING_JSON`, `ONCHAIN_RECEIPT_ACTIVE_KEY_ID`, and `ONCHAIN_RECEIPT_TRUSTED_KEY_IDS` are all **NOT_CONFIGURED** in the inspected RDC process environment. No values were read or printed.
- Disposition: **PARTIALLY REMEDIATED / OPEN**. Code path is bounded if configured, but no approved response-cap value or representative maximum legitimate payload measurements exist. No provider request was made.

### Focused verification
- Ran with `/tmp/binance-module11-test-venv/bin/python`:
  `python -m unittest tests.test_onchain_providers tests.test_onchain_receipt_config tests.test_onchain_acceptance_receipts tests.test_onchain_intelligence tests.test_onchain_aggregation tests.test_onchain_store_protocols -v`
- Result: **122 tests, 0 failures, 0 errors, 0 skips**.
- These are unit/adapter/aggregation/store-contract tests with controlled fixtures. They do not prove live provider response behavior, provider account entitlement, TLS/proxy operation in production, receipt key custody, or PostgreSQL worker acceptance.
- Existing design documents and test suites were not changed. No source behavior was changed.

### Activation and disposition
- Runtime activation of Module 9 workers/aggregator in `main.py` remains absent in the inspected call path. Do not wire it into scheduled production publishing until provider provenance, mapping policy, response cap, and separately approved disposable PostgreSQL acceptance are complete.
- Module 9 remains **FAIL / PARTIAL**. AUD-ONCHAIN-001 and AUD-ONCHAIN-002 remain open; AUD-ONCHAIN-004 remains partially remediated/open.
- Overall project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.
## 88. AUD-ANN-001 — CMS WebSocket reconnect does not provide a durable announcement replay checkpoint (25 November 2026)

### Scope and evidence
- Read the existing CMS worker implementation in the separate /tmp/binance-cms-worker-receipts worktree, its lifecycle tests, normalizer/store, and installed official @binance/cms package version 1.0.3 documentation and declaration surface. This was read-only; neither worktree was modified by the inspection.
- announcement-worker/src/worker.js:179-187 connects and subscribes to comAnnouncementEn() with a reconnect delay. Lines 235-245 process only messages delivered to the live stream callback and serialize accepted writes in an in-memory promise queue.
- announcement-worker/src/store.js:73-91 persists operational timestamps (last_message_at, last_persisted_at) but no provider cursor, sequence, resume token, or replay watermark. Event uniqueness by content_hash is duplicate suppression, not missing-message recovery.
- announcement-worker/src/normalize.js:109-112 derives sourceId from catalogId + publishDate + title; the code explicitly says this is an exact-payload fingerprint, not a stable article ID across edited revisions. sourceUrl is the generic announcement landing page, not an article permalink (lines 110-118).
- Installed SDK README node_modules/@binance/cms/README.md:50-73 describes the stream as real-time push notifications. Lines 85-99 document reconnect delay; lines 147-149 say active subscriptions are re-subscribed after reconnection/renewal. The inspected README and SDK declaration/API surface expose no replay cursor, historical offset, or missed-message recovery contract. This is a statement about the inspected SDK surface, not proof that no separate Binance announcements API exists.
- Worker test announcement-worker/test/worker-lifecycle.test.js:447-460 verifies transport error -> DEGRADED and subsequent open -> LISTENING. It does not simulate a disconnect with announcements published during the gap and prove that those announcements are replayed or backfilled.

### Confirmed gap and operational impact
- Automatic reconnection restores the live subscription, but does not by itself establish delivery of announcements published while disconnected. The worker has no durable provider checkpoint or reconciliation/backfill step after reconnect.
- last_message_at is an observability timestamp, not a replay cursor. content_hash deduplicates messages received more than once; it cannot discover messages never delivered to this process.
- Because the feed lacks a documented stable article ID in the inspected payload contract, current local source_id also cannot safely correlate edited revisions as one canonical article.
- Impact: a transient WebSocket/network outage or process downtime can leave an undetected hole in announcement intelligence. Downstream research may then miss listing, delisting, maintenance, security, or other announcements. A healthy LISTENING state after reconnect is not evidence that the gap was repaired.

### Disposition
- AUD-ANN-001 remains HIGH / PARTIALLY REMEDIATED / OPEN. Existing worker reconnect/heartbeat/degraded-state handling is useful transport resilience, but it is not historical replay or completeness assurance.
- Do not invent a Binance replay cursor, sequence number, or endpoint. Before implementation, verify whether a separate official announcements REST/history API is available and permitted for this account, its pagination/retention/rate-limit semantics, and how its records map to the CMS push payload. If no supported history source exists, document the irreducible completeness limitation and define an owner-approved gap-alert/manual reconciliation procedure.
- Closure requires an outage-window acceptance test: persist a known pre-outage watermark, simulate messages published during disconnection, run the approved reconciliation path, prove every missed item is ingested exactly once, and verify source identity/revision handling. Also test retention-window expiry and unrecoverable gaps fail visibly rather than returning a false completeness/healthy status.
- No code, test, schema, migration, provider request, secret, DB, deployment, workflow, publication, stage, commit or push was changed/performed during this re-audit. Overall remains PARTIAL / NOT PRODUCTION-READY / NO-GO.
## 89. AUD-ANN-001 — Official-source historical backfill feasibility check (25 November 2026)

### Official documentation findings
- Opened Binance Developer Documentation: `https://developers.binance.com/en/docs/products/announcements/announcement` (page last modified 8 August 2026). It documents one announcement topic, `com_announcement_en`, and says subscribers receive push notifications when Binance publishes English announcements. The documented response fields are catalogId, catalogName, publishDate, title, body, and disclaimer. The page does not document a REST history/list endpoint, cursor, offset, pagination, retention window, or replay/resume semantics.
- Binance Support Center has a public category/archive page at `https://www.binance.com/en/support/announcement`, with topic links and latest article links. That confirms a human-facing archive exists; the page alone does not establish a supported machine API or a stable pagination contract.
- Binance Spot API official repository README states that streams, endpoints, parameters and payloads described in its docs are official/supported, while other undocumented streams/endpoints/parameters/payloads are unsupported and used at the user's own risk. This is Spot API documentation scope, so it is a cautionary policy signal, not a direct legal ruling on the separate CMS support website.
- A community-maintained RSSHub route currently illustrates use of `https://www.binance.com/bapi/apex/v1/public/apex/cms/article/list/query` with pageNo/pageSize/catalogId, and the legacy project adapter once referenced a similar `/bapi/composite/...` path. This is third-party reverse-engineered evidence, not official endpoint documentation; it cannot be promoted into a production dependency or source-authority claim.

### Existing code disposition verified
- `main.py` class `BinanceAnnouncementEngine` still defines the legacy BAPI URL but `fetch_announcements()` deliberately logs `legacy undocumented Binance BAPI is disabled` and returns an empty list. The fail-closed behavior is correct and must not be bypassed merely to obtain backfill.
- CMS worker README already explicitly says the documented interface used by this worker is WebSocket push, scheduled invocations can have gaps, and no historical replay guarantee exists. This aligns with the official docs.

### Feasibility conclusion
- **No official, documented historical announcement API/backfill contract was found in the official CMS announcement documentation reviewed.** A public Support Center archive exists, but its programmatic access/pagination contract and permission for automated reconciliation are not documented by the sources reviewed.
- Therefore no implementation against the observed BAPI route is approved or justified by current evidence. Do not enable the legacy adapter, scrape internal endpoints, or treat RSSHub as an authoritative provider.
- Recommended safe disposition: retain the live official CMS WebSocket as a low-latency signal, keep the feed-completeness limitation explicit, and pursue one of two owner-approved paths: (1) obtain written/official confirmation and documentation for a historical API/feed including stable article identity, pagination, retention, rate limits and usage permissions; or (2) accept the absence of supported replay and implement visible coverage-gap alerting/manual reconciliation against the human-facing Support Center archive, with no claim of complete automated coverage.
- A follow-up acceptance design must test disconnect windows, missed-item detection, duplicate idempotency, revision correlation, archive unavailability, and expiry beyond the archive's available window. No production source should be implemented until its authority and usage contract are established.

### Changes and verification
- This is a research/audit addendum only. No source code, tests, schema, migrations, dependencies, environment variables, secrets, provider credentials, DB, runtime wiring, deployment, workflow, or publication was changed.
- Existing `main.py` fail-closed adapter behavior was read-only verified. CMS worker worktree remained clean at HEAD `9f91646a398d95765072b300c462987f4350fc5e`.
- Overall status remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.

## 90. AUD-GIT-007 — revalidation of default-branch scheduled publisher safety (25 November 2026)

### Current remote state inspected (read-only)
- `git ls-remote origin HEAD refs/heads/main` returned the same current default-branch SHA: `a0c34ef68c276b8ff48eb719d475ee9613f1f2bd`. The local `origin/main` tracking ref was stale (`bab7b7b6...`) and was not used as evidence.
- Read the live `main` files through the connected GitHub repository integration at that exact default branch. Workflow blob SHA: `cf5f6224b08f2248495f740602a3bb31186be4ae`; `main.py` blob SHA: `fcde74b8a42c2844435470d830d8125c674418e3`.
- Current `.github/workflows/run_bot.yml` still has `schedule: "*/5 * * * *"`, `workflow_dispatch`, and the `run-agent` job for non-PR events. However, the job explicitly sets `DRY_RUN: "1"` in the environment for the `python main.py` invocation. The same environment applies to scheduled and manually dispatched non-PR runs.
- Current `main.py` parses `DRY_RUN` with a safe default of `"1"`; `Config.from_env()` treats only `0`, `false`, or `no` as live mode. `PostPublisher.publish()` returns through the local `[DRY-RUN]` save path before `_try_square_api()` whenever `config.dry_run` is true. The normal run path calls `publisher.publish()`, so the workflow's explicit value currently fences this call from Square publication.
- Current default-branch code does **not** expose an independent `PUBLISHER_ENABLED` authorization gate. Thus the default-branch workflow is presently default-off through its explicit `DRY_RUN=1`, but a future workflow/environment change to `DRY_RUN=0` would still enable the Square API path if the key is available. The stronger PR-branch gate is not yet universal.

### Updated disposition
- The prior Section 27 / register statement that current live `main` sets `DRY_RUN=0` and had already published successfully is historical evidence from an earlier default-branch commit; it is not an accurate description of the current `a0c34ef...` tip.
- `AUD-GIT-007` is therefore **PARTIALLY REMEDIATED / OPEN (revalidation supersedes prior current-state claim)**: scheduled workflow is currently dry-run fenced, but there is no independent fail-closed publisher authorization gate in default-branch `main.py`, and the current workflow still injects `SQUARE_API_KEY` into the job environment.
- Closure requires an owner-approved activation contract and an independent publisher gate that remains false unless explicitly enabled through a separately controlled setting; tests must prove `DRY_RUN=0` alone cannot publish. Do not alter the live default branch, workflow, secrets or schedule as part of this audit.

### Boundaries
- This pass only read remote refs, the current default-branch workflow and current `main.py`, and official GitHub Actions schedule documentation. No `fetch` changed local refs; no workflow dispatch, provider request, publishing, secret access, workflow mutation, deployment, database operation, stage, commit, push or merge occurred.
- The local `origin/main` tracking ref remains stale and was not refreshed. The current remote SHA was obtained directly from `git ls-remote`.
- Overall project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.

## 91. AUD-GIT-007 — PR-branch publisher kill-switch workflow hardening (25 November 2026)

### Reconciliation against PR #14 and local continuation branch
- Re-read PR #14 metadata and full PR description through the GitHub integration. PR #14 head is `layer-1/module9-onchain-continuation` at `7acbb8f5014b52288e110dee368173ae7edd7429`; it remains OPEN / DRAFT / UNMERGED. Its declared scope explicitly includes an independent default-off `PUBLISHER_ENABLED` gate, requiring both `DRY_RUN=false` and explicit enablement for live publication.
- Inspected the current local continuation branch `main.py`: `Config.publisher_enabled` defaults to `False`; `Config.from_env()` parses `PUBLISHER_ENABLED` with default false; `Config.validate()` rejects live mode unless enabled; `PostPublisher.publish()` returns `PUBLISHER_DISABLED` before authorization/network if false; the image upload call site is also guarded by both `not dry_run` and `publisher_enabled`. Existing tests cover default-off config, live config validation and no-network publisher disablement.
- This confirms the independent code gate exists on the PR #14/local continuation branch. The earlier Section 90 statement that current default-branch `main.py` lacks it remains accurate for the separately inspected default-branch blob, but must not be generalized to PR #14.

### Workflow defense-in-depth change (local PR branch only)
- Added explicit `PUBLISHER_ENABLED: "0"` beside `DRY_RUN: "1"` in `.github/workflows/run_bot.yml` for the scheduled/manual `run-agent` process. This makes the workflow-level default-off intent explicit rather than relying only on the application's default value.
- Added a static regression assertion in `tests/test_scheduled_persistence_safety.py` requiring both `DRY_RUN: "1"` and `PUBLISHER_ENABLED: "0"` in the scheduled workflow.
- TDD: RED confirmed the new workflow assertion failed because the explicit publisher environment variable was absent. GREEN: after adding the workflow setting, the regression passed.
- Focused tests passed: scheduled workflow contract **1/1**; publisher kill-switch/config/no-network tests **3/3**. Full isolated repository suite after this workflow/test change: **1078 tests, 0 failures/errors, 69 skipped** (68.248 seconds).

### Current disposition and remaining boundary
- `AUD-GIT-007` is **REMEDIATED IN PR #14 WORKTREE / HOSTED CI PENDING / DEFAULT MAIN NOT YET ALIGNED**. This is not a production closure: default branch still has the older code without the independent publisher gate; PR #14 remains draft/unmerged; the local workflow/test changes are uncommitted and unpublished.
- The current remote `main` workflow's explicit `DRY_RUN: "1"` continues to fence the current default-branch publisher call, but it does not provide the second independent application gate. Do not change default branch or activate publishing as part of this continuation.
- No real Binance API request, media upload, publication, workflow dispatch, secret read, DB/Neon operation, migration, deployment, stage, commit, push or merge occurred. Project remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.


### Section 92 — AUD-SCORE-001 fallback ranking remediation (25 November 2026)

- Re-inspected the active candidate path and its downstream routing. `skills_used` is false for the current MarketScanner fallback; fallback candidates are marked `review`, enter the DeepSeek review path, and do not meet the `direct` candidate predicate. Module 14 remains independently fail-closed with `factors=None` and `policy=None`.
- Removed the undocumented `abs(change_24h) * 3 + turnover_ratio_pct * 10` score assignment. Added `_route_market_scanner_candidate_for_review()` to mark fallback candidates review-only and clear any stale `_skills_score` metadata. The caller now logs discovery-order routing and does not sort MarketScanner candidates by a synthetic score; Python input/discovery order is preserved. The Skills Hub scoring/sort branch remains separate and unchanged.
- Added `test_market_scanner_candidates_are_review_only_without_fabricated_scores` in `tests/test_end_to_end_pipeline.py`. TDD evidence: the new test first failed because the helper did not exist; after implementation it passed. The regression also seeds a stale score and verifies it is removed, preserves input order, and verifies all candidates remain review-only.
- Focused verification: `tests.test_end_to_end_pipeline` + `tests.test_scheduled_persistence_safety`: **23 tests, 0 failures/errors**. Full isolated suite: **1079 tests, 0 failures/errors, 69 skipped** (71.535 seconds). `compileall -q main.py image_engine.py layer1 tests`: PASS; `git diff --check`: PASS; source scan confirms the retired fallback formula is absent.
- Scope: this removes an unsupported ranking influence; it does not validate the Skills Hub score policy, candidate discovery completeness, DeepSeek review quality, Module 14 scoring/provenance, or publication authorization. No publish eligibility is granted by this change.
- Status: **AUD-SCORE-001 REMEDIATED LOCALLY / HOSTED CI PENDING**. M7 remains PARTIAL.
- No provider calls, live market requests, Binance publication, production DB/Neon, migration, deployment, workflow dispatch, secret reads, staging, commit, push or merge.


## 93. AUD-M14-001 — scoring activation gate revalidation (25 November 2026)

### Proposal and policy state
- Re-read `MODULE14_OPPORTUNITY_SCORING_POLICY_PROPOSAL.md` from the worktree. Its status is explicitly **PROPOSAL ONLY — NOT APPROVED FOR RUNTIME**; activation is prohibited until evidence instrumentation, historical calibration, owner sign-off and separate runtime acceptance are complete. It defines no numeric weights, cut-offs, per-factor floors or production factor values.
- The proposal's approval checklist remains unchecked for source-backed typed feature providers, sufficient point-in-time historical examples, independent adjudicated labels, chronological out-of-time evaluation, subgroup/sensitivity/false-PROCEED analysis, shadow-only acceptance and explicit owner/runtime activation approval. No evidence in the inspected repository establishes that these gates have since been completed.
- Module 7 `SCORING_POLICY.md` is explicitly not Module 14 policy; borrowing its weights remains prohibited. Public Binance Square policy research supports hard compliance gates and qualitative rubric boundaries, not numeric scoring coefficients.

### Runtime integration revalidation
- `main.py` current `OpportunityEvaluationEngine().evaluate()` call at approximately lines 5001–5015 passes `factors=None` and `policy=None`. This preserves the intended fail-closed `DEFER` path; it does not create a production score or `PROCEED`.
- The same call currently hard-codes `unsupported_causal_framing=False` and `materially_new=False`; `duplicate_angle` is inferred from a short publication cooldown (`posted_hours_ago < repetition_soft_hours`), not from semantic editorial-angle comparison. The proposal itself says the cooldown is not a novelty proof and notes that event-level material-change comparison is not yet wired into this Module 14 call.
- These booleans are not a present authorization bypass because policy and factor inputs remain absent and the evaluator defers. They are, however, incomplete/unsafe inputs for any future activation. Before a policy is enabled, the caller must provide verified gate assessments and novelty evidence from the exact research/event/publication lineage; unknown gate states must not be represented as `False`.
- Do not wire the existing event comparator into `materially_new` without separate tests for asset/event scope, exact event identity, lifecycle state, and editorial-angle distinction. Event-level lexical material change is not equivalent to semantic editorial novelty.

### Verification and disposition
- Re-read evaluator hard-gate ordering and the raw-factor fail-closed regression tests. Focused `tests.test_opportunity` + `tests.test_opportunity_registry_resolution`: **71 tests, 0 failures/errors, 2 skipped**. Existing regression `test_raw_numeric_factor_mapping_cannot_produce_proceed` confirms a complete all-90 raw mapping still returns `DEFER`, no score, and `REGISTRY_BOUND_FACTOR_PROVENANCE_REQUIRED`; `test_unconfigured_policy_defers_instead_of_guessing_weights` confirms `policy=None` returns `DEFER`.
- No factor provider, policy value, threshold, floor, label, calibration corpus or owner approval was invented. No scoring activation or runtime change made in this review.
- **AUD-M14-001 remains HIGH / OPEN / FAIL-CLOSED DEFER.** Additional pre-activation caller gaps are recorded above. M14 remains FAIL / DEFER; overall remains PARTIAL / NOT PRODUCTION-READY / NO-GO.
- No live provider, production DB/Neon, migration, secret read, workflow dispatch, deployment, publisher call, Binance post, staging, commit, push or merge.

## 94. AUD-M21-001 — current PostgreSQL recovery test revalidation (25 November 2026)

### Scope and preserved state
- Continued from the existing Layer 1 worktree `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `7acbb8f5014b52288e110dee368173ae7edd7429`.
- Re-read the current project context, the Module 21 audit section, the PostgreSQL publication store, `tests/test_publication_postgres.py`, `tests/test_scheduled_postgres_acceptance.py`, `tests/test_reconcile_publications.py`, and `tests/test_publication_runtime.py`.
- Existing six-file dirty worktree was preserved. No source code, migration, test, workflow, runtime configuration, credential or database was changed in this pass.

### Current local execution
- Presence-only checks found `TEST_POSTGRES_DSN`, `POSTGRES_DSN` and `ANNOUNCEMENT_DATABASE_URL` all UNSET. No DSN values were read and no database connection was attempted.
- Ran with `/tmp/binance-module11-test-venv/bin/python`:
  `python -m unittest tests.test_publication_postgres tests.test_scheduled_postgres_acceptance tests.test_reconcile_publications tests.test_publication_runtime -v`
- Result: **78 tests run; 48 passed, 0 failures/errors, 30 skipped**. All 30 skips were guarded by the missing `TEST_POSTGRES_DSN`. The passing set includes six pure PostgreSQL state-machine tests, reconciliation CLI/backend contract tests, runtime adapter/configuration tests, and deterministic input/migration contract tests.
- The two real `run_once` PostgreSQL scheduled acceptance tests were skipped. DB-backed tests for process-kill rollback, fresh-process lease recovery, explicit operator recovery, competing lease acquisition, quota concurrency, interrupted `SUBMITTING` attempt reconciliation and unknown-outcome reconciliation were also skipped.

### Revalidated implementation contract
- PostgreSQL backend selection requires an explicit DSN and does not silently fall back to SQLite.
- Runtime migration verification checks expected migration checksums without applying migrations.
- Singleton run lease acquisition is advisory-lock serialized. Recovery requires explicit process-termination confirmation, expected run ID, operator identity and evidence; it does not reclaim a lease solely because it is old.
- Lease completion updates the run and removes only the matching lease transactionally.
- PostgreSQL attempt/quota state transitions and unknown-outcome reconciliation are implemented as transactional store operations; pure state-machine tests validate allowed transitions, but not database lock behavior or crash durability.

### Disposition and exact remaining acceptance
- **AUD-M21-001 remains HIGH / PARTIAL / OPEN.** This pass found no reproducible local defect and does not upgrade Module 21 status.
- A prior DB-backed acceptance result, if referenced elsewhere in this report, must remain scoped to its exact named disposable test batch and must not be conflated with this DSN-absent local run or a production recovery drill.
- Still required: run the guarded migration and scheduled `run_once` acceptance against an explicitly approved disposable PostgreSQL target; execute fresh-process crash recovery, process-kill rollback, concurrent lease/authorization and unknown-publication-outcome reconciliation against that database; then separately approve and execute operator recovery/restore drills with recorded operator identity and evidence. Production DB/Neon remains out of scope.
- No endpoint was started, no migration applied, no provider or publisher called, no workflow dispatched, no deployment/publication performed, and no stage/commit/push/merge occurred.
- Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.

## 95. AUD-ONCHAIN-001 — acceptance-receipt trust-boundary revalidation (25 November 2026)

### Scope
- Continued in `/tmp/binance-w2e-continuation`, branch `work/module9-continuation-local`, HEAD `7acbb8f5014b52288e110dee368173ae7edd7429`.
- Re-read `layer1/onchain.py`, `layer1/onchain_providers.py`, `layer1/onchain_postgres.py`, `layer1/onchain_aggregation.py`, and the current acceptance-receipt tests. The guessed legacy test path `tests/test_onchain.py` does not exist; current focused receipt suite is `tests/test_onchain_acceptance_receipts.py`.

### Current controls confirmed
- An unsigned caller-constructed `OnChainValidationResult(status='ACCEPTED', ...)` does not pass the persisted receipt verifier; receipt signing disabled returns `UNAVAILABLE` and persistence rejects it.
- Signed receipts bind a canonical observation fingerprint, result identity/status/reason fields, key ID, and an evidence fingerprint that is included in the HMAC payload. Reads require a configured trusted key ID and verify the HMAC; tampered observation payloads are downgraded/rejected. Trusted retired keys can be retained during key rotation.
- The current receipt tests explicitly cover unapproved key IDs, missing signing configuration, SQLite observation tampering, evidence restoration/reverification, and trusted previous-key rotation.
- Focused execution: `/tmp/binance-module11-test-venv/bin/python -m unittest tests.test_onchain_acceptance_receipts -v` — **6 tests, 6 passed, 0 failures/errors**.

### Remaining trust-boundary limitation
- The receipt is an application HMAC over the observation and the engine's assertion that its supplied eligibility/mapping/observation inputs passed validation. It does not prove the observation was derived from an authentic raw provider response, does not cryptographically authenticate provider TLS/endpoint response bytes, and does not independently prove source authority/freshness for the asset mapping.
- `evidence_fingerprint` is signed but the persistence read API only receives the observation and validation result; it cannot independently recompute the original eligibility+mapping+observation envelope from the stored record. This is an integrity/attestation limitation, not evidence that the current signature check is bypassable. Do not overstate the HMAC as provider-origin authenticity.
- No new adversarial defect was reproduced in this pass. A complete fix requires an approved trust architecture: fetch-bound typed provider response attestations/derivation manifest, durable eligibility+mapping snapshot linkage, explicit source-host/TLS/proxy policy, key custody/rotation/revocation, and adversarial SQLite/PostgreSQL tamper and fresh-process acceptance. Do not invent provider authority rules or treat a raw response hash alone as authenticity.

### Disposition
- `AUD-ONCHAIN-001` remains **HIGH / PARTIALLY REMEDIATED / OPEN**. The HMAC receipt closes the earlier unsigned-status-object weakness for the tested persisted paths; it does not close upstream provider provenance.
- No provider request, DB/Neon connection, migration, secret read/provisioning, worker activation, deployment, publisher action, workflow dispatch, stage, commit, push or merge occurred. Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.

## 96. AUD-ONCHAIN-002 — source-policy proposal and current enforcement boundary (25 November 2026)

### Source review
- Re-read the complete `ONCHAIN_MAPPING_SOURCE_POLICY_PROPOSAL.md` (98 lines), `ONCHAIN_PROVIDER_RESPONSE_ATTESTATION_DESIGN.md`, `_validate_mapping()` and the Module 9 intelligence tests.
- The mapping proposal is explicitly **PROPOSAL ONLY — NOT APPROVED, NOT IMPLEMENTED**. It identifies six owner decisions: source-class semantics; exact authoritative host/path/contract evidence matrix; source-specific maximum age/revalidation cadence; independent corroboration requirements; verifier identity/key custody/revocation; and treatment of generic fixtures as synthetic-only.
- The proposal explicitly warns that `OFFICIAL_NETWORK` documentation of a standard does not prove a particular token contract; an explorer does not by itself prove issuer ownership; Binance Spot eligibility/CoinGecko identity do not alone prove on-chain mapping.
- Current `_validate_mapping()` still accepts a source-type label plus syntactically valid HTTPS URL and future-checks `verified_at`; it does not fetch or bind a source payload, enforce host/path/network/asset-class authority, or expire old mappings. SQLite and PostgreSQL mapping readers reuse that validator. Aggregation does not add mapping-attestation expiry.

### Verification
- Re-ran the Module 9 local unit/contract batch with the isolated interpreter:
  `python -m unittest tests.test_onchain_providers tests.test_onchain_receipt_config tests.test_onchain_acceptance_receipts tests.test_onchain_intelligence tests.test_onchain_aggregation tests.test_onchain_store_protocols -v`
- Result: **122 tests, 0 failures, 0 errors, 0 skips**. This is controlled fixture/unit/structural protocol evidence only; it does not prove source authenticity, source ownership, approved TTLs, provider account operation, or disposable PostgreSQL mapping-expiry acceptance.

### Decision and disposition
- No host/path allowlist, source-to-field authority matrix, corroboration policy, TTL, verifier identity, or key custody rule can be responsibly selected from the code/tests alone. Implementing a guessed value would create false source authority and could either reject legitimate mappings or admit unsafe ones.
- Therefore no behavior change was made. `AUD-ONCHAIN-002` remains **HIGH / OPEN / OWNER POLICY APPROVAL BLOCKED**. Until the owner decisions are supplied, mappings with `mapping_status=VERIFIED` must not be represented as reproducible source-backed proof, and Module 9 must remain inactive.
- No provider request, database/Neon connection, migration, secret read/provisioning, worker activation, deployment, workflow dispatch, publication, staging, commit, push or merge occurred. Overall remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.

## 97. AUD-ONCHAIN-002 — `VERIFIED` mapping fixture and caller reachability inventory (25 November 2026)

- Searched all Python source and test files for `mapping_status="VERIFIED"`, source-class labels, mapping persistence calls, `list_verified_mappings()`, and `_validate_mapping()`.
- No production `OnChainAssetMapping(... mapping_status="VERIFIED" ...)` construction or mapping-seeding/approval service was found in non-test application code. The concrete `save_verified()` writes found are exercised from tests; the store method itself validates the mapping and observation before persistence.
- Generic URLs such as `https://bitcoin.org/`, `https://solana.com`, `https://xrpl.org`, and `https://example.org/token` occur in test fixtures only. These are not evidence that those domains are approved source authorities for the corresponding asset/contract assertion.
- SQLite and PostgreSQL `list_verified_mappings()` both re-run the central `_validate_mapping()` before returning a mapping. The worker-local validators check network/representation/contract shape but do not independently implement source authority; they rely on the injected mapping-store contract. Production stores apply the central syntactic validator, which still lacks source host/path binding and expiry.
- `main.py` contains no construction/activation of the four Module 9 workers or `OnChainTransferAggregator`; the current scheduled runtime therefore does not currently consume these fixture mappings through the on-chain worker pipeline. This reachability fact reduces current runtime exposure but does not resolve the pre-activation trust blocker.
- No production mapping ingestion/review workflow exists to retrieve source documents, verify project-domain ownership, bind extracted fields to a source payload, or issue a verifier-bound mapping record. This confirms the source-policy proposal's stated implementation gap.
- Disposition unchanged: fixtures are test-only by location and usage; no evidence supports elevating their URLs to trusted sources. `AUD-ONCHAIN-002` remains HIGH / OPEN pending exact owner-approved source matrix and freshness policy plus an implemented verifier. No code behavior changed.

## 98. AUD-ONCHAIN-004 — current cap configuration and repository-wide regression verification (26 November 2026)

- Re-read the bounded transport implementation, adapter environment constructors, worker page/range bounds, and previous AUD-ONCHAIN-004 acceptance record.
- The shared reader enforces the configured positive byte ceiling for both REST and JSON-RPC, rejects oversized declared Content-Length before reading, and uses a bounded stream read/overflow probe. Both default Alchemy and Chainstack environment constructors require ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES; no implicit default is used.
- Worker record/page/range limits (including Bitcoin/XRPL page sizes, Solana page sizes, and per-run block/slot/ledger windows) constrain requested work but do not prove an upper bound on serialized JSON response size. Provider response shapes can include nested transaction/metadata structures, so record counts cannot be converted into a defensible byte ceiling without representative telemetry.
- Presence-only environment check in the inspected RDC process: ONCHAIN_MAX_PROVIDER_RESPONSE_BYTES, ALCHEMY_API_KEY, and CHAINSTACK_XRPL_ENDPOINT are all UNSET. No values were read. No provider request was made.
- Repository-wide isolated test suite after the latest audit/context updates: python -m unittest discover -s tests -p 'test_*.py' — 1,079 tests, 0 failures, 0 errors, 69 skipped (68.737s test runtime; process runtime 73.69s). The 69 skips remain environment/integration-gated and this suite does not establish live provider payload envelopes or provider account behavior.
- AUD-ONCHAIN-004 remains MEDIUM / PARTIALLY REMEDIATED / OPEN. Do not provision an arbitrary cap: collect authorized representative maximum payload telemetry per actual query shape/provider/network, define a memory budget and safety margin, then approve a cap value and perform controlled provider acceptance. No provider, database/Neon, migration, secret, runtime activation, deployment, publication, workflow dispatch, staging, commit, push or merge occurred.

## 99. AUD-GIT-006 — scheduled execution contract revalidation (26 November 2026)

- Re-read the active local continuation workflow and Python entrypoint. Workflow remains cron every five minutes, job timeout five minutes, concurrency group binance-square-bot, cancel-in-progress false, and does not set queue: max.
- The workflow explicitly sets POST_INTERVAL=0 and MAX_ITERATIONS=1. main.py entrypoint therefore selects main() single-run mode rather than main_loop(); main() invokes run_once() exactly once and closes its stores. This removes the prior ambiguity that the scheduled job itself intends a 24-iteration/two-hour loop: that loop is not selected by the current workflow environment.
- The five-minute job timeout still bounds installation plus the one-shot run. If an invocation is still running when later schedule events arrive, the concurrency group can retain only the default pending slot; a newer pending run can replace an older pending run. The local workflow does not configure a durable catch-up queue.
- Current local code/workflow proves the intended invocation shape, not GitHub actual event delivery. Historical run-gap statistics in the earlier finding were measured on 22 November and are not re-measured here; no fresh hosted Actions API/run-history query was performed in this local pass. Therefore no cause for missed scheduled events is claimed.
- Disposition: AUD-GIT-006 remains MEDIUM / OPEN. The current five-minute one-shot contract is statically coherent; remaining acceptance requires fresh hosted run-history telemetry, an owner-defined missed-tick/catch-up SLO, and alerting/idempotent bounded catch-up if missed ticks are not acceptable. Do not change concurrency queueing or trigger schedule without that contract.
- No workflow dispatch, live run, deployment, publication, DB/provider call, staging, commit, push or merge occurred.

## 100. AUD-CODE-001 and AUD-MARKET-001 — quarantined legacy provider and scheduled market-history durability (26 November 2026)

### AUD-CODE-001 — Skills Hub is explicitly quarantined
- Re-inspected the current candidate path. It contains an explicit comment that the undocumented Skills Hub BAPI remains disabled; runtime sets skills_used=false and skills_candidates=[] and obtains the candidate universe from MarketScanner.
- The SkillsHubEngine class and weighted score/parser implementation remain in main.py, but repository search found no runtime instantiation or invocation outside the class definition. The only active candidate path marks MarketScanner fallback candidates review-only and does not apply Skills Hub score thresholds.
- Disposition: treat Skills Hub as INTENTIONALLY QUARANTINED / NOT AN ACTIVE PROVIDER. Keep the disabled guard. Do not activate the undocumented endpoint. Physical deletion/archive is deferred cleanup because the old class and helper branches are interleaved with the large main.py module; removing them now would be a broad refactor without a demonstrated runtime defect. The audit status is updated from ambiguous dead-path review to documented quarantine, not to a claim that the legacy code is production-ready.

### AUD-MARKET-001 — root cause of missing 24h timestamped baseline in scheduled GitHub Actions mode
- Re-read MarketAnalysisEngine._return(): 1h/24h returns require a prior observation for the exact same canonical asset, provider and currency within the documented window tolerance. Untimestamped sparkline arrays are correctly excluded. Missing history remains PARTIAL with explicit HISTORY_BASELINE_24H_UNAVAILABLE; no zero or synthetic return is generated.
- The scheduled workflow defaults PERSISTENCE_BACKEND to sqlite unless the repository variable explicitly selects postgresql. In SQLite mode, _persist_layer1_market_intelligence() opens Layer1Store(database_path), whose market observations are stored in local agent.db. The workflow checks out the repository and uploads agent.db only as an artifact after execution; it does not restore/download the prior run's artifact, and agent.db is not tracked in Git. A GitHub-hosted job workspace is therefore not a durable cross-run market-observation store.
- When PERSISTENCE_BACKEND=postgresql is explicitly selected, the runtime passes the PostgreSQL publication-store connection into PostgresLayer1Store for Layer 1 market history. That is the durable design path, but requires an explicitly configured PostgreSQL DSN, successful migration/runtime verification and isolated acceptance. The inspected workflow comments already state PostgreSQL must be configured before scheduled live-publishing enablement; this audit does not assume the variable/secret exists.
- Consequence: the default GitHub scheduled workflow can repeatedly start with an empty local SQLite market-history database, so timestamped 1h/24h baselines cannot reliably accumulate across invocations. The partial status is honest and safe, but the default scheduled configuration does not meet a requirement for persistent historical market analysis.
- Disposition: AUD-MARKET-001 remains MEDIUM / OPEN. Closure requires an approved durable Layer 1 history backend for scheduled execution (or another authenticated, versioned durable store), verified retention/query semantics, and a multi-run acceptance proving observations from run A are available to run B and produce correctly windowed returns. Do not turn artifact upload into an assumed restore mechanism or switch the workflow to a production DSN without separate authorization.
- No provider/DB connection, migration, workflow dispatch, deploy, publication, staging, commit, push or merge occurred.

## 101. AUD-EVID-001 — CMS producer receipt implementation revalidation across isolated worktrees (26 November 2026)

### Current evidence supersedes the earlier pre-integration statements
- Re-read the Layer 1 downstream importer and shared Python receipt contract, plus the separate CMS worker worktree at /tmp/binance-cms-worker-receipts/announcement-worker. The CMS producer receipt integration described in the 24-November implementation section is present in the current isolated worktree; earlier Section 65/66 statements that the producer contract is absent are historical and superseded by that implementation record.
- CMS producer signs the normalized SDK event using the dedicated authority binance_announcement_cms and a separate keyring, then persists the receipt in the same parameterized INSERT as the normalized event. Migration 002 adds nullable ingestion_receipt JSONB; old rows remain unreceipted. The worker has insert-only access to the event/receipt payload and does not read back the receipt column.
- Layer 1 importer selects ingestion_receipt and reconstructs the exact normalized payload, including canonical UTC timestamps, catalog/source/content identity, body/title/disclaimer/publisher and source URL. It verifies HMAC, authority and trusted key ID before saving AnnouncementEvidence. Missing/tampered/untrusted receipts are counted as untrusted and not persisted.
- Both components use the same domain-separated HMAC envelope and canonical JSON contract. The Node test suite includes a deterministic cross-language vector; the Python suite independently verifies that Node-produced receipt.
- Trust semantics remain bounded: the HMAC proves that a holder of the CMS worker key attested to the normalized message received via the official SDK transport. It is not a Binance-origin digital signature and does not establish a stable Binance article ID/permalink; source_id remains a local fingerprint and source_url remains the announcement landing page.

### Verification in current isolated worktrees
- CMS worker: npm test — **63 tests total, 62 passed, 0 failed, 1 skipped**. The skipped test is PostgreSQL role/TLS integration; no database connection or migration was attempted.
- Layer 1 receipt/importer/Spot/evidence batch: **123 tests, 0 failures/errors, 0 skipped**. Includes the Node-to-Python receipt vector, importer payload tamper rejection, missing/untrusted receipt handling, separate CMS keyring, Spot fetch-bound receipt and persisted ClaimRegistry evidence tests.
- The CMS worker worktree remains branch work/cms-worker-receipts, HEAD 9f91646a398d95765072b300c462987f4350fc5e, clean. It was inspected only; no modifications made. Layer 1 remains branch work/module9-continuation-local, HEAD 7acbb8f5014b52288e110dee368173ae7edd7429.
- The Layer 1 workflow supplies only the CMS verification keyring/trusted IDs. The CMS worker's separate workflow requires the active signer/keyring/trusted IDs. Presence of those production secrets/variables was not checked in GitHub and no key values were read or provisioned.

### Remaining acceptance and disposition
- AUD-EVID-001 is **PARTIALLY REMEDIATED / OPEN**, not closed. Producer code is in an isolated unmerged CMS worktree/PR #2; Layer 1 importer code is local/uncommitted. Hosted CI, disposable PostgreSQL migration + producer/importer/least-privilege/tamper acceptance, approved production key custody/provisioning, deployed worker verification and real feed-coverage acceptance remain outstanding.
- The PostgreSQL integration test was skipped; no PostgreSQL endpoint was available in the current RDC environment. Docker CLI exists but no local PostgreSQL server/listener or usable Docker daemon was available. No fallback to production/Neon was attempted.
- No CMS provider request, database connection/migration, secret read/provisioning, worker deployment, workflow dispatch, publication, staging, commit, push or merge occurred. Module 11 remains PARTIAL; overall remains PARTIAL / NOT PRODUCTION-READY / NO-GO.

## 102. AUD-LIFE-001 — lifecycle transition trust-boundary revalidation (26 November 2026)

- Re-read the SQLite and PostgreSQL lifecycle adapters, AnnouncementEvidence model, and the publication authorization/revalidation consumers.
- Current behavior remains fail-closed: direct observe() cannot create VERIFIED/CONFIRMED state from caller-supplied status strings; caller-supplied resolved/withdrawn flags or resolution_evidence_id strings are rejected unless an exact verifier-issued proof contract exists. sync_announcements() requires an exact verifier-issued, unchanged ClaimRegistry and binds verified claim/evidence pairs to the exact asset and event evidence.
- Existing material revision handling distinguishes material status/body/title/event-time changes from cosmetic formatting and non-material revisions. Stale events are not reopened by old evidence. Publication authorization rechecks the exact persisted lifecycle event and rejects withdrawn/changed/missing event bindings.
- Focused execution: tests.test_event_lifecycle, tests.test_event_lifecycle_postgres, tests.test_module4_announcement_runtime_integration, tests.test_publication_authorization, tests.test_publication_runtime — **74 tests, 68 passed, 6 skipped, 0 failures/errors**. All six skips are TEST_POSTGRES_DSN-gated lifecycle integration tests; previously recorded dedicated disposable PostgreSQL lifecycle suite 10/10 remains historical acceptance evidence, not a fresh run in this pass.
- Disposition unchanged: AUD-LIFE-001 remains MEDIUM / PARTIALLY REMEDIATED / OPEN. A typed verifier-issued resolution/withdrawal proof still has no approved contract for authority, exact event/asset linkage, supported resolution/withdrawal claim types, evidence freshness and conflict handling. Do not re-enable terminal transitions using arbitrary strings or invent a policy.
- No code change. No DB/Neon connection, migration, provider call, publication, workflow dispatch, stage, commit, push or merge occurred.

## 103. Module 6 candidate discovery — focused implementation and runtime-integration revalidation (26 November 2026)

- Re-read CandidateDiscoveryFilteringEngine.build(), its market/event/trend freshness validation, asset-scoped matching, candidate identity fingerprint rules, and optional on-chain corroboration path.
- Confirmed discovery candidates require exact canonical asset identity, ELIGIBLE Binance Spot decision, at least one fresh source-backed market/event/trend signal; invalid, stale or missing signals are rejected with explicit reason codes. Candidate identity is asset + material event, else trend cluster, else market references. Additional sources update evidence without changing an existing material event identity.
- On-chain aggregation is optional corroboration only: cannot create a discovery candidate, bypass eligibility, or affect scoring. The integration path checks exact asset/symbol/network/mapping/representation/decimals/threshold, timestamp bounds and summary identity.
- Focused verification: tests.test_layer1_foundation + tests.test_onchain_candidate_integration — **115 tests, 0 failures/errors, 0 skips**. Coverage includes stale/future provider timestamps, canonical identity, exact Binance pair eligibility, material event grouping, trend deduplication/independence, on-chain corroboration non-authority, persistence, runtime integration and failure paths.
- Reconciliation: prior register marked M6 NOT VERIFIED. Current evidence justifies upgrading that coarse status to **PARTIAL**, not PASS: implementation and focused tests exist, but production provider coverage/availability, durable scheduled history, and cross-module hosted/runtime acceptance remain incomplete. No module-level production certification is inferred from unit tests.
- No code change. No live provider, DB/Neon, migration, publication, workflow dispatch, stage, commit, push or merge occurred.

## 104. Module 19 Cloudflare image generation and visual QA — local revalidation (26 November 2026)

- Re-read CloudflareWorkersAIImageGenerator, ImageComposer, image artifact sidecar, authorized Binance media upload path and VisualQualityEngine.
- Local controls verified in code/tests: fixed FLUX.2 klein 4B model identifier; account ID/token required before network; no redirect-following transport; request timeout and prompt/dimension bounds; hard 20 MiB response read limit; base64/JSON/image decode validation; pixel/dimension/format bounds; atomic output write; prompt/final-image hashes and sidecar metadata; exact draft/image binding; dry-run image generation disabled; legacy GitHub repository upload interfaces disabled.
- Authorized Binance media upload remains separate from image generation and requires exact publication authorization/hash, allowlisted presigned host, no redirects, bounded file bytes, HTTP 200/201 storage acknowledgement and validated final Binance CDN URL. Tests verify polling is not attempted after an unconfirmed storage PUT.
- Focused verification: tests.test_cloudflare_image_generation + tests.test_visual_quality — **52 tests, 0 failures/errors, 0 skipped**. These use mocked transport and local image fixtures; they do not establish Cloudflare account entitlement, real Workers AI inference, deployed model availability, billing/quota, or authenticated Binance media upload.
- Presence-only check: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are both UNSET in the inspected RDC process. No secret values read; no provider request made.
- Reconciliation: M19 remains PARTIAL. The earlier register's "Pillow unavailable" statement is stale for this isolated test interpreter (the focused image suite imports and uses PIL successfully), but live Cloudflare/account smoke acceptance remains absent. No live request should be made without explicit provider/account approval.
- No code change, provider, DB/Neon, migration, media upload, publication, workflow dispatch, deployment, stage, commit, push or merge occurred.

## 105. Module 15 DeepSeek client and generation gates — local revalidation (26 November 2026)

- Re-read Config validation, DeepSeekGenerator Phase 1/2 gates, and layer1.deepseek_client transport/response validation.
- Current controls: direct official HTTPS endpoint/model allowlist; bearer-secret redirect rejection; mandatory positive operator response-byte cap whenever DEEPSEEK_API_KEY is configured; Content-Length validation before body read; incremental bounded read for chunked/undeclared lengths; bounded retry/backoff; non-transient auth errors are not retried; unexpected model/tool calls/refusals/truncated generation are rejected; response identity/usage fields are validated; logs avoid secret/response-body disclosure.
- Generation is gated on resolved ClaimRegistry, research package, editorial brief and opportunity decision; failed or malformed model responses return no ranking/post and do not fall back to another AI provider. Generated numeric claims are checked against verified register values.
- Focused verification: tests.test_deepseek_client + tests.test_deepseek_generator — 44 tests, 0 failures/errors, 0 skips.
- Presence-only check: DEEPSEEK_API_KEY and DEEPSEEK_MODEL are UNSET in the inspected RDC process. No secret values read; no live inference attempted. DEEPSEEK_MAX_RESPONSE_BYTES is therefore not provisioned in this process; code requires it when the API key is configured.
- Disposition: M15 remains PARTIAL. Unit/mock acceptance does not establish current account entitlement, model availability, latency/rate-limit envelope, production response-size calibration or real generated-content quality. AUD-LLM-001 remains FIXED LOCALLY / HOSTED CI PENDING with operator cap provisioning and provider acceptance outstanding.
- No code change, provider call, DB/Neon, migration, publication, workflow dispatch, deployment, stage, commit, push or merge occurred.

## 106. Module 18 content/editorial/persisted-validation gate revalidation (26 November 2026)

- Re-read ContentVerificationEngine, EditorialBrief validation/store, DraftStore validation ledger, and SQLite/PostgreSQL publication authorization paths.
- Confirmed AUD-CONTENT-001 controls remain present: content validation requires an intact typed READY EditorialBrief; exact approved_claim_ids allowlist is enforced; prohibited-claim text is rejected; draft persistence resolves the persisted brief and exact research-package binding; publication authorization rechecks the draft's approved claim allowlist and exact persisted brief identity.
- Confirmed AUD-CONTENT-002 controls remain present: SOURCE_ASSERTION sentence must include exact supporting publisher attribution using supported sentence forms; wrong/missing publisher attribution is rejected. Upstream source authenticity remains a separate AUD-EVID-001 concern.
- Persisted text validation records reject caller-asserted PASS, fabricated/mutated results and mismatched draft hashes; visual validation is bound to exact draft/image hashes and version. The authorization tests recheck current lifecycle and editorial claim allowlist before permission.
- Focused suite: tests.test_content_verification, tests.test_content_generation, tests.test_research_package, tests.test_editorial_strategy, tests.test_publication_authorization, tests.test_publication_runtime — **108 tests, 0 failures/errors, 0 skips**.
- Disposition: AUD-CONTENT-001/002 remain PARTIALLY REMEDIATED / OPEN because PostgreSQL-backed persisted validation/authorization and hosted acceptance are not freshly verified in this pass; deterministic content/SQLite paths are present. Module 18 remains PARTIALLY REMEDIATED, not PASS. No code change.
- No DB/Neon connection, migration, provider, publication, workflow dispatch, deployment, staging, commit, push or merge occurred.

## 107. Hosted GitHub Actions and isolated PostgreSQL acceptance revalidation (26 November 2026)

### PR #14 — Layer 1 / Modules 9–21
- Read-only GitHub PR metadata: PR #14 remains OPEN / DRAFT / UNMERGED; head branch layer-1/module9-onchain-continuation; head SHA 7acbb8f5014b52288e110dee368173ae7edd7429.
- Hosted PR workflow run 45506068788, run number 369, event pull_request, head SHA exactly 7acbb8f5014b52288e110dee368173ae7edd7429, completed SUCCESS.
- Both jobs passed: mocked-safety-tests and Isolated PostgreSQL integration acceptance.
- The PostgreSQL job workflow starts a disposable PostgreSQL 16 service and sets TEST_POSTGRES_DSN/TEST_POSTGRES_ALLOWED_HOST. Its command includes test_onchain_postgres, test_layer1_postgres, test_claim_registry_postgres, test_event_lifecycle_postgres, test_legacy_postgres, test_postgres_adapter_atomicity, test_publication_postgres, test_scheduled_postgres_acceptance, and test_module4_announcement_importer_postgres. Job success establishes that the selected command exited successfully against the CI disposable PostgreSQL service; it is stronger evidence than local DSN-gated skips.
- The preceding run 45505474974 failed only its PostgreSQL integration job; the subsequent run 45506068788 on the same PR head passed both jobs. This is a corrected CI outcome, not a reason to hide the earlier failure.
- This hosted CI result covers committed PR head 7acbb8f5014b52288e110dee368173ae7edd7429 only. It does **not** cover the current local uncommitted deltas in .github/workflows/run_bot.yml, main.py, tests/test_end_to_end_pipeline.py, or tests/test_scheduled_persistence_safety.py.

### PR #2 — isolated CMS worker
- Read-only GitHub PR metadata: PR #2 remains OPEN / DRAFT / UNMERGED; head branch feature/binance-cms-announcement-worker; head SHA 9f91646a398d95765072b300c462987f4350fc5e.
- Hosted workflow run 45504868037 completed SUCCESS. All three jobs passed: mocked-announcement-tests, python-layer1-tests, and postgres-security-integration.
- The PostgreSQL job provisions a disposable PostgreSQL 16 container with generated TLS certificates, applies the versioned migrations with a dedicated migrator role, applies least-privilege grants, verifies worker/importer permissions and TLS hostname validation, and runs the worker tests including the receipt persistence/role checks. This closes the prior "CMS PostgreSQL integration skipped/no hosted evidence" gap for that exact PR head.
- This hosted CI result does not prove that production CMS secrets are provisioned, that the workflow is deployed from the default branch, that a live Binance CMS stream is received, or that source coverage/replay is complete.

### Updated acceptance interpretation
- AUD-ONCHAIN-005: disposable PostgreSQL worker/aggregator acceptance is locally and hosted-CI verified at PR #14 head; retain FIXED LOCALLY / HOSTED CI VERIFIED for that committed head. Module 9 remains FAIL/PARTIAL due to independent AUD-ONCHAIN-001/002/004 trust/policy/response-cap blockers and inactive runtime.
- AUD-M21-001: disposable PostgreSQL publication/scheduled acceptance is hosted-CI verified at PR #14 head. The separate production operational crash/recovery/restore/operator drills, live deployment/restore evidence, and local uncommitted workflow/runtime deltas remain open. Keep HIGH / PARTIAL / OPEN.
- AUD-EVID-001: CMS worker PostgreSQL receipt/role/TLS acceptance is hosted-CI verified at PR #2 head; importer PostgreSQL receipt acceptance is included in successful PR #14 PostgreSQL job. HMAC remains worker-boundary attestation, not Binance-origin signature. Both PRs remain unmerged and no production keys/workers were deployed.
- No GitHub workflow was dispatched or rerun by this audit. No repository write, merge, deployment, secret access, DB/Neon connection, provider call, publication, staging, commit or push occurred.

## 108. Current consolidated module disposition — reconciled 26 November 2026

This section supersedes the stale 22-November status table in Section 27 for the specific items revalidated in Sections 96–107. It does not certify the project or silently close unreviewed findings.

| Module | Current disposition | Verified evidence in this continuation | Remaining blocker |
|---|---|---|---|
| M1 Configuration / orchestration | PARTIAL | one-shot workflow contract; run lease and config safety tests | hosted operational telemetry, complete failure/recovery matrix |
| M2 Market data intelligence | PARTIAL | timestamp/provenance validation; 115 foundation tests | durable cross-run market history and real provider coverage |
| M3 Binance listing eligibility | PARTIAL | exact Spot pair/identity proof, final revalidation tests | approved runtime key/provider operation and deployed acceptance |
| M4 Announcement intelligence | PARTIAL | CMS receipt producer/importer code, 123 Python tests, 62/63 Node tests; PR #2 hosted PostgreSQL/TLS job success | PR merge/deployment, production key custody, replay/backfill, live feed completeness |
| M5 Trend intelligence | PARTIAL | trend source normalization/clustering and foundation suite | provider coverage and durable source history |
| M6 Candidate discovery | PARTIAL | 115 foundation + on-chain candidate integration tests | full hosted/live provider and durable scheduled acceptance |
| M7 Relevance / scoring | PARTIAL | unsupported fallback score removed locally; review-only routing | approved Skills Hub scoring policy/provider or explicit permanent retirement |
| M8 Market analysis | PARTIAL | typed metrics and missing-history fail-closed behavior | durable cross-run history; no inferred surge baseline |
| M9 On-chain intelligence | FAIL / PARTIAL | 122 local tests; PR #14 hosted PostgreSQL job passed worker/store suites | AUD-ONCHAIN-001 provider attestation; AUD-ONCHAIN-002 source authority/freshness policy; AUD-ONCHAIN-004 approved byte cap; runtime activation remains disabled |
| M10 Event graph | PARTIALLY REMEDIATED | deterministic graph status tie-break tests in prior evidence | hosted CI on latest local delta and broader graph/provider acceptance |
| M11 Evidence verification | PARTIAL | 123 receipt/importer/evidence tests; CMS producer/importer hosted PostgreSQL acceptance | HMAC is not provider-origin signature; stable CMS article ID/permalink absent; production key custody/deployment; on-chain provenance |
| M12 Event lifecycle | PARTIALLY REMEDIATED | 74 focused tests; historical disposable PostgreSQL lifecycle 10/10; PR #14 PostgreSQL job success | typed verifier-issued resolution/withdrawal proof policy |
| M13 Deep research | PARTIALLY REMEDIATED | research package tests and generic hash/tamper checks; PR #14 PostgreSQL job success | PRIMARY evidence completeness remains RESEARCH_MORE when absent; source authenticity |
| M14 Opportunity evaluation | FAIL / DEFER | 71 opportunity/registry tests; raw numeric mappings DEFER | approved policy, source-backed typed factors, historical labels/out-of-time validation, shadow acceptance and owner activation |
| M15 DeepSeek integration | PARTIAL | 44 client/generator tests | no live inference/model entitlement/quality acceptance; API key and response cap not provisioned in inspected process |
| M16 Editorial strategy | PARTIALLY REMEDIATED | editorial tests and hash/tamper checks; PR #14 PostgreSQL job success | full production/provider/editorial acceptance |
| M17 Content generation | PARTIAL | draft persistence/sequence and generation tests; PR #14 PostgreSQL job success | live DeepSeek, broad semantic quality and deployment acceptance |
| M18 Content verification / safety | PARTIALLY REMEDIATED | 108 content/research/editorial/authorization/runtime tests | hosted PG execution of local deltas and semantic entailment limits; upstream source trust |
| M19 Cloudflare image generation | PARTIAL | 52 image/visual tests; mocked bounded generator | no live Cloudflare account/model/quota acceptance; credentials unset in inspected process |
| M20 Visual QA | PARTIAL | 52 image/visual tests, blank-image/pixel/font/hash checks | generated-background OCR and live generated-image acceptance |
| M21 Publication / persistence / recovery | PARTIAL | PR #14 hosted disposable PostgreSQL job success including publication and scheduled acceptance | production operational crash/recovery/restore/operator drills; local uncommitted deltas not CI-tested; live publisher remains disabled |

### Active cross-module blockers
- HIGH: AUD-ONCHAIN-001 (provider response provenance), AUD-ONCHAIN-002 (mapping source authority/freshness), AUD-M14-001 (approved opportunity policy), AUD-M21-001 (operational recovery), AUD-ANN-001 (no official replay/backfill contract), AUD-EVID-001 (production CMS trust/key/deployment gates).
- MEDIUM: AUD-ONCHAIN-004 (provider byte cap), AUD-MARKET-001 (scheduled durable market history), AUD-GIT-006 (missed-tick/catch-up SLO), AUD-LIFE-001 (typed resolution/withdrawal proof), AUD-CONTENT-001/002 PostgreSQL/local-delta and semantic limits.
- Skills Hub is intentionally quarantined, not an active provider. The scheduled Square workflow is dry-run and publisher-disabled. No production database, live provider, authenticated media upload, or real Square publication acceptance is claimed.
- Overall disposition remains **PARTIAL / NOT PRODUCTION-READY / NO-GO**.

## 109. AUD-GIT-007 — default-branch publisher gate and protection revalidation (26 November 2026)

### Current remote default-branch facts (read-only GitHub API)
- Default branch main currently points to 94ebdc81aff1b9b6e6678e8eaac1adbabbfbd1e0 (auto-save post-record commit dated 25-Nov-2026). The branch API reports protected: false; branch protection is disabled.
- Current default-branch workflow .github/workflows/run_bot.yml explicitly injects DRY_RUN: "1" for the scheduled and manually dispatched run-agent job and does not inject PUBLISHER_ENABLED.
- Current default-branch main.py has no PUBLISHER_ENABLED/publisher_enabled field, config parser, or publisher gate. Config.from_env() defaults DRY_RUN to "1"; PostPublisher.publish() checks only config.dry_run before the live Square request path. _generate_image_list() also explicitly returns without generation/upload when dry-run is true.
- Therefore the current scheduled/manual workflow configuration is dry-run fenced for both content publish and image generation/upload. However, this is a single configuration-level fence: if the workflow value is changed to DRY_RUN=0 while the Square key remains injected, the current default-branch application has no independent publisher authorization check. The PR/local branch code gate is not on default main.
- Latest observed main schedule run in the API page was run 45588421357 (run 1836), event schedule, head commit 20edeeb46471883a4340c647b1d60f706519ca08, conclusion SUCCESS; its run-agent job succeeded and the PR-only safety job was skipped. This run predates the current auto-save main tip and is not evidence of the current SHA executing.
- PR #14 still remains OPEN / DRAFT / UNMERGED at 7acbb8f5014b52288e110dee368173ae7edd7429. Its main.py has a default-off PUBLISHER_ENABLED gate and the local continuation workflow explicitly sets PUBLISHER_ENABLED=0. That local workflow addition is uncommitted and was not part of hosted run 45506068788. The hosted run therefore does not verify the explicit workflow env assertion.
- The focused local publisher/workflow verification was rerun: workflow assertion 1/1 passed and tests.test_publisher_safety 57/57 passed. An initial test invocation used a non-existent test method name and failed at test discovery; the corrected exact method then passed. No application behavior change was made.

### Disposition
- AUD-GIT-007 remains PARTIALLY REMEDIATED / OPEN. Current default main is safely dry-run by explicit workflow config, and its dry-run path skips image generation; nevertheless, default-branch code lacks the independent publisher kill switch and branch protection is disabled. A future workflow/config edit could enable live publishing without a second application-level gate.
- Required closure: integrate the independent default-off code gate into default branch through the normal reviewed PR path, set explicit PUBLISHER_ENABLED: "0" in the default-branch workflow, require suitable branch protection/review checks, and verify the merged default-branch SHA. Do not edit main, enable publishing, alter secrets, or change schedules in this continuation.
- No workflow dispatch/rerun, remote write, branch protection change, secret access, provider request, image/media upload, publication, database operation, staging, commit, push or merge occurred.

## 110. AUD-ANN-001 / AUD-EVID-001 — default-branch CMS ingestion activation and replay revalidation (26 November 2026)

### Default branch workflow inventory (read-only GitHub)
- Enumerated the current default-branch .github/workflows directory at main SHA 94ebdc81aff1b9b6e6678e8eaac1adbabbfbd1e0. It contains binance-cms-manual-smoke.yml, provider-verification.yml and run_bot.yml. There is no scheduled binance-cms-announcement-ingestion.yml on default main.
- The only CMS workflow on default main is manual workflow_dispatch. It checks out worker source from integration/binance-cms-worker-main, installs its package and runs a four-minute bounded CMS listener; it is a smoke workflow, not a five-minute scheduled ingestion deployment.
- The referenced integration worker commit 47e85384f2eeba2ac5bb4f2fb2cfa26ec4dc6558 tree contains announcement-worker/src/worker.js but no announcement-worker/src/receipts.js. It is not the receipt-enabled PR #2 source.
- The separate PR #2 branch feature/binance-cms-announcement-worker contains the scheduled five-minute ingestion workflow, four-minute connection window, bounded SIGTERM drain, receipt signing keyring and active/trusted key IDs. PR #2 remains OPEN / DRAFT / UNMERGED. Its successful hosted CI proves the isolated worker build/tests and disposable DB role/TLS acceptance, not deployment from default main.
- The default-branch manual smoke workflow does not configure the CMS receipt keyring/active/trusted key IDs used by the newer PR #2 producer. This is consistent with its checked-out integration worker being the pre-receipt branch, but it must not be described as the current receipt-enabled scheduled ingestion service.

### Replay/backfill boundary
- Re-read the pinned @binance/cms package README, SDK export contract test, worker README and ingestion workflow. The documented package surface exposes WebSocket Streams, heartbeat, reconnect/renewal and subscription management; no supported CMS historical query/replay/backfill API is exposed by the pinned package or the worker's integration.
- The worker opens a new bounded connection for each scheduled run. The four-minute connection in a five-minute cron cadence is a target gap only; GitHub scheduled events are best-effort and may be delayed/dropped. The SDK reconnects/resubscribes within a run but does not restore messages missed while disconnected or between runs. Database deduplication cannot recover messages that were never received.
- Current Layer 1 correctly reports OBSERVED_ONLY_NO_HISTORICAL_REPLAY / PARTIAL_COVERAGE_NO_REPLAY and unresolved revision correlation when no stable provider ID is present. Do not relabel this as complete announcement coverage.

### Verification and disposition
- The full isolated Python suite was rerun after the current local changes: 1,079 tests, 0 failures, 0 errors, 69 skipped (69.401 seconds test runtime; 73.24 seconds process runtime).
- No behavior change. AUD-ANN-001 remains HIGH / OPEN: default main does not deploy the receipt-enabled scheduled worker; PR #2 remains unmerged; historical replay/backfill is not documented; feed completeness and stable revision identity are unavailable. AUD-EVID-001 remains PARTIALLY REMEDIATED / OPEN: worker-key receipt contract is verified in PR CI, but production deployment/key custody and provider-origin authenticity remain unresolved.
- No manual workflow dispatch, live CMS connection, database operation/migration, secret access, deployment, provider request, publication, staging, commit, push or merge occurred.

## 111. AUD-GIT-001 / AUD-GIT-002 / AUD-IMG-001 — default-branch Git history and image uploader drift (26 November 2026)

### Current default-main implementation re-read
- Remote main SHA remains 94ebdc81aff1b9b6e6678e8eaac1adbabbfbd1e0; main.py blob fcde74b8a42c2844435470d830d8125c674418e3; image_engine.py blob 8558f4c76f4b1c7cbea1ff801affef12ef8bb65a.
- main.py _try_git_push() reads GH_TOKEN/GITHUB_TOKEN and GITHUB_REPOSITORY, stages published_posts.jsonl and posts/, then commits without an explicit pathspec. It sets origin's URL to a token-bearing HTTPS URL in .git/config. It chooses the current named branch, but if branch detection returns unknown or HEAD it explicitly falls back to main. There is no exact GITHUB_REF/checked-out branch equality check, no GIT_HISTORY_ALLOWED_REFS allowlist, and no rejection of main.
- _retry_pending_push() is invoked in the startup path before the normal market scan and is not gated by DRY_RUN. Thus the current default workflow's DRY_RUN=1 does not disable this Git history write path when a pending JSONL change exists.
- The default-main workflow grants contents:write and actions:write and injects GH_TOKEN from GITHUB_TOKEN. GitHub reports the main branch unprotected. The combination makes the legacy write path operationally reachable in the scheduled job; this audit did not trigger or attempt it.
- Current default-main image_engine.py still contains legacy image persistence paths: GitHub Contents API PUT /repos/{owner}/{repo}/contents/images/{filename}, Git push uploader, and raw GitHub URL fallback. The REST uploader sends Authorization: Bearer GH_TOKEN; the Git uploader sets a token-bearing origin URL, stages/commits an image and pushes. The normal image generation path is currently skipped when DRY_RUN=1, but becomes reachable if that single workflow setting is changed to live mode. PR #14's replacement disables these legacy repository-write interfaces and uses the separate authorization-bound Binance media flow.
- Current PR #14 main.py has materially stronger Git behavior: rejects main/HEAD/unknown, requires exact GITHUB_REF match and exact operator allowlist in Actions, uses process-scoped Git config for auth rather than persisting a token URL, and commits explicit pathspecs only. The local continuation branch adds this behavior; PR #14 is still open/unmerged and does not protect default main today.

### Finding disposition
- AUD-GIT-001 remains CRITICAL / REMEDIATED IN PR #14 WORKTREE ONLY / DEFAULT MAIN OPEN. The default-main detached-HEAD-to-main fallback is confirmed in the current remote blob.
- AUD-GIT-002 remains HIGH / REMEDIATED IN PR #14 WORKTREE ONLY / DEFAULT MAIN OPEN. The default-main git commit has no pathspec and can include unrelated pre-staged content.
- AUD-IMG-001 remains HIGH / REMEDIATED IN PR #14 WORKTREE ONLY / DEFAULT MAIN OPEN. The default-main legacy GitHub REST/Git image repository writers remain present and are not disabled.
- These are branch-drift findings, not regressions in the local continuation branch. The local branch's current changes remain uncommitted and no hosted CI result covers them. Do not patch remote main directly; closure requires normal PR review/merge, appropriate branch protection, and verification of the resulting default-branch SHA.
- No workflow dispatch, Git push, GitHub Contents API write, token/secret read, image upload, publication, DB/provider call, staging, commit, push or merge occurred.

### Actual default-main write observed (read-only commit inspection)
- The latest observed scheduled run 45588421357 started on parent commit 20edeeb46471883a4340c647b1d60f706519ca08 at 2026-11-25 09:45:26 UTC and completed SUCCESS at 09:45:53 UTC.
- Current main tip 94ebdc81aff1b9b6e6678e8eaac1adbabbfbd1e0 is the corresponding bot-authored "Auto-save: post records [2026-11-25]" commit, timestamped 09:45:48 UTC, inside that scheduled run window.
- Read-only commit diff shows the only changed file is published_posts.jsonl and the added record is LINK with link="[DRY-RUN]" at 09:45:48 UTC. This proves the default scheduled job actually performed the legacy Git commit/push persistence path while DRY_RUN was enabled; it does not prove a real Binance Square post was published.
- This reconciles the workflow's apparent dry-run status with a real repository write side effect: DRY_RUN blocks the Square publication/image path but does not disable startup pending-history Git sync or the post-history auto-save push.

## 112. Default-branch runtime activation gap — Layer 1 / 21-module architecture is not deployed (26 November 2026)

### Current main source/workflow inventory
- Current default main SHA: 94ebdc81aff1b9b6e6678e8eaac1adbabbfbd1e0. main.py blob fcde74b8a42c2844435470d830d8125c674418e3 contains 4,003 lines.
- Read-only source symbol scan found zero occurrences of Layer1/layer1, DeepSeek/deepseek, OnChainTransferAggregator, ContentVerificationEngine or PUBLISHER_ENABLED. It still contains GeminiGenerator and the legacy MarketScanner/PostPublisher flow.
- Default-main run_bot.yml installs Pillow only, injects GEMINI_API_KEY and SQUARE_API_KEY, sets DRY_RUN=1, and invokes python main.py. It does not install the Layer 1 announcement importer requirements, configure the CMS read-only DB connection, configure on-chain providers, or select the PR #14 DeepSeek/Cloudflare/Layer 1 runtime.
- Therefore the 21-module continuation code in PR #14 is not the runtime currently executed by the default scheduled workflow. Existing default-main schedule runs exercise the legacy Gemini agent in dry-run mode; the newer Layer 1 stack remains an unmerged continuation.

### Current PR stack state (read-only GitHub metadata)
- PR #12: OPEN / UNMERGED, non-draft, branch layer-1/module8-market-analysis at f7e6fc511e146b6bfb6f25afb0009c369d8afd4a; base layer-1/module5-6-candidate-intelligence.
- PR #13: OPEN / DRAFT / UNMERGED, branch layer-1/module9-onchain-intelligence at 3afed37192b66c57aba2f17ba841a84a60227cda; base PR #12 branch.
- PR #14: OPEN / DRAFT / UNMERGED, branch layer-1/module9-onchain-continuation at 7acbb8f5014b52288e110dee368173ae7edd7429; base PR #13 branch.
- PR #2: OPEN / DRAFT / UNMERGED, branch feature/binance-cms-announcement-worker at 9f91646a398d95765072b300c462987f4350fc5e; base layer-1/completion-hardening.
- PR #14 successful hosted CI validates its branch head, not default main and not the uncommitted local changes. PR #12/#13/#14 form a stacked dependency chain that has not been merged into main. PR #2 is a separate CMS worker branch and is also unmerged.

### Disposition
- Add deployment blocker AUD-DEPLOY-001 — HIGH / OPEN: the production/default scheduled entrypoint does not run the 21-module architecture. It remains on the legacy Gemini pipeline; new Layer 1 and CMS worker integrations are not deployed.
- Closure requires an owner-approved merge/deployment sequence for the stacked PRs, resolution of the open Module 9/14/21 trust and operational blockers, reviewed default-branch workflow/dependency/config changes, and post-deploy smoke/acceptance against explicitly approved non-production services. Do not merge, rebase, retarget, dispatch, deploy or switch default main in this audit.
- No code change, GitHub write, PR update, workflow dispatch, deployment, secret access, DB/provider operation, publication, staging, commit, push or merge occurred.


## 113. Prioritized remediation and release-gate plan (26 November 2026)

This is an execution order, not authorization to mutate the default branch, merge PRs, deploy services, access production systems, or publish. Each gate requires evidence on the exact candidate SHA. Passing unit tests alone does not close a production blocker.

### P0 — Contain default-branch write and publish exposure
1. **AUD-GIT-001 / AUD-GIT-002 / AUD-IMG-001:** default `main` still contains unsafe legacy history sync and image repository writers. The scheduled workflow has `contents:write`/`actions:write` capability and the branch is unprotected. The `[DRY-RUN]` record commit proves `DRY_RUN=1` does not prevent repository writes. Owner-approved containment should remove unnecessary write permissions/token exposure from the legacy scheduled job or otherwise disable those write paths, then migrate to the hardened explicit-pathspec/ref-allowlisted implementation through reviewed PRs. Verify no token-bearing remote URL persistence and no unrelated staged-file inclusion.
2. **AUD-GIT-007:** default `main` lacks an independent application publisher gate; its current `DRY_RUN=1` is only a configuration fence. Bring the default-off `PUBLISHER_ENABLED` gate and explicit workflow `PUBLISHER_ENABLED=0` to the default branch through review, require branch protection/status checks, and verify the resulting default SHA. Do not enable live publishing as part of closure.
3. **AUD-DEPLOY-001:** document the deployed entrypoint and runtime inventory. The current default workflow runs legacy Gemini `main.py`, not the 21-module stack. Treat the new architecture as not deployed until the exact merged workflow, dependencies, config, persistence and service identity are verified.

**P0 exit evidence:** reviewed change on protected branch; exact default SHA; workflow permissions and environment re-read; publisher remains fail-closed; Git/image write paths either removed or explicitly authorized; no real publication.

### P1 — Close trust and decision-policy blockers before activation
1. **Module 9 / AUD-ONCHAIN-001:** establish a provider-origin trust model. Current HMAC receipts authenticate the application/key-holder envelope, not the upstream provider response. Require documented provider identity, transport/proxy boundary, response binding and key custody; do not call a raw payload hash provider authentication.
2. **Module 9 / AUD-ONCHAIN-002:** obtain an owner-approved mapping source matrix and freshness/corroboration policy, then implement a verifier against that policy. Do not invent trusted hosts, TTLs or corroborator rules. Keep on-chain runtime inactive until this passes.
3. **Module 14 / AUD-M14-001:** keep `PROCEED` fail-closed. Require an approved factor rubric, source-backed typed factors, historical labelled data, out-of-time evaluation, calibration/threshold governance, shadow-mode evidence and explicit owner activation.
4. **Module 21 / AUD-M21-001:** extend acceptance beyond disposable CI to documented operational crash/restart, lease fencing, restore/backup, reconciliation and operator drills on an approved non-production target. Production DB remains untouched.
5. **CMS / AUD-ANN-001 and AUD-EVID-001:** deploy the receipt-enabled worker only through an approved sequence; establish production key custody and provider-origin trust. Since no supported historical replay/backfill API was identified, explicitly quantify coverage limitations and missed-event handling rather than claiming complete feed coverage.

**P1 exit evidence:** policy owners and exact source/provider contracts documented; verifier tests demonstrate rejection of forged/stale/ambiguous inputs; no unresolved trust shortcut; durable recovery and replay limitations accepted; all module gates still disabled until approval.

### P2 — Complete integration and operational acceptance
1. Verify scheduled durable market-history baseline (`AUD-MARKET-001`) and catch-up/missed-tick SLO (`AUD-GIT-006`).
2. Verify DeepSeek and Cloudflare credentials/model entitlements, bounded transport, quota, latency, content quality, generated-image visual QA and cost controls in approved non-production accounts; current local tests are mocked and credentials were absent in the inspected environment.
3. Verify end-to-end event-to-research-to-editorial-to-draft-to-image-to-authorization flow with persisted provenance and negative tests; distinguish SQLite from PostgreSQL and local deltas from hosted CI.
4. Verify publisher authorization, quota reservation/finalization, ambiguous outcome reconciliation, duplicate suppression and recovery with no live Square post.
5. Run the complete suite and hosted CI on the exact final candidate SHA; include all local uncommitted changes only after an authorized reviewed commit. Record skipped tests and their reasons; no skipped integration test counts as passed.
6. Perform a deployment rehearsal on approved staging resources, followed by an explicit production-readiness review and owner sign-off. Only then consider a separate live-publication authorization.

### Dependency and sequencing constraints
- PR #12 → PR #13 → PR #14 is a stacked dependency chain; PR #2 is separate. Do not merge or retarget these mechanically. Review each base/head relationship and acceptance evidence before an owner-approved sequence.
- The successful PR #14 hosted run applies to committed head `7acbb8f5014b52288e110dee368173ae7edd7429`, not the current six-file dirty worktree. The successful PR #2 run applies only to `9f91646a398d95765072b300c462987f4350fc5e`.
- Current local verification (1,079 tests, 69 skipped; compileall; diff check) is evidence for the inspected local worktree only. It is not production acceptance and does not prove the skipped cases.
- No source-policy, scoring, key-custody, replay, provider entitlement or operational recovery policy may be inferred from tests or fabricated to clear a gate.

### Current release decision
**NO-GO / NOT PRODUCTION-READY.** The project can continue in isolated development and audit mode. Live publishing, production deployment, production database access/migration, and on-chain decision activation remain prohibited pending the gates above and separate owner authorization.

### 113.1 Local P0 workflow write-capability containment — 26 November 2026

A minimal workflow containment change was implemented in the isolated continuation worktree using TDD:

- Added `test_scheduled_workflow_has_no_repository_write_credentials`; it failed before the fix because the workflow declared `contents: write` and passed `GH_TOKEN` into the application environment.
- Changed the scheduled job permission to `contents: read`.
- Set `actions/checkout` `persist-credentials: false`; the checkout action can still use its read-scoped token to fetch source, but does not leave credentials in Git config for later application subprocesses.
- Removed explicit checkout token override, application `GH_TOKEN`, and `GIT_HISTORY_ALLOWED_REFS` injection. The application no longer receives an intended GitHub write credential from this workflow.
- Preserved `DRY_RUN: "1"` and `PUBLISHER_ENABLED: "0"`.

**Verification:** focused workflow + persistence-integrity + Git-push security suite: 29 tests passed, 0 failures/errors. Full isolated suite: 1,080 tests passed, 0 failures/errors, 69 skipped (70.191s). `compileall` and `git diff --check` passed. The six-file dirty worktree remains intact, no files are staged, and HEAD remains `7acbb8f5014b52288e110dee368173ae7edd7429`.

**Limitations:** this is a local uncommitted candidate change, not a fix on remote `main`; no hosted workflow run validates this exact dirty state. It also intentionally disables the workflow's Git-based publication-history push/retry path. Do not claim durable Git history synchronization from this workflow until a separately reviewed, least-privilege persistence design is approved. Existing default-main permissions, legacy Git helper/image paths, branch protection, and deployment-runtime blockers remain open. No workflow was dispatched, no remote write occurred, and no real publication/provider/media/production DB operation occurred.

### 113.2 Durable-state guard and fresh default-branch comparison — 26 November 2026

A follow-up risk was found in the previous local containment candidate: after removing the scheduled job's GitHub write token, the workflow still defaulted `PERSISTENCE_BACKEND` to SQLite. On ephemeral GitHub-hosted runners, SQLite and `published_posts.jsonl` are not durable across runs; removing Git sync without enforcing an external durable backend could lose cooldown/publication state. This is not an acceptable security trade-off.

TDD remediation:
- Added `test_scheduled_workflow_refuses_ephemeral_sqlite_without_git_history_writer`.
- Confirmed it failed before the workflow change because no durable-backend preflight existed.
- Added a preflight to the scheduled execution step. It exits nonzero before `python main.py` unless `PERSISTENCE_BACKEND` is exactly `postgresql` and `POSTGRES_DSN` is non-empty. It does not connect to a database during the preflight.
- The workflow still has `contents: read`, `persist-credentials: false`, no app-injected `GH_TOKEN`/`GIT_HISTORY_ALLOWED_REFS`, `DRY_RUN=1`, and `PUBLISHER_ENABLED=0`.
- Consequence: if the repository variable/secret are absent or configured for SQLite, scheduled runs stop safely rather than run with ephemeral persistence. No database configuration was inspected or changed, and no DB connection was made.

Verification after this follow-up: full isolated suite **1,081 tests, 0 failures, 0 errors, 69 skipped** (64.243s); compileall PASS; PyYAML workflow parse PASS (`run-agent` job); `git diff --check` PASS. Workflow-specific preflight, read-only permission and safety contract tests: 3/3 PASS. The 69 skipped tests remain unverified.

Fresh GitHub read-only comparison:
- Default `main` workflow blob SHA `cf5f6224b08f2248495f740602a3bb31186be4ae` still declares `contents: write` and `actions: write`, and injects `GH_TOKEN` from `GITHUB_TOKEN`.
- Default `main` image uploader blob SHA `8558f4c76f4b1c7cbea1ff801affef12ef8bb65a` still contains GitHub Contents API and Git-push image writers.
- PR #14 image uploader blob SHA `48d7f02f34d26805f66249a01769a2e15110cbb4` disables those legacy write methods. PR #14's committed workflow still grants `contents: write` and injects `GH_TOKEN`; the read-only workflow plus durable PostgreSQL preflight exists only in the local dirty candidate.
- GitHub's branch-protection endpoint returned 403 `Resource not accessible by integration` on this read attempt. This is an access limitation, not evidence that protection is enabled or disabled; prior audit evidence remains pending an authorized settings read.

No remote branch or PR was modified. No workflow was dispatched, no credentials were read, no PostgreSQL connection/migration occurred, and no real publishing or media upload occurred. This remains a local uncommitted change and default `main` remains exposed until an approved reviewed PR is merged.


### 113.3 Scheduled workflow artifact data-exposure review — 26 November 2026

Read-only review of the current local candidate `.github/workflows/run_bot.yml` and the artifact-producing code paths identified an additional workflow data-governance issue:

- The unconditional `actions/upload-artifact@v4` step runs with `if: always()` and uploads `posts/`, `research/`, `prompts/`, `drafts/`, `images/`, `agent.db`, and `published_posts.jsonl` when present. No explicit `retention-days` is set in this workflow.
- The application writes market/research packages under `research/`, complete DeepSeek writing prompts under `prompts/`, rejected generated content under `drafts/`, generated images under `images/`, and local publication records/database files. These are application outputs, not merely transient build logs.
- The artifact step is a separate data-egress path from Git write permissions. Setting `contents: read` and `persist-credentials: false` does not restrict who can download workflow artifacts; artifact access follows repository/workflow access controls.
- No evidence in this review establishes that these files contain API credentials or that an unauthorized party accessed them. The confirmed issue is that potentially sensitive operational/research/editorial material is uploaded as a broad bundle without explicit per-path classification, redaction, or workflow-specific retention policy.
- `.gitignore` currently ignores `drafts/` and `posts/`, but does not list `research/`, `prompts/`, `images/`, `agent.db`, or `published_posts.jsonl`. This is a separate local-repository hygiene concern; no local files were staged or added during this review.

**Finding:** AUD-WF-003 — MEDIUM / OPEN: scheduled workflow uploads broad operational artifacts, including research packages, prompts, generated media and local persistence files, without explicit retention or content classification. Recommended closure: decide which outputs are genuinely required for debugging/review; prefer a minimal allowlist (e.g. sanitized run summary and non-sensitive failure diagnostics), exclude DBs/prompts/raw research unless approved, set a short explicit retention period, and verify artifact access policy. Add tests that assert the intended artifact allowlist and retention. Do not delete or mutate existing user artifacts as part of this audit.

Other workflow security scan results:
- Enumerated four workflow files: `announcement-worker-tests.yml`, `phase1-safety-tests.yml`, `provider-verification.yml`, and `run_bot.yml`.
- A repository-wide scan of `.github` found no `github.token`, `secrets.GITHUB_TOKEN`, `GH_TOKEN`, `contents: write`, `actions: write`, `pull-requests: write`, `packages: write`, `id-token: write`, or `persist-credentials: true` references in the current local candidate.
- All four workflows declare read-only `contents: read` permissions at workflow/job scope. The provider verification workflow is manual-only and its existing tests assert it cannot enter the scheduled publisher path.
- Third-party actions use version tags (e.g. `@v4`/`@v5`) rather than immutable commit SHAs. This was recorded as a supply-chain hardening opportunity, not upgraded to a confirmed compromise.

Publisher gate revalidation:
- `Config.from_env()` defaults `publisher_enabled=False`; live config validation rejects `DRY_RUN=0` unless `PUBLISHER_ENABLED=true`.
- `PostPublisher.publish()` checks dry-run and then the publisher kill switch before authorization/network submission. The disabled-publisher regression asserts no network opener call.
- Focused tests already present: `test_publisher_kill_switch_defaults_off`, `test_live_config_requires_explicit_publisher_enablement`, and `test_disabled_publisher_blocks_before_authorization_or_network`. No application code change was needed in this review.

No tests or source behavior were changed in this checkpoint. No workflow was dispatched, no artifact was uploaded/downloaded/deleted, no secret was read, no provider/DB was contacted, and no real media upload or publication occurred. The findings apply to the local uncommitted candidate; default `main` remains a separate remote state.

### 113.4 AUD-WF-003 remediation candidate — runtime artifact export disabled (26 November 2026)

TDD was applied to the scheduled workflow:
- Added `test_scheduled_workflow_does_not_export_unclassified_runtime_artifacts` first and ran it against the previous workflow. It failed as expected because `actions/upload-artifact@v4` uploaded the full runtime directories and local persistence files.
- Removed the unconditional `actions/upload-artifact@v4` step entirely. The scheduled workflow now exports no application runtime files as workflow artifacts. This is intentionally conservative: no research packages, complete prompts, drafts, images, SQLite DB or local publication ledger are bundled for artifact download. Normal workflow logs remain subject to GitHub Actions access/retention policy.
- Added generated runtime paths `research/`, `prompts/`, `images/` and `agent.db` to `.gitignore` to reduce accidental addition of future generated/local state. Existing tracked images (16 files) remain tracked and untouched. `published_posts.jsonl` is already tracked by Git; adding a `.gitignore` rule would not untrack it, so it was deliberately not represented as protected by ignore rules. No index or tracked ledger mutation occurred.
- Focused scheduled persistence suite: **24 tests passed**, 0 failures/errors.
- Full isolated suite after the new regression and workflow change: **1,082 tests, 0 failures, 0 errors, 69 skipped** (63.079s). `compileall` PASS; PyYAML parse PASS and confirmed no artifact upload action; `git diff --check` PASS.

Disposition: AUD-WF-003 is **PARTIALLY REMEDIATED LOCALLY / OPEN**. Broad application artifact export is disabled in the local uncommitted candidate. Remaining work: decide whether sanitized diagnostic artifacts are needed; if so, design a minimal explicit allowlist, redact/classify contents, set explicit retention and test access/retention policy. The current workflow has no artifact-based diagnostics. This local change has not been pushed or run in hosted CI and does not change the remote default branch.

No artifact upload/download/deletion was performed. No secret, DB, provider, media upload, publication, staging, commit, push or merge occurred.

### 113.5 Scheduled PostgreSQL publication-history continuity review — 26 November 2026

Read-only trace of the local scheduled candidate after removal of Git write credentials and runtime artifact export:

- PostPublisher._publish_postgres_authorized() persists the remote post identity as PUBLICATION_UNKNOWN, then writes the confirmed post to the shared PostgreSQL posts table via PostgresLegacyDatabase.save_post(), and only then transitions the attempt to PUBLISHED_CONFIRMED. The PostgreSQL path does not depend on the ephemeral JSONL file or Git push for the authoritative post-history row.
- PostgresLegacyDatabase.get_posted_hours_dict() reads the persisted posts table; the scheduled pipeline merges this database history into posted_hours_data before objective candidate filtering.
- Independently, PostgresPublicationStore._duplicate_policy_reasons_in_transaction() reads recent publication_attempts and rejects SUBMITTING / PUBLICATION_UNKNOWN attempts for the same symbol with UNRESOLVED_PUBLICATION_ATTEMPT. This protects the ambiguous-response / remote-accepted-but-not-finalized path even if the posts row has not yet been written.
- This is static code-path verification only. No PostgreSQL endpoint was contacted and no production or disposable database was mutated in this review. Existing disposable PostgreSQL integration coverage is separately documented in Sections 107 and 110; those hosted runs apply to their recorded PR commits, not the dirty local candidate.

Verification on the exact local worktree:
- Full isolated suite: 1,082 tests, 0 failures, 0 errors, 69 skipped (64.501s).
- compileall for main.py, image_engine.py, layer1, and tests: PASS.
- run_bot.yml parsed with PyYAML; assertions confirmed read-only workflow, persist-credentials: false, PUBLISHER_ENABLED: 0, PostgreSQL preflight and no upload-artifact step: PASS.
- git diff --check: PASS.
- Worktree remains work/module9-continuation-local, HEAD 7acbb8f5014b52288e110dee368173ae7edd7429, seven existing modified files, all unstaged. Sixteen tracked image assets remain unchanged.

Disposition: no additional persistence-code change was justified by this trace. The workflow's mandatory PostgreSQL preflight is conservative and intentionally prevents scheduled runs against ephemeral SQLite when Git-based history synchronization has been removed. It also means the scheduled job will exit before main.py unless repository variable PERSISTENCE_BACKEND=postgresql and secret POSTGRES_DSN are correctly configured; those settings were not inspected or tested. AUD-WF-003 remains PARTIALLY REMEDIATED LOCALLY / OPEN pending hosted validation and a decision on sanitized diagnostics. Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.

No workflow dispatch, GitHub write, secret access, database connection/migration, provider request, image upload, Binance publication, staging, commit, push, merge or deployment occurred.


## 113.6 Default-branch security state refresh — GitHub read-only API, 26 November 2026

This read supersedes the earlier branch-protection API 403 limitation for the current default-branch state:

- GitHub repository metadata confirms default branch `main`.
- `GET /repos/shehrozali6465372-ctrl/Binance-bot/branches/main` reports current main SHA `94ebdc81aff1b9b6e6678e8eaac1adbabbfbd1e0` (commit 2026-11-25T09:45:48Z) and `protected: false`; protection reports `enabled: false`, required-status-check enforcement `off`, and no required checks.
- At that exact SHA, `.github/workflows/run_bot.yml` still grants `contents: write` and `actions: write`, checks out with `token: ${{ secrets.GITHUB_TOKEN }}`, and exposes `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` to the application. It restores/saves the publication-history cache and uploads `posts/`, `research/`, `prompts/`, `drafts/`, `images/`, `agent.db`, and `published_posts.jsonl` as an artifact.
- At the same exact SHA, the workflow maps Gemini credentials/model, not the DeepSeek + Cloudflare + CMS/PostgreSQL configuration present in the local continuation candidate. The workflow hardcodes `DRY_RUN: "1"`, but the main-branch `main.py` has no independent `PUBLISHER_ENABLED` control. Therefore the currently checked-in workflow is dry-run, but it lacks defense-in-depth against a future accidental dry-run toggle.
- `main.py` at this SHA still accepts `GH_TOKEN` / `GITHUB_TOKEN` in `_try_git_push()` and `_retry_pending_push()`. `image_engine.py` still contains legacy `binance_square_upload()`, generic `upload()`, `_github_api_upload()`, and `_git_push_image()` paths. This confirms the default-branch code is materially behind the local PR #14 candidate.
- Current PR metadata refresh: PR #12 OPEN / UNMERGED / non-draft; PR #13 OPEN / UNMERGED / DRAFT; PR #14 OPEN / UNMERGED / DRAFT. PR #14 base is `layer-1/module9-onchain-intelligence`, head `layer-1/module9-onchain-continuation`, head SHA `7acbb8f5014b52288e110dee368173ae7edd7429`. PR #2 is OPEN / UNMERGED / DRAFT, separate CMS worker branch.
- Hosted PR #14 head run `45506068788` remains completed SUCCESS, but it tests committed SHA `7acbb8f...`, not the seven-file dirty local candidate.

**Disposition:** AUD-GIT-007 is now directly confirmed HIGH / OPEN: main is unprotected with required checks disabled, while its scheduled workflow retains broad write credentials and legacy write paths. AUD-GIT-001, AUD-GIT-002, AUD-IMG-001 and AUD-WF-003 remain unremediated on default `main` until reviewed fixes reach a protected/controlled release path. No remote write was made.

No GitHub settings, workflow, branch, PR, secret or repository file was changed. This was read-only metadata/source retrieval. No workflow dispatch, provider request, database access, image upload, publication, commit, push, merge or deployment occurred.

### 113.7 Exact default-main tree vs committed PR #14 tree — 26 November 2026

A fresh read-only Git fetch was performed in the existing continuation worktree. FETCH_HEAD resolved to the GitHub default-main commit 94ebdc81aff1b9b6e6678e8eaac1adbabbfbd1e0 (parent 20edeeb46471883a4340c647b1d60f706519ca08); the PR #14 head ref resolved to 7acbb8f5014b52288e110dee368173ae7edd7429 (parent 054737dbf0d51c03b5289147605af58b038e3ef8). The local origin/main tracking ref was stale at bab7b7b6beaa2f4d5ee86d9de5394b8324504297, so it was not used as the current default-main comparison target. Fetch updated only local Git object/ref metadata; no working-tree branch, index, remote ref, or GitHub resource was changed.

Tree-to-tree comparison of exact current main and PR #14 head confirms that PR #14 contains the 21-module Layer 1 implementation and substantial changes to main.py / image_engine.py, but PR #14's committed scheduled workflow is not the same as the seven-file local candidate:

- PR #14's committed .github/workflows/run_bot.yml still declares permissions: contents: write, checks out with token: ${{ secrets.GITHUB_TOKEN }}, and injects GH_TOKEN: ${{ secrets.GITHUB_TOKEN }} plus GIT_HISTORY_ALLOWED_REFS. The workflow still uploads posts/, research/, prompts/, drafts/, images/, agent.db, published_posts.jsonl under if: always(), without an explicit retention period.
- PR #14's committed workflow defaults PERSISTENCE_BACKEND to sqlite and invokes python main.py directly; it does not contain the local candidate's mandatory PostgreSQL/POSTGRES_DSN preflight. On an ephemeral hosted runner, the committed PR workflow therefore does not establish durable cross-run persistence by itself. Whether application-level runtime checks stop it must be separately validated; do not assume the workflow's env mapping is sufficient.
- PR #14's committed workflow no longer contains the pull_request-triggered dry-run-safety-tests job that exists on current main. Other repository workflows may cover some tests, but this particular workflow no longer provides that PR gate.
- PR #14's main.py does contain the explicit publisher kill switch (PUBLISHER_ENABLED defaults false and PostPublisher.publish() checks it) and the hardened Git-history writer (rejects main/HEAD/unknown, requires exact workflow-ref/allowlist match, and uses explicit staging targets). Its image_engine.py retains legacy method names for compatibility, but binance_square_upload(), upload(), _github_api_upload() and _git_push_image() are disabled stubs returning no upload result; the active Binance presigned-media path is separate. This is a meaningful code-level improvement over current main.
- The local dirty candidate goes further than committed PR #14 for workflow containment: contents: read, persist-credentials: false, no GH_TOKEN / Git-history allowlist environment, PUBLISHER_ENABLED=0, no broad artifact upload, and a fail-closed PostgreSQL preflight. These improvements remain local/uncommitted and have not been hosted-validated.

**Release disposition:** PR #14 head is not a production-ready replacement for current main as-is. Its application-code hardening must not be conflated with its still-privileged scheduled workflow. Keep AUD-GIT-007 HIGH/OPEN and AUD-WF-003 MEDIUM/OPEN on default main; add a release-blocking subfinding AUD-WF-004 HIGH/OPEN for the committed PR #14 workflow retaining write-capable checkout/token and broad runtime artifact export, and AUD-PERSIST-004 HIGH/OPEN for the committed PR #14 scheduled workflow lacking the local PostgreSQL preflight. These findings are based on exact source/tree inspection, not a live workflow run. PR #14's recorded hosted SUCCESS applies to its committed head and does not validate the dirty local workflow candidate.

**Merge sequencing:** PR #14 is still OPEN/DRAFT and targets layer-1/module9-onchain-intelligence rather than main. It is part of a stacked branch/PR sequence. No merge-base was available from the fetched refs for a direct ancestry comparison, so the diff above is explicitly a tree-to-tree comparison, not proof of a safe merge order. Do not merge PR #14 directly into main or treat its successful CI as release approval. First reconcile the stack/base chain, land prerequisite PRs in order, incorporate the reviewed local workflow hardening into a dedicated PR, require protected-branch checks, then validate the exact final commit in hosted CI before deployment.

No code behavior was changed in this checkpoint. No workflow was dispatched, no GitHub write, secret read, provider/database access, media upload, Binance publication, staging, commit, push, PR update, merge or deployment occurred. Existing seven modified local files remain unstaged; HEAD remains 7acbb8f5014b52288e110dee368173ae7edd7429.
### 113.8 Exact PR stack ancestry and CMS branch divergence — 26 November 2026

Read-only GitHub PR metadata plus local read-only fetch of the exact base/head branch refs established the following ancestry:

- PR #12: base layer-1/module5-6-candidate-intelligence at 8b46af4; head layer-1/module8-market-analysis at f7e6fc5. The base tip is an ancestor of the head; 0 base-only commits and 4 head-only commits.
- PR #13: base layer-1/module8-market-analysis at f7e6fc5; head layer-1/module9-onchain-intelligence at 3afed37. The base tip is an ancestor of the head; 0 base-only commits and 22 head-only commits.
- PR #14: base layer-1/module9-onchain-intelligence at 3afed37; head layer-1/module9-onchain-continuation at 7acbb8f. The base tip is an ancestor of the head; 0 base-only commits and 261 head-only commits.
- This confirms the PR #12 → PR #13 → PR #14 stack order. Merge prerequisites in that order; PR #14 is not a direct mainline PR.
- PR #2 CMS worker: base layer-1/completion-hardening at d7ff271; head feature/binance-cms-announcement-worker at 9f91646. The base is NOT an ancestor of the head: merge-base ec1ee7b. The base-only side is exactly one commit, d7ff271, adding the locked 20x architecture document (1,104 lines); the head-only side contains the CMS worker history (68 commits). The mergeability API currently reports true, but that is not equivalent to full functional integration acceptance. Review the architecture-document addition and rerun the PR's hosted integration on the final merged candidate.

These branch refs were fetched into local refs/remotes/origin/stack-* and refs/remotes/origin/cms-* only. The checked-out branch remains work/module9-continuation-local at 7acbb8f; no checkout, reset, rebase, cherry-pick, merge, commit, push or PR mutation occurred.

### 113.9 Scheduled PostgreSQL DSN preflight rejects whitespace-only values — 26 November 2026

TDD remediation of a narrow fail-open configuration edge:

- Added test_scheduled_workflow_rejects_whitespace_only_postgres_dsn before the workflow change. It failed because the preflight accepted any non-empty string, including whitespace-only POSTGRES_DSN values.
- Updated the local scheduled workflow preflight to strip all POSIX whitespace from the DSN for the emptiness check (`printf '%s' "$POSTGRES_DSN" | tr -d '[:space:]'`) while retaining the original DSN value for the application. The preflight still requires PERSISTENCE_BACKEND exactly `postgresql`; it does not print or otherwise expose the DSN.
- Focused scheduled persistence + Git push security + publisher safety suites: 97 tests passed, 0 failures/errors.
- Full isolated suite on the changed candidate: **1,083 tests, 0 failures, 0 errors, 69 skipped** (69.297s).
- compileall (main.py, image_engine.py, layer1, tests): PASS. PyYAML parse and workflow safety assertions: PASS. `git diff --check`: PASS.

Limitation: this preflight verifies that the configured DSN is non-whitespace, not that the database is reachable, TLS-verified, correctly permissioned, migrated, backed up or operationally durable. No connection attempt was made. The local candidate remains uncommitted and has not been hosted-validated.

No workflow dispatch, secret read, DB/provider connection, migration, media upload, Binance publication, Git staging, commit, push, merge or deployment occurred. The seven modified worktree files remain unstaged; HEAD remains 7acbb8f5014b52288e110dee368173ae7edd7429. Overall project remains PARTIAL / NOT PRODUCTION-READY / NO-GO.
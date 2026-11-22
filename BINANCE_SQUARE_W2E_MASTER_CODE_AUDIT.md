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
| M2 Market data intelligence | NOT VERIFIED | Source symbols inventoried; implementation path pending |
| M3 Binance listing eligibility | PARTIAL | Runtime eligibility wiring observed; full engine/proof review pending |
| M4 Announcement intelligence | PARTIAL | Importer/runtime status and known coverage limitation carried forward; full code review pending |
| M5 Trend intelligence | FAIL | AUD-MAIN-002: single-run path omits trend engine |
| M6 Candidate discovery | NOT VERIFIED | Pending |
| M7 Relevance scoring | NOT VERIFIED | Pending |
| M8 Market analysis | PARTIAL | Historical baseline limitation carried forward; full code review pending |
| M9 On-chain intelligence | FAIL / PARTIAL | AUD-ONCHAIN-001/002/003 carried forward; full implementation and worker/storage review pending |
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
| M20 Visual QA | NOT VERIFIED | Pending |
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
- **Status:** CONFIRMED TEST-DESIGN FALSE-PASS; RUNTIME EXECUTION BLOCKED
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
- **Status:** CONFIRMED METRIC-SEMANTICS DEFECT
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
  - The active fallback branch computes `heuristic = min(abs(coin.change_24h) * 3 + coin.volume_ratio * 10, 100)` at `main.py:4890-4895` and sorts candidates by this score at `:4903-4904`.
  - This is a ranking heuristic, not the Module 14 policy; the code path does not attach a calibration dataset, empirical validation, factor provenance, or an approved policy version to the coefficients `3` and `10`.
  - `volume_ratio` is itself the CoinGecko turnover percentage proxy described in `AUD-MKT-001`, not an average-volume multiple.
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
- Main runtime calls `EventIntelligenceGraphEngine().rebuild_from_store(store, onchain_summary_refs=...)` at `main.py:5920-5922`, and `EvidenceVerificationEngine().rebuild_from_store(store, onchain_summary_refs=...)` at `main.py:5940-5942`. The observed main path supplies aggregation summary refs, not individual normalized on-chain transfer observations. This strengthens, but does not independently close, `AUD-ONCHAIN-003`.
- The on-chain summary-to-candidate bridge at `main.py:5850-5908` only attaches qualifying summary IDs after the discovery candidate and exact Binance eligibility gates; on-chain is explicitly optional corroboration, not a discovery or publish-authority input. This is the intended safe direction, but does not cure the forged validation receipt/mapping provenance findings.


## 12. Reconciled module matrix after focused code review and test batches

This matrix supersedes the preliminary matrix in section 7. Status reflects the evidence actually available, not merely the existence of a module or passing isolated tests.

| Module | Current status | Reason |
|---|---|---|
| M1 Configuration / run lifecycle | PARTIAL | SQLite run lease and focused tests reviewed; PostgreSQL lease parity, multi-process crash/restart and operational recovery still not accepted |
| M2 Market intelligence / provider normalization | PARTIAL | Canonical identity and market normalization tests pass; historical baseline coverage and live provider verification remain incomplete |
| M3 Binance listing eligibility | PARTIAL | Exact Spot eligibility and fail-closed mock tests pass; live official metadata and independent identity proof not verified |
| M4 Announcement intelligence | PARTIAL | Importer/runtime tests pass; no historical replay and unstable provider revision IDs limit completeness |
| M5 Trend intelligence | FAIL | Scheduled single-run entrypoint drops trend engine; market turnover proxy also misrepresented as x-volume |
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
| M20 Visual QA | FAIL | Existing test fixture proves metadata-only false PASS for blank image; image tests pass as a suite but do not cure this design defect |
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
- Recommendation: remove/disable legacy repository-upload fallback from production-facing interfaces, or replace with a narrowly scoped API that does not persist credentials and cannot commit unrelated index entries. Add isolated temporary-repository tests for staged-file contamination, detached HEAD, branch allowlisting, command failures, and remote credential persistence. Do not run the legacy path against the real repository as part of diagnostics.

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

### AUD-ONCHAIN-003 — PostgreSQL stores are not pluggable into current worker/aggregation pipeline
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
- **Status:** CONFIRMED STORE-BOUNDARY GAP; no database tampering or production impact demonstrated.
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
- ContentVerificationEngine accepts any publicly constructed `ClaimRegistry` instance and trusts its result states. This is the same typed-registry trust assumption already recorded as AUD-RESEARCH-002 / AUD-EVID-001; no duplicate finding count is added here.
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
- Re-read the visual validator and its blank-image PASS fixture. The previously recorded finding remains accurate: the sidecar claims text/geometry while the test image is a solid-color PNG with no text pixels, and the validator does not verify the glyph pixels.
- The active ImageComposer does render deterministic overlays in the normal path, but Module 20 still cannot independently detect a blank/replaced image with a self-consistent sidecar or unexpected generated text/logos/charts in the background.
- This section is a Module 20 continuation note only. Section 13 remains the canonical finding and severity record; no second visual-QA finding is counted.

### Module 20 positive controls and disposition
- Exact 10 MiB image and 1 MiB sidecar read limits; 2,000,000 decoded-pixel cap checked before image loading; corrupt/decompression-bomb images fail closed.
- Requires exact 1080x1350 PNG, exact canonical asset/ticker, approved Cloudflare model, matching final-image and draft hashes, prompt hash format, generation-parameter bounds and deterministic overlay metadata.
- Rejects chart data references and numeric overlays unless absent; checks overlay boxes, minimum font size, conservative contrast, clipping and overlap.
- Existing visual test inventory includes draft/image mismatch, tampered image hash, malformed sidecar, missing overlay geometry, overlap/clipping, low contrast, small text, oversized file, pixel-limit and decompression-bomb cases. These tests were **not executed** because Pillow is missing in the RDC Python environment; source inspection only.
- Module 20 remains **PARTIAL / NOT PRODUCTION-CERTIFIED** until overlay pixels and generated-background content are independently verified and the full Pillow-dependent test suite runs in an approved environment.
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
| AUD-MAIN-001 | CRITICAL | OPEN — history-integrity check fails open on Git uncertainty/corrupt state |
| AUD-MAIN-002 | HIGH | OPEN — one-shot workflow omits trend engine |
| AUD-ONCHAIN-001 | CRITICAL | OPEN — caller-forgeable acceptance/provenance receipt |
| AUD-ONCHAIN-002 | HIGH | OPEN — mapping VERIFIED state lacks reproducible source proof/freshness |
| AUD-ONCHAIN-003 | HIGH | OPEN — individual observations not demonstrated in main ClaimRegistry path |
| AUD-ONCHAIN-004 | MEDIUM | OPEN — provider response body lacks explicit byte limit |
| AUD-M14-001 | HIGH | OPEN / FAIL-CLOSED DEFER — production scoring policy not calibrated/approved/activated |
| AUD-M14-002 | HIGH | OPEN — raw factor values can PROCEED in evaluator interface; current scheduled path remains DEFER |
| AUD-M21-001 | HIGH | PARTIAL / OPEN — PostgreSQL durability and recovery acceptance not run against an approved disposable DB in this environment |
| AUD-ANN-001 | HIGH | PARTIAL / OPEN — announcement stream has no historical replay guarantee |
| AUD-MARKET-001 | MEDIUM | PARTIAL / OPEN — incomplete timestamped historical market baselines |
| AUD-MKT-001 | HIGH | OPEN — turnover percentage is interpreted as an x volume-spike ratio |
| AUD-GRAPH-001 | MEDIUM | OPEN — equal-timestamp relationship conflict resolution can prefer weaker status |
| AUD-LIFE-001 | MEDIUM | OPEN — direct lifecycle API trusts caller-supplied VERIFIED state/evidence reference; active sync path is safer |
| AUD-RESEARCH-001 | MEDIUM | OPEN — research package hash is not recomputed/verified at store boundary/read |
| AUD-RESEARCH-002 | MEDIUM | OPEN — research builder trusts typed ClaimRegistry origin/state |
| AUD-LLM-001 | MEDIUM | OPEN — DeepSeek response body has no explicit byte limit |
| AUD-EDITORIAL-001 | MEDIUM | OPEN — editorial brief hash is not recomputed/verified at persistence/read |
| AUD-EVID-001 | MEDIUM | OPEN — caller-controlled provenance flags can manufacture primary/corroboration status |
| AUD-DRAFT-001 | MEDIUM | OPEN — tied timestamps can select an older PASS for final authorization |
| AUD-CONTENT-001 | MEDIUM | OPEN — verified claims outside the approved editorial brief can pass |
| AUD-CONTENT-002 | MEDIUM | OPEN — SOURCE_ASSERTION can pass without publisher attribution |
| AUD-PUB-001 | HIGH | FIX IMPLEMENTED LOCALLY — hosted CI pending |
| AUD-PUB-002 | HIGH | FIX IMPLEMENTED LOCALLY — hosted CI pending |
| AUD-VIS-001 | HIGH | OPEN — visual QA test design permits blank-image false PASS; pixel verification absent |
| AUD-WF-002 | CRITICAL | OPEN — fixed-key workflow cache can restore stale publication history over newer Git state |
| AUD-GIT-001 | CRITICAL (original) | PARTIALLY CLOSED — active branch guard rejects main/detached/unknown, but trusted workflow-ref allowlist is absent |
| AUD-GIT-002 | HIGH (original) | CLOSED for active `_try_git_push()` path — explicit pathspec prevents unrelated staged files entering its commit; does not close legacy image uploader path |
| AUD-GIT-003 | HIGH | OPEN — clean local commit ahead of origin is not detected/retried |
| AUD-GIT-006 | MEDIUM | OPEN — scheduled-run delivery far below configured cadence; cause not isolated |
| AUD-GIT-007 | HIGH | OPEN — live default-branch scheduled publisher lacks PR branch's explicit default-off publisher gate |
| AUD-IMG-001 | HIGH | OPEN — legacy image uploader retains separate unsafe Git/REST repository mutation path; no active main publication call site was found in reviewed path |
| AUD-SCORE-001 | MEDIUM | OPEN — active MarketScanner coefficients lack documented empirical/source justification |
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
3. Critical `AUD-ONCHAIN-001` leaves a caller-forgeable provider-acceptance trust boundary.
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
| M2 Market data intelligence | FAIL / PARTIAL | `AUD-MKT-001` metric-semantics defect; `AUD-MARKET-001` historical baseline gap |
| M3 Binance listing eligibility | PARTIAL | Full provider/source proof and runtime acceptance not certified |
| M4 Announcement intelligence | PARTIAL | `AUD-ANN-001` replay/backfill and read-only DB role evidence missing |
| M5 Trend intelligence | FAIL | `AUD-MAIN-002` one-shot workflow omits HotSearchEngine |
| M6 Candidate discovery | NOT VERIFIED | Full module and cross-layer behavior not completed |
| M7 Relevance / scoring | PARTIAL | `AUD-SCORE-001` heuristic coefficients lack documented empirical/source justification |
| M8 Market analysis | PARTIAL | `AUD-MARKET-001` historical baseline coverage incomplete |
| M9 On-chain intelligence | FAIL / PARTIAL | `AUD-ONCHAIN-001..004`; worker/storage and source trust gaps |
| M10 Event graph | PARTIAL | `AUD-GRAPH-001` equal-timestamp conflict resolution defect |
| M11 Evidence verification | PARTIAL | `AUD-EVID-001` caller-controlled provenance trust boundary |
| M12 Event lifecycle | PARTIAL | `AUD-LIFE-001` direct API validation gap; active sync path is safer |
| M13 Deep research | PARTIAL | `AUD-RESEARCH-001/002` store hash/origin validation gaps |
| M14 Opportunity evaluation | FAIL / DEFER | `AUD-M14-001/002`; no approved source-backed calibrated production scoring policy |
| M15 DeepSeek integration | PARTIAL | `AUD-LLM-001` response-size bound; live provider verification not performed in this pass |
| M16 Editorial strategy | PARTIAL | `AUD-EDITORIAL-001` persisted brief hash verification gap |
| M17 Content generation | PARTIAL | `AUD-DRAFT-001` tied-timestamp validation-order defect |
| M18 Content verification / safety | PARTIAL | `AUD-CONTENT-001/002` editorial allowlist and source attribution gaps |
| M19 Cloudflare image generation | PARTIAL | Provider docs cross-checked; no authenticated runtime/account smoke test; Pillow unavailable |
| M20 Visual QA | FAIL / PARTIAL | `AUD-VIS-001` blank-image false PASS; pixel proof and tests incomplete |
| M21 Publication / persistence / recovery | FAIL / PARTIAL | `AUD-MAIN-001`, `AUD-PUB-001/002`, `AUD-M21-001`, `AUD-GIT-003` |

### Ordered closure plan
1. Close critical publication-history integrity and workflow cache rollback defects (`AUD-MAIN-001`, `AUD-WF-002`) with isolated regression tests before any live publishing enablement.
2. Close Module 21 authorization/quota consistency defects (`AUD-PUB-001`, `AUD-PUB-002`). Decide explicitly whether SQLite live publishing is supported; if not, enforce PostgreSQL-only live mode rather than relying on undocumented operational assumptions.
3. Correct the one-shot trend-engine wiring (`AUD-MAIN-002`) and add a non-publishing regression test.
4. Complete approved disposable PostgreSQL acceptance, concurrency, crash/restart, unknown-outcome and operator recovery tests for `AUD-M21-001`.
5. Resolve the on-chain acceptance trust boundary and prove the intended individual-observation/ClaimRegistry contract (`AUD-ONCHAIN-001/002/003`); add provider response size limits (`AUD-ONCHAIN-004`).
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
- Project status remains NO-GO / PARTIAL / NOT PRODUCTION-READY because unrelated critical/high findings remain open, including AUD-ONCHAIN-001, AUD-PUB-001/002, AUD-MAIN-002, AUD-GIT-003, and the remaining source/evidence/content/visual and policy gaps.


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

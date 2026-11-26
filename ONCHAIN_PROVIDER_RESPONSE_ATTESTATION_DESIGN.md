# Module 9 — Provider response attestation design (AUD-ONCHAIN-001)

**Status:** DESIGN PROPOSAL ONLY — no production trust policy or implementation activated\
**Finding:** AUD-ONCHAIN-001 — HIGH / PARTIALLY REMEDIATED / OPEN\
**Scope:** Provider response provenance from HTTPS transport through normalized on-chain events, acceptance receipts, persistence, and evidence replay.

## 1. Problem statement

The existing version-1 Module 9 HMAC acceptance receipt binds a trusted key holder's signature to an `EligibilityDecision` + `OnChainAssetMapping` + `OnChainObservation` application snapshot. It detects later tampering with that snapshot when the verification key and trusted key ID are configured. It does not establish that the snapshot came from the named upstream provider.

The current provider transport reads bounded HTTP response bytes, parses JSON, returns decoded values, and discards the raw response bytes. `ProviderDataPage` contains provider/network/scope and page/finality metadata but no request digest, response digest, endpoint identity proof, or transport receipt. Worker code normalizes the returned records and persists them. The downstream acceptance engine accepts caller-constructible dataclasses and signs the supplied snapshot if its signing key is configured.

A local HMAC is not an upstream provider signature. Unless a provider publishes a verifiable response-signing protocol, the strongest honest claim is: a controlled ingestion service received these bytes over a verified TLS connection from an explicitly configured provider endpoint, validated the response, and attested to the exact normalized projection.

## 2. Current evidence and limitations

- `layer1/onchain_providers.py:144-167` validates HTTPS URL syntax, configures the default no-redirect opener, and stores the endpoint. This is useful transport hardening, but not a persisted provider response attestation.
- `layer1/onchain_providers.py:183-205` and `:223-255` read bounded raw bytes, decode JSON, validate a basic RPC envelope, and return only the decoded object/result. The raw bytes and request/response association are not carried forward.
- `layer1/onchain_providers.py:270-288` defines `ProviderDataPage` with provider/network/scope/records/pagination/finality fields only; no source-response digest or receipt exists.
- `layer1/onchain_evm_worker.py:195-238`, `layer1/onchain_bitcoin_worker.py:208-251`, `layer1/onchain_solana_worker.py:247-314`, and `layer1/onchain_xrpl_worker.py:225-292` validate response-shaped records and persist normalized events. They do not receive a cryptographically verifiable transport receipt.
- `layer1/onchain.py:72-105` defines `OnChainObservation` and `OnChainValidationResult` without a provider response digest, source request identity, or transport attestation field.
- `layer1/onchain.py:218-252` verifies the HMAC over the observation and validation envelope. `:254-283` signs the supplied eligibility/mapping/observation snapshot. Neither operation verifies a provider response.
- `layer1/onchain_aggregation.py:146-185` checks the shape and age of caller-supplied Binance Spot eligibility fields, then invokes the acceptance engine; it does not independently verify a fetch-bound Spot receipt or raw provider response.
- `tests/test_onchain_intelligence.py:18-29, 43-76` constructs synthetic eligibility, mapping, and observation objects directly. This is valid unit-test isolation, but it demonstrates that the acceptance API's inputs are application objects, not objects whose origin is established by the provider transport.
- Repository search found no `main.py` activation of the four Module 9 workers/aggregator or `evidence_from_onchain_observation`; the lower-level library path is not the deployed runtime's current evidence path.

## 3. Required trust model

1. **Configured source identity:** an operator-approved provider ID, network ID, exact HTTPS hostname, endpoint profile, and allowed RPC method set. Never persist credential-bearing endpoint URLs or raw API keys.
2. **Transport assurance:** use the platform TLS stack with certificate-chain and hostname validation; reject redirects; define proxy/environment trust policy explicitly; do not claim TLS provides a provider-signed payload.
3. **Request binding:** canonicalize and hash the request method and non-secret parameters. Exclude credentials and redact secret-bearing endpoint paths. Bind network, scope, range, page/cursor identity, and protocol version.
4. **Response binding:** hash the exact bounded response bytes before JSON parsing. Preserve the response status, selected non-sensitive headers, byte length, receipt timestamp, and raw-response SHA-256. Do not persist secret-bearing headers or unbounded bodies.
5. **Semantic binding:** hash a deterministic, versioned normalized projection that binds every emitted event/record to the exact request and response receipt. Include the canonical block/ledger header evidence used to derive event block identity and time.
6. **Trusted attestation:** only a narrowly scoped ingestion signer may issue the receipt after transport, schema, scope, finality, and canonical-header validation. The downstream acceptance engine must verify the receipt and derive the observation from the receipt-bound normalized record; it must not accept arbitrary caller-built `OnChainObservation` as trusted source evidence.
7. **Persistence/replay:** persist receipt, normalized projection hash, key ID, authority ID, provider profile ID, and schema version atomically with each event/page/checkpoint. Reverify signatures, allowlists, request/response/projection hashes, and exact event-to-projection binding on restore. Support trusted historical keys during rotation.
8. **Honest provenance labels:** use `TLS_PROVIDER_RESPONSE_ATTESTED` (or equivalent) for the application attestation. Reserve `PROVIDER_SIGNED` for a provider's independently verifiable signature scheme. Do not conflate these states.

## 4. Design boundaries

- A raw-response hash alone is not authentication; an attacker who can replace both payload and hash can recompute it.
- A worker HMAC receipt authenticates the worker's attestation only if signing-key custody and process access are restricted. It does not protect against compromise of that worker or signer.
- HTTPS authenticates the configured endpoint under the trust roots and hostname checks of the runtime. It does not protect against a compromised provider, compromised CA/trust store, compromised local host, or semantically false provider data.
- Multiple RPC methods used to derive one event (transaction page, canonical block header, finalized head) must each have a distinct request/response receipt and be linked into one derivation manifest. A receipt for only the transaction page is insufficient if canonical block time/hash came from a separate call.
- Do not add endpoint hostnames, provider independence groups, TLS pinning, provider response-signature algorithms, or TTLs by guesswork. Obtain owner approval and provider documentation first.

## 5. Proposed implementation sequence (not yet authorized)

1. Approve the source profile matrix: provider IDs, exact hosts, network/method matrix, proxy policy, endpoint identifiers, TLS policy, and credential handling.
2. Define immutable `ProviderRequestIdentity`, `ProviderResponseAttestation`, and `NormalizedRecordAttestation` contracts with strict finite canonical JSON, domain separation, schema versioning, bounded fields, and no secrets.
3. Extend the default transport to return a typed response envelope containing decoded JSON plus raw response digest/length/status/receipt time and a canonical request digest. Keep existing public adapter return shapes backward-compatible only if provenance cannot be silently dropped; otherwise make provenance mandatory for production worker paths.
4. Bind adapter parsing outputs to those envelopes. For every worker, link all relevant response receipts (page, transaction details, canonical block/ledger headers, finalized head) to a versioned derivation manifest.
5. Restrict receipt issuance to the trusted ingestion boundary. Inject signer capability into the transport/adapter worker only; do not make arbitrary library callers able to sign arbitrary observation-shaped objects.
6. Change acceptance to consume verified typed attestation records, not caller-supplied status labels or arbitrary dataclasses. Keep test-only fixtures clearly separated from production acceptance constructors.
7. Persist event/page receipts atomically with canonical event and checkpoint updates; add SQLite and PostgreSQL parity, tamper/replay/fresh-process/key-rotation tests.
8. Add worker-to-aggregator integration tests proving the final normalized event and acceptance evidence are derived from the exact attested response chain.
9. Only after isolated tests pass, separately approve worker runtime wiring and disposable PostgreSQL acceptance. Production activation remains a separate change.

## 6. Required adversarial acceptance tests

- Replace response bytes while retaining an old receipt; reject.
- Replace request method/parameters, network, scope, block range, page cursor, or endpoint profile; reject.
- Change a normalized record while keeping the raw response digest; reject projection/derivation binding.
- Rebind an event to a different canonical block header, block time, transaction index, or contract/mint; reject.
- Supply a caller-constructed `OnChainObservation` and fabricated `ACCEPTED` result without a valid trusted ingestion receipt; remain UNVERIFIED.
- Supply a valid HMAC receipt for a different authority, provider profile, key ID, or schema version; reject.
- Tamper with persisted response receipt, derivation manifest, normalized projection, event row, or checkpoint independently; fail closed on fresh-process restore.
- Rotate keys while preserving verification of previously trusted receipts; reject removed/untrusted key IDs.
- Confirm redirects, untrusted TLS certificates, hostname mismatch, proxy override, malformed content length, oversized response, and invalid RPC envelope fail closed.
- Verify no API key, credential-bearing URL, authorization header, or raw secret is persisted, logged, or included in hashes exposed to users.

## 7. Closure criteria

AUD-ONCHAIN-001 cannot close until the approved provider trust profile exists, the raw request/response-to-normalized-event chain is verifiably bound, the signer is isolated at the ingestion boundary, all persistence paths reverify receipts after restart, adversarial tests pass for both stores, and a separately approved disposable PostgreSQL worker/aggregator acceptance run succeeds. No live provider or production database is required for the ordinary unit/integration suite.

**Current disposition remains HIGH / PARTIALLY REMEDIATED / OPEN.** No provider policy, runtime wiring, production key, database, migration, deployment, publication, commit, or push is authorized by this design note.

# Binance Square OpenAPI / Automation Compliance Review

**Review date:** 2026-11-22\
**Scope:** Official Binance Square Posting OpenAPI and Binance Skills Hub square-post workflow.\
**Code/runtime effect:** NONE. Documentation correction only. No publisher, gateway, credentials, schedules, account, database, or live post was touched.

## Corrected executive finding

The earlier interpretation that automated posting is categorically blocked was incomplete and is withdrawn.

Binance documents an official Square Posting OpenAPI key and an official Binance Skills Hub square-post skill specifically for programmatic publishing through compatible AI agents. Binance's own official tutorial demonstrates connecting the posting key to OpenClaw and publishing through that skill. Therefore, the project may use this documented, account-authorized OpenAPI route subject to its actual constraints and Binance policies.

This does not authorize browser automation, undocumented endpoints, credential sharing, bypassing limits, spam, or unsupported actions. Use the official posting API/skill contract and keep content quality, policy, account authorization and rate limits as hard controls.

## Verified official product facts

1. Dedicated posting key: created by the creator in Binance Square Creator Center; one dedicated Square posting API key per creator account; posting-only permission, no asset/trading operations; keep secret and regenerate if compromised. Sources: https://www.binance.com/en/square/post/298569766519442 and https://www.binance.com/square/creator-center/home
2. Limits: 100 successful posts/day per posting API key (default documented limit); 400 uploads/day in the official Skills Hub contract. Errors include 220009 (daily post limit exceeded) and 220014 (daily upload limit exceeded). Source: https://www.binance.com/en/skills/detail/binance/square-post
3. Supported formats in the retrieved Skills Hub contract: text-only short posts; image posts with up to 4 images; long-form article with optional single cover; video with automatically generated cover. Images and video are mutually exclusive in one post.
4. Skill scope: creates new posts only; does not read/list/search existing posts, edit/delete, comment/like, manage profiles, or schedule/draft. Source: https://www.binance.com/en/skills/detail/binance/square-post
5. Official agent integration: Binance's official tutorial demonstrates creating a Square posting key, installing binance/binance-skills-hub/skills/binance/square-post, configuring OpenClaw and publishing. Source: https://www.binance.com/en/square/post/298569766519442

## Engineering disposition

- Use the dedicated Binance Square Posting OpenAPI key and official square-post skill/API contract. Do not substitute browser automation or undocumented endpoints.
- Enforce a durable per-account daily successful-post counter and a safety margin below the documented 100-post cap; reconcile uncertain outcomes before retrying to avoid duplicates.
- Enforce the 400 uploads/day limit independently.
- Respect supported media constraints. Do not assume scheduling exists: the retrieved skill explicitly excludes scheduling/drafts.
- Keep the key in secret storage/environment injection only. Never print it, place it in CLI arguments, commit it, or expose it in logs.
- Keep quality, evidence verification, duplicate detection, platform policy, user authorization and human review controls. API availability is not permission to spam or publish unsupported/misleading content.
- Do not activate live publishing during diagnostics. Activation remains subject to explicit owner approval and end-to-end acceptance.

## Reconciliation with general Community Guidelines

General Square Community Guidelines contain broad prohibitions concerning abusive bot activity, spam, mass-similar posts and high-frequency abuse. The dedicated official Posting OpenAPI and Binance's own agent skill/tutorial establish a specific supported programmatic publishing path. Correct interpretation: use only that documented, account-owned API workflow and comply with content/anti-spam controls—not that all automation is prohibited.

Guidelines: https://www.binance.com/en/support/faq/detail/ecb50ef2012f40b2a2c4f72eaa5b569f

## Evidence boundary and status

The sources establish the official posting API, key scope, limits, skill-supported formats and skill boundaries. They do not guarantee that every account has the feature enabled in every region, guarantee every content item will publish, or grant scheduling/read/edit capabilities. Current account eligibility and key validity must be checked by the account owner in Creator Center. This review did not access the user's account, inspect/retrieve any key, call the posting API, or publish anything.

**OFFICIAL API PATH VERIFIED.** Project integration and production acceptance remain separate engineering tasks. No code/runtime change is made by this document.

## Existing repository publisher compatibility audit — 2026-11-22

Read-only inspection of the current continuation worktree (`main.py`, `layer1/publication_authorization.py`, and `tests/test_publisher_safety.py`) found the following implementation facts. No publisher code was changed.

1. `PostPublisher.API_URL` currently points to `https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add`, and the request uses `X-Square-OpenAPI-Key`. This is the same `/content/add` operation referenced by the official skill's documented 504-after-submission behavior. The endpoint path/header alone do not establish full compatibility with the current official skill workflow.
2. The project currently constructs its own request rather than invoking Binance's maintained `scripts/post-text.mjs`, `post-image.mjs`, or `post-video.mjs`. The current official skill (version 2.0.0 in the GitHub SKILL.md metadata) explicitly says not to hand-code normal posting requests; its scripts own upload, processing/polling, cover generation, and publication. This is a compatibility/maintenance gap requiring a scoped owner-approved decision—not proof that the API key or endpoint is unauthorized.
3. The current payload always sets `contentType: 1`, uses `bodyTextOnly`, and optionally passes `imageList` directly. The inspected publisher path does not perform the official skill's media upload/polling flow or implement the documented article/video request modes. End-to-end media compatibility is therefore NOT VERIFIED.
4. The payload applies `_limit_hashtags(content)` before submission. The official skill says preserve user content exactly, without rewriting, translating, adding hashtags/cashtags, or changing punctuation. Exact-content preservation is therefore NOT VERIFIED and appears inconsistent wherever `_limit_hashtags` changes the supplied draft.
5. Current configuration reads `SQUARE_API_KEY`; the official skill contract reads `BINANCE_SQUARE_OPENAPI_KEY` or its documented config file. Whether deployment configuration securely maps the official key into `SQUARE_API_KEY` has not been inspected; do not expose or print environment values.
6. Existing publisher treats HTTP 5xx (including 504) as `PUBLICATION_UNKNOWN` and blocks blind resubmission. The official skill says a specific script result of `Success!` with unavailable ID/link after `/content/add` 504 is considered successful. Keep the project's stricter unknown/reconciliation state until a safe, evidence-backed integration mapping is designed; do not infer confirmed post identity without an ID/link or other supported proof.
7. Existing authorization, durable attempt/quota fencing, and no-blind-retry protections are valuable and must be preserved if the integration is ever adapted. Do not replace them with a direct unguarded script invocation.

### Required next engineering decision

Before any publisher modification, produce a design that calls the official skill's maintained scripts (or an officially documented equivalent) *behind* the existing single publication gateway, preserving immutable authorization, durable quota reservation/consumption, idempotency, secret injection, unknown-outcome fencing, and no-live-post test isolation. Establish a supported way to reconcile the skill's 504-success-without-ID outcome with the project's durable ledger. Owner approval is required before changing the publisher/gateway or installing the skill.

**Status:** Official API/skill route verified; current project publisher's full contract compatibility is **NOT VERIFIED / GAP IDENTIFIED**. No credentials inspected, no skill installed, no publisher or gateway changed, and no live post made.

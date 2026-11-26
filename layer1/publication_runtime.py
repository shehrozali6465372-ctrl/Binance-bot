"""Adapters that keep publication-critical records on one explicit PostgreSQL store.

SQLite remains the default for existing deployments. These adapters are selected
only when PERSISTENCE_BACKEND=postgresql and a PostgreSQL store is explicitly
constructed by the application bootstrap.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json


class PostgresClaimRegistryStore:
    def __init__(self, store):
        if not callable(getattr(store, "save_claim_registry", None)):
            raise TypeError("PostgreSQL claim registry store is required")
        self.store = store

    def save(self, registry):
        return self.store.save_claim_registry(registry)

    def load_latest(self):
        return self.store.load_latest_claim_registry()


class PostgresResearchPackageStore:
    def __init__(self, store):
        if not callable(getattr(store, "save_research_package", None)):
            raise TypeError("PostgreSQL publication store is required")
        self.store = store

    def save(self, package):
        payload = asdict(package)
        payload.pop("version", None)
        payload.pop("package_id", None)
        saved = self.store.save_research_package(
            research_key=package.research_key, package_hash=package.package_hash,
            cutoff_at=package.cutoff_at, payload=payload,
        )
        return replace(package, version=saved["version"], package_id=saved["package_id"])

    def load_latest(self, research_key):
        return self.store.load_latest_research_package(research_key)


class PostgresEditorialBriefStore:
    def __init__(self, store):
        if not callable(getattr(store, "save_editorial_brief", None)):
            raise TypeError("PostgreSQL publication store is required")
        self.store = store

    def has_angle(self, event_id, angle_id):
        row = self.store.conn.execute(
            "SELECT 1 FROM editorial_brief_versions WHERE event_id=%s AND angle_id=%s LIMIT 1",
            (event_id, angle_id),
        ).fetchone()
        return row is not None

    def save(self, brief):
        if brief.status != "READY":
            raise ValueError("only a READY editorial brief may be persisted")
        payload = asdict(brief)
        # Version and brief ID are assigned atomically by PostgreSQL and are
        # returned as row metadata; never persist the in-memory pending identity.
        payload.pop("version", None)
        payload.pop("brief_id", None)
        saved = self.store.save_editorial_brief(
            event_id=brief.event_id, angle_id=brief.angle_id,
            research_package_id=brief.research_package_id,
            brief_hash=brief.brief_hash, payload=payload,
        )
        return replace(brief, version=saved["version"], brief_id=saved["brief_id"])

    def load_latest(self, event_id, angle_id):
        return self.store.load_latest_editorial_brief(event_id, angle_id)


class PostgresOpportunityDecisionStore:
    def __init__(self, store):
        if not callable(getattr(store, "save_opportunity_decision", None)):
            raise TypeError("PostgreSQL publication store is required")
        self.store = store

    def save(self, research_package_id, decision):
        return self.store.save_opportunity_decision(research_package_id, decision)

    def load(self, decision_id):
        return self.store.load_opportunity_decision(decision_id)


class PostgresDraftStore:
    def __init__(self, store):
        required = ("save_draft", "save_text_validation", "save_visual_validation", "save_image_artifact")
        if any(not callable(getattr(store, name, None)) for name in required):
            raise TypeError("PostgreSQL publication store is required")
        self.store = store

    def save_draft(self, *args, **kwargs):
        return self.store.save_draft(*args, **kwargs)

    def save_text_validation(self, **kwargs):
        return self.store.save_text_validation(**kwargs)

    def save_visual_validation(self, **kwargs):
        return self.store.save_visual_validation(**kwargs)

    def save_image_artifact(self, metadata, *, image_path):
        return self.store.save_image_artifact(metadata, image_path=image_path)

    def image_artifact(self, draft_hash, image_hash):
        return self.store.load_image_artifact(draft_hash, image_hash)

    def latest_text_validation(self, draft_hash):
        record = self.store.load_latest_text_validation(draft_hash)
        return record["status"] if record else None

    def visual_validation(self, draft_hash, image_hash):
        record = self.store.load_latest_visual_validation(draft_hash, image_hash)
        return record["status"] if record else None

    def load_latest(self, draft_key):
        return self.store.load_latest_draft(draft_key)


class PostgresPublicationAuthorizationEngine:
    """Build and persist authorization using only the PostgreSQL provenance ledger."""
    def __init__(self, store):
        if not callable(getattr(store, "save_publication_authorization", None)):
            raise TypeError("PostgreSQL publication store is required")
        self.store = store

    def reserve_daily_quota(self, **kwargs):
        return self.store.reserve_daily_quota(**kwargs)

    def mark_quota_status(self, reservation_id, status):
        return self.store.mark_quota_status(reservation_id, status)

    def authorize(self, *, symbol, asset_id, content, image_hashes,
                  eligibility_snapshot_at, eligibility_max_age_seconds,
                  event_state, evidence_status, text_validation_status,
                  visual_validation_status, quota_reservation_id,
                  repetition_hard_hours=12, now=None, ttl_seconds=60):
        import hashlib
        import json
        import re
        from dataclasses import asdict
        from datetime import datetime, timedelta, timezone
        from layer1.publication_authorization import (
            PublicationAuthorization, _draft_provenance_digest, _parse_time,
        )
        current = _parse_time(now or datetime.now(timezone.utc).isoformat())
        if not isinstance(content, str) or not content.strip():
            raise ValueError("authorization requires a non-empty exact draft")
        if (not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9]{2,20}", symbol.strip())
                or not isinstance(asset_id, str)
                or not re.fullmatch(r"coingecko:[a-z0-9][a-z0-9-]{1,99}", asset_id)):
            raise ValueError("authorization requires canonical asset identity")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 300:
            raise ValueError("authorization TTL must be between 1 and 300 seconds")
        if isinstance(eligibility_max_age_seconds, bool) or not isinstance(eligibility_max_age_seconds, int) or not 1 <= eligibility_max_age_seconds <= 600:
            raise ValueError("eligibility freshness bound must be between 1 and 600 seconds")
        if isinstance(repetition_hard_hours, bool) or not isinstance(repetition_hard_hours, int) or not 1 <= repetition_hard_hours <= 168:
            raise ValueError("repetition_hard_hours must be between 1 and 168")
        hashes = tuple(sorted(image_hashes))
        if len(set(hashes)) != len(hashes) or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in hashes):
            raise ValueError("image hashes must be unique SHA-256 hex digests")
        draft_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        draft = self.store.conn.execute(
            "SELECT draft_id,research_package_id,editorial_brief_id,approved_claim_ids_json,content "
            "FROM content_draft_versions WHERE content_hash=%s AND asset_id=%s ORDER BY version DESC LIMIT 1",
            (draft_hash, asset_id),
        ).fetchone()
        if draft is None or draft["content"] != content:
            raise ValueError("exact draft must be persisted in PostgreSQL with provenance")
        brief = self.store.conn.execute(
            "SELECT event_id,research_package_id,payload_json FROM editorial_brief_versions WHERE brief_id=%s",
            (draft["editorial_brief_id"],),
        ).fetchone()
        if brief is None or brief["research_package_id"] != draft["research_package_id"]:
            raise ValueError("persisted editorial brief does not match the draft research package")
        brief_payload = brief["payload_json"]
        if isinstance(brief_payload, str):
            brief_payload = json.loads(brief_payload)
        from layer1.editorial_strategy import editorial_brief_approved_claim_ids
        allowed_claim_ids = set(editorial_brief_approved_claim_ids(brief_payload))
        claims = draft["approved_claim_ids_json"]
        if isinstance(claims, str):
            claims = json.loads(claims)
        if not isinstance(claims, list) or not claims or any(not isinstance(v, str) or not v for v in claims):
            raise ValueError("persisted draft requires approved claim references")
        if not set(claims).issubset(allowed_claim_ids):
            raise ValueError("draft approved claims exceed the persisted editorial brief allowlist")
        text = self.store.load_latest_text_validation(draft_hash)
        if text is None or text["status"] != "PASS":
            raise ValueError("persisted text validation is not PASS for this exact draft")
        for image_hash in hashes:
            visual = self.store.load_latest_visual_validation(draft_hash, image_hash)
            if visual is None or visual["status"] != "PASS" or visual["validation_version"] != "visual-quality-v3":
                raise ValueError("persisted visual validation is not current PASS for this exact image")
        authorized_claims = tuple(sorted(claims))
        provenance = _draft_provenance_digest(
            draft["draft_id"], asset_id, draft_hash, draft["research_package_id"],
            draft["editorial_brief_id"], authorized_claims,
        )
        duplicate_reasons = self.store.validate_persisted_duplicate_policy(
            symbol=symbol.upper(), asset_id=asset_id, event_id=brief["event_id"],
            event_state=event_state, content_hash=draft_hash,
            quota_reservation_id=quota_reservation_id, now=current,
            repetition_hard_hours=repetition_hard_hours,
        )
        if duplicate_reasons:
            raise ValueError("publication authorization denied: " + ",".join(duplicate_reasons))
        candidate = PublicationAuthorization(
            authorization_id="", symbol=symbol.upper(), asset_id=asset_id,
            draft_id=draft["draft_id"], research_package_id=draft["research_package_id"],
            editorial_brief_id=draft["editorial_brief_id"], event_id=brief["event_id"],
            approved_claim_ids=authorized_claims, draft_provenance_hash=provenance,
            content_hash=draft_hash, image_hashes=hashes,
            eligibility_snapshot_at=_parse_time(eligibility_snapshot_at).isoformat(),
            eligibility_max_age_seconds=eligibility_max_age_seconds,
            event_state=event_state, evidence_status=evidence_status,
            text_validation_status=text_validation_status,
            visual_validation_status=visual_validation_status,
            quota_reservation_id=quota_reservation_id,
            repetition_hard_hours=repetition_hard_hours,
            duplicate_policy_passed=True,
            created_at=current.isoformat(),
            expires_at=(current + timedelta(seconds=ttl_seconds)).isoformat(),
        )
        reasons = candidate.validate_for_submission(
            symbol=symbol, asset_id=asset_id, content=content,
            image_hashes=hashes, now=current.isoformat(),
        )
        reasons = tuple(sorted(set(reasons) | set(self.validate_persisted_event_binding(candidate))))
        if reasons:
            raise ValueError("publication authorization denied: " + ",".join(reasons))
        payload = asdict(candidate)
        payload.pop("authorization_id")
        authorization_id = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        authorized = PublicationAuthorization(**{**asdict(candidate), "authorization_id": authorization_id})
        self.store.save_publication_authorization(authorized)
        return authorized

    def validate_persisted_duplicate_policy(self, authorization, *, now=None, exclude_idempotency_key=None):
        from layer1.publication_authorization import _parse_time
        return self.store.validate_persisted_duplicate_policy(
            symbol=authorization.symbol, asset_id=authorization.asset_id,
            event_id=authorization.event_id, event_state=authorization.event_state,
            content_hash=authorization.content_hash,
            quota_reservation_id=authorization.quota_reservation_id,
            now=_parse_time(now) if now else _parse_time(authorization.created_at),
            repetition_hard_hours=authorization.repetition_hard_hours,
            exclude_idempotency_key=exclude_idempotency_key,
        )

    def validate_persisted_event_binding(self, authorization):
        brief = self.store.conn.execute(
            "SELECT event_id,research_package_id,payload_json FROM editorial_brief_versions WHERE brief_id=%s",
            (authorization.editorial_brief_id,),
        ).fetchone()
        if brief is None:
            return ("EDITORIAL_BRIEF_MISSING",)
        reasons = []
        if brief["event_id"] != authorization.event_id:
            reasons.append("EDITORIAL_EVENT_IDENTITY_CHANGED")
        if brief["research_package_id"] != authorization.research_package_id:
            reasons.append("EDITORIAL_RESEARCH_PACKAGE_CHANGED")
        try:
            brief_payload = brief["payload_json"]
            if isinstance(brief_payload, str):
                brief_payload = json.loads(brief_payload)
            from layer1.editorial_strategy import editorial_brief_approved_claim_ids
            allowed_claim_ids = set(editorial_brief_approved_claim_ids(brief_payload))
            if not set(authorization.approved_claim_ids).issubset(allowed_claim_ids):
                reasons.append("EDITORIAL_CLAIM_ALLOWLIST_CHANGED")
        except (TypeError, ValueError, json.JSONDecodeError):
            reasons.append("EDITORIAL_CLAIM_ALLOWLIST_INVALID")
        event = self.store.load_event_lifecycle(authorization.event_id)
        if authorization.event_state == "NO_EVENT":
            if event is not None:
                reasons.append("UNEXPECTED_PERSISTED_EVENT_FOR_NO_EVENT_AUTHORIZATION")
        elif event is None:
            reasons.append("EVENT_LIFECYCLE_RECORD_MISSING")
        elif event["asset_id"] != authorization.asset_id or event["state"] != authorization.event_state:
            reasons.append("EVENT_LIFECYCLE_CHANGED_AFTER_AUTHORIZATION")
        elif event["state"] not in {"CONFIRMED", "DEVELOPING"}:
            reasons.append("EVENT_STATE_NOT_PUBLISHABLE")
        return tuple(sorted(set(reasons)))


class PostgresRunLease:
    """RunLease-compatible adapter backed by the shared PostgreSQL runtime store."""
    _ALLOWED_STATUSES = {"SUCCEEDED", "NO_CANDIDATE_OR_BLOCKED", "FAILED", "INTERRUPTED"}

    def __init__(self, store):
        required = ("inspect_active_run_lease", "acquire_run_lease", "finish_run_lease")
        if any(not callable(getattr(store, name, None)) for name in required):
            raise TypeError("PostgreSQL publication store is required")
        self.store = store
        self.run_id = None

    def inspect_active(self):
        return self.store.inspect_active_run_lease()

    def acquire(self, context):
        self.store.acquire_run_lease(context)
        self.run_id = context.run_id

    def recover_interrupted(
        self, expected_run_id, *, process_termination_confirmed, evidence, recovered_by,
    ):
        if process_termination_confirmed is not True:
            raise ValueError("process termination confirmation is required")
        if self.run_id == expected_run_id:
            raise RuntimeError("current process cannot recover its own active run lease")
        recover = getattr(self.store, "recover_interrupted_run_lease", None)
        if not callable(recover):
            raise TypeError("PostgreSQL store does not support explicit run recovery")
        return recover(
            expected_run_id=expected_run_id,
            process_termination_confirmed=True,
            evidence=evidence,
            recovered_by=recovered_by,
        )

    def finish(self, status, summary=None):
        if not self.run_id:
            return
        if status not in self._ALLOWED_STATUSES:
            raise ValueError(f"unsupported run status: {status}")
        self.store.finish_run_lease(self.run_id, status, summary or {})
        self.run_id = None

    def close(self):
        # The PostgreSQL connection belongs to the application bootstrap and is
        # shared with publication persistence; closing this adapter must not close it.
        return None

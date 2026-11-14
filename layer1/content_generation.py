"""Versioned draft provenance and append-only validation records (Module 17)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Sequence


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DraftRecord:
    draft_key: str
    draft_id: str
    version: int
    asset_id: str
    content_hash: str
    research_package_id: str
    editorial_brief_id: str
    approved_claim_ids: tuple[str, ...]
    created_at: str


class DraftStore:
    """Persist exact draft versions and validation decisions in the publisher's existing DB."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("draft store requires SQLite connection")
        self.connection = connection
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS content_draft_versions (
            draft_key TEXT NOT NULL,
            version INTEGER NOT NULL,
            draft_id TEXT NOT NULL UNIQUE,
            asset_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            research_package_id TEXT NOT NULL,
            editorial_brief_id TEXT NOT NULL,
            approved_claim_ids_json TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(draft_key, version),
            UNIQUE(draft_key, content_hash)
        );
        CREATE TABLE IF NOT EXISTS content_draft_validation_results (
            validation_id TEXT PRIMARY KEY,
            draft_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            reasons_json TEXT NOT NULL,
            validation_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_draft_validation_latest
            ON content_draft_validation_results(draft_hash, created_at);
        CREATE TABLE IF NOT EXISTS visual_validation_results (
            validation_id TEXT PRIMARY KEY,
            draft_hash TEXT NOT NULL,
            image_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            reasons_json TEXT NOT NULL,
            validation_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(draft_hash, image_hash, validation_id)
        );
        CREATE INDEX IF NOT EXISTS idx_visual_validation_pair
            ON visual_validation_results(draft_hash, image_hash, created_at);
        CREATE TABLE IF NOT EXISTS image_generation_artifacts (
            artifact_id TEXT PRIMARY KEY,
            draft_hash TEXT NOT NULL,
            image_hash TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            request_id TEXT,
            generated_at TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            generation_parameters_json TEXT NOT NULL,
            source_image_hash TEXT NOT NULL,
            image_path TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(draft_hash, image_hash)
        );
        """)
        self.connection.commit()

    def save_draft(
        self, content: str, *, asset_id: str, research_package_id: str,
        editorial_brief_id: str, approved_claim_ids: Sequence[str],
    ) -> DraftRecord:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("draft content must be non-empty")
        if not isinstance(asset_id, str) or not asset_id.startswith("coingecko:"):
            raise ValueError("draft requires canonical asset identity")
        if (
            not isinstance(research_package_id, str) or not research_package_id.strip()
            or not isinstance(editorial_brief_id, str) or not editorial_brief_id.strip()
        ):
            raise ValueError("draft requires research package and editorial brief IDs")
        if not isinstance(approved_claim_ids, Sequence) or isinstance(approved_claim_ids, (str, bytes)):
            raise ValueError("approved claim IDs must be a sequence of claim ID strings")
        if any(not isinstance(value, str) or not value.strip() for value in approved_claim_ids):
            raise ValueError("draft requires verified claim references")
        claim_ids = tuple(sorted(set(approved_claim_ids)))
        if not claim_ids:
            raise ValueError("draft requires verified claim references")
        content_hash = _hash(content)
        draft_key = _hash(asset_id + "|" + editorial_brief_id)
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            existing = self.connection.execute(
                "SELECT version, draft_id, created_at, research_package_id, "
                "editorial_brief_id, approved_claim_ids_json FROM content_draft_versions "
                "WHERE draft_key=? AND content_hash=?",
                (draft_key, content_hash),
            ).fetchone()
            if existing:
                stored_claim_ids = tuple(json.loads(existing[5]))
                if (
                    existing[3] != research_package_id
                    or existing[4] != editorial_brief_id
                    or stored_claim_ids != claim_ids
                ):
                    raise ValueError(
                        "identical draft hash has conflicting immutable research/claim provenance"
                    )
                return DraftRecord(
                    draft_key=draft_key, draft_id=existing[1], version=existing[0],
                    asset_id=asset_id, content_hash=content_hash,
                    research_package_id=existing[3],
                    editorial_brief_id=existing[4],
                    approved_claim_ids=stored_claim_ids, created_at=existing[2],
                )
            version = int(self.connection.execute(
                "SELECT COALESCE(MAX(version),0) FROM content_draft_versions WHERE draft_key=?",
                (draft_key,),
            ).fetchone()[0]) + 1
            draft_id = _hash(draft_key + "|" + str(version) + "|" + content_hash)
            self.connection.execute(
                "INSERT INTO content_draft_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (draft_key, version, draft_id, asset_id, content_hash,
                 research_package_id, editorial_brief_id,
                 json.dumps(claim_ids, separators=(",", ":")), content, created_at),
            )
        return DraftRecord(
            draft_key=draft_key, draft_id=draft_id, version=version,
            asset_id=asset_id, content_hash=content_hash,
            research_package_id=research_package_id,
            editorial_brief_id=editorial_brief_id,
            approved_claim_ids=claim_ids, created_at=created_at,
        )

    def save_text_validation(
        self, *, draft_hash: str, status: str, reasons: Sequence[str],
        validation_version: str,
    ) -> str:
        if (
            not isinstance(draft_hash, str) or len(draft_hash) != 64
            or any(char not in "0123456789abcdef" for char in draft_hash)
            or not isinstance(status, str) or status not in {"PASS", "NEEDS_REVISION", "REJECT"}
        ):
            raise ValueError("invalid text validation record")
        if not isinstance(validation_version, str) or not validation_version.strip():
            raise ValueError("validation version is required")
        if not isinstance(reasons, Sequence) or isinstance(reasons, (str, bytes)):
            raise ValueError("validation reasons must be a sequence of strings")
        if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise ValueError("validation reasons must be non-empty strings")
        payload = {
            "draft_hash": draft_hash, "status": status,
            "reasons": sorted(set(reasons)), "version": validation_version,
        }
        validation_id = _hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO content_draft_validation_results VALUES (?, ?, ?, ?, ?, ?)",
                (validation_id, draft_hash, status,
                 json.dumps(payload["reasons"], separators=(",", ":")),
                 validation_version, datetime.now(timezone.utc).isoformat()),
            )
        return validation_id

    def save_visual_validation(
        self, *, draft_hash: str, image_hash: str, status: str,
        reasons: Sequence[str], validation_version: str,
    ) -> str:
        if (
            not isinstance(draft_hash, str) or len(draft_hash) != 64
            or any(char not in "0123456789abcdef" for char in draft_hash)
            or not isinstance(image_hash, str) or len(image_hash) != 64
            or any(char not in "0123456789abcdef" for char in image_hash)
            or not isinstance(status, str) or status not in {"PASS", "NEEDS_REVISION", "REJECT"}
        ):
            raise ValueError("invalid visual validation record")
        if not isinstance(validation_version, str) or not validation_version.strip():
            raise ValueError("validation version is required")
        if not isinstance(reasons, Sequence) or isinstance(reasons, (str, bytes)):
            raise ValueError("visual validation reasons must be a sequence of strings")
        if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise ValueError("visual validation reasons must be non-empty strings")
        payload = {
            "draft_hash": draft_hash, "image_hash": image_hash, "status": status,
            "reasons": sorted(set(reasons)), "version": validation_version,
        }
        validation_id = _hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO visual_validation_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                (validation_id, draft_hash, image_hash, status,
                 json.dumps(payload["reasons"], separators=(",", ":")),
                 validation_version, datetime.now(timezone.utc).isoformat()),
            )
        return validation_id


    def save_image_artifact(self, metadata: dict, *, image_path: str) -> str:
        required = {
            "provider", "model", "generated_at", "prompt_hash",
            "generation_parameters", "source_image_hash", "final_image_hash",
            "draft_hash", "asset_id", "symbol", "dimensions",
        }
        if not isinstance(metadata, dict) or not required.issubset(metadata):
            raise ValueError("image artifact metadata is incomplete")
        for name in ("prompt_hash", "source_image_hash", "final_image_hash", "draft_hash"):
            value = metadata.get(name)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("image artifact contains an invalid " + name)
        if metadata["provider"] != "cloudflare_workers_ai" or not metadata["model"]:
            raise ValueError("image artifact provider/model is not approved")
        if not isinstance(metadata["asset_id"], str) or not metadata["asset_id"].startswith("coingecko:"):
            raise ValueError("image artifact requires canonical asset identity")
        if not isinstance(metadata["symbol"], str) or not metadata["symbol"].strip():
            raise ValueError("image artifact requires an asset symbol")
        if metadata["model"] != "@cf/black-forest-labs/flux-2-klein-4b":
            raise ValueError("image artifact model is not the approved Workers AI model")
        generation = metadata["generation_parameters"]
        if (
            not isinstance(generation, dict)
            or isinstance(generation.get("width"), bool)
            or not isinstance(generation.get("width"), int)
            or isinstance(generation.get("height"), bool)
            or not isinstance(generation.get("height"), int)
            or not 256 <= generation.get("width", 0) <= 1920
            or not 256 <= generation.get("height", 0) <= 1920
            or generation.get("output_format") not in {"PNG", "JPEG", "WEBP"}
        ):
            raise ValueError("image generation parameters are invalid")
        dimensions = metadata["dimensions"]
        if (
            not isinstance(dimensions, list) or len(dimensions) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in dimensions)
        ):
            raise ValueError("image artifact dimensions are invalid")
        if not isinstance(image_path, str) or not image_path.strip():
            raise ValueError("image artifact path is required")
        try:
            generated_at = datetime.fromisoformat(metadata["generated_at"].replace("Z", "+00:00"))
            if generated_at.tzinfo is None or generated_at.utcoffset() is None:
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ValueError("image artifact generated_at must be timezone-aware ISO-8601") from None
        artifact_payload = {
            "draft_hash": metadata["draft_hash"],
            "image_hash": metadata["final_image_hash"],
            "asset_id": metadata["asset_id"],
            "symbol": metadata["symbol"].upper(),
            "provider": metadata["provider"],
            "model": metadata["model"],
            "request_id": metadata.get("request_id"),
            "generated_at": metadata["generated_at"],
            "prompt_hash": metadata["prompt_hash"],
            "generation_parameters": metadata["generation_parameters"],
            "source_image_hash": metadata["source_image_hash"],
            "image_path": image_path,
        }
        artifact_id = _hash(json.dumps(
            artifact_payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ))
        metadata_json = json.dumps(
            metadata, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        with self.connection:
            existing = self.connection.execute(
                "SELECT artifact_id, metadata_json, image_path FROM image_generation_artifacts "
                "WHERE draft_hash=? AND image_hash=?",
                (metadata["draft_hash"], metadata["final_image_hash"]),
            ).fetchone()
            if existing:
                if existing[1] != metadata_json or existing[2] != image_path:
                    raise ValueError("exact draft/image pair already has different immutable provenance")
                return existing[0]
            self.connection.execute(
                "INSERT INTO image_generation_artifacts VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, metadata["draft_hash"], metadata["final_image_hash"],
                 metadata["asset_id"], metadata["symbol"].upper(), metadata["provider"],
                 metadata["model"], metadata.get("request_id"), metadata["generated_at"],
                 metadata["prompt_hash"],
                 json.dumps(metadata["generation_parameters"], sort_keys=True, separators=(",", ":")),
                 metadata["source_image_hash"], image_path, metadata_json,
                 datetime.now(timezone.utc).isoformat()),
            )
        return artifact_id

    def image_artifact(self, draft_hash: str, image_hash: str) -> dict | None:
        row = self.connection.execute(
            "SELECT metadata_json, image_path, artifact_id FROM image_generation_artifacts "
            "WHERE draft_hash=? AND image_hash=?",
            (draft_hash, image_hash),
        ).fetchone()
        if not row:
            return None
        return {
            "artifact_id": row[2], "image_path": row[1],
            "metadata": json.loads(row[0]),
        }

    def latest_text_validation(self, draft_hash: str) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM content_draft_validation_results WHERE draft_hash=? "
            "ORDER BY created_at DESC, validation_id DESC LIMIT 1",
            (draft_hash,),
        ).fetchone()
        return row[0] if row else None

    def visual_validation(self, draft_hash: str, image_hash: str) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM visual_validation_results WHERE draft_hash=? AND image_hash=? "
            "ORDER BY created_at DESC, validation_id DESC LIMIT 1",
            (draft_hash, image_hash),
        ).fetchone()
        return row[0] if row else None

    def load_latest(self, draft_key: str) -> dict | None:
        row = self.connection.execute(
            "SELECT draft_id, version, asset_id, content_hash, research_package_id, "
            "editorial_brief_id, approved_claim_ids_json, content, created_at "
            "FROM content_draft_versions WHERE draft_key=? ORDER BY version DESC LIMIT 1",
            (draft_key,),
        ).fetchone()
        if not row:
            return None
        return {
            "draft_id": row[0], "version": row[1], "asset_id": row[2],
            "content_hash": row[3], "research_package_id": row[4],
            "editorial_brief_id": row[5], "approved_claim_ids": json.loads(row[6]),
            "content": row[7], "created_at": row[8],
        }
